import asyncio
import pytchat
import time
import subprocess
import os
import sys
import json
import threading
import http.server
import socketserver
from datetime import datetime
from vncdotool import api as vnc
from collections import defaultdict

# ========================= CONFIG =========================
selected_platform = "both" # Default
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
VOTE_DURATION = 100
REQUIRED_VOTES = 2
# We write here which command will open which file
VM_DATABASE = {
    "win10": r"D:\VMSVMWARE\w8\Windows 10 x64.vmx", # Write your own path buddy
    "win8": r"D:\VMSVMWARE\w88\Windows 8.x x64.vmx",
    "win7": r"D:\w777\Windows 7 x64.vmx"
}

VOTE_SETTINGS = {
    "duration": 60,      # How many seconds should the voting last?
    "required_votes": 2  # How many people must vote at least?
}

active_voters = defaultdict(lambda: 0)
votes = {"restartvm": [], "revert": []}
last_command_time = {}

# ========================= ULTIMATE SCANCODE MAP =========================
# We use direct X11 Machine codes (Keysym) to bypass the bugs of the vncdotool library
SCANCODE_MAP = {
    "esc": chr(0xff1b), "escape": chr(0xff1b),
    "tab": chr(0xff09),
    "enter": chr(0xff0d), "return": chr(0xff0d),
    "space": " ",
    "backspace": chr(0xff08),  # HERE IS YOUR REMEDY!
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
    "f9": chr(0xffc6), "f10": chr(0xffc7), "f11": chr(0xffc8), "f12": chr(0xffc9)
}

# ========================= OVERLAY SYSTEM =========================
overlay_data = {"chat": [], "running_command": ""}
seen_message_ids = set()
last_write_time = 0

def update_overlay(author=None, message=None, running=None, msg_id=None):
    global last_write_time
    changed = False
    current_time = time.time()
  
    if running is not None and overlay_data.get("running_command") != running:
        overlay_data["running_command"] = running
        changed = True
  
    if author and message and msg_id and msg_id not in seen_message_ids:
        seen_message_ids.add(msg_id)
        overlay_data["chat"].append({
            "author": str(author),
            "message": str(message),
            "id": str(msg_id)
        })
      
        if len(overlay_data["chat"]) > 20:
            removed = overlay_data["chat"].pop(0)
            seen_message_ids.discard(removed.get("id"))
      
        changed = True
  
    if changed and (current_time - last_write_time > 0.15):
        try:
            with open("overlay.json", "w", encoding="utf-8") as f:
                json.dump(overlay_data, f, ensure_ascii=False, separators=(',', ':'))
            last_write_time = current_time
        except Exception as e:
            print(f"[Overlay Error] {e}")

async def show_running_command(cmd_text):
    update_overlay(running=cmd_text)
    await asyncio.sleep(2)
    if overlay_data["running_command"] == cmd_text:
        update_overlay(running="")

def start_overlay_server():
    PORT = 8080
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    try:
        with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
            print(f"🌐 Overlay Server running at: http://localhost:{PORT}/chat.html")
            httpd.serve_forever()
    except OSError:
        print("⚠️ Port 8080 is busy. Overlay server might fail to start.")

# ========================= REMOTE SECURITY =========================
def speak_text(text: str):
    print(f"\n📣 [SPEAKER]: {text}\n")

# ========================= VM CONTROLLER =========================
class VMController:
    def __init__(self):
        self.client = None
        self.cursor_x = 512
        self.cursor_y = 384

    async def connect_fresh(self):
        await self._disconnect()
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔌 New VNC Connection...")
            loop = asyncio.get_event_loop()
            self.client = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: vnc.connect(
                    f"{VNC_HOST}::{VNC_PORT}", password=str(VNC_PASSWORD)
                )),
                timeout=8
            )
            print("✅ Fresh VNC Connected")
            return self.client
        except Exception as e:
            print(f"❌ VNC Connect Failed: {e}")
            self.client = None
            return None

    async def _disconnect(self):
        if self.client:
            try: self.client.disconnect()
            except: pass
        self.client = None        

    async def send_key(self, key: str):
            client = await self.connect_fresh()
            if not client: return False
            try:
                loop = asyncio.get_event_loop()
                clean_key = key.strip().lower()
                
                # We get the real equivalent from SCANCODE_MAP
                mapped_key = SCANCODE_MAP.get(clean_key, clean_key)

                if "+" in key:
                    # Combo (Ctrl+C etc.) operations here (same as existing code)
                    keys = key.split("+")
                    mapped_keys = [SCANCODE_MAP.get(k.strip().lower(), k.strip().lower()) for k in keys]
                    try:
                        for k in mapped_keys:
                            await asyncio.wait_for(loop.run_in_executor(None, lambda k2=k: client.keyDown(k2)), timeout=2.0)
                            await asyncio.sleep(0.01)
                    finally:
                        for k in reversed(mapped_keys):
                            try: await asyncio.wait_for(loop.run_in_executor(None, lambda k2=k: client.keyUp(k2)), timeout=2.0)
                            except: pass
                    print(f"⌨️ Combo sent: {'+'.join(mapped_keys)}")
                
                else:
                    # --- NEW BLOCK PREVENTING STUCK/FREEZING ---
                    def do_safe_press():
                        try:
                            client.keyDown(mapped_key)
                            time.sleep(0.1)
                        finally:
                            client.keyUp(mapped_key)  # ss

                    await asyncio.wait_for(loop.run_in_executor(None, do_safe_press), timeout=10.0)
                    print(f"⌨️ Key sent and forced release: {mapped_key}")

                return True
            # Find the 'except Exception as e:' part in your code and update the print like this:
            except Exception as e:
                print(f"❌ Key Send Error: {str(e)}")
                import traceback
                traceback.print_exc() # <--- Add this so we can take an X-ray of the error

    async def type_text(self, text: str):
        client = await self.connect_fresh()
        if not client: return False
        try:
            loop = asyncio.get_event_loop()
            for char in text:
                if char.isupper() or char in '!@#$%^&*()_+{}|:"<>?~':
                    # ARMOR 2: Guarantee Shift when typing uppercase/special characters
                    try:
                        await asyncio.wait_for(loop.run_in_executor(None, lambda: client.keyDown(SCANCODE_MAP["shift"])), timeout=2.0)
                        key_to_send = char.lower() if char.isupper() else char
                        await asyncio.wait_for(loop.run_in_executor(None, lambda k=key_to_send: client.keyPress(k)), timeout=2.0)
                    finally:
                        try:
                            await asyncio.wait_for(loop.run_in_executor(None, lambda: client.keyUp(SCANCODE_MAP["shift"])), timeout=2.0)
                        except: pass
                else:
                    await asyncio.wait_for(loop.run_in_executor(None, lambda c=char: client.keyPress(c)), timeout=2.0)
                await asyncio.sleep(0.007)
            print(f"⌨️ Text sent: {text}")
            return True
        except:
            # If the process fails, release Shift just in case
            try:
                loop = asyncio.get_event_loop()
                await asyncio.wait_for(loop.run_in_executor(None, lambda: client.keyUp("shift")), timeout=1.0)
            except: pass
            await self._disconnect()
            return False

controller = VMController()

def update_vote_json(restart_time=0, revert_time=0):
    data = {
        "restartvm": {"current": len(votes["restartvm"]), "required": REQUIRED_VOTES, "remaining_time": restart_time},
        "revert": {"current": len(votes["revert"]), "required": REQUIRED_VOTES, "remaining_time": revert_time}
    }
    try:
        with open("votes.json", "w") as f: json.dump(data, f)
    except Exception: pass

async def get_user_input():
    global YOUTUBE_VIDEO_ID, VMX_PATH, selected_platform, vm_list
    
    # --- 1. LOAD VM LIST ---
    if os.path.exists(VM_DATABASE_FILE):
        with open(VM_DATABASE_FILE, "r") as f:
            vm_list = json.load(f)
    
    # --- 2. UPDATE OR REGISTRATION MODE ---
    # If there are no VMs or the user says 'yes', it enters registration mode
    update_needed = False
    if vm_list:
        print("\n" + "="*60)
        print(f"Registered VMs: {', '.join(vm_list.keys())}")
        choice = input("Do you want to update/add VMs? (yes/no): ").lower().strip()
        if choice == "yes":
            update_needed = True
    else:
        update_needed = True

    if update_needed:
        print("\n--- VM Registration Mode (Type 'DONE' to finish) ---")
        while True:
            path = input("Enter VMX File Path (or DONE): ").strip().replace('"', '')
            if path.upper() == "DONE": break
            if not os.path.exists(path):
                print("❌ Path does not exist!")
                continue
            alias = input(f"Give a short name for this VM (e.g., w11): ").strip().lower()
            vm_list[alias] = path
        
        with open(VM_DATABASE_FILE, "w") as f:
            json.dump(vm_list, f)
        print("✅ Database updated!")

    # --- 3. VM SELECTION (THIS SHOULD EXIT THE LOOP) ---
    print("\nAvailable VMs:")
    for alias in vm_list: print(f" - {alias}")
    
    while True:
        selection = input("Select VM name to use: ").strip().lower()
        if selection in vm_list:
            VMX_PATH = vm_list[selection]
            break # If the selection is correct, break the loop and go down to (platforms)
        print("❌ Invalid selection. Please type one of the names above.")

    # --- 4. PLATFORM SELECTION ---
    selected_platform = "1"
    YOUTUBE_VIDEO_ID = input("Enter YouTube Live Video ID: ").strip()

    print(f"\n🚀 Booting {selection.upper()} on Platform {selected_platform}...")
    print("="*60 + "\n")

def is_on_cooldown(cmd: str) -> bool:
    now = time.time()
    if cmd in last_command_time and now - last_command_time[cmd] < COOLDOWN.get(cmd, 5): return True
    last_command_time[cmd] = now
    return False

async def run_vmrun(args: list):
    try:
        if not os.path.exists(VMRUN_PATH): return False
        # Thanks to loop.run_in_executor, subprocess doesn't freeze the code
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            lambda: subprocess.run([VMRUN_PATH] + args, capture_output=True, text=True, timeout=60)
        )
        return result.returncode == 0
    except Exception as e:
        print(f"❌ VMRun Error: {e}")
        return False

async def execute_vm_action(vote_type: str):
    votes[vote_type] = []
    update_vote_json()
    
    if vote_type == "restartvm":
        # Added 'await' to the beginning
        await run_vmrun(["-T", "ws", "reset", VMX_PATH, "hard"])
    elif vote_type == "revert":
        # Added 'await' to the beginning
        await run_vmrun(["-T", "ws", "revertToSnapshot", VMX_PATH, "snp"])
        await asyncio.sleep(5)
        await run_vmrun(["-T", "ws", "start", VMX_PATH, "gui"])

async def start_vote(vote_type: str, starter: str):
    votes[vote_type] = [starter]
    print(f"🗳️ Voting started for !{vote_type} by {starter}")
    if vote_type == "restartvm": update_vote_json(restart_time=VOTE_DURATION)
    else: update_vote_json(revert_time=VOTE_DURATION)
    for remaining in range(VOTE_DURATION, 0, -1):
        await asyncio.sleep(1)
        if vote_type == "restartvm": update_vote_json(restart_time=remaining)
        else: update_vote_json(revert_time=remaining)
        if len(votes[vote_type]) >= REQUIRED_VOTES:
            print(f"✅ Vote PASSED early for !{vote_type}")
            await execute_vm_action(vote_type)
            return
    votes[vote_type] = []
    update_vote_json()

async def process_command(message: str, author: str):
    if not message.startswith(PREFIX): return
    raw_commands = [cmd.strip() for cmd in message.split(PREFIX) if cmd.strip()]
    active_voters[author] = time.time()
    for raw_cmd in raw_commands:
        parts = raw_cmd.split()
        if not parts: continue
      
        command = parts[0].lower()
        args = parts[1:]
      
        full_cmd_string = f"Running: {PREFIX}{command} {' '.join(args)}".strip()
        asyncio.create_task(show_running_command(full_cmd_string))
        
        if command == "startvm":
            if is_on_cooldown("startvm"): continue
            await run_vmrun(["start", VMX_PATH, "gui"])
        elif command == "restartvm":
            if votes["restartvm"]:
                if author not in votes["restartvm"]:
                    votes["restartvm"].append(author)
                    update_vote_json(restart_time=VOTE_DURATION)
                    if len(votes["restartvm"]) >= REQUIRED_VOTES: 
                        asyncio.create_task(execute_vm_action("restartvm"))
            else: asyncio.create_task(start_vote("restartvm", author))
        elif command == "revert":
            if votes["revert"]:
                if author not in votes["revert"]:
                    votes["revert"].append(author)
                    update_vote_json(revert_time=VOTE_DURATION)
                    if len(votes["revert"]) >= REQUIRED_VOTES: 
                        asyncio.create_task(execute_vm_action("revert"))
            else: asyncio.create_task(start_vote("revert", author))
        elif command in ["key", "press"] and args:
            await controller.send_key(" ".join(args).lower())
        elif command == "combo" and args:
            full_input = "+".join(args).lower().replace(" ", "+")
            while "++" in full_input: full_input = full_input.replace("++", "+")
            await controller.send_key(full_input)
            await asyncio.sleep(1.0)
        elif command == "hold" and args:
            key_name = args[0].lower()
            key = SCANCODE_MAP.get(key_name, key_name)
            hold_duration = float(args[1]) if len(args) > 1 else 1.0
            hold_duration = min(hold_duration, 3.0)  # ss
            client = await controller.connect_fresh()
            if client:
                loop = asyncio.get_event_loop()
                try:
                    await loop.run_in_executor(None, lambda: client.keyDown(key))
                    await asyncio.sleep(hold_duration)
                finally:
                    # ss
                    try:
                        await loop.run_in_executor(None, lambda: client.keyUp(key))
                    except:
                        pass
        elif command == "release" and args:
            client = await controller.connect_fresh()
            if client:
                key = SCANCODE_MAP.get(args[0].lower(), args[0].lower())
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: client.keyUp(key))
        # ARMOR 3: Recovery command. If trolls lock the keys, it resets when typed from chat.
        elif command == "releaseall":
            client = await controller.connect_fresh()
            if client:
                loop = asyncio.get_event_loop()
                release_keys = ["shift", "ctrl", "alt", "win"]  # ss
                for k in release_keys:
                    mapped = SCANCODE_MAP.get(k, k)  # ss
                    try:
                        await loop.run_in_executor(None, lambda key=mapped: client.keyUp(key))
                    except:
                        pass
                print("✅ All modifier keys released.")
        elif command in ["send", "typeenter"] and args:
            await controller.type_text(" ".join(args))
            await asyncio.sleep(0.05)
            await controller.send_key("enter")
        elif command == "type" and args:
            await controller.type_text(" ".join(args))
        elif command in ["move", "mouse", "mv"] and args:
            client = await controller.connect_fresh()
            if client:
                try:
                    if args[0].isalpha():
                        direction = args[0].lower()
                        step = int(args[1]) if len(args) > 1 and args[1].isdigit() else 40
                        if direction == "up": controller.cursor_y -= step
                        elif direction == "down": controller.cursor_y += step
                        elif direction == "left": controller.cursor_x -= step
                        elif direction == "right": controller.cursor_x += step
                        controller.cursor_x = max(0, min(1920, controller.cursor_x))
                        controller.cursor_y = max(0, min(1080, controller.cursor_y))
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, lambda: client.mouseMove(controller.cursor_x, controller.cursor_y))
                    elif len(args) >= 2:
                        dx, dy = int(args[0]), int(args[1])
                        controller.cursor_x = max(0, min(1920, controller.cursor_x + dx))
                        controller.cursor_y = max(0, min(1080, controller.cursor_y + dy))
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(None, lambda: client.mouseMove(controller.cursor_x, controller.cursor_y))
                except: pass
        elif command in ["abs", "cursor", "moveabs"] and len(args) >= 2:
            client = await controller.connect_fresh()
            if client:
                try:
                    controller.cursor_x = max(0, min(1920, int(args[0])))
                    controller.cursor_y = max(0, min(1080, int(args[1])))
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: client.mouseMove(controller.cursor_x, controller.cursor_y))
                except: pass
        elif command in ["drag", "dragrel"] and len(args) >= 2:
            client = await controller.connect_fresh()
            if client:
                try:
                    dx, dy = int(args[0]), int(args[1])
                    controller.cursor_x = max(0, min(1920, controller.cursor_x + dx))
                    controller.cursor_y = max(0, min(1080, controller.cursor_y + dy))
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: client.mouseDrag(controller.cursor_x, controller.cursor_y))
                except: pass
        elif command in ["click", "lclick"]:
            client = await controller.connect_fresh()
            if client:
                count = int(args[0]) if args and args[0].isdigit() else 1
                loop = asyncio.get_event_loop()
                for _ in range(count):
                    await loop.run_in_executor(None, lambda: client.mousePress(1))
                    await asyncio.sleep(0.01)
        elif command in ["rclick", "rightclick"]:
            client = await controller.connect_fresh()
            if client:
                count = int(args[0]) if args and args[0].isdigit() else 1
                loop = asyncio.get_event_loop()
                for _ in range(count):
                    await loop.run_in_executor(None, lambda: client.mousePress(2))
                    await asyncio.sleep(0.01)
        elif command in ["scroll", "wheel"] and args:
            client = await controller.connect_fresh()
            if client:
                try:
                    delta = int(args[0])
                    button = 4 if delta > 0 else 5
                    loop = asyncio.get_event_loop()
                    for _ in range(abs(delta) // 120):
                        await loop.run_in_executor(None, lambda b=button: client.mousePress(b))
                        await asyncio.sleep(0.01)
                except: pass
        elif command == "wait" and args and args[0].replace('.', '', 1).isdigit():
            await asyncio.sleep(min(float(args[0]), 5.0))

async def main():
    # 1. Start the overlay server
    update_overlay()
    threading.Thread(target=start_overlay_server, daemon=True).start()
    
    # 2. Get VM and Platform selections from the user
    await get_user_input()
    
    print("🚀 Bot starting...\n")

    tasks = []

    await youtube_loop()

# Move the YouTube loop here from the while True part in your existing code:
async def youtube_loop():
    while True:
        chat = None
        chat_start = time.time()
        try:
            chat = pytchat.create(video_id=YOUTUBE_VIDEO_ID)
            print("📡 Chat Connected")

            while chat.is_alive():
                # 200s chat reset
                if time.time() - chat_start > 200:
                    print("🔄 Chat Reset")
                    break

                for c in chat.get().sync_items():
                    msg = c.message.strip()
                    if not msg: continue
                    print(f"📨 [{datetime.now().strftime('%H:%M:%S')}] {c.author.name}: {msg}")
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
                except:
                    pass
        await asyncio.sleep(0.4)

if __name__ == "__main__":
    try: asyncio.run(main())
    except KeyboardInterrupt: print("\n👋 Bot stopped.")