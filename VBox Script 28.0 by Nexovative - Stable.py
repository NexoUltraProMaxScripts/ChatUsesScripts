import subprocess
import time
import signal as _signal_module
import threading as _threading_module

# ── pytchat fix: signal.signal() only works on main thread.
# When the bot runs in a worker thread, patch it to be a no-op. ──
_orig_signal = _signal_module.signal
def _safe_signal(sig, handler):
    if _threading_module.current_thread() is _threading_module.main_thread():
        return _orig_signal(sig, handler)
_signal_module.signal = _safe_signal

import pytchat
from vboxapi import VirtualBoxManager
import os
import threading
import sys
import re
import win32com.client
import http.server
import socketserver
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# ========================= CUSTOM COMMANDS =========================
CUSTOM_COMMANDS_FILE = "custom_commands.json"
custom_commands = {}  # {"!bubbles": [{"action": "combo", "args": "win+r"}, ...]}

def load_custom_commands():
    global custom_commands
    try:
        if os.path.exists(CUSTOM_COMMANDS_FILE):
            with open(CUSTOM_COMMANDS_FILE, "r", encoding="utf-8") as f:
                custom_commands = json.load(f)
            print(f"[CustomCmd] {len(custom_commands)} custom command(s) loaded.")
    except Exception as e:
        print(f"[CustomCmd] Load error: {e}")
        custom_commands = {}

def save_custom_commands():
    try:
        with open(CUSTOM_COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(custom_commands, f, indent=2, ensure_ascii=False)
        print(f"[CustomCmd] Saved {len(custom_commands)} command(s).")
    except Exception as e:
        print(f"[CustomCmd] Save error: {e}")

def execute_custom_command(trigger):
    steps = custom_commands.get(trigger, [])
    print(f"[CustomCmd] Executing '{trigger}' ({len(steps)} steps)")
    for step in steps:
        action = step.get("action", "").lower().strip()
        args   = step.get("args",   "").strip()
        try:
            if action == "combo":
                keys = [k.strip().lower() for k in args.replace("+", " ").split()]
                send_combo(keys)
            elif action in ("send", "type", "text", "say"):
                send_keyboard(args)
            elif action in ("sendenter", "typeenter", "sendline"):
                send_keyboard(args)
                time.sleep(0.05)
                send_special_enter()
            elif action == "enter":
                send_special_enter()
            elif action in ("key", "press"):
                k = args.lower().strip()
                if k in SCANCODES:
                    send_scancode(SCANCODES[k][0])
                    time.sleep(0.02)
                    send_scancode(SCANCODES[k][1])
                else:
                    send_keyboard(k)
            elif action in ("keydown", "hold"):
                k = args.lower().strip()
                if k in SCANCODES:
                    send_scancode(SCANCODES[k][0])
            elif action in ("keyup", "release"):
                k = args.lower().strip()
                if k in SCANCODES:
                    send_scancode(SCANCODES[k][1])
            elif action in ("wait", "pause", "delay"):
                try:
                    ms = float(args)
                    time.sleep(max(0, min(ms, 5000)) / 1000.0)
                except ValueError:
                    time.sleep(0.5)
            elif action in ("click", "lclick"):
                handle_mouse("click", args)
            elif action in ("rclick", "rightclick"):
                handle_mouse("rclick", args)
            elif action in ("move", "mouse", "mv"):
                handle_mouse("move", args)
            elif action in ("abs", "cursor", "moveabs"):
                handle_mouse("abs", args)
            elif action in ("scroll", "wheel"):
                handle_mouse("scroll", args)
            print(f"[CustomCmd]   → {action} {args}")
        except Exception as e:
            print(f"[CustomCmd] Step error ({action} {args}): {e}")

# ========================= OVERLAY SYSTEM =========================
overlay_data = {"chat": [], "running_command": "", "viewers": None, "likes": None, "subscribers": None}
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
        overlay_data["chat"].append({"author": str(author), "message": str(message), "id": str(msg_id)})
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

# def fetch_youtube_stats():
  #  """Background thread: polls YouTube Data API v3 every 30s for live viewer/like/subscriber counts."""
   # import urllib.request
   # while True:
      #  try:
       #     if YOUTUBE_API_KEY and VIDEO_ID:
                # Live viewer count + like count from video resource
            #    url_video = (
                 #   f"https://www.googleapis.com/youtube/v3/videos"
                 #   f"?part=statistics,liveStreamingDetails&id={VIDEO_ID}&key={YOUTUBE_API_KEY}"
             #   )
             #   with urllib.request.urlopen(url_video, timeout=10) as r:
                #    vdata = json.loads(r.read().decode())
               # items = vdata.get("items", [])
               # if items:
               #     stats = items[0].get("statistics", {})
               #     live  = items[0].get("liveStreamingDetails", {})
               #     overlay_data["viewers"]     = int(live.get("concurrentViewers", 0)) if live.get("concurrentViewers") else None
               #     overlay_data["likes"]       = int(stats.get("likeCount", 0))        if stats.get("likeCount")       else None
                    # Subscriber count requires channel ID — fetch from video snippet first if not cached
                 #   url_snap = (
                  #      f"https://www.googleapis.com/youtube/v3/videos"
                  #      f"?part=snippet&id={VIDEO_ID}&key={YOUTUBE_API_KEY}"
                  #  )
                  #  with urllib.request.urlopen(url_snap, timeout=10) as r2:
                  #      snap = json.loads(r2.read().decode())
                  #  channel_id = snap.get("items", [{}])[0].get("snippet", {}).get("channelId", "")
                 #   if channel_id:
                  #      url_ch = (
                  #          f"https://www.googleapis.com/youtube/v3/channels"
                  #          f"?part=statistics&id={channel_id}&key={YOUTUBE_API_KEY}"
                    #    )
                   #     with urllib.request.urlopen(url_ch, timeout=10) as r3:
                   #         cdata = json.loads(r3.read().decode())
                   #     sub_count = cdata.get("items", [{}])[0].get("statistics", {}).get("subscriberCount")
                   #     overlay_data["subscribers"] = int(sub_count) if sub_count else None
                    # Write updated stats immediately
                  #  try:
                     #   with open("overlay.json", "w", encoding="utf-8") as f:
                    #        json.dump(overlay_data, f, ensure_ascii=False, separators=(',', ':'))
                #    except Exception:
                #        pass
     #   except Exception as e:
      #      print(f"[Stats] Fetch error: {e}")
      #  time.sleep(30)

def start_overlay_server():
    PORT = 8083
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args): pass
    try:
        with socketserver.TCPServer(("", PORT), QuietHandler) as httpd:
            print(f"[Overlay] Server running at: http://localhost:{PORT}/chat.html")
            httpd.serve_forever()
    except OSError:
        print("[Overlay] Port 8083 is busy.")

# ========================= SCANCODES =========================
SCANCODES = {
    "esc": ("01","81"), "tab": ("0f","8f"), "enter": ("1c","9c"), "space": ("39","b9"),
    "backspace": ("0e","8e"), "delete": ("53","d3"), "del": ("53","d3"),
    "insert": ("52","d2"), "home": ("47","c7"), "end": ("4f","cf"),
    "pageup": ("49","c9"), "pagedown": ("51","d1"),
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
            return path
    return None

def get_vm_list():
    """Fetches the VM list from VirtualBox."""
    vbm = get_vboxmanage_path()
    if not vbm:
        return []
    try:
        result = subprocess.run([vbm, "list", "vms"], capture_output=True, text=True)
        # Each line: "VM Name" {uuid}
        vms = re.findall(r'"([^"]+)"', result.stdout)
        return vms
    except Exception as e:
        print(f"[VM List] Error: {e}")
        return []

VBOXMANAGE_PATH = get_vboxmanage_path()
COOLDOWN_START  = 120
VOTES_JSON_FILE = "votes.json"
VOTE_FILE_BAN   = "ban_vote.html"
STATUS_FILE     = "newstatus.html"

# Shared vote state written to votes.json (read by overlay.html)
_votes_state = {
    "restartvm": {"remaining_time": 0, "current": 0, "required": 2},
    "revert":    {"remaining_time": 0, "current": 0, "required": 2},
}

def update_votes_json(vote_type: str, current: int, required: int, remaining_time: float = 0):
    """Write the current vote state for one vote type to votes.json."""
    _votes_state[vote_type]["current"]        = current
    _votes_state[vote_type]["required"]       = required
    _votes_state[vote_type]["remaining_time"] = max(0, int(remaining_time))
    try:
        with open(VOTES_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(_votes_state, f, separators=(',', ':'))
    except Exception as e:
        print(f"[Votes] Write error: {e}")
BAN_DURATION      = 1800
VOTE_TIMEOUT      = 120
SUCCESS_SOUND_FILE = "success.mp3"
ADMIN_USERNAME     = "Nexora-WN"
YOUTUBE_API_KEY    = ""   # Optional: paste your YouTube Data API v3 key here for live stats

# Global bot state (set at runtime from GUI)
VIDEO_ID = ""
VM_NAME  = ""

mgr  = VirtualBoxManager(None, None)
vbox = mgr.getVirtualBox()

active_users = set()
bot_stop_event = threading.Event()   # set this to actually stop the bot + its background threads
vote_restart = {}
vote_revert  = {}
banned_users = {}
ban_votes    = {}
restart_start_time = None
revert_start_time  = None
revert_in_progress   = False
restart_in_progress  = False
AUTO_START_ENABLED = True   # if False, watchdog_restart will not auto-revive a powered-off VM
AUTO_START_CONFIG_FILE = "auto_start_config.json"

def load_auto_start_config():
    global AUTO_START_ENABLED
    try:
        if os.path.exists(AUTO_START_CONFIG_FILE):
            with open(AUTO_START_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            AUTO_START_ENABLED = bool(data.get("enabled", True))
            print(f"[AutoStart] Config loaded. Enabled={AUTO_START_ENABLED}")
    except Exception as e:
        print(f"[AutoStart] Load error: {e}")
        AUTO_START_ENABLED = True

def save_auto_start_config():
    try:
        with open(AUTO_START_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": AUTO_START_ENABLED}, f, indent=2)
        print(f"[AutoStart] Config saved. Enabled={AUTO_START_ENABLED}")
    except Exception as e:
        print(f"[AutoStart] Save error: {e}")

VOTE_ACTION_COOLDOWN = 60          # seconds after a restart/revert before another can be voted
restart_cooldown_until = 0.0       # epoch time when restart cooldown expires
revert_cooldown_until  = 0.0       # epoch time when revert cooldown expires

# ========================= OS VOTING SYSTEM =========================
OS_VOTING_CONFIG_FILE = "os_voting_config.json"
OS_VOTE_STATUS_FILE   = "os_vote_status.html"
OS_VOTE_REQUIRED      = 3
OS_VOTE_TIMEOUT       = 120
OS_VOTE_SLOTS         = 5

OS_VOTING_ENABLED = False
OS_LIST = []   # list of dicts: {"name": str, "trigger": str, "vm": str}  (max 5 entries)

os_votes            = {}   # {trigger: set(usernames)}
os_vote_start_time  = None
os_switch_in_progress = False
current_os_vm = None     # currently running OS's VM name (used as active VM_NAME target)

def load_os_voting_config():
    """Load the OS voting configuration (enabled flag + up to 5 OS entries) from disk."""
    global OS_VOTING_ENABLED, OS_LIST
    try:
        if os.path.exists(OS_VOTING_CONFIG_FILE):
            with open(OS_VOTING_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            OS_VOTING_ENABLED = bool(data.get("enabled", False))
            OS_LIST = data.get("os_list", [])[:OS_VOTE_SLOTS]
            print(f"[OSVoting] Config loaded. Enabled={OS_VOTING_ENABLED}, entries={len(OS_LIST)}")
    except Exception as e:
        print(f"[OSVoting] Load error: {e}")
        OS_VOTING_ENABLED = False
        OS_LIST = []

def save_os_voting_config():
    """Persist the OS voting configuration to disk."""
    try:
        data = {"enabled": OS_VOTING_ENABLED, "os_list": OS_LIST}
        with open(OS_VOTING_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[OSVoting] Config saved. Enabled={OS_VOTING_ENABLED}, entries={len(OS_LIST)}")
    except Exception as e:
        print(f"[OSVoting] Save error: {e}")

def get_os_trigger_map():
    """Returns {trigger_lower: os_entry} for all valid, fully-configured OS entries."""
    result = {}
    for entry in OS_LIST:
        trig = (entry.get("trigger") or "").strip().lower().lstrip("!")
        vm   = (entry.get("vm") or "").strip()
        name = (entry.get("name") or "").strip()
        if trig and vm and name:
            result[trig] = entry
    return result

def update_os_vote_status():
    """Writes the current OS voting tally to OS_VOTE_STATUS_FILE for the stream overlay."""
    trigger_map = get_os_trigger_map()
    rows = ""
    for trig, entry in trigger_map.items():
        count = len(os_votes.get(trig, set()))
        rows += (f"<div class='os-row'><span class='os-name'>{entry['name']} "
                  f"(!{trig})</span><span class='os-count'>{count}/{OS_VOTE_REQUIRED}</span></div>")
    active_name = "—"
    for entry in OS_LIST:
        if entry.get("vm") == current_os_vm:
            active_name = entry.get("name", "—")
            break
    html = f"""<html><head><style>
    body{{background:rgba(0,0,0,0);color:white;font-family:Arial;text-align:center;font-size:22px;text-shadow:2px 2px 4px #000;}}
    #c{{margin-top:20px;padding:16px;background:rgba(0,0,0,0.5);border-radius:12px;display:inline-block;min-width:260px;}}
    h1{{color:#7c5cbf;font-size:24px;margin:0 0 10px 0;}}
    .os-row{{display:flex;justify-content:space-between;gap:18px;padding:4px 0;font-size:18px;}}
    .active{{color:#3ddc97;}}
    </style></head><body><div id="c">
    <h1>OS Vote</h1>
    <p class="active">Currently running: {active_name}</p>
    {rows if rows else "<p>No OS options configured.</p>"}
    </div>
    <script>setInterval(()=>location.reload(),10000);</script></body></html>"""
    try:
        with open(OS_VOTE_STATUS_FILE, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception as e:
        print(f"[OSVoting] Status write error: {e}")

def switch_os(target_entry, announce=True):
    """Powers off the current OS VM (if different) and boots the target OS VM."""
    global current_os_vm, VM_NAME, os_switch_in_progress, os_votes, os_vote_start_time
    os_switch_in_progress = True
    try:
        target_name = target_entry.get("name", "Unknown OS")
        target_vm   = target_entry.get("vm", "")
        if not target_vm:
            print("[OSVoting] Target entry has no VM assigned, aborting switch.")
            return
        if announce:
            speak_text(f"Switching to {target_name}...")
        update_status(f"Switching to {target_name}...")
        if current_os_vm and current_os_vm != target_vm:
            try:
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', current_os_vm, 'poweroff'], check=True)
                time.sleep(3)
            except Exception as e:
                print(f"[OSVoting] Poweroff error ({current_os_vm}): {e}")
        try:
            subprocess.run([VBOXMANAGE_PATH, 'startvm', target_vm], check=True)
        except Exception as e:
            print(f"[OSVoting] Startvm error ({target_vm}): {e}")
        current_os_vm = target_vm
        VM_NAME = target_vm
        update_status(f"Running {target_name}")
        play_success_sound()
        print(f"[OSVoting] Switched to '{target_name}' ({target_vm})")
    finally:
        os_votes.clear()
        os_vote_start_time = None
        update_os_vote_status()
        os_switch_in_progress = False

def os_vote_timeout_checker():
    """Background thread: clears stale OS votes after OS_VOTE_TIMEOUT seconds of inactivity."""
    global os_votes, os_vote_start_time
    while not bot_stop_event.is_set():
        if bot_stop_event.wait(1):
            break
        if os_vote_start_time is not None:
            if time.time() - os_vote_start_time > OS_VOTE_TIMEOUT:
                os_votes.clear()
                os_vote_start_time = None
                update_os_vote_status()
                print("[OSVoting] Votes timed out")
    print("[OSVoting] Timeout checker stopped.")

COMMANDS_HELP = """
Commands (! prefix)
!restartvm / !revert  → dynamic vote required
!ban @user            → 3 votes to ban 30 min
!startvm, !modlaunch  → start VM
!restore / !focus     → bring VM to front
!move/!abs/!drag      → mouse control
!click / !rclick / !mclick / !scroll
!type / !send / !say  → keyboard text
!typeenter / !sendline
!key / !press / !combo / !chord
!keydown / !keyup
!wait / !pause        → delay
!votehelp / !clearvotes
!win7 !win8 ... → OS voting (if enabled in GUI)
"""

def speak_text(text):
    try:
        speaker = win32com.client.Dispatch("SAPI.SpVoice")
        speaker.Speak(text)
    except Exception as e:
        print(f"[Speech] Error: {e}")

def send_keyboard(text):
    try:
        subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'keyboardputstring', text], check=True)
        print(f"[KB] Typed: {text}")
    except Exception as e:
        print(f"[KB] Error: {e}")

def send_scancode(scancode_str):
    try:
        bytes_list = [scancode_str[i:i+2] for i in range(0, len(scancode_str), 2)]
        for byte in bytes_list:
            subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'keyboardputscancode', byte], check=True)
            time.sleep(0.008)
    except Exception as e:
        print(f"[Scancode] Error: {e}")

def send_special_enter():
    send_scancode('1c')
    time.sleep(0.015)
    send_scancode('9c')

def play_success_sound():
    try:
        subprocess.Popen(['start', SUCCESS_SOUND_FILE], shell=True)
    except Exception as e:
        print(f"[Sound] Error: {e}")

def start_vm():
    try:
        update_status("Starting...")
        subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
        update_status("Running")
        print("[VM] Started!")
    except Exception as e:
        update_status("VM is already running!")
        print(f"[VM] Already running: {e}")

def restore_window():
    try:
        subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'gui', 'show'], check=True)
        print("[VM] Window brought to front!")
    except:
        print("[VM] Restore: Not working in headless mode!")

def get_mouse_and_session():
    session = mgr.getSessionObject(vbox)
    machine = vbox.findMachine(VM_NAME)
    machine.lockMachine(session, 1)
    console = session.console
    mouse   = console.mouse
    return mouse, session

def unlock_session(session):
    if session.state == 1:
        session.unlockMachine(0)

def handle_mouse(cmd, args):
    try:
        mouse, session = get_mouse_and_session()
        parts   = args.split()
        buttons = 0
        if cmd in ['move', 'mouse', 'mv']:
            if len(parts) == 2:
                mouse.putMouseEvent(int(parts[0]), int(parts[1]), 0, 0, buttons)
            elif args in ['left','right','up','down']:
                dx = {'left':-20,'right':20,'up':0,'down':0}.get(args,0)
                dy = {'left':0,'right':0,'up':-20,'down':20}.get(args,0)
                mouse.putMouseEvent(dx, dy, 0, 0, buttons)
        elif cmd in ['abs', 'cursor', 'moveabs']:
            if len(parts) == 2:
                mouse.putMouseEventAbsolute(int(parts[0]), int(parts[1]), 0, 0, buttons)
        elif cmd in ['click', 'lclick']:
            count = int(args) if args.isdigit() else 1
            for _ in range(count):
                mouse.putMouseEvent(0,0,0,0,1)
                mouse.putMouseEvent(0,0,0,0,0)
        elif cmd in ['rclick', 'rightclick']:
            count = int(args) if args.isdigit() else 1
            for _ in range(count):
                mouse.putMouseEvent(0,0,0,0,2)
        elif cmd in ['mclick', 'middleclick']:
            count = int(args) if args.isdigit() else 1
            for _ in range(count):
                mouse.putMouseEvent(0,0,0,0,4)
        elif cmd in ['drag', 'dragrel']:
            if len(parts) >= 2:
                button = 1 if len(parts)==2 else (1 if parts[0]=='left' else 2 if parts[0]=='right' else 4)
                dx, dy = int(parts[-2]), int(parts[-1])
                mouse.putMouseEvent(0,0,0,0,button)
                mouse.putMouseEvent(dx,dy,0,0,button)
                mouse.putMouseEvent(0,0,0,0,0)
        elif cmd in ['dragabs', 'drag_absolute']:
            if len(parts) >= 2:
                button = 1 if len(parts)==2 else (1 if parts[0]=='left' else 2 if parts[0]=='right' else 4)
                x, y = int(parts[-2]), int(parts[-1])
                mouse.putMouseEventAbsolute(x,y,0,0,button)
                mouse.putMouseEventAbsolute(x,y,0,0,0)
        elif cmd in ['scroll', 'wheel']:
            dz = int(args) if args else 0
            mouse.putMouseEvent(0,0,dz,0,0)
        unlock_session(session)
        print(f"[Mouse] {cmd} {args}")
    except Exception as e:
        print(f"[Mouse] Error: {e}")

def update_ban_vote_display(target, current_votes, required, remaining_time=None):
    action_text   = f"Ban @{target}" if target else "Empty"
    remaining_str = f"Remaining time: {int(remaining_time)} s" if remaining_time is not None else ""
    html = f"""<html><head><style>
    body{{background:rgba(0,0,0,0);color:white;font-family:Arial;text-align:center;font-size:28px;text-shadow:2px 2px 4px #000;}}
    #c{{margin-top:40px;padding:20px;background:rgba(0,0,0,0.5);border-radius:12px;display:inline-block;}}
    h1{{color:#ff4444;}} .progress{{width:80%;height:25px;background:rgba(255,255,255,0.2);border-radius:12px;margin:15px auto;overflow:hidden;}}
    .bar{{height:100%;width:{int((current_votes/required)*100)}%;background:#ff4444;transition:width 0.5s;}}
    </style></head><body><div id="c"><h1>Ban Vote</h1>
    <p>{action_text}</p><p>{current_votes}/{required}</p><p>{remaining_str}</p>
    <div class="progress"><div class="bar"></div></div></div>
    <script>setInterval(()=>location.reload(),10000);</script></body></html>"""
    with open(VOTE_FILE_BAN, "w", encoding="utf-8") as f: f.write(html)

def update_status(message):
    html = f"""<html><head><style>
    body{{background:rgba(0,0,0,0);color:white;font-family:Arial;font-size:32px;text-align:center;text-shadow:2px 2px 4px #000;}}
    #s{{margin-top:20px;padding:10px;background:rgba(0,0,0,0.4);border-radius:8px;display:inline-block;}}
    </style></head><body><div id="s">Status: {message}</div>
    <script>setInterval(()=>location.reload(),10000);</script></body></html>"""
    with open(STATUS_FILE, "w", encoding="utf-8") as f: f.write(html)
    print(f"[Status] {message}")

def vote_timeout_checker():
    global vote_restart, vote_revert, ban_votes, restart_start_time, revert_start_time
    while not bot_stop_event.is_set():
        if bot_stop_event.wait(1):
            break
        current_time = time.time()

        # Restart: update remaining_time every second so overlay stays in sync
        if restart_start_time is not None:
            elapsed = current_time - restart_start_time
            if elapsed > VOTE_TIMEOUT:
                vote_restart.clear(); restart_start_time = None
                update_votes_json("restartvm", 0, 2, 0)
                print("[Vote] Restart votes timed out")
            else:
                remaining = max(0, VOTE_TIMEOUT - elapsed)
                update_votes_json("restartvm", len(vote_restart), _votes_state["restartvm"]["required"], remaining)

        # Revert: same live update
        if revert_start_time is not None:
            elapsed = current_time - revert_start_time
            if elapsed > VOTE_TIMEOUT:
                vote_revert.clear(); revert_start_time = None
                update_votes_json("revert", 0, 2, 0)
                print("[Vote] Revert votes timed out")
            else:
                remaining = max(0, VOTE_TIMEOUT - elapsed)
                update_votes_json("revert", len(vote_revert), _votes_state["revert"]["required"], remaining)

        to_remove = [t for t, d in ban_votes.items()
                     if 'start_time' in d and current_time - d['start_time'] > VOTE_TIMEOUT]
        for t in to_remove:
            del ban_votes[t]
            update_ban_vote_display(None, 0, 3)
            print(f"[Vote] Ban vote timed out: {t}")
    print("[Vote] Timeout checker stopped.")

def watchdog_restart():
    global revert_in_progress
    while not bot_stop_event.is_set():
        try:
            if not AUTO_START_ENABLED:
                if bot_stop_event.wait(10):
                    break
                continue
            result = subprocess.run([VBOXMANAGE_PATH, 'showvminfo', VM_NAME, '--machinereadable'],
                                    capture_output=True, text=True)
            lines = [l for l in result.stdout.splitlines() if l.startswith('VMState="')]
            if lines:
                vm_state = lines[0].split('=')[1].strip('"')
                if vm_state in ["poweroff", "aborted", "gurumeditation"]:
                    if revert_in_progress or os_switch_in_progress:
                        print("[Watchdog] Revert/OS-switch in progress, ignoring down state.")
                    else:
                        print(f"[Watchdog] VM down ({vm_state}). Auto-restarting...")
                        update_status("Auto-starting...")
                        speak_text("Auto starting virtual machine...")
                        subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
                        update_status("Running")
                        speak_text("Running")
        except Exception as e:
            print(f"[Watchdog] Error: {e}")
        if bot_stop_event.wait(10):
            break
    print("[Watchdog] Stopped.")

class YouTubeChatBot:
    def __init__(self):
        self.video_id = VIDEO_ID
        self.chat = None
        self.reconnect()
        update_overlay()
        threading.Thread(target=start_overlay_server, daemon=True).start()
        if not self.chat or not self.chat.is_alive():
            print("[Bot] Could not connect to YouTube live chat!")
            return
        print("[Bot] Connected to YouTube chat!")
        print(COMMANDS_HELP)
        self.last_start_time = 0
        threading.Thread(target=vote_timeout_checker, daemon=True).start()
        threading.Thread(target=watchdog_restart, daemon=True).start()
        threading.Thread(target=os_vote_timeout_checker, daemon=True).start()
        if OS_VOTING_ENABLED:
            update_os_vote_status()
       # threading.Thread(target=fetch_youtube_stats, daemon=True).start()

    def reconnect(self):
        print("[Bot] Reconnecting to YouTube chat...")
        if self.chat:
            try: self.chat.terminate()
            except: pass
        try:
            self.chat = pytchat.create(video_id=self.video_id)
            print("[Bot] Reconnect successful.")
            return True
        except Exception as e:
            print(f"[Bot] Reconnect failed: {e}")
            return False

    def run(self):
        global restart_start_time, revert_start_time, revert_in_progress, restart_in_progress, restart_cooldown_until, revert_cooldown_until, os_vote_start_time
        last_reconnect   = time.time()
        RECONNECT_INTERVAL = 150
        print("[Bot] Waiting for chat messages...")
        while not bot_stop_event.is_set():
            if time.time() - last_reconnect > RECONNECT_INTERVAL:
                print("[Bot] Periodic reconnect...")
                self.reconnect()
                last_reconnect = time.time()
            if not self.chat or not self.chat.is_alive():
                self.reconnect()
                if bot_stop_event.wait(5):
                    break
                continue
            try:
                for c in self.chat.get().sync_items():
                    if bot_stop_event.is_set():
                        break
                    msg      = c.message.strip()
                    user     = c.author.name.strip().lower()
                    is_owner = getattr(c.author, 'isChatOwner', False)
                    update_overlay(author=user, message=msg, msg_id=c.id)
                    if user in banned_users:
                        if time.time() < banned_users[user]: continue
                        else: del banned_users[user]
                    active_users.add(c.author.name.strip())
                    print(f"[Chat] [{user}]: {msg}")

                    if msg.startswith('!'):
                        chain_parts = [p.strip() for p in msg.split('!') if p.strip()]
                        for part in chain_parts:
                            sub_parts = part.split(maxsplit=1)
                            cmd  = sub_parts[0].lower()
                            args = sub_parts[1] if len(sub_parts) > 1 else ""

                            # ── Custom command check (first priority) ──
                            trigger = "!" + cmd
                            if trigger in custom_commands:
                                threading.Thread(
                                    target=execute_custom_command,
                                    args=(trigger,), daemon=True
                                ).start()
                                continue

                            # ── OS voting commands (e.g. !win7, !win10) ──
                            if OS_VOTING_ENABLED:
                                os_trigger_map = get_os_trigger_map()
                                if cmd in os_trigger_map:
                                    if os_switch_in_progress:
                                        continue
                                    target_entry = os_trigger_map[cmd]
                                    # Owner bypass: switch immediately, no vote needed
                                    if is_owner:
                                        print(f"[OSVoting] Switch bypassed by owner: {user} → {target_entry['name']}")
                                        threading.Thread(target=switch_os, args=(target_entry,), daemon=True).start()
                                        continue
                                    if target_entry.get("vm") == current_os_vm:
                                        continue  # already running, no point voting for it
                                    if not os_votes:
                                        os_vote_start_time = time.time()
                                    voters = os_votes.setdefault(cmd, set())
                                    if user in voters:
                                        continue
                                    voters.add(user)
                                    update_os_vote_status()
                                    print(f"[OSVoting] Vote for '{target_entry['name']}': {len(voters)}/{OS_VOTE_REQUIRED}")
                                    if len(voters) >= OS_VOTE_REQUIRED:
                                        print(f"[OSVoting] Threshold reached → switching to {target_entry['name']}")
                                        threading.Thread(target=switch_os, args=(target_entry,), daemon=True).start()
                                    continue

                            # ── Built-in commands ──
                            if cmd in ['wait', 'pause', 'delay']:
                                try:
                                    delay = float(args)
                                    delay = max(0, min(delay, 5.0))
                                    time.sleep(delay)
                                except: pass
                                continue

                            if cmd in ['type', 'text', 'say']:
                                send_keyboard(args)
                            elif cmd in ['typeenter', 'send', 'sendline']:
                                send_keyboard(args)
                                send_special_enter()
                            elif cmd == 'enter':
                                send_special_enter()
                            elif cmd in ['fullscreen', 'fs']:
                                print("[Bot] Fullscreen hint (manual)")
                            elif cmd in ['move','mouse','mv','abs','cursor','moveabs',
                                         'drag','dragrel','dragabs','drag_absolute',
                                         'click','lclick','rclick','rightclick',
                                         'mclick','middleclick','scroll','wheel']:
                                handle_mouse(cmd, args)
                            elif cmd in ['startvm','modlaunch','launchvm','start_mc','startmc']:
                                if time.time() - self.last_start_time > COOLDOWN_START:
                                    start_vm()
                                    self.last_start_time = time.time()
                                else:
                                    print("[Bot] !startvm cooldown active")
                            elif cmd in ['restore','refresh','restore_window','focus','front','bringtofront']:
                                restore_window()
                            elif cmd in ['key', 'press']:
                                k = args.lower().strip()
                                if k in SCANCODES:
                                    send_scancode(SCANCODES[k][0])
                                    time.sleep(0.01)
                                    send_scancode(SCANCODES[k][1])
                                else:
                                    send_keyboard(k)
                            elif cmd in ['keydown', 'hold']:
                                k = args.lower().strip()
                                if k in SCANCODES: send_scancode(SCANCODES[k][0])
                            elif cmd in ['keyup', 'release']:
                                k = args.lower().strip()
                                if k in SCANCODES: send_scancode(SCANCODES[k][1])
                            elif cmd in ['combo','chord','multi']:
                                keys = args.lower().replace('+',' ').split()
                                if keys: send_combo(keys)
                                else: send_keyboard(args)
                            elif cmd == 'run':
                                send_combo(['win','r'])
                            elif cmd == 'votehelp':
                                update_status("Commands in description!")
                            elif cmd == 'clearvotes':
                                if user == ADMIN_USERNAME.lower():
                                    vote_restart.clear(); vote_revert.clear(); ban_votes.clear()
                                    restart_start_time = None; revert_start_time = None
                                    update_votes_json("restartvm", 0, 2, 0)
                                    update_votes_json("revert",    0, 2, 0)
                                    update_ban_vote_display(None,0,3)
                                    os_votes.clear(); os_vote_start_time = None
                                    update_os_vote_status()
                                    speak_text("Votes cleared by admin!")
                                    print("[Admin] Votes cleared")

                            # Vote logic
                            active_count   = max(1, len(active_users))
                            required_votes = 2
                            current_time   = time.time()

                            if cmd in ['restart','restartvm']:
                                if restart_in_progress: continue
                                if current_time < restart_cooldown_until:
                                    remaining_cd = int(restart_cooldown_until - current_time)
                                    print(f"[Vote] Restart on cooldown ({remaining_cd}s left)")
                                    continue
                                # Owner bypass: skip vote, execute immediately
                                if is_owner:
                                    print(f"[Vote] Restart bypassed by owner: {user}")
                                    speak_text("Restarting Virtual Machine...")
                                    vote_restart.clear(); restart_start_time=None; active_users.clear()
                                    restart_in_progress = True
                                    update_status("Restarting...")
                                    update_votes_json("restartvm", required_votes, required_votes, 0)
                                    subprocess.run([VBOXMANAGE_PATH,'controlvm',VM_NAME,'reset'], check=True)
                                    restart_cooldown_until = time.time() + VOTE_ACTION_COOLDOWN
                                    update_status("Running"); play_success_sound()
                                    update_votes_json("restartvm", 0, required_votes, 0)
                                    restart_in_progress = False
                                    continue
                                if not vote_restart: restart_start_time = current_time
                                if user in vote_restart: continue
                                vote_restart[user] = current_time
                                current   = len(vote_restart)
                                remaining = max(0, VOTE_TIMEOUT-(current_time-restart_start_time)) if restart_start_time else 0
                                update_votes_json("restartvm", current, required_votes, remaining)
                                if current >= required_votes:
                                    print("[Vote] Restart threshold reached!")
                                    speak_text("Restarting Virtual Machine...")
                                    vote_restart.clear(); restart_start_time=None; active_users.clear()
                                    restart_in_progress = True
                                    update_status("Restarting...")
                                    subprocess.run([VBOXMANAGE_PATH,'controlvm',VM_NAME,'reset'], check=True)
                                    restart_cooldown_until = time.time() + VOTE_ACTION_COOLDOWN
                                    update_status("Running"); play_success_sound()
                                    update_votes_json("restartvm", 0, required_votes, 0)
                                    restart_in_progress = False

                            elif cmd == 'revert':
                                if revert_in_progress: continue
                                if current_time < revert_cooldown_until:
                                    remaining_cd = int(revert_cooldown_until - current_time)
                                    print(f"[Vote] Revert on cooldown ({remaining_cd}s left)")
                                    continue
                                # Owner bypass: skip vote, execute immediately
                                if is_owner:
                                    print(f"[Vote] Revert bypassed by owner: {user}")
                                    speak_text("Reverting Virtual Machine...")
                                    vote_revert.clear(); revert_start_time=None; active_users.clear()
                                    revert_in_progress = True
                                    update_status("Reverting...")
                                    update_votes_json("revert", required_votes, required_votes, 0)
                                    subprocess.run([VBOXMANAGE_PATH,'controlvm',VM_NAME,'poweroff'], check=True)
                                    time.sleep(3)
                                    subprocess.run([VBOXMANAGE_PATH,'snapshot',VM_NAME,'restorecurrent'], check=True)
                                    time.sleep(3)
                                    subprocess.run([VBOXMANAGE_PATH,'startvm',VM_NAME], check=True)
                                    revert_cooldown_until = time.time() + VOTE_ACTION_COOLDOWN
                                    update_status("Running"); play_success_sound()
                                    update_votes_json("revert", 0, required_votes, 0)
                                    revert_in_progress = False
                                    continue
                                if not vote_revert: revert_start_time = current_time
                                if user in vote_revert: continue
                                vote_revert[user] = current_time
                                current   = len(vote_revert)
                                remaining = max(0, VOTE_TIMEOUT-(current_time-revert_start_time)) if revert_start_time else 0
                                update_votes_json("revert", current, required_votes, remaining)
                                if current >= required_votes:
                                    print("[Vote] Revert threshold reached!")
                                    speak_text("Reverting Virtual Machine...")
                                    vote_revert.clear(); revert_start_time=None; active_users.clear()
                                    revert_in_progress = True
                                    update_status("Reverting...")
                                    subprocess.run([VBOXMANAGE_PATH,'controlvm',VM_NAME,'poweroff'], check=True)
                                    time.sleep(3)
                                    subprocess.run([VBOXMANAGE_PATH,'snapshot',VM_NAME,'restorecurrent'], check=True)
                                    time.sleep(3)
                                    subprocess.run([VBOXMANAGE_PATH,'startvm',VM_NAME], check=True)
                                    revert_cooldown_until = time.time() + VOTE_ACTION_COOLDOWN
                                    update_status("Running"); play_success_sound()
                                    update_votes_json("revert", 0, required_votes, 0)
                                    revert_in_progress = False

                            elif cmd == 'ban':
                                if not args.startswith('@'): continue
                                target_raw = args[1:].split()[0].strip()
                                target     = target_raw.lower()
                                active_clean = {t.strip().lstrip('@').lower() for t in active_users}
                                if target not in active_clean: continue
                                if target not in ban_votes:
                                    ban_votes[target] = {'voters': set(), 'start_time': current_time}
                                if user in ban_votes[target]['voters']: continue
                                ban_votes[target]['voters'].add(user)
                                cbv       = len(ban_votes[target]['voters'])
                                remaining = max(0, VOTE_TIMEOUT-(current_time-ban_votes[target]['start_time']))
                                update_ban_vote_display(target_raw, cbv, 3, remaining)
                                if cbv >= 3:
                                    banned_users[target] = time.time() + BAN_DURATION
                                    update_status(f"@{target_raw} banned 30 min!")
                                    speak_text(f"Banned {target_raw} for 30 minutes.")
                                    play_success_sound()
                                    del ban_votes[target]
                                    update_ban_vote_display(None, 0, 3)

            except Exception as e:
                if bot_stop_event.is_set():
                    break
                err = str(e).lower()
                if "timeout" in err or "timed out" in err:
                    print("[Bot] Timeout → reconnecting...")
                else:
                    print(f"[Bot] Error: {e} → reconnecting...")
                self.reconnect()
                if bot_stop_event.wait(5):
                    break
            if bot_stop_event.wait(0.05):
                break

        # Clean shutdown
        if self.chat:
            try: self.chat.terminate()
            except: pass
        print("[Bot] Stopped.")


# ========================= STDOUT REDIRECT =========================
class ConsoleRedirect:
    """Redirects stdout/stderr to a Tkinter ScrolledText widget."""
    def __init__(self, widget):
        self.widget = widget
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr

    def write(self, msg):
        self._orig_stdout.write(msg)
        try:
            self.widget.configure(state='normal')
            ts = time.strftime("%H:%M:%S")
            self.widget.insert('end', f"[{ts}] {msg}")
            self.widget.see('end')
            self.widget.configure(state='disabled')
        except: pass

    def flush(self): pass

    def start(self):
        sys.stdout = self
        sys.stderr = self

    def stop(self):
        sys.stdout = self._orig_stdout
        sys.stderr = self._orig_stderr


# ========================= GUI =========================
class UltraBotGUI:
    # ── Color palette ──
    BG       = "#0f0f1a"
    BG2      = "#16162a"
    BG3      = "#1e1e35"
    ACCENT   = "#7c5cbf"
    ACCENT2  = "#a07cdf"
    GREEN    = "#3ddc97"
    RED      = "#e05c7a"
    YELLOW   = "#f0c060"
    TEXT     = "#e8e8f0"
    TEXTDIM  = "#8888aa"
    CONSOLE  = "#0a0a14"
    CONTEXT  = "#00e676"
    BORDER   = "#2d2d50"

    def __init__(self, root):
        self.root = root
        self.root.title("🤖 UltraBot Control Panel")
        self.root.geometry("900x680")
        self.root.minsize(760, 560)
        self.root.configure(bg=self.BG)
        self.root.resizable(True, True)

        self._bot_thread   = None
        self._bot_running  = False
        self._bot_instance = None
        self._console_redir = None

        # Edit state for Command Builder
        self._editing_cmd  = None   # trigger key being edited
        self._step_items   = []     # list of {"action":..,"args":..} dicts

        self._build_styles()
        load_os_voting_config()
        load_auto_start_config()
        self._build_ui()
        load_custom_commands()
        self._refresh_cmd_list()

    # ── TTK Styles ──
    def _build_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".",
            background=self.BG, foreground=self.TEXT,
            fieldbackground=self.BG2, bordercolor=self.BORDER,
            troughcolor=self.BG2, selectbackground=self.ACCENT,
            selectforeground=self.TEXT, font=("Segoe UI", 10))
        style.configure("TNotebook",
            background=self.BG, tabmargins=[2, 4, 0, 0])
        style.configure("TNotebook.Tab",
            background=self.BG2, foreground=self.TEXTDIM,
            padding=[16, 6], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
            background=[("selected", self.BG3)],
            foreground=[("selected", self.TEXT)])
        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.BG2)
        style.configure("TLabel",  background=self.BG,  foreground=self.TEXT)
        style.configure("Dim.TLabel", background=self.BG2, foreground=self.TEXTDIM)
        style.configure("TEntry",
            fieldbackground=self.BG3, foreground=self.TEXT,
            insertcolor=self.TEXT, bordercolor=self.BORDER, relief="flat")
        style.configure("TCombobox",
            fieldbackground=self.BG3, foreground=self.TEXT,
            selectbackground=self.ACCENT, arrowcolor=self.ACCENT2)
        style.map("TCombobox", fieldbackground=[("readonly", self.BG3)])
        # Buttons
        for name, bg, fg in [
            ("Green.TButton",  self.GREEN,  "#000"),
            ("Red.TButton",    self.RED,    "#fff"),
            ("Accent.TButton", self.ACCENT, "#fff"),
            ("Dim.TButton",    self.BG3,    self.TEXT),
        ]:
            style.configure(name, background=bg, foreground=fg,
                            font=("Segoe UI", 10, "bold"), relief="flat", padding=[10,5])
            style.map(name, background=[("active", self.ACCENT2)])
        style.configure("TScrollbar",
            background=self.BG3, troughcolor=self.BG,
            arrowcolor=self.ACCENT2, bordercolor=self.BG)

    # ── Main UI ──
    def _build_ui(self):
        # Title bar
        title_bar = tk.Frame(self.root, bg=self.BG2, height=48)
        title_bar.pack(fill="x", side="top")
        title_bar.pack_propagate(False)
        tk.Label(title_bar, text="🤖  UltraBot Control Panel",
                 bg=self.BG2, fg=self.TEXT,
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=16, pady=8)
        self._status_dot = tk.Label(title_bar, text="⬤  Stopped",
                                    bg=self.BG2, fg=self.RED,
                                    font=("Segoe UI", 10, "bold"))
        self._status_dot.pack(side="right", padx=16)

        # Notebook
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        tab1 = ttk.Frame(nb)
        tab2 = ttk.Frame(nb)
        tab3 = ttk.Frame(nb)
        tab4 = ttk.Frame(nb)
        nb.add(tab1, text="  ▶  Main  ")
        nb.add(tab2, text="  ⚙  Command Builder  ")
        nb.add(tab3, text="  🖥  VM Controls  ")
        nb.add(tab4, text="  🗳  OS Voting  ")

        self._build_main_tab(tab1)
        self._build_cmd_builder_tab(tab2)
        self._build_vm_controls_tab(tab3)
        self._build_os_voting_tab(tab4)
        self._sync_main_vm_lock()

    # ──────────────── TAB 1 : MAIN ────────────────
    def _build_main_tab(self, parent):
        parent.configure(style="TFrame")

        # Config card
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        card.pack(fill="x", padx=12, pady=(12,6))

        # YouTube ID
        tk.Label(card, text="YouTube Video ID", bg=self.BG2,
                 fg=self.TEXTDIM, font=("Segoe UI",9,"bold")).grid(
                 row=0, column=0, sticky="w", padx=(0,8))
        self._yt_var = tk.StringVar()
        yt_entry = ttk.Entry(card, textvariable=self._yt_var, width=32,
                             font=("Segoe UI Mono", 10))
        yt_entry.grid(row=0, column=1, sticky="ew", padx=(0,12), ipady=4)
        tk.Label(card, text="🔗", bg=self.BG2, fg=self.ACCENT2,
                 font=("Segoe UI",12)).grid(row=0, column=2, padx=2)

        # VM selector
        tk.Label(card, text="VirtualBox VM", bg=self.BG2,
                 fg=self.TEXTDIM, font=("Segoe UI",9,"bold")).grid(
                 row=1, column=0, sticky="w", padx=(0,8), pady=(10,0))
        self._vm_var = tk.StringVar()
        self._vm_combo = ttk.Combobox(card, textvariable=self._vm_var,
                                      state="readonly", width=30,
                                      font=("Segoe UI",10))
        self._vm_combo.grid(row=1, column=1, sticky="ew", padx=(0,12),
                            pady=(10,0), ipady=3)
        ttk.Button(card, text="🔄 Refresh", style="Dim.TButton",
                   command=self._refresh_vm_list).grid(
                   row=1, column=2, pady=(10,0))
        self._vm_select_note = tk.Label(card, text="", bg=self.BG2,
                 fg=self.YELLOW, font=("Segoe UI", 8, "italic"))
        self._vm_select_note.grid(row=2, column=0, columnspan=3, sticky="w", pady=(2,0))

        # Auto-start watchdog toggle
        tk.Label(card, text="Auto-Start Watchdog", bg=self.BG2,
                 fg=self.TEXTDIM, font=("Segoe UI",9,"bold")).grid(
                 row=3, column=0, sticky="w", padx=(0,8), pady=(10,0))
        self._auto_start_var = tk.BooleanVar(value=AUTO_START_ENABLED)
        auto_chk = tk.Checkbutton(card,
            text="Auto-restart the VM if it's found powered off",
            variable=self._auto_start_var, bg=self.BG2, fg=self.TEXT,
            selectcolor=self.BG3, activebackground=self.BG2,
            activeforeground=self.TEXT, font=("Segoe UI", 9),
            command=self._on_auto_start_toggle)
        auto_chk.grid(row=3, column=1, columnspan=2, sticky="w", pady=(10,0))

        card.columnconfigure(1, weight=1)

        # Start / Stop buttons
        btn_frame = tk.Frame(parent, bg=self.BG)
        btn_frame.pack(fill="x", padx=12, pady=6)
        ttk.Button(btn_frame, text="▶  Start Bot", style="Green.TButton",
                   command=self._start_bot).pack(side="left", padx=(0,8))
        ttk.Button(btn_frame, text="⏹  Stop Bot", style="Red.TButton",
                   command=self._stop_bot).pack(side="left")

        # Console label
        tk.Label(parent, text="Console Output",
                 bg=self.BG, fg=self.TEXTDIM,
                 font=("Segoe UI",9,"bold")).pack(
                 anchor="w", padx=16, pady=(4,0))

        # Console
        console_frame = tk.Frame(parent, bg=self.BORDER, bd=1)
        console_frame.pack(fill="both", expand=True, padx=12, pady=(2,6))
        self._console = scrolledtext.ScrolledText(
            console_frame,
            bg=self.CONSOLE, fg=self.CONTEXT,
            font=("Cascadia Code", 9) if self._font_exists("Cascadia Code")
                 else ("Consolas", 9),
            insertbackground=self.CONTEXT,
            selectbackground=self.ACCENT,
            relief="flat", bd=0, state='disabled',
            wrap='word'
        )
        self._console.pack(fill="both", expand=True, padx=1, pady=1)

        # Admin command bar
        admin_frame = tk.Frame(parent, bg=self.BG2, pady=6)
        admin_frame.pack(fill="x", padx=12, pady=(0,8))
        tk.Label(admin_frame, text="Admin CMD:",
                 bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI",9,"bold")).pack(side="left", padx=(8,6))
        self._admin_var = tk.StringVar()
        admin_entry = ttk.Entry(admin_frame, textvariable=self._admin_var,
                                width=36, font=("Segoe UI Mono",10))
        admin_entry.pack(side="left", padx=(0,8), ipady=4)
        admin_entry.bind("<Return>", lambda e: self._send_admin_cmd())
        ttk.Button(admin_frame, text="Send ↵", style="Accent.TButton",
                   command=self._send_admin_cmd).pack(side="left")

        # Initial VM list load
        self._refresh_vm_list()

    # ──────────────── TAB 2 : COMMAND BUILDER ────────────────
    def _build_cmd_builder_tab(self, parent):
        parent.configure(style="TFrame")

        pane = tk.PanedWindow(parent, orient="horizontal",
                              bg=self.BG, sashwidth=6,
                              sashrelief="flat", bd=0)
        pane.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Left panel: command list ──
        left = ttk.Frame(pane, style="Card.TFrame", padding=8)
        pane.add(left, minsize=180, width=220)

        tk.Label(left, text="Custom Commands",
                 bg=self.BG2, fg=self.ACCENT2,
                 font=("Segoe UI",10,"bold")).pack(anchor="w", pady=(0,6))

        list_frame = tk.Frame(left, bg=self.BG3, highlightbackground=self.BORDER,
                              highlightthickness=1)
        list_frame.pack(fill="both", expand=True)
        self._cmd_listbox = tk.Listbox(
            list_frame,
            bg=self.BG3, fg=self.TEXT,
            selectbackground=self.ACCENT, selectforeground="#fff",
            activestyle="none", font=("Segoe UI Mono",10),
            relief="flat", bd=0, exportselection=False
        )
        self._cmd_listbox.pack(fill="both", expand=True)
        self._cmd_listbox.bind("<<ListboxSelect>>", self._on_cmd_select)

        btn_row = tk.Frame(left, bg=self.BG2)
        btn_row.pack(fill="x", pady=(6,0))
        ttk.Button(btn_row, text="＋ New", style="Green.TButton",
                   command=self._new_cmd).pack(side="left", expand=True, fill="x", padx=(0,4))
        ttk.Button(btn_row, text="🗑 Del", style="Red.TButton",
                   command=self._delete_cmd).pack(side="left", expand=True, fill="x")

        # ── Right panel: editor ──
        right = ttk.Frame(pane, style="Card.TFrame", padding=10)
        pane.add(right, minsize=300)

        # Trigger name row
        trig_row = tk.Frame(right, bg=self.BG2)
        trig_row.pack(fill="x", pady=(0,10))
        tk.Label(trig_row, text="Trigger:", bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI",9,"bold")).pack(side="left", padx=(0,8))
        self._trig_var = tk.StringVar()
        ttk.Entry(trig_row, textvariable=self._trig_var,
                  font=("Segoe UI Mono",11), width=18).pack(side="left", ipady=4)
        tk.Label(trig_row, text="(e.g. !bubbles)",
                 bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI",9)).pack(side="left", padx=8)

        # ── Chain Input ──
        chain_card = tk.Frame(right, bg=self.BG3, pady=8, padx=10)
        chain_card.pack(fill="x", pady=(0,10))

        hdr_row = tk.Frame(chain_card, bg=self.BG3)
        hdr_row.pack(fill="x", pady=(0,4))
        tk.Label(hdr_row, text="⚡ Quick Chain Input",
                 bg=self.BG3, fg=self.ACCENT2,
                 font=("Segoe UI",9,"bold")).pack(side="left")
        tk.Label(hdr_row,
                 text="  Write in chat syntax → parse into steps",
                 bg=self.BG3, fg=self.TEXTDIM,
                 font=("Segoe UI",8)).pack(side="left")

        chain_entry_row = tk.Frame(chain_card, bg=self.BG3)
        chain_entry_row.pack(fill="x")
        self._chain_var = tk.StringVar()
        chain_entry = ttk.Entry(chain_entry_row, textvariable=self._chain_var,
                                font=("Segoe UI Mono", 10))
        chain_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0,8))
        chain_entry.bind("<Return>", lambda e: self._parse_chain_input())
        ttk.Button(chain_entry_row, text="⇨ Parse Steps",
                   style="Accent.TButton",
                   command=self._parse_chain_input).pack(side="left")

        tk.Label(chain_card,
                 text='Example: !combo win+r !send cmd.exe',
                 bg=self.BG3, fg=self.TEXTDIM,
                 font=("Segoe UI",8), wraplength=440, justify="left"
                 ).pack(anchor="w", pady=(4,0))

        # ── Steps header ──
        steps_hdr = tk.Frame(right, bg=self.BG2)
        steps_hdr.pack(fill="x", pady=(0,4))
        tk.Label(steps_hdr, text="Steps",
                 bg=self.BG2, fg=self.ACCENT2,
                 font=("Segoe UI",10,"bold")).pack(side="left")
        tk.Label(steps_hdr,
                 text="  (Fill via Parse or add manually below)",
                 bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI",8)).pack(side="left")

        # Steps list (Treeview)
        tree_frame = tk.Frame(right, bg=self.BORDER, bd=1)
        tree_frame.pack(fill="both", expand=True, pady=(0,6))

        cols = ("action", "args")
        self._step_tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            height=8, selectmode="browse"
        )
        self._step_tree.heading("action", text="Action")
        self._step_tree.heading("args",   text="Arguments")
        self._step_tree.column("action",  width=120, minwidth=90)
        self._step_tree.column("args",    width=240, minwidth=120)
        self._step_tree.pack(fill="both", expand=True, side="left")

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                                    command=self._step_tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self._step_tree.configure(yscrollcommand=tree_scroll.set)

        # Step reorder/delete buttons
        step_btn_row = tk.Frame(right, bg=self.BG2)
        step_btn_row.pack(fill="x", pady=(0,8))
        for txt, cmd in [("▲ Up","_step_up"), ("▼ Down","_step_down"),
                         ("✕ Remove","_step_remove")]:
            ttk.Button(step_btn_row, text=txt, style="Dim.TButton",
                       command=lambda c=cmd: getattr(self, c)()
                       ).pack(side="left", padx=(0,4))

        # Add step row
        add_frame = tk.Frame(right, bg=self.BG3, pady=8, padx=8)
        add_frame.pack(fill="x", pady=(0,8))
        tk.Label(add_frame, text="Add Step:", bg=self.BG3, fg=self.TEXTDIM,
                 font=("Segoe UI",9,"bold")).pack(side="left", padx=(0,8))

        ACTIONS = ["combo","send","sendenter","key","keydown","keyup",
                   "wait","click","rclick","move","abs","scroll"]
        self._action_var = tk.StringVar(value="combo")
        action_cb = ttk.Combobox(add_frame, textvariable=self._action_var,
                                  values=ACTIONS, state="readonly", width=12)
        action_cb.pack(side="left", padx=(0,8), ipady=3)

        tk.Label(add_frame, text="Args:", bg=self.BG3, fg=self.TEXTDIM,
                 font=("Segoe UI",9)).pack(side="left", padx=(0,4))
        self._args_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self._args_var, width=20,
                  font=("Segoe UI Mono",10)).pack(side="left", padx=(0,8), ipady=3)
        ttk.Button(add_frame, text="＋ Add Step", style="Accent.TButton",
                   command=self._add_step).pack(side="left")

        # Hint label
        hint = ("combo: win+r  |  send: notepad.exe  |  wait: 500 (ms)  |  "
                "sendenter: hello  |  key: enter  |  click / rclick")
        tk.Label(right, text=hint, bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI",8), wraplength=420, justify="left"
                 ).pack(anchor="w", pady=(0,6))

        # Save / Test buttons
        save_row = tk.Frame(right, bg=self.BG2)
        save_row.pack(fill="x")
        ttk.Button(save_row, text="💾  Save Command", style="Green.TButton",
                   command=self._save_cmd).pack(side="left", padx=(0,8))
        ttk.Button(save_row, text="▶  Test Now", style="Accent.TButton",
                   command=self._test_cmd).pack(side="left")

    # ──────────────── TAB 3 : VM CONTROLS ────────────────
    def _build_vm_controls_tab(self, parent):
        parent.configure(style="TFrame")

        # Header
        tk.Label(parent, text="Virtual Machine Controls",
                 bg=self.BG, fg=self.ACCENT2,
                 font=("Segoe UI", 13, "bold")).pack(pady=(24, 4))
        tk.Label(parent,
                 text="Direct admin actions — no vote required.",
                 bg=self.BG, fg=self.TEXTDIM,
                 font=("Segoe UI", 9)).pack(pady=(0, 28))

        # Button grid card
        grid_card = ttk.Frame(parent, style="Card.TFrame", padding=28)
        grid_card.pack(padx=60, pady=0, fill="x")

        btn_cfg = [
            # (label, icon, color_style, description, method)
            ("Start VM",    "▶",  "Green.TButton",
             "Power on the virtual machine.",     self._vm_start),
            ("Restart VM",  "🔄", "Accent.TButton",
             "Send a reset signal to the VM.",    self._vm_restart),
            ("Revert VM",   "⏮",  "Accent.TButton",
             "Power off, restore snapshot, boot.", self._vm_revert),
            ("Shutdown VM", "⏹",  "Red.TButton",
             "Force power off the virtual machine.", self._vm_shutdown),
        ]

        for i, (label, icon, style, desc, cmd) in enumerate(btn_cfg):
            row = i // 2
            col = i % 2

            cell = tk.Frame(grid_card, bg=self.BG2, padx=16, pady=16)
            cell.grid(row=row, column=col, padx=12, pady=12, sticky="nsew")
            grid_card.columnconfigure(col, weight=1)

            # Icon + label
            btn_inner = tk.Frame(cell, bg=self.BG2)
            btn_inner.pack()
            tk.Label(btn_inner, text=icon,
                     bg=self.BG2, fg=self.TEXT,
                     font=("Segoe UI", 22)).pack()
            ttk.Button(btn_inner, text=label, style=style,
                       command=cmd, width=18).pack(pady=(6, 0))
            tk.Label(cell, text=desc,
                     bg=self.BG2, fg=self.TEXTDIM,
                     font=("Segoe UI", 8),
                     wraplength=180, justify="center").pack(pady=(6, 0))

        # VM status indicator
        status_frame = tk.Frame(parent, bg=self.BG)
        status_frame.pack(pady=28)
        tk.Label(status_frame, text="Last action:",
                 bg=self.BG, fg=self.TEXTDIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
        self._vm_action_label = tk.Label(status_frame, text="—",
                                          bg=self.BG, fg=self.TEXT,
                                          font=("Segoe UI", 9, "bold"))
        self._vm_action_label.pack(side="left")

    # ──────────────── TAB 4 : OS VOTING ────────────────
    def _build_os_voting_tab(self, parent):
        parent.configure(style="TFrame")

        header = ttk.Frame(parent, style="TFrame")
        header.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(header, text="Chat OS Voting System",
                 bg=self.BG, fg=self.ACCENT2,
                 font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(header,
                 text=(f"Viewers vote with chat commands (e.g. !win7, !win8). "
                       f"{OS_VOTE_REQUIRED} votes switch the running OS. "
                       f"The channel owner bypasses voting and switches instantly."),
                 bg=self.BG, fg=self.TEXTDIM, font=("Segoe UI", 9),
                 wraplength=760, justify="left").pack(anchor="w", pady=(2, 0))

        # Enable toggle
        toggle_card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        toggle_card.pack(fill="x", padx=16, pady=(10, 8))
        self._os_voting_var = tk.BooleanVar(value=OS_VOTING_ENABLED)
        chk = tk.Checkbutton(toggle_card,
            text="Enable OS Voting System (uncheck = single fixed OS, classic mode)",
            variable=self._os_voting_var, bg=self.BG2, fg=self.TEXT,
            selectcolor=self.BG3, activebackground=self.BG2,
            activeforeground=self.TEXT, font=("Segoe UI", 10, "bold"),
            command=self._on_os_voting_toggle)
        chk.pack(anchor="w")

        # Scrollable rows card
        self._os_rows_card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        self._os_rows_card.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        col_hdr = tk.Frame(self._os_rows_card, bg=self.BG2)
        col_hdr.pack(fill="x", pady=(0, 6))
        tk.Label(col_hdr, text="#", bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI", 9, "bold"), width=2).grid(row=0, column=0, padx=4)
        tk.Label(col_hdr, text="Display Name", bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI", 9, "bold"), width=18, anchor="w").grid(row=0, column=1, padx=4)
        tk.Label(col_hdr, text="Chat Trigger", bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI", 9, "bold"), width=14, anchor="w").grid(row=0, column=2, padx=4)
        tk.Label(col_hdr, text="VirtualBox VM", bg=self.BG2, fg=self.TEXTDIM,
                 font=("Segoe UI", 9, "bold"), width=24, anchor="w").grid(row=0, column=3, padx=4)

        self._os_name_vars    = []
        self._os_trigger_vars = []
        self._os_vm_vars      = []
        self._os_vm_combos    = []

        existing = OS_LIST + [{}] * (OS_VOTE_SLOTS - len(OS_LIST))
        for i in range(OS_VOTE_SLOTS):
            entry = existing[i] if i < len(existing) else {}
            row = tk.Frame(self._os_rows_card, bg=self.BG2)
            row.pack(fill="x", pady=3)

            tk.Label(row, text=str(i + 1), bg=self.BG2, fg=self.TEXTDIM,
                     font=("Segoe UI", 9), width=2).grid(row=0, column=0, padx=4)

            name_var = tk.StringVar(value=entry.get("name", ""))
            ttk.Entry(row, textvariable=name_var, width=18,
                      font=("Segoe UI", 10)).grid(row=0, column=1, padx=4, ipady=3)
            self._os_name_vars.append(name_var)

            trig_var = tk.StringVar(value=entry.get("trigger", ""))
            trig_entry = ttk.Entry(row, textvariable=trig_var, width=14,
                                    font=("Segoe UI Mono", 10))
            trig_entry.grid(row=0, column=2, padx=4, ipady=3)
            self._os_trigger_vars.append(trig_var)
            tk.Label(row, text="(no ! needed, e.g. win7)", bg=self.BG2, fg=self.TEXTDIM,
                     font=("Segoe UI", 7)).grid(row=1, column=2, sticky="w", padx=4)

            vm_var = tk.StringVar(value=entry.get("vm", ""))
            vm_combo = ttk.Combobox(row, textvariable=vm_var, width=24,
                                     state="readonly", font=("Segoe UI", 9))
            vm_combo.grid(row=0, column=3, padx=4, ipady=3)
            self._os_vm_vars.append(vm_var)
            self._os_vm_combos.append(vm_combo)

        btn_row = tk.Frame(parent, bg=self.BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 14))
        ttk.Button(btn_row, text="🔄 Refresh VM List", style="Dim.TButton",
                   command=self._refresh_os_vm_lists).pack(side="left", padx=(0, 8))
        ttk.Button(btn_row, text="💾 Save OS Voting Config", style="Green.TButton",
                   command=self._save_os_voting_config).pack(side="left")

        self._refresh_os_vm_lists()
        self._set_os_rows_enabled(OS_VOTING_ENABLED)

    def _refresh_os_vm_lists(self):
        vms = get_vm_list()
        for combo in self._os_vm_combos:
            current = combo.get()
            combo['values'] = vms
            if current and current in vms:
                combo.set(current)
        self._log(f"[OSVoting] VM list refreshed ({len(vms)} found).")

    def _set_os_rows_enabled(self, enabled):
        state = "readonly" if enabled else "disabled"
        for combo in self._os_vm_combos:
            combo.configure(state=state)

    def _on_auto_start_toggle(self):
        global AUTO_START_ENABLED
        AUTO_START_ENABLED = self._auto_start_var.get()
        save_auto_start_config()
        self._log(f"[AutoStart] Watchdog {'enabled' if AUTO_START_ENABLED else 'disabled'} by user.")

    def _sync_main_vm_lock(self):
        """Lock the Main tab VM selector when OS Voting is enabled, since the
        bot then uses the OS Voting tab's list instead."""
        if OS_VOTING_ENABLED:
            self._vm_combo.configure(state="disabled")
            self._vm_select_note.configure(
                text="🗳 OS Voting is enabled — this selector is ignored. "
                     "The bot uses the VMs configured in the 'OS Voting' tab.")
        else:
            self._vm_combo.configure(state="readonly")
            self._vm_select_note.configure(text="")

    def _on_os_voting_toggle(self):
        self._set_os_rows_enabled(self._os_voting_var.get())

    def _save_os_voting_config(self):
        global OS_VOTING_ENABLED, OS_LIST
        enabled = self._os_voting_var.get()
        new_list = []
        for i in range(OS_VOTE_SLOTS):
            name = self._os_name_vars[i].get().strip()
            trig = self._os_trigger_vars[i].get().strip().lower().lstrip("!")
            vm   = self._os_vm_vars[i].get().strip()
            if name or trig or vm:
                new_list.append({"name": name, "trigger": trig, "vm": vm})

        if enabled:
            valid = [e for e in new_list if e["name"] and e["trigger"] and e["vm"]]
            if len(valid) < 2:
                messagebox.showerror("Invalid Configuration",
                    "OS Voting needs at least 2 fully filled rows "
                    "(Display Name + Chat Trigger + VM) to be enabled.")
                return
            triggers = [e["trigger"] for e in valid]
            if len(triggers) != len(set(triggers)):
                messagebox.showerror("Invalid Configuration",
                    "Chat triggers must be unique across all OS entries.")
                return

        OS_VOTING_ENABLED = enabled
        OS_LIST = new_list
        save_os_voting_config()
        self._set_os_rows_enabled(enabled)
        self._sync_main_vm_lock()
        self._log(f"[OSVoting] Saved. Enabled={enabled}, entries={len(new_list)}")
        messagebox.showinfo("Saved", "OS Voting configuration saved.")

    def _vm_set_last(self, text, color=None):
        self._vm_action_label.configure(
            text=text,
            fg=color or self.TEXT
        )

    def _vm_start(self):
        if not VM_NAME:
            messagebox.showerror("No VM", "Start the bot first to select a VM.")
            return
        self._vm_set_last("Starting…", self.YELLOW)
        self._log("[VM] Start requested by admin.")
        def run():
            try:
                speak_text("Starting Virtual Machine...")
                update_status("Starting...")
                start_vm()
                self.root.after(0, lambda: self._vm_set_last("Started ✔", self.GREEN))
            except Exception as e:
                self.root.after(0, lambda: self._vm_set_last(f"Error: {e}", self.RED))
                print(f"[VM] Start error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _vm_restart(self):
        if not VM_NAME:
            messagebox.showerror("No VM", "Start the bot first to select a VM.")
            return
        if not messagebox.askyesno("Restart VM", f"Reset '{VM_NAME}' now?"):
            return
        self._vm_set_last("Restarting…", self.YELLOW)
        self._log("[VM] Restart requested by admin.")
        def run():
            try:
                speak_text("Restarting Virtual Machine...")
                update_status("Restarting...")
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'reset'], check=True)
                update_status("Running")
                play_success_sound()
                self.root.after(0, lambda: self._vm_set_last("Restarted ✔", self.GREEN))
            except Exception as e:
                self.root.after(0, lambda: self._vm_set_last(f"Error: {e}", self.RED))
                print(f"[VM] Restart error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _vm_revert(self):
        if not VM_NAME:
            messagebox.showerror("No VM", "Start the bot first to select a VM.")
            return
        if not messagebox.askyesno("Revert VM",
                f"Power off '{VM_NAME}', restore snapshot and reboot?\n"
                "This will discard all unsaved VM state."):
            return
        self._vm_set_last("Reverting…", self.YELLOW)
        self._log("[VM] Revert requested by admin.")
        def run():
            global revert_in_progress, revert_start_time
            try:
                speak_text("Reverting Virtual Machine...")
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
                revert_start_time = None
                revert_in_progress = False
                update_votes_json("revert", 0, 2, 0)
                self.root.after(0, lambda: self._vm_set_last("Reverted ✔", self.GREEN))
            except Exception as e:
                revert_in_progress = False
                self.root.after(0, lambda: self._vm_set_last(f"Error: {e}", self.RED))
                print(f"[VM] Revert error: {e}")
        threading.Thread(target=run, daemon=True).start()

    def _vm_shutdown(self):
        if not VM_NAME:
            messagebox.showerror("No VM", "Start the bot first to select a VM.")
            return
        if not messagebox.askyesno("Shutdown VM",
                f"Force power off '{VM_NAME}'?\nUnsaved VM state will be lost."):
            return
        self._vm_set_last("Shutting down…", self.YELLOW)
        self._log("[VM] Shutdown requested by admin.")
        def run():
            try:
                speak_text("Shutting down Virtual Machine...")
                update_status("Shutting down...")
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'poweroff'], check=True)
                update_status("Stopped")
                self.root.after(0, lambda: self._vm_set_last("Powered off ✔", self.TEXTDIM))
            except Exception as e:
                self.root.after(0, lambda: self._vm_set_last(f"Error: {e}", self.RED))
                print(f"[VM] Shutdown error: {e}")
        threading.Thread(target=run, daemon=True).start()

    # ──────────────── Helpers ────────────────
    @staticmethod
    def _font_exists(name):
        import tkinter.font as tkfont
        return name in tkfont.families()

    def _log(self, msg):
        self._console.configure(state='normal')
        ts = time.strftime("%H:%M:%S")
        self._console.insert('end', f"[{ts}] {msg}\n")
        self._console.see('end')
        self._console.configure(state='disabled')

    def _set_status(self, text, color):
        self._status_dot.configure(text=f"⬤  {text}", fg=color)

    # ──────────────── VM List ────────────────
    def _refresh_vm_list(self):
        vms = get_vm_list()
        self._vm_combo['values'] = vms
        if vms:
            self._vm_combo.current(0)
            self._log(f"VirtualBox: {len(vms)} VM(s) found.")
        else:
            self._log("⚠️ No VMs found (VirtualBox installed?)")

    # ──────────────── Bot Start / Stop ────────────────
    def _start_bot(self):
        global VIDEO_ID, VM_NAME, current_os_vm
        yt  = self._yt_var.get().strip()
        vm  = self._vm_var.get().strip()
        if not yt:
            messagebox.showerror("Missing Input", "Please enter a YouTube Video ID.")
            return
        if self._bot_running:
            self._log("⚠️ Bot is already running!")
            return

        if OS_VOTING_ENABLED:
            valid_entries = [e for e in OS_LIST if e.get("name") and e.get("trigger") and e.get("vm")]
            if len(valid_entries) < 2:
                messagebox.showerror("OS Voting Misconfigured",
                    "OS Voting is enabled but fewer than 2 valid OS entries are configured.\n"
                    "Go to the OS Voting tab and fix the configuration, or disable voting.")
                return
            VM_NAME = valid_entries[0]["vm"]
            current_os_vm = VM_NAME
            self._log(f"[OSVoting] Voting enabled — starting with '{valid_entries[0]['name']}'.")
        else:
            if not vm:
                messagebox.showerror("Missing Input", "Please select a VirtualBox VM.")
                return
            VM_NAME = vm
            current_os_vm = vm

        VIDEO_ID = yt
        self._bot_running = True
        bot_stop_event.clear()
        self._set_status("Running", self.GREEN)

        # Redirect stdout → console
        self._console_redir = ConsoleRedirect(self._console)
        self._console_redir.start()

        self._log(f"Starting bot → YT: {VIDEO_ID}  |  VM: {VM_NAME}")

        self._bot_instance = None
        self._bot_thread = threading.Thread(target=self._run_bot, daemon=True)
        self._bot_thread.start()

    def _run_bot(self):
        try:
            bot = YouTubeChatBot()
            self._bot_instance = bot
            if bot.chat and bot.chat.is_alive():
                bot.run()
            else:
                print("[Bot] Chat connection failed at startup.")
        except Exception as e:
            print(f"[Bot] Fatal error: {e}")
        finally:
            self._bot_instance = None
            self._bot_running = False
            self.root.after(0, lambda: self._set_status("Stopped", self.RED))

    def _stop_bot(self):
        if not self._bot_running:
            self._log("Bot is already stopped.")
            return
        self._log("Stopping bot... (may take a few seconds to finish current loop)")
        bot_stop_event.set()
        # Force the underlying chat connection closed immediately so the
        # blocking chat.get() call in run() doesn't keep us waiting.
        if self._bot_instance and self._bot_instance.chat:
            try:
                self._bot_instance.chat.terminate()
            except Exception as e:
                print(f"[Bot] Error terminating chat connection: {e}")
        self._bot_running = False
        if self._console_redir:
            self._console_redir.stop()
            self._console_redir = None
        self._set_status("Stopped", self.RED)
        self._log("Bot stopped by user.")

    # ──────────────── Admin CMD ────────────────
    def _send_admin_cmd(self):
        global revert_in_progress, revert_start_time
        cmd = self._admin_var.get().strip()
        if not cmd: return
        self._admin_var.set("")
        self._log(f"[AdminCMD] {cmd}")

        def run():
            c = cmd.lower()
            if c == '!startvm':
                speak_text("Starting Virtual Machine...")
                update_status("Starting...")
                start_vm()
            elif c == '!restart':
                speak_text("Restarting Virtual Machine...")
                update_status("Restarting...")
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'reset'])
                update_status("Running"); play_success_sound()
            elif c.startswith('!speak '):
                speak_text(cmd[7:].strip())
            elif c == '!revert':
                speak_text("Reverting Virtual Machine...")
                revert_in_progress = True
                update_status("Reverting...")
                subprocess.run([VBOXMANAGE_PATH, 'controlvm', VM_NAME, 'poweroff'], check=True)
                time.sleep(3)
                subprocess.run([VBOXMANAGE_PATH, 'snapshot', VM_NAME, 'restorecurrent'], check=True)
                time.sleep(3)
                subprocess.run([VBOXMANAGE_PATH, 'startvm', VM_NAME], check=True)
                update_status("Running"); play_success_sound()
                vote_revert.clear(); revert_start_time = None; revert_in_progress = False
                update_votes_json("revert", 0, 2, 0)
            elif c == '!clearvotes':
                vote_restart.clear(); vote_revert.clear(); ban_votes.clear()
                update_votes_json("restartvm", 0, 2, 0)
                update_votes_json("revert",    0, 2, 0)
                update_ban_vote_display(None, 0, 3)
                os_votes.clear()
                update_os_vote_status()
                speak_text("Votes cleared by admin!")
                print("[Admin] Votes cleared")
            else:
                print(f"[Admin] Unknown command: {cmd}")

        threading.Thread(target=run, daemon=True).start()

    # ──────────────── Command Builder ────────────────
    # ──────────────── Chain Parser ────────────────
    def _parse_chain_input(self):
        """
        Parses a chat-style chain like '!combo win+r !wait 800 !send notepad.exe'
        into individual steps. Replaces the current step list (does not append).
        """
        raw = self._chain_var.get().strip()
        if not raw:
            messagebox.showinfo("Empty", "Chain input field is empty.")
            return

        # Split on '!', discard empty parts
        parts = [p.strip() for p in raw.split('!') if p.strip()]
        if not parts:
            messagebox.showwarning("Parse Error", "No valid command found.\nCommands must start with !.")
            return

        steps = []
        for part in parts:
            tokens = part.split(maxsplit=1)
            action = tokens[0].lower()
            args   = tokens[1] if len(tokens) > 1 else ""
            steps.append({"action": action, "args": args})

        self._step_items = steps
        self._refresh_step_tree()
        self._chain_var.set("")   # clear
        self._log(f"[ChainParse] {len(steps)} step(s) created: "
                  + "  →  ".join(f"{s['action']}({s['args']})" for s in steps))

    def _refresh_cmd_list(self):
        self._cmd_listbox.delete(0, 'end')
        for trigger in sorted(custom_commands.keys()):
            self._cmd_listbox.insert('end', trigger)

    def _on_cmd_select(self, event=None):
        sel = self._cmd_listbox.curselection()
        if not sel: return
        trigger = self._cmd_listbox.get(sel[0])
        self._editing_cmd = trigger
        self._trig_var.set(trigger)
        self._step_items  = list(custom_commands.get(trigger, []))
        self._refresh_step_tree()

    def _refresh_step_tree(self):
        for row in self._step_tree.get_children():
            self._step_tree.delete(row)
        for i, step in enumerate(self._step_items):
            tag = "even" if i % 2 == 0 else "odd"
            self._step_tree.insert("", "end",
                values=(step["action"], step["args"]), tags=(tag,))
        self._step_tree.tag_configure("even", background=self.BG3)
        self._step_tree.tag_configure("odd",  background=self.BG2)

    def _add_step(self):
        action = self._action_var.get().strip()
        args   = self._args_var.get().strip()
        if not action:
            messagebox.showwarning("Missing", "Please select an action.")
            return
        self._step_items.append({"action": action, "args": args})
        self._refresh_step_tree()
        self._args_var.set("")

    def _selected_step_idx(self):
        sel = self._step_tree.selection()
        if not sel: return None
        children = self._step_tree.get_children()
        return list(children).index(sel[0])

    def _step_up(self):
        idx = self._selected_step_idx()
        if idx is None or idx == 0: return
        self._step_items[idx-1], self._step_items[idx] = \
            self._step_items[idx], self._step_items[idx-1]
        self._refresh_step_tree()
        self._step_tree.selection_set(self._step_tree.get_children()[idx-1])

    def _step_down(self):
        idx = self._selected_step_idx()
        if idx is None or idx >= len(self._step_items)-1: return
        self._step_items[idx], self._step_items[idx+1] = \
            self._step_items[idx+1], self._step_items[idx]
        self._refresh_step_tree()
        self._step_tree.selection_set(self._step_tree.get_children()[idx+1])

    def _step_remove(self):
        idx = self._selected_step_idx()
        if idx is None: return
        self._step_items.pop(idx)
        self._refresh_step_tree()

    def _new_cmd(self):
        self._editing_cmd = None
        self._trig_var.set("!")
        self._step_items  = []
        self._refresh_step_tree()
        self._cmd_listbox.selection_clear(0, 'end')

    def _save_cmd(self):
        trigger = self._trig_var.get().strip()
        if not trigger.startswith("!") or len(trigger) < 2:
            messagebox.showerror("Invalid Trigger",
                "Trigger must start with ! and have a name.\nExample: !bubbles")
            return
        custom_commands[trigger] = list(self._step_items)
        save_custom_commands()
        self._refresh_cmd_list()
        self._log(f"[CustomCmd] Saved '{trigger}' with {len(self._step_items)} step(s).")

    def _delete_cmd(self):
        sel = self._cmd_listbox.curselection()
        if not sel:
            messagebox.showinfo("Select", "Select a command to delete.")
            return
        trigger = self._cmd_listbox.get(sel[0])
        if messagebox.askyesno("Delete", f"Delete '{trigger}'?"):
            del custom_commands[trigger]
            save_custom_commands()
            self._refresh_cmd_list()
            self._new_cmd()
            self._log(f"[CustomCmd] Deleted '{trigger}'.")

    def _test_cmd(self):
        trigger = self._trig_var.get().strip()
        if trigger not in custom_commands:
            messagebox.showinfo("Not Saved", "Save the command first, then test.")
            return
        threading.Thread(target=execute_custom_command,
                         args=(trigger,), daemon=True).start()
        self._log(f"[CustomCmd] Testing '{trigger}'...")


# ========================= MAIN =========================
if __name__ == '__main__':
    load_custom_commands()
    root = tk.Tk()
    app  = UltraBotGUI(root)
    root.mainloop()
