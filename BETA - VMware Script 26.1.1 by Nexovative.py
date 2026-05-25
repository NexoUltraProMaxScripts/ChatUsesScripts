import asyncio
import traceback
import pytchat
import time
import subprocess
import os
import json
import threading
import http.server
import socketserver
from datetime import datetime
from vncdotool import api as vnc
from collections import defaultdict

# ========================= CONFIG =========================
VM_DATABASE_FILE = "vms.json"
vm_list = {}
VNC_HOST = "localhost"
VNC_PORT = 5900
VNC_PASSWORD = "1234"
YOUTUBE_VIDEO_ID = None
VMX_PATH = None
PREFIX = "!"
VMRUN_PATH = r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"
COOLDOWN = {"startvm": 45}

# Single source of truth for vote settings.
# FIX: Removed the dead VOTE_SETTINGS dict that was never read by any logic.
VOTE_DURATION   = 100  # Seconds the voting window stays open
REQUIRED_VOTES  = 2    # Minimum unique voters required to pass

# VM_DATABASE example entries (edit vms.json directly or use registration mode):
#   "win10": r"D:\VMSVMWARE\w8\Windows 10 x64.vmx"
#   "win8":  r"D:\VMSVMWARE\w88\Windows 8.x x64.vmx"
#   "win7":  r"D:\w777\Windows 7 x64.vmx"

active_voters   = defaultdict(lambda: 0)
votes           = {"restartvm": [], "revert": []}
last_command_time = {}

# Guard set that prevents the same vote action from being executed twice
# concurrently (race condition between start_vote and process_command).
# FIX: Added to resolve the double-execution race condition.
_executing_votes: set = set()

# ========================= SCANCODE MAP =========================
# Direct X11 keysym codes to bypass bugs in the vncdotool library.
SCANCODE_MAP = {
    "esc": chr(0xff1b), "escape": chr(0xff1b),
    "tab": chr(0xff09),
    "enter": chr(0xff0d), "return": chr(0xff0d),
    "space": " ",
    "backspace": chr(0xff08),
    "delete": chr(0xffff), "del": chr(0xffff),
    "insert": chr(0xff63), "ins": chr(0xff63),
    "home": chr(0xff50),
    "end": chr(0xff57),
    "pageup": chr(0xff55), "pgup": chr(0xff55),
    "pagedown": chr(0xff56), "pgdn": chr(0xff56),
    "ctrl": chr(0xffe3), "control": chr(0xffe3),
    "alt": chr(0xffe9),
    "shift": chr(0xffe1),
    "capslock": chr(0xffe5),
    "win": chr(0xffeb), "super": chr(0xffeb), "windows": chr(0xffeb),
    "up": chr(0xff52),
    "down": chr(0xff54),
    "left": chr(0xff51),
    "right": chr(0xff53),
    "f1": chr(0xffbe), "f2": chr(0xffbf), "f3": chr(0xffc0), "f4": chr(0xffc1),
    "f5": chr(0xffc2), "f6": chr(0xffc3), "f7": chr(0xffc4), "f8": chr(0xffc5),
    "f9": chr(0xffc6), "f10": chr(0xffc7), "f11": chr(0xffc8), "f12": chr(0xffc9),
}

# ========================= OVERLAY SYSTEM =========================
overlay_data    = {"chat": [], "running_command": ""}
seen_message_ids = set()
last_write_time = 0


def update_overlay(author=None, message=None, running=None, msg_id=None):
    global last_write_time
    changed      = False
    current_time = time.time()

    if running is not None and overlay_data.get("running_command") != running:
        overlay_data["running_command"] = running
        changed = True

    if author and message and msg_id and msg_id not in seen_message_ids:
        seen_message_ids.add(msg_id)
        overlay_data["chat"].append({
            "author":  str(author),
            "message": str(message),
            "id":      str(msg_id),
        })

        if len(overlay_data["chat"]) > 20:
            removed = overlay_data["chat"].pop(0)
            seen_message_ids.discard(removed.get("id"))

        changed = True

    if changed and (current_time - last_write_time > 0.15):
        try:
            with open("overlay.json", "w", encoding="utf-8") as f:
                json.dump(overlay_data, f, ensure_ascii=False, separators=(",", ":"))
            last_write_time = current_time
        except Exception as e:
            print(f"[Overlay Error] {e}")


async def show_running_command(cmd_text: str):
    update_overlay(running=cmd_text)
    await asyncio.sleep(2)
    if overlay_data["running_command"] == cmd_text:
        update_overlay(running="")


def start_overlay_server():
    PORT = 8080

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Suppress request logs

    try:
        with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
            print(f"Overlay server running at: http://localhost:{PORT}/chat.html")
            httpd.serve_forever()
    except OSError:
        print("Port 8080 is busy. Overlay server could not start.")


# ========================= SPEAKER =========================
def speak_text(text: str):
    print(f"\n[SPEAKER]: {text}\n")


# ========================= VM CONTROLLER =========================
class VMController:
    def __init__(self):
        self.client   = None
        self.cursor_x = 512
        self.cursor_y = 384
        # Prevents concurrent VNC operations (avoids stuck keys).
        self._lock        = asyncio.Lock()
        # Emergency signal that tells an active hold loop to stop early.
        self._abort_hold  = False

    async def connect_fresh(self):
        await self._disconnect()
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] New VNC connection...")
            loop = asyncio.get_event_loop()
            self.client = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: vnc.connect(f"{VNC_HOST}::{VNC_PORT}", password=str(VNC_PASSWORD)),
                ),
                timeout=8,
            )
            print("Fresh VNC connected.")
            return self.client
        except Exception as e:
            print(f"VNC connect failed: {e}")
            self.client = None
            return None

    async def _disconnect(self):
        if self.client:
            try:
                self.client.disconnect()
            except Exception:
                pass
        self.client = None

    async def send_key(self, key: str):
        # Lock the entire operation so no other command can call connect_fresh()
        # mid-execution and disconnect the client (which was causing stuck keys).
        async with self._lock:
            client = await self.connect_fresh()
            if not client:
                return False
            try:
                loop      = asyncio.get_event_loop()
                clean_key = key.strip().lower()
                mapped_key = SCANCODE_MAP.get(clean_key, clean_key)

                if "+" in clean_key:
                    # Combo keys, e.g. ctrl+c, win+r
                    keys       = clean_key.split("+")
                    mapped_keys = [
                        SCANCODE_MAP.get(k.strip(), k.strip()) for k in keys
                    ]
                    try:
                        for k in mapped_keys:
                            await asyncio.wait_for(
                                loop.run_in_executor(None, lambda k2=k: client.keyDown(k2)),
                                timeout=2.0,
                            )
                            await asyncio.sleep(0.01)
                    finally:
                        # Always release all keys, even if keyDown raised an error midway.
                        for k in reversed(mapped_keys):
                            try:
                                await asyncio.wait_for(
                                    loop.run_in_executor(None, lambda k2=k: client.keyUp(k2)),
                                    timeout=2.0,
                                )
                            except Exception:
                                pass
                    print(f"Combo sent: {'+'.join(mapped_keys)}")

                else:
                    # Single key: press and release atomically in the same thread.
                    def do_safe_press():
                        try:
                            client.keyDown(mapped_key)
                            time.sleep(0.1)
                        finally:
                            client.keyUp(mapped_key)

                    await asyncio.wait_for(
                        loop.run_in_executor(None, do_safe_press), timeout=10.0
                    )
                    print(f"Key sent and released: {mapped_key}")

                return True

            except Exception as e:
                print(f"Key send error: {e}")
                traceback.print_exc()
                # FIX: Was missing 'return False' here; the function returned None on error.
                return False

    async def type_text(self, text: str):
        # Same lock as send_key — prevents connection being torn down mid-typing.
        async with self._lock:
            client = await self.connect_fresh()
            if not client:
                return False
            try:
                loop = asyncio.get_event_loop()
                for char in text:
                    if char.isupper() or char in '!@#$%^&*()_+{}|:"<>?~':
                        # Hold Shift for uppercase / special characters.
                        try:
                            await asyncio.wait_for(
                                loop.run_in_executor(
                                    None, lambda: client.keyDown(SCANCODE_MAP["shift"])
                                ),
                                timeout=2.0,
                            )
                            key_to_send = char.lower() if char.isupper() else char
                            await asyncio.wait_for(
                                loop.run_in_executor(
                                    None, lambda k=key_to_send: client.keyPress(k)
                                ),
                                timeout=2.0,
                            )
                        finally:
                            try:
                                await asyncio.wait_for(
                                    loop.run_in_executor(
                                        None, lambda: client.keyUp(SCANCODE_MAP["shift"])
                                    ),
                                    timeout=2.0,
                                )
                            except Exception:
                                pass
                    else:
                        await asyncio.wait_for(
                            loop.run_in_executor(None, lambda c=char: client.keyPress(c)),
                            timeout=2.0,
                        )
                    await asyncio.sleep(0.007)

                print(f"Text sent: {text}")
                return True

            except Exception:
                # Make sure Shift is not left held down after any error.
                try:
                    loop = asyncio.get_event_loop()
                    await asyncio.wait_for(
                        loop.run_in_executor(
                            None, lambda: client.keyUp(SCANCODE_MAP["shift"])
                        ),
                        timeout=1.0,
                    )
                except Exception:
                    pass
                await self._disconnect()
                return False


controller = VMController()


# ========================= VOTE HELPERS =========================
def update_vote_json(restart_time: int = 0, revert_time: int = 0):
    data = {
        "restartvm": {
            "current":        len(votes["restartvm"]),
            "required":       REQUIRED_VOTES,
            "remaining_time": restart_time,
        },
        "revert": {
            "current":        len(votes["revert"]),
            "required":       REQUIRED_VOTES,
            "remaining_time": revert_time,
        },
    }
    try:
        with open("votes.json", "w") as f:
            json.dump(data, f)
    except Exception:
        pass


async def execute_vm_action(vote_type: str):
    # FIX: Guard against double execution. If start_vote and process_command both
    # trigger this for the same vote_type at the same time, only the first one runs.
    if vote_type in _executing_votes:
        return
    _executing_votes.add(vote_type)
    try:
        votes[vote_type] = []
        update_vote_json()

        if vote_type == "restartvm":
            await run_vmrun(["-T", "ws", "reset", VMX_PATH, "hard"])
        elif vote_type == "revert":
            await run_vmrun(["-T", "ws", "revertToSnapshot", VMX_PATH, "snp"])
            await asyncio.sleep(5)
            await run_vmrun(["-T", "ws", "start", VMX_PATH, "gui"])
    finally:
        _executing_votes.discard(vote_type)


async def start_vote(vote_type: str, starter: str):
    votes[vote_type] = [starter]
    print(f"Vote started for !{vote_type} by {starter}")

    if vote_type == "restartvm":
        update_vote_json(restart_time=VOTE_DURATION)
    else:
        update_vote_json(revert_time=VOTE_DURATION)

    for remaining in range(VOTE_DURATION, 0, -1):
        await asyncio.sleep(1)
        if vote_type == "restartvm":
            update_vote_json(restart_time=remaining)
        else:
            update_vote_json(revert_time=remaining)

        if len(votes[vote_type]) >= REQUIRED_VOTES:
            print(f"Vote PASSED early for !{vote_type}")
            await execute_vm_action(vote_type)
            return

    votes[vote_type] = []
    update_vote_json()
    print(f"Vote for !{vote_type} expired without reaching required votes.")


# ========================= SETUP =========================
async def get_user_input():
    global YOUTUBE_VIDEO_ID, VMX_PATH, vm_list

    # --- 1. Load VM list ---
    if os.path.exists(VM_DATABASE_FILE):
        with open(VM_DATABASE_FILE, "r") as f:
            vm_list = json.load(f)

    # --- 2. Registration / update mode ---
    update_needed = False
    if vm_list:
        print("\n" + "=" * 60)
        print(f"Registered VMs: {', '.join(vm_list.keys())}")
        choice = input("Do you want to update/add VMs? (yes/no): ").lower().strip()
        if choice == "yes":
            update_needed = True
    else:
        update_needed = True

    if update_needed:
        print("\n--- VM Registration Mode (type DONE to finish) ---")
        while True:
            path = input("Enter VMX file path (or DONE): ").strip().replace('"', "")
            if path.upper() == "DONE":
                break
            if not os.path.exists(path):
                print("Path does not exist.")
                continue
            alias = input("Short name for this VM (e.g. w11): ").strip().lower()
            vm_list[alias] = path

        with open(VM_DATABASE_FILE, "w") as f:
            json.dump(vm_list, f)
        print("Database updated.")

    # --- 3. VM selection ---
    if not vm_list:
        print("No VMs registered. Exiting.")
        raise SystemExit(1)

    print("\nAvailable VMs:")
    for alias in vm_list:
        print(f"  - {alias}")

    while True:
        selection = input("Select VM name to use: ").strip().lower()
        if selection in vm_list:
            VMX_PATH = vm_list[selection]
            break
        print("Invalid selection. Please type one of the names listed above.")

    # --- 4. Platform selection ---
    # FIX: Was hardcoded to "1"; now actually prompts the user.
    # Only YouTube is implemented; Twitch support can be added in youtube_loop equivalent.
    print("\nPlatform options:")
    print("  1 - YouTube Live")
    while True:
        platform_choice = input("Select platform (1): ").strip()
        if platform_choice in ("1", ""):
            YOUTUBE_VIDEO_ID = input("Enter YouTube Live Video ID: ").strip()
            break
        print("Invalid option. Only YouTube (1) is currently supported.")

    print(f"\nBooting {selection.upper()} — platform: YouTube")
    print("=" * 60 + "\n")


# ========================= VM RUNNER =========================
def is_on_cooldown(cmd: str) -> bool:
    now = time.time()
    if cmd in last_command_time and now - last_command_time[cmd] < COOLDOWN.get(cmd, 5):
        return True
    last_command_time[cmd] = now
    return False


async def run_vmrun(args: list) -> bool:
    try:
        if not os.path.exists(VMRUN_PATH):
            print(f"vmrun not found at: {VMRUN_PATH}")
            return False
        # run_in_executor prevents subprocess.run from blocking the async loop.
        loop   = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                [VMRUN_PATH] + args,
                capture_output=True,
                text=True,
                timeout=60,
            ),
        )
        return result.returncode == 0
    except Exception as e:
        print(f"VMRun error: {e}")
        return False


# ========================= COMMAND PROCESSOR =========================
async def process_command(message: str, author: str):
    if not message.startswith(PREFIX):
        return

    # FIX: Old code used message.split(PREFIX) which split on every "!" including
    # those inside arguments (e.g. "!type Hello! World" broke into two commands).
    # New approach: strip the leading prefix once, then split only on " !" (space +
    # prefix) so that "!" inside argument text is never treated as a command boundary.
    content      = message[len(PREFIX):]
    raw_commands = [cmd.strip() for cmd in content.split(f" {PREFIX}") if cmd.strip()]

    active_voters[author] = time.time()

    for raw_cmd in raw_commands:
        parts = raw_cmd.split()
        if not parts:
            continue

        command = parts[0].lower()
        args    = parts[1:]

        full_cmd_string = f"Running: {PREFIX}{command} {' '.join(args)}".strip()
        asyncio.create_task(show_running_command(full_cmd_string))

        # ---------- VM control commands ----------
        if command == "startvm":
            if is_on_cooldown("startvm"):
                continue
            # FIX: Was missing the required -T ws hosttype flags.
            await run_vmrun(["-T", "ws", "start", VMX_PATH, "gui"])

        elif command == "restartvm":
            if votes["restartvm"]:
                if author not in votes["restartvm"]:
                    votes["restartvm"].append(author)
                    update_vote_json(restart_time=VOTE_DURATION)
                    # FIX: Guard against double execution via _executing_votes in
                    # execute_vm_action — start_vote may also trigger it independently.
                    if len(votes["restartvm"]) >= REQUIRED_VOTES:
                        asyncio.create_task(execute_vm_action("restartvm"))
            else:
                asyncio.create_task(start_vote("restartvm", author))

        elif command == "revert":
            if votes["revert"]:
                if author not in votes["revert"]:
                    votes["revert"].append(author)
                    update_vote_json(revert_time=VOTE_DURATION)
                    if len(votes["revert"]) >= REQUIRED_VOTES:
                        asyncio.create_task(execute_vm_action("revert"))
            else:
                asyncio.create_task(start_vote("revert", author))

        # ---------- Keyboard commands ----------
        elif command in ("key", "press") and args:
            await controller.send_key(" ".join(args).lower())

        elif command == "combo" and args:
            full_input = "+".join(args).lower().replace(" ", "+")
            while "++" in full_input:
                full_input = full_input.replace("++", "+")
            await controller.send_key(full_input)
            await asyncio.sleep(1.0)

        elif command == "hold" and args:
            key_name = args[0].lower()
            key      = SCANCODE_MAP.get(key_name, key_name)

            # FIX: float() was called without error handling; non-numeric input crashed.
            try:
                hold_duration = float(args[1]) if len(args) > 1 else 1.0
            except ValueError:
                hold_duration = 1.0
            hold_duration = min(hold_duration, 3.0)

            controller._abort_hold = False
            async with controller._lock:
                client = await controller.connect_fresh()
                if client:
                    loop        = asyncio.get_event_loop()
                    key_released = False
                    try:
                        await loop.run_in_executor(None, lambda: client.keyDown(key))
                        elapsed = 0.0
                        while elapsed < hold_duration and not controller._abort_hold:
                            await asyncio.sleep(0.05)
                            elapsed += 0.05
                    finally:
                        try:
                            await loop.run_in_executor(None, lambda: client.keyUp(key))
                            key_released = True
                        except Exception:
                            pass
                        if not key_released:
                            # Recovery: open a fresh connection and force-send keyUp.
                            try:
                                rc = await asyncio.wait_for(
                                    loop.run_in_executor(
                                        None,
                                        lambda: vnc.connect(
                                            f"{VNC_HOST}::{VNC_PORT}",
                                            password=str(VNC_PASSWORD),
                                        ),
                                    ),
                                    timeout=5,
                                )
                                await loop.run_in_executor(None, lambda: rc.keyUp(key))
                                rc.disconnect()
                                print(f"Key force-released via recovery connection: {key}")
                            except Exception:
                                print(f"Recovery keyUp also failed for: {key}")

        elif command == "release" and args:
            client = await controller.connect_fresh()
            if client:
                key  = SCANCODE_MAP.get(args[0].lower(), args[0].lower())
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: client.keyUp(key))

        elif command == "releaseall":
            # Signal any active hold to abort immediately.
            controller._abort_hold = True
            await asyncio.sleep(0.15)
            client = await controller.connect_fresh()
            if client:
                loop           = asyncio.get_event_loop()
                release_keys   = ["shift", "ctrl", "alt", "win", "capslock", "super", "control", "windows"]
                released_values = set()
                for k in release_keys:
                    mapped = SCANCODE_MAP.get(k)
                    if mapped and mapped not in released_values:
                        released_values.add(mapped)
                        try:
                            await loop.run_in_executor(
                                None, lambda mk=mapped: client.keyUp(mk)
                            )
                        except Exception:
                            pass
                print("All modifier keys released.")

        # ---------- Text commands ----------
        elif command in ("send", "typeenter") and args:
            await controller.type_text(" ".join(args))
            await asyncio.sleep(0.05)
            await controller.send_key("enter")

        elif command == "type" and args:
            await controller.type_text(" ".join(args))

        # ---------- Mouse commands ----------
        elif command in ("move", "mouse", "mv") and args:
            client = await controller.connect_fresh()
            if client:
                try:
                    if args[0].isalpha():
                        direction = args[0].lower()
                        step      = int(args[1]) if len(args) > 1 and args[1].isdigit() else 40
                        if direction == "up":    controller.cursor_y -= step
                        elif direction == "down":  controller.cursor_y += step
                        elif direction == "left":  controller.cursor_x -= step
                        elif direction == "right": controller.cursor_x += step
                        controller.cursor_x = max(0, min(1920, controller.cursor_x))
                        controller.cursor_y = max(0, min(1080, controller.cursor_y))
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: client.mouseMove(controller.cursor_x, controller.cursor_y),
                        )
                    elif len(args) >= 2:
                        dx, dy = int(args[0]), int(args[1])
                        controller.cursor_x = max(0, min(1920, controller.cursor_x + dx))
                        controller.cursor_y = max(0, min(1080, controller.cursor_y + dy))
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: client.mouseMove(controller.cursor_x, controller.cursor_y),
                        )
                except Exception:
                    pass

        elif command in ("abs", "cursor", "moveabs") and len(args) >= 2:
            client = await controller.connect_fresh()
            if client:
                try:
                    controller.cursor_x = max(0, min(1920, int(args[0])))
                    controller.cursor_y = max(0, min(1080, int(args[1])))
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: client.mouseMove(controller.cursor_x, controller.cursor_y),
                    )
                except Exception:
                    pass

        elif command in ("drag", "dragrel") and len(args) >= 2:
            client = await controller.connect_fresh()
            if client:
                try:
                    dx, dy = int(args[0]), int(args[1])
                    controller.cursor_x = max(0, min(1920, controller.cursor_x + dx))
                    controller.cursor_y = max(0, min(1080, controller.cursor_y + dy))
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: client.mouseDrag(controller.cursor_x, controller.cursor_y),
                    )
                except Exception:
                    pass

        elif command in ("click", "lclick"):
            client = await controller.connect_fresh()
            if client:
                count = int(args[0]) if args and args[0].isdigit() else 1
                loop  = asyncio.get_event_loop()
                for _ in range(count):
                    await loop.run_in_executor(None, lambda: client.mousePress(1))
                    await asyncio.sleep(0.01)

        elif command in ("rclick", "rightclick"):
            client = await controller.connect_fresh()
            if client:
                count = int(args[0]) if args and args[0].isdigit() else 1
                loop  = asyncio.get_event_loop()
                for _ in range(count):
                    # FIX: Was mousePress(2) which is MIDDLE click in VNC protocol.
                    # Right click is button 3.
                    await loop.run_in_executor(None, lambda: client.mousePress(3))
                    await asyncio.sleep(0.01)

        elif command in ("scroll", "wheel") and args:
            client = await controller.connect_fresh()
            if client:
                try:
                    delta  = int(args[0])
                    button = 4 if delta > 0 else 5  # 4 = scroll up, 5 = scroll down
                    loop   = asyncio.get_event_loop()
                    # FIX: Was "abs(delta) // 120" which treated deltas like Windows
                    # WM_MOUSEWHEEL units; chat-sourced deltas are plain step counts
                    # (1, 2, 3 …) so dividing by 120 always produced 0, making scroll
                    # completely non-functional.
                    for _ in range(abs(delta)):
                        await loop.run_in_executor(None, lambda b=button: client.mousePress(b))
                        await asyncio.sleep(0.01)
                except Exception:
                    pass

        elif command == "wait" and args and args[0].replace(".", "", 1).isdigit():
            await asyncio.sleep(min(float(args[0]), 5.0))


# ========================= MAIN LOOPS =========================
async def youtube_loop():
    while True:
        chat       = None
        chat_start = time.time()
        try:
            chat = pytchat.create(video_id=YOUTUBE_VIDEO_ID)
            print("Chat connected.")

            while chat.is_alive():
                # Refresh the chat connection every 200 seconds.
                if time.time() - chat_start > 200:
                    print("Chat connection reset.")
                    break

                for c in chat.get().sync_items():
                    msg = c.message.strip()
                    if not msg:
                        continue
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {c.author.name}: {msg}")
                    update_overlay(author=c.author.name, message=msg, msg_id=c.id)
                    if msg.startswith(PREFIX):
                        await process_command(msg, c.author.name)

                await asyncio.sleep(0.4)

        except Exception as e:
            print(f"Chat loop error: {e}")
            await asyncio.sleep(3)
        finally:
            if chat:
                try:
                    chat.terminate()
                except Exception:
                    pass

        await asyncio.sleep(0.4)


async def main():
    # 1. Bootstrap overlay
    update_overlay()
    threading.Thread(target=start_overlay_server, daemon=True).start()

    # 2. Interactive setup
    await get_user_input()
    print("Bot starting...\n")

    # FIX: Removed the dead "tasks = []" list that was created but never populated
    # or gathered. Add additional loops here if Twitch or other platforms are needed,
    # then gather them together with asyncio.gather().
    await asyncio.gather(
        youtube_loop(),
        # twitch_loop(),  # Add here when implemented
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped.")
