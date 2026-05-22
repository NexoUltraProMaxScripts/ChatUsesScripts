import subprocess
import time
import pytchat
from vboxapi import VirtualBoxManager
import os
import threading
import sys
import win32com.client  # Windows Speech API
import http.server
import socketserver
import json

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

def start_overlay_server():
    PORT = 8083
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    try:
        with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
            print(f"🌐 Overlay Server running at: http://localhost:{PORT}/chat.html")
            httpd.serve_forever()
    except OSError:
        print("⚠️ Port 8083 is busy.")

# Scancode list
SCANCODES = {
    "esc": ("01","81"), "tab": ("0f","8f"), "enter": ("1c","9c"), "space": ("39","b9"),
    "backspace": ("0e","8e"), "delete": ("53","d3"), "del": ("53","d3"), "insert": ("52","d2"), "home": ("47","c7"),
    "end": ("4f","cf"), "pageup": ("49","c9"), "pagedown": ("51","d1"),
    "ctrl": ("1d","9d"), "alt": ("38","b8"), "shift": ("2a","aa"), "capslock": ("3a","ba"),
    "win": ("e05b","e0db"), "super": ("e05b","e0db"),
    "f1": ("3b","bb"), "f2": ("3c","bc"), "f3": ("3d","bd"), "f4": ("3e","be"),
    "f5": ("3f","bf"), "f6": ("40","c0"), "f7": ("41","c1"), "f8": ("42","c2"),
    "f9": ("43","c3"), "f10": ("44","c4"), "f11": ("57","d7"), "f12": ("58","d8"),
    "up": ("48","c8"), "down": ("50","d0"), "left": ("4b","cb"), "right": ("4d","cd"),
    "a": ("1e","9e"), "b": ("30","b0"), "c": ("2e","ae"), "d": ("20","a0"),
    "e": ("12","92"), "f": ("21","a1"), "g": ("22","a2"), "h": ("23","a3"),
    "i": ("17","97"), "j": ("24","a4"), "k": ("25","a5"), "l": ("26","a6"),
    "m": ("32","b2"), "n": ("31","b1"), "o": ("18","98"), "p": ("19","99"),
    "q": ("10","90"), "r": ("13","93"), "s": ("1f","9f"), "t": ("14","94"),
    "u": ("16","96"), "v": ("2f","af"), "w": ("11","91"), "x": ("2d","ad"),
    "y": ("15","95"), "z": ("2c","ac"),
    "0": ("0b","8b"), "1": ("02","82"), "2": ("03","83"), "3": ("04","84"),
    "4": ("05","85"), "5": ("06","86"), "6": ("07","87"), "7": ("08","88"),
    "8": ("09","89"), "9": ("0a","8a"),
}

def send_combo(keys):
    down_codes = []
    up_codes = []
    for k in keys:
        if k in SCANCODES:
            down, up = SCANCODES[k]
            send_scancode(down)
            time.sleep(0.01)
            up_codes.insert(0, up)
    for up in up_codes:
        send_scancode(up)
        time.sleep(0.01)
        
def get_vboxmanage_path():
    possible_paths = [
        r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        r"C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe",
        r"D:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        r"E:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"VBoxManage found at: {path}")
            return path
    
    print("⚠️ VBoxManage.exe not found! Please install VirtualBox.")
    return None

VBOXMANAGE_PATH = get_vboxmanage_path() 
COOLDOWN_START = 120
VOTE_FILE_RESTART = "restart_vote.html"
VOTE_FILE_REVERT = "revert_vote.html"
VOTE_FILE_BAN = "ban_vote.html"
STATUS_FILE = "newstatus.html"
BAN_DURATION = 1800
VOTE_TIMEOUT = 120  # 2 minutes (seconds)
SUCCESS_SOUND_FILE = "success.mp3"  # Optional file
ADMIN_USERNAME = "Nexora-WN"  # YouTube username for admin commands

mgr = VirtualBoxManager(None, None)
vbox = mgr.getVirtualBox()

active_users = set()
vote_restart = {}
vote_revert = {}
banned_users = {}
ban_votes = {}

restart_start_time = None
revert_start_time = None
revert_in_progress = False
restart_in_progress = False

COMMANDS_HELP = """
Commands (type with ! prefix)
!restartvm requires dynamic votes based on active users (1-3)
!revert requires dynamic votes based on active users (1-3)
!ban @user - requires 3 votes to ban user for 30 minutes (vote expires in 3 min)
Start VM: !startvm, !modlaunch, !launchvm, !start_mc, !startmc, !restore
Refresh / Bring to front: !restore, !refresh, !restore_window, !focus, !front, !bringtofront
Move mouse (relative): !move, !mouse, !mv
Move mouse (absolute): !abs, !cursor, !moveabs
Drag (relative): !drag, !dragrel
Drag (absolute): !dragabs, !drag_absolute
Click: !click, !lclick
Right click: !rclick, !rightclick
Middle click: !mclick, !middleclick
Scroll: !scroll, !wheel
Type text: !type, !text, !say
Type + Enter: !typeenter, !send, !sendline
Key press: !key, !press
Combo: !combo, !chord, !multi
Key down: !keydown, !hold
Key up: !keyup, !release
Wait: !wait, !pause, !delay
Fullscreen hint: !fullscreen, !fs
!votehelp - show this help
!clearvotes - clear all votes (admin only)
Note: 'shutdown' word is permanently blocked!
"""

def speak_text(text):
    """Windows SAPI"""
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
        print(f"Spoken: {text}")
    except Exception as e:
        print(f"Speak error: {e} - SAPI not available?")

def send_keyboard(text):
    try:
        vbox_path = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
        subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'keyboardputstring', text], check=True)
        print(f"Keyboard: {text}")
    except Exception as e:
        print(f"Keyboard error: {e}")

def send_scancode(scancode_str):
    try:
        vbox_path = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
        bytes_list = [scancode_str[i:i+2] for i in range(0, len(scancode_str), 2)]
        for byte in bytes_list:
            subprocess.run([vbox_path, 'controlvm', VM_NAME, 'keyboardputscancode', byte], check=True)
            time.sleep(0.008)
        print(f"Scancode sent: {scancode_str}")
    except Exception as e:
        print(f"Scancode error: {e}")

def send_special_enter():
    send_scancode('1c')
    time.sleep(0.015)
    send_scancode('9c')

def play_success_sound():
    try:
        subprocess.Popen(['start', SUCCESS_SOUND_FILE], shell=True)
        print("Success sound played!")
    except Exception as e:
        print(f"Sound play error: {e} - success.mp3 not found?")

def start_vm():
    try:
        update_status("Starting...")
        vbox_path = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
        subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
        update_status("Running")
        print("VM started!")
    except Exception as e:
        update_status("VM is already running!")
        print(f"VM is already running! {e}")

def restore_window():
    try:
        vbox_path = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
        subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'gui', 'show'], check=True)
        print("VM window brought to front!")
    except:
        print("Restore window: Not working in headless mode!")

def get_mouse_and_session():
    session = mgr.getSessionObject(vbox)
    machine = vbox.findMachine(VM_NAME)
    progress = machine.lockMachine(session, 1)
    console = session.console
    mouse = console.mouse
    return mouse, session

def unlock_session(session):
    if session.state == 1:
        session.unlockMachine(0)

def handle_mouse(cmd, args):
    try:
        mouse, session = get_mouse_and_session()
        parts = args.split()
        buttons = 0

        if cmd in ['move', 'mouse', 'mv']:
            if len(parts) == 2:
                dx, dy = int(parts[0]), int(parts[1])
                mouse.putMouseEvent(dx, dy, 0, 0, buttons)
            elif args in ['left','right','up','down']:
                dx = dy = 0
                if args == 'left': dx = -20
                elif args == 'right': dx = 20
                elif args == 'up': dy = -20
                elif args == 'down': dy = 20
                mouse.putMouseEvent(dx, dy, 0, 0, buttons)

        elif cmd in ['abs', 'cursor', 'moveabs']:
            if len(parts) == 2:
                x, y = int(parts[0]), int(parts[1])
                mouse.putMouseEventAbsolute(x, y, 0, 0, buttons)

        elif cmd in ['click', 'lclick']:
            count = int(args) if args.isdigit() else 1
            for _ in range(count):
                mouse.putMouseEvent(0, 0, 0, 0, 1)
                mouse.putMouseEvent(0, 0, 0, 0, 0)

        elif cmd in ['rclick', 'rightclick']:
            count = int(args) if args.isdigit() else 1
            for _ in range(count):
                mouse.putMouseEvent(0, 0, 0, 0, 2)

        elif cmd in ['mclick', 'middleclick']:
            count = int(args) if args.isdigit() else 1
            for _ in range(count):
                mouse.putMouseEvent(0, 0, 0, 0, 4)

        elif cmd in ['drag', 'dragrel']:
            if len(parts) >= 2:
                button = 1 if len(parts) == 2 else (1 if parts[0] == 'left' else 2 if parts[0] == 'right' else 4)
                dx, dy = int(parts[-2]), int(parts[-1])
                mouse.putMouseEvent(0, 0, 0, 0, button)
                mouse.putMouseEvent(dx, dy, 0, 0, button)
                mouse.putMouseEvent(0, 0, 0, 0, 0)

        elif cmd in ['dragabs', 'drag_absolute']:
            if len(parts) >= 2:
                button = 1 if len(parts) == 2 else (1 if parts[0] == 'left' else 2 if parts[0] == 'right' else 4)
                x, y = int(parts[-2]), int(parts[-1])
                mouse.putMouseEventAbsolute(x, y, 0, 0, button)
                mouse.putMouseEventAbsolute(x, y, 0, 0, 0)

        elif cmd in ['scroll', 'wheel']:
            dz = int(args) if args else 0
            mouse.putMouseEvent(0, 0, dz, 0, 0)

        unlock_session(session)
        print(f"Mouse: {cmd} {args}")
    except Exception as e:
        print(f"Mouse error: {e} - VM running? Guest Additions?")

def update_restart_vote_display(current_votes, required, remaining_time=None, start_time=None):
    remaining_str = f"Remaining time: {int(remaining_time)} s" if remaining_time is not None else ""
    js_countdown = ""
    if start_time is not None:
        js_countdown = f"""
        <script>
            var startTime = {start_time * 1000};  // milliseconds
            var timeout = {VOTE_TIMEOUT * 1000};
            function updateTimer() {{
                var now = Date.now();
                var elapsed = now - startTime;
                var remaining = Math.max(0, timeout - elapsed);
                var seconds = Math.floor(remaining / 1000);
                document.getElementById('timer').innerText = 'Remaining time: ' + seconds + ' s';
                if (remaining <= 0) {{
                    document.getElementById('timer').innerText = 'Timed out!';
                }}
            }}
            setInterval(updateTimer, 1000);
            updateTimer();  // Initial call
        </script>
        <p id="timer">{remaining_str}</p>
        """
    else:
        js_countdown = f"<p>{remaining_str}</p>"

    html_content = f"""
    <html>
    <head>
        <style>
            body {{ background-color: rgba(0,0,0,0); color: white; font-family: Arial; text-align: center; font-size: 28px; text-shadow: 2px 2px 4px #000; }}
            #container {{ margin-top: 40px; padding: 20px; background: rgba(0,0,0,0.5); border-radius: 12px; display: inline-block; }}
            h1 {{ color: #00ff90; margin-bottom: 15px; }}
            p {{ margin: 8px 0; }}
            .progress {{ width: 80%; height: 25px; background: rgba(255,255,255,0.2); border-radius: 12px; margin: 15px auto; overflow: hidden; }}
            .bar {{ height: 100%; width: {int((current_votes/required)*100)}%; background: lime; transition: width 0.5s; }}
        </style>
    </head>
    <body>
        <div id="container">
            <h1>Restart Vote Status</h1>
            <p>{current_votes} / {required} votes collected!</p>
            <p>Required: {required} votes based on active users</p>
            {js_countdown}
            <div class="progress"><div class="bar"></div></div>
        </div>
        <script>setInterval(() => {{location.reload();}}, 10000);</script>  </body>
    </html>
    """
    with open(VOTE_FILE_RESTART, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Restart vote updated: {current_votes}/{required} - {remaining_str}")

def update_revert_vote_display(current_votes, required, remaining_time=None, start_time=None):
    remaining_str = f"Remaining time: {int(remaining_time)} s" if remaining_time is not None else ""
    js_countdown = ""
    if start_time is not None:
        js_countdown = f"""
        <script>
            var startTime = {start_time * 1000};
            var timeout = {VOTE_TIMEOUT * 1000};
            function updateTimer() {{
                var now = Date.now();
                var elapsed = now - startTime;
                var remaining = Math.max(0, timeout - elapsed);
                var seconds = Math.floor(remaining / 1000);
                document.getElementById('timer').innerText = 'Remaining time: ' + seconds + ' s';
                if (remaining <= 0) {{
                    document.getElementById('timer').innerText = 'Timed out!';
                }}
            }}
            setInterval(updateTimer, 1000);
            updateTimer();
        </script>
        <p id="timer">{remaining_str}</p>
        """
    else:
        js_countdown = f"<p>{remaining_str}</p>"

    html_content = f"""
    <html>
    <head>
        <style>
            body {{ background-color: rgba(0,0,0,0); color: white; font-family: Arial; text-align: center; font-size: 28px; text-shadow: 2px 2px 4px #000; }}
            #container {{ margin-top: 40px; padding: 20px; background: rgba(0,0,0,0.5); border-radius: 12px; display: inline-block; }}
            h1 {{ color: #00ff90; margin-bottom: 15px; }}
            p {{ margin: 8px 0; }}
            .progress {{ width: 80%; height: 25px; background: rgba(255,255,255,0.2); border-radius: 12px; margin: 15px auto; overflow: hidden; }}
            .bar {{ height: 100%; width: {int((current_votes/required)*100)}%; background: lime; transition: width 0.5s; }}
        </style>
    </head>
    <body>
        <div id="container">
            <h1>Revert Vote Status</h1>
            <p>{current_votes} / {required} votes collected!</p>
            <p>Required: {required} votes based on active users</p>
            {js_countdown}
            <div class="progress"><div class="bar"></div></div>
        </div>
        <script>setInterval(() => {{location.reload();}}, 10000);</script>  </body>
    </html>
    """
    with open(VOTE_FILE_REVERT, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Revert vote updated: {current_votes}/{required} - {remaining_str}")

def update_ban_vote_display(target, current_votes, required, remaining_time=None):
    action_text = f"Ban @{target}" if target else "Empty"
    remaining_str = f"Remaining time: {int(remaining_time)} s" if remaining_time is not None else ""
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ background-color: rgba(0,0,0,0); color: white; font-family: Arial; text-align: center; font-size: 28px; text-shadow: 2px 2px 4px #000; }}
            #container {{ margin-top: 40px; padding: 20px; background: rgba(0,0,0,0.5); border-radius: 12px; display: inline-block; }}
            h1 {{ color: #ff4444; margin-bottom: 15px; }}
            p {{ margin: 8px 0; }}
            .progress {{ width: 80%; height: 25px; background: rgba(255,255,255,0.2); border-radius: 12px; margin: 15px auto; overflow: hidden; }}
            .bar {{ height: 100%; width: {int((current_votes/required)*100)}%; background: #ff4444; transition: width 0.5s; }}
        </style>
    </head>
    <body>
        <div id="container">
            <h1>Ban Vote Status</h1>
            <p>Action: {action_text}</p>
            <p>Votes: {current_votes}/{required}</p>
            <p>{remaining_str}</p>
            <div class="progress"><div class="bar"></div></div>
        </div>
        <script>setInterval(() => {{location.reload();}}, 10000);</script>  </body>
    </html>
    """
    with open(VOTE_FILE_BAN, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Ban vote updated: {action_text} - {current_votes}/{required} - {remaining_str}")

def update_status(message):
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ background-color: rgba(0,0,0,0); color: white; font-family: Arial; font-size: 32px; text-align: center; text-shadow: 2px 2px 4px #000; }}
            #status {{ margin-top: 20px; padding: 10px; background: rgba(0,0,0,0.4); border-radius: 8px; display: inline-block; }}
        </style>
    </head>
    <body>
        <div id="status">Status: {message}</div>
        <script>setInterval(() => {{location.reload();}}, 10000);</script>  </body>
    </html>
    """
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Status updated: {message}")

def vote_timeout_checker():
    global vote_restart, vote_revert, ban_votes, restart_start_time, revert_start_time
    while True:
        time.sleep(1) 
        current_time = time.time()

        if restart_start_time is not None and current_time - restart_start_time > VOTE_TIMEOUT:
            vote_restart.clear()
            restart_start_time = None
            update_restart_vote_display(0, 3, 0, None)
            print("Restart votes timed out, cleared")

        if revert_start_time is not None and current_time - revert_start_time > VOTE_TIMEOUT:
            vote_revert.clear()
            revert_start_time = None
            update_revert_vote_display(0, 3, 0, None)
            print("Revert votes timed out, cleared")

        to_remove = []
        for target, data in ban_votes.items():
            if 'start_time' in data and current_time - data['start_time'] > VOTE_TIMEOUT:
                to_remove.append(target)
        for target in to_remove:
            del ban_votes[target]
            update_ban_vote_display(None, 0, 3)
            print(f"Ban vote timed out for {target}, cleared")

def watchdog_restart():
    global revert_in_progress
    vbox_path = r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
    while True:
        try:
            result = subprocess.run([VBOXMANAGE_PATH, 'showvminfo', VM_NAME, '--machinereadable'], capture_output=True, text=True)
            status_line = [line for line in result.stdout.splitlines() if line.startswith('VMState="')]
            if status_line:
                vm_state = status_line[0].split('=')[1].strip('"')
                if vm_state in ["poweroff", "aborted", "gurumeditation"]:
                    if revert_in_progress:
                        print("Watchdog: Reverting in progress, ignoring VM down state.")
                    else:
                        print(f"Watchdog: VM down! ({vm_state}). Restarting.")
                        update_status("Auto-starting...")
                        speak_text("Auto starting virtual machine...")
                        subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
                        update_status("Running")
                        speak_text("Running")
                        print("VM automatically restarted!")
        except Exception as e:
            print(f"Watchdog error: {e}")
            update_status("Startup failed!")
        time.sleep(10)

class YouTubeChatBot:
    def __init__(self):
        self.video_id = VIDEO_ID
        self.chat = None
        self.reconnect() 
        
        # Overlay
        update_overlay()
        threading.Thread(target=start_overlay_server, daemon=True).start()
        
        if not self.chat or not self.chat.is_alive():
            print("Could not connect to YouTube live chat!")
            return

        print("Connected to YouTube chat!")
        print(COMMANDS_HELP)
        self.last_start_time = 0
        self.ban_votes = {}
        threading.Thread(target=vote_timeout_checker, daemon=True).start()
        threading.Thread(target=watchdog_restart, daemon=True).start()
        
        
    def reconnect(self):
        """ss"""
        print("Reconnecting to YouTube chat...")
        if self.chat:
            try:
                self.chat.terminate()
            except:
                pass
        
        try:
            self.chat = pytchat.create(video_id=self.video_id)
            print("Reconnect successful.")
            return True
        except Exception as e:
            print(f"Reconnect failed: {e}")
            return False

    def run(self):
        global restart_start_time, revert_start_time, revert_in_progress, restart_in_progress
        last_reconnect = time.time()
        RECONNECT_INTERVAL = 150

        print("Bot started. Waiting for chat messages...")

        while True:
            if time.time() - last_reconnect > RECONNECT_INTERVAL:
                print("Periodic reconnect triggered...")
                self.reconnect()
                last_reconnect = time.time()

            if not self.chat or not self.chat.is_alive():
                print("Chat is not alive. Reconnecting...")
                self.reconnect()
                time.sleep(5)
                continue

            try:
                for c in self.chat.get().sync_items():
                    msg = c.message.strip()
                    user = c.author.name.strip().lower()
                    
                    # Overlay update
                    update_overlay(author=user, message=msg, msg_id=c.id)

                    if user in banned_users:
                        if time.time() < banned_users[user]:
                            continue
                        else:
                            del banned_users[user]

                    active_users.add(c.author.name.strip())
                    print(f"[{user}]: {msg}")

                    if msg.startswith('!'):
                        chain_parts = [part.strip() for part in msg.split('!') if part.strip()]
                        for part in chain_parts:
                            sub_parts = part.split(maxsplit=1)
                            cmd = sub_parts[0].lower()
                            args = sub_parts[1] if len(sub_parts) > 1 else ""

                            if cmd in ['wait', 'pause', 'delay']:
                                try:
                                    delay = float(args)
                                    
                                    # security
                                    if delay > 5.0:
                                        delay = 5.0
                                        print(f"Wait limit applied: {user} wanted {args}s → limited to 5s")
                                    elif delay <= 0:
                                        print(f"Invalid wait (≤0) ignored by {user}")
                                        continue
                                        
                                    print(f"Chain delay: {delay:.2f}s (by {user})")
                                    time.sleep(delay)        
                                    
                                except ValueError:
                                    print(f"Invalid wait value by {user}: {args}")
                                except Exception as e:
                                    print(f"Wait error by {user}: {e}")
                                continue

                            if cmd in ['type', 'text', 'say']:
                                send_keyboard(args)
                            elif cmd in ['typeenter', 'send', 'sendline']:
                                send_keyboard(args)
                                send_special_enter()
                            elif cmd == 'enter':
                                send_special_enter()
                            elif cmd in ['fullscreen', 'fs']:
                                print("Fullscreen hint: Manual!")
                            
                           # elif cmd == 'speak':
                                # Only moderators and the stream owner can use this command
                               # if not (c.author.isChatModerator or c.author.isChatOwner):
                                   # print(f"⚠️ Only moderators can use !speak → {user}")
                                   # continue
                                
                              #  if not args.strip():
                                  #  speak_text("Please write something after the !speak command.")
                                  #  print(f"!speak command used without text by {user}")
                                  #  continue
                                
                               # text = args.strip()
                                # Limit text length to avoid issues with Windows SAPI
                               # if len(text) > 280:
                                #    text = text[:277] + "..."
                                
                               # print(f"[MOD SPEAK] {user}: {text}")
                               # speak_text(text)
                                
                                # Optional: Show short feedback on the overlay
                                # update_status(f"Mod spoke: {text[:50]}...")

                            elif cmd in ['move', 'mouse', 'mv', 'abs', 'cursor', 'moveabs', 'drag', 'dragrel', 'dragabs', 'drag_absolute', 'click', 'lclick', 'rclick', 'rightclick', 'mclick', 'middleclick', 'scroll', 'wheel']:
                                handle_mouse(cmd, args)

                            elif cmd in ['startvm', 'modlaunch', 'launchvm', 'start_mc', 'startmc']:
                                if time.time() - self.last_start_time > COOLDOWN_START:
                                    start_vm()
                                    self.last_start_time = time.time()
                                else:
                                    print("Cooldown active!")
                            elif cmd in ['restore', 'refresh', 'restore_window', 'focus', 'front', 'bringtofront']:
                                restore_window()

                            elif cmd in ['key', 'press']:
                                key = args.lower().strip()
                                if key in SCANCODES:
                                    down, up = SCANCODES[key]
                                    send_scancode(down)
                                    time.sleep(0.01)
                                    send_scancode(up)
                                else:
                                    send_keyboard(key)

                            elif cmd in ['keydown', 'hold']:
                                key = args.lower().strip()
                                if key in SCANCODES:
                                    down, up = SCANCODES[key]
                                    send_scancode(down)

                            elif cmd in ['keyup', 'release']:
                                key = args.lower().strip()
                                if key in SCANCODES:
                                    down, up = SCANCODES[key]
                                    send_scancode(up)

                            elif cmd in ['combo','chord','multi']:
                                keys = args.lower().replace('+',' ').split()
                                if keys:
                                    send_combo(keys)
                                else:
                                    send_keyboard(args)
                            
                            elif cmd == 'run':
                                print(f"!run → Win+R by {user}")
                                send_combo(['win', 'r'])

                            elif cmd == 'votehelp':
                                update_status("Commands in description! Type !votehelp again to refresh.")
                                print("Vote help requested - commands in description")

                            elif cmd == 'clearvotes':
                                if user == ADMIN_USERNAME.lower():
                                    vote_restart.clear()
                                    vote_revert.clear()
                                    ban_votes.clear()
                                    restart_start_time = None
                                    revert_start_time = None
                                    update_restart_vote_display(0, 3)
                                    update_revert_vote_display(0, 3)
                                    update_ban_vote_display(None, 0, 3)
                                    print("All votes cleared by admin")
                                    speak_text("Votes cleared by admin!")
                                else:
                                    print(f"Clear votes attempted by non-admin: {user}")

                            # ================== Dss ==================
                            active_count = max(1, len(active_users))
                            
                            if active_count <= 3:
                                required_votes = 2
                            elif active_count <= 6:
                                required_votes = 2
                            else:
                                required_votes = 2
                            # =========================================================

                            current_time = time.time()

                            if cmd in ['restart', 'restartvm']:
                                # ss
                                if 'restart_in_progress' in globals() and restart_in_progress:
                                    print(f"⚠️ Restart is already in progress by {user}")
                                    continue
                                
                                # ss
                                if not vote_restart:
                                    restart_start_time = current_time
                                
                                # ss
                                if user in vote_restart:
                                    print(f"{user} already voted for restart")
                                    continue
                                
                                vote_restart[user] = current_time
                                current = len(vote_restart)
                                remaining = max(0, VOTE_TIMEOUT - (current_time - restart_start_time)) if restart_start_time else None
                                
                                update_restart_vote_display(current, required_votes, remaining, start_time=restart_start_time)
                                
                                # ss
                                if current >= required_votes:
                                    print(f"Full dynamic votes ({current}/{required_votes})! Restarting VM...")
                                    speak_text("Restarting Virtual Machine...")
                                    
                                    # ss
                                    vote_restart.clear()
                                    restart_start_time = None
                                    active_users.clear()
                                    
                                    # ss
                                    restart_in_progress = True
                                    
                                    update_status("Restarting...")
                                    
                                    # ss
                                    subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'reset'], check=True)
                                    
                                    update_status("Running")
                                    play_success_sound()
                                    update_restart_vote_display(0, required_votes, 0, start_time=None)
                                    
                                    restart_in_progress = False
                                    print("Restart completed successfully.")

                            elif cmd == 'revert':
                                if revert_in_progress:
                                    print(f"⚠️ Revert is already in progress by {user}")
                                    continue
                                
                                if not vote_revert:
                                    revert_start_time = current_time
                                
                                if user in vote_revert:
                                    print(f"{user} already voted for revert")
                                    continue
                                
                                vote_revert[user] = current_time
                                current = len(vote_revert)
                                remaining = max(0, VOTE_TIMEOUT - (current_time - revert_start_time)) if revert_start_time else None
                                
                                update_revert_vote_display(current, required_votes, remaining, start_time=revert_start_time)
                                
                                if current >= required_votes:
                                    print(f"Full dynamic votes ({current}/{required_votes})! Reverting snapshot...")
                                    speak_text("Reverting Virtual Machine...")
                                    
                                    vote_revert.clear()
                                    revert_start_time = None
                                    active_users.clear()
                                    
                                    revert_in_progress = True
                                    
                                    update_status("Reverting...")
                                    subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'poweroff'], check=True)
                                    time.sleep(3)
                                    subprocess.run([VBOXMANAGE_PATH, 'snapshot', VM_NAME, 'restorecurrent'], check=True)
                                    time.sleep(3)
                                    subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
                                    
                                    update_status("Running")
                                    play_success_sound()
                                    update_revert_vote_display(0, required_votes, 0, start_time=None)
                                    
                                    revert_in_progress = False
                                    print("Revert completed successfully.")

                            elif cmd == 'ban':
                                if not args.startswith('@'):
                                    continue
                                target_raw = args[1:].split()[0].strip()
                                target = target_raw.lower()
                                print(f"Ban attempt: user={user}, target_raw={target_raw}, target={target}")

                                active_clean = {t.strip().lstrip('@').lower() for t in active_users}
                                if target not in active_clean:
                                    print(f"Ban target not active: {target}")
                                    continue

                                if target not in ban_votes:
                                    ban_votes[target] = {'voters': set(), 'start_time': current_time}
                                    print(f"New ban vote started: {target}")

                                if user in ban_votes[target]['voters']:
                                    print(f"{user} already voted")
                                    continue

                                ban_votes[target]['voters'].add(user)

                                current_ban_votes = len(ban_votes[target]['voters'])
                                remaining = max(0, VOTE_TIMEOUT - (current_time - ban_votes[target]['start_time']))
                                update_ban_vote_display(target_raw, current_ban_votes, 3, remaining)

                                if current_ban_votes >= 3:
                                    ban_end = time.time() + BAN_DURATION
                                    banned_users[target] = ban_end
                                    update_status(f"@{target_raw} banned for 30 minutes!")
                                    print(f"@{target_raw} banned for 30 min!")
                                    play_success_sound()
                                    speak_text(f"Banned @{target_raw} for 30 minutes.")
                                    if target in ban_votes:
                                        del ban_votes[target]
                                    update_ban_vote_display(None, 0, 3)

            except Exception as e:
                error_msg = str(e).lower()
                if "read operation timed out" in error_msg or "timeout" in error_msg or "read timed out" in error_msg:
                    print(f"⚠️ Read timeout detected → Reconnecting automatically...")
                else:
                    print(f"⚠️ pytchat error: {e} → Reconnecting...")

                self.reconnect()
                time.sleep(5)

            time.sleep(0.05)

def admin_console_listener():
    print("Admin console active! Commands: !startvm, !restart, !revert, !exit, !clearvotes")
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == '!startvm':
                print("Admin: Starting VM!")
                speak_text("Starting Virtual Machine...")
                update_status("Starting...")
                start_vm()
                update_status("Running")
                play_success_sound()
            elif cmd == '!restart':
                print("Admin: Restarting VM!")
                speak_text("Restarting Virtual Machine...")
                update_status("Restarting...")
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'reset'])
                update_status("Running")
                play_success_sound()
            
            elif cmd.startswith('!speak '):
                text = cmd[7:].strip() 
                if text:
                    print(f"Admin speaking: {text}")
                    speak_text(text)
                else:
                    print("Usage: !speak <text>")
            
            elif cmd == '!speak':
                print("Usage: !speak text")

            elif cmd == '!revert':
                print("Admin: Reverting snapshot!")
                speak_text("Reverting Virtual Machine...")
                global revert_in_progress
                revert_in_progress = True
                update_status("Reverting...")
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'poweroff'], check=True)
                time.sleep(3)
                subprocess.run([VBOXMANAGE_PATH, 'snapshot', VM_NAME, 'restorecurrent'], check=True)
                time.sleep(3)
                subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
                update_status("Running")
                play_success_sound()
                vote_revert.clear()
                global revert_start_time
                revert_start_time = None
                revert_in_progress = False
                update_revert_vote_display(0, 3)
            elif cmd == '!clearvotes':
                vote_restart.clear()
                vote_revert.clear()
                ban_votes.clear()
                restart_start_time = None
                revert_start_time = None
                update_restart_vote_display(0, 3)
                update_revert_vote_display(0, 3)
                update_ban_vote_display(None, 0, 3)
                print("All votes cleared by admin")
                speak_text("Votes cleared by admin!")
            elif cmd == '!exit':
                print("Admin console closing...")
                break
            else:
                print("Unknown command.")
        except KeyboardInterrupt:
            print("Admin console closing...")
            break
        except Exception as e:
            print(f"Admin error: {e}")

# ====================== MAIN ======================
if __name__ == '__main__':
    print("=== UltraBot Guest Script ===\n")

    print("Please enter stream information:")
    VIDEO_ID = input("Enter YouTube Video ID: ").strip()
    VM_NAME = input("Enter VirtualBox VM Name: ").strip()
    
    if not VIDEO_ID:
        print("❌ Error: Video ID cannot be empty!")
        sys.exit(1)
    if not VM_NAME:
        print("❌ Error: VM Name cannot be empty!")
        sys.exit(1)
    
    print(f"\n✅ Configuration Loaded:")
    print(f"   YouTube Video ID : {VIDEO_ID}")
    print(f"   VirtualBox VM Name: {VM_NAME}")
    print("-" * 50)
    
    time.sleep(1.5)

    print("Starting Bot...\n")

    bot = YouTubeChatBot()
    
    admin_thread = threading.Thread(target=admin_console_listener, daemon=True)
    admin_thread.start()
    
    if bot.chat and bot.chat.is_alive():
        bot.run()
    else:
        print("❌ Chat connection failed at startup. Exiting.")