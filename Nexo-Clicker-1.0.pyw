"""
NexoClicker - Auto Clicker Application

Requirements:
    pip install pynput

Run:
    python nexoclicker.py
"""

import threading
import time
import random
import tkinter as tk
from tkinter import ttk

from pynput.mouse import Controller as MouseController, Button as MouseButton
from pynput.keyboard import Controller as KeyboardController, Key, KeyCode, Listener as KeyListener


# ----------------------------- Color Theme -----------------------------
BG_MAIN = "#1e1f22"
BG_PANEL = "#2a2b2f"
BG_INPUT = "#3a3b40"
FG_TEXT = "#e6e6e6"
FG_MUTED = "#9a9a9a"
ACCENT_GREEN = "#3ecf6d"
BORDER = "#3a3b40"
DANGER = "#e05252"

mouse = MouseController()
keyboard = KeyboardController()


def key_to_string(key):
    """Convert a pynput key object to a readable string."""
    if isinstance(key, KeyCode):
        if key.char:
            return key.char.upper()
        return str(key)
    if isinstance(key, Key):
        return key.name.upper()
    return str(key)


def string_to_key(name):
    """Best-effort conversion of a stored key name back to a pynput key object."""
    name = name.strip()
    try:
        return getattr(Key, name.lower())
    except AttributeError:
        if len(name) == 1:
            return KeyCode.from_char(name.lower())
        return KeyCode.from_char(name[0].lower())


class ToggleButtonGroup(tk.Frame):
    """A small segmented control, e.g. [Rate | Interval] or [Off | On]."""

    def __init__(self, parent, options, default_index=0, command=None, **kwargs):
        super().__init__(parent, bg=BG_PANEL, **kwargs)
        self.command = command
        self.buttons = []
        self.selected = tk.IntVar(value=default_index)

        for i, label in enumerate(options):
            btn = tk.Button(
                self,
                text=label,
                bd=0,
                relief="flat",
                font=("Segoe UI", 9, "bold"),
                cursor="hand2",
                command=lambda idx=i: self.select(idx),
                padx=14,
                pady=6,
            )
            btn.grid(row=0, column=i, padx=(0 if i == 0 else 2, 0))
            self.buttons.append(btn)

        self._refresh_styles()

    def select(self, index):
        self.selected.set(index)
        self._refresh_styles()
        if self.command:
            self.command(index)

    def get(self):
        return self.selected.get()

    def _refresh_styles(self):
        active = self.selected.get()
        for i, btn in enumerate(self.buttons):
            if i == active:
                btn.configure(bg=ACCENT_GREEN, fg="#0d1f12", activebackground=ACCENT_GREEN)
            else:
                btn.configure(bg=BG_INPUT, fg=FG_TEXT, activebackground=BG_INPUT)


class Section(tk.Frame):
    """A bordered card/section. Hint labels registered via add_hint() automatically
    re-wrap to the section's current width, so text never gets clipped."""

    def __init__(self, parent, title, icon="", **kwargs):
        super().__init__(parent, bg=BG_PANEL, highlightbackground=BORDER,
                          highlightthickness=1, bd=0, **kwargs)
        header = tk.Frame(self, bg=BG_PANEL)
        header.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(header, text=f"{icon}  {title}", bg=BG_PANEL, fg=FG_TEXT,
                 font=("Segoe UI", 10, "bold")).pack(side="left")

        self.body = tk.Frame(self, bg=BG_PANEL)
        self.body.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        self._hint_labels = []
        self.bind("<Configure>", self._on_resize)

    def add_hint(self, text):
        lbl = tk.Label(self.body, text=text, bg=BG_PANEL, fg=FG_MUTED,
                        font=("Segoe UI", 8), justify="left", anchor="w")
        lbl.pack(anchor="w", fill="x", pady=(0, 8))
        self._hint_labels.append(lbl)
        return lbl

    def _on_resize(self, event):
        wrap = max(event.width - 28, 80)
        for lbl in self._hint_labels:
            lbl.configure(wraplength=wrap)


class NexoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NexoClicker")
        self.root.configure(bg=BG_MAIN)
        self.root.geometry("640x520")
        self.root.minsize(520, 420)

        self._setup_style()

        # ---------------- State ----------------
        self.running = False
        self.click_thread = None
        self.clicks_done = 0
        self.start_time = None

        self.hotkey = "f7"
        self.capturing_hotkey = False
        self._hotkey_listener = None
        self._pressed_hotkeys = set()

        # ---------------- Header ----------------
        title_bar = tk.Frame(root, bg=BG_MAIN)
        title_bar.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(title_bar, text="⚡ NexoClicker", bg=BG_MAIN, fg=FG_TEXT,
                 font=("Segoe UI", 15, "bold")).pack(side="left")
        self.status_label = tk.Label(title_bar, text="● Stopped", bg=BG_MAIN,
                                      fg=DANGER, font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side="right")

        # ---------------- Tabs ----------------
        self.notebook = ttk.Notebook(root, style="Nexo.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        self.main_tab = tk.Frame(self.notebook, bg=BG_MAIN)
        self.advanced_tab = tk.Frame(self.notebook, bg=BG_MAIN)
        self.cps_tab = tk.Frame(self.notebook, bg=BG_MAIN)
        self.notebook.add(self.main_tab, text="Main")
        self.notebook.add(self.advanced_tab, text="Advanced")
        self.notebook.add(self.cps_tab, text="CPS Test")

        self._build_main_tab(self.main_tab)
        self._build_advanced_tab(self.advanced_tab)
        self._build_cps_tab(self.cps_tab)

        # ---------------- Footer ----------------
        footer = tk.Frame(root, bg=BG_MAIN)
        footer.pack(fill="x", padx=16, pady=(4, 14))
        self.start_stop_btn = tk.Button(
            footer, text=f"Start ({self.hotkey.upper()})", bg=ACCENT_GREEN, fg="#0d1f12",
            font=("Segoe UI", 11, "bold"), bd=0, relief="flat", cursor="hand2",
            padx=18, pady=8, command=self.toggle_clicking
        )
        self.start_stop_btn.pack(side="left")

        self.counter_label = tk.Label(footer, text="Clicks: 0", bg=BG_MAIN, fg=FG_MUTED,
                                       font=("Segoe UI", 10))
        self.counter_label.pack(side="right")

        # Start global hotkey listener
        self._start_hotkey_listener()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Style setup
    # ------------------------------------------------------------------
    def _setup_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                         foreground=FG_TEXT, arrowcolor=FG_TEXT)

        style.configure("Nexo.TNotebook", background=BG_MAIN, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure("Nexo.TNotebook.Tab", background=BG_PANEL, foreground=FG_MUTED,
                         padding=[16, 8], font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Nexo.TNotebook.Tab",
                  background=[("selected", BG_MAIN)],
                  foreground=[("selected", ACCENT_GREEN)])

    def _entry(self, parent, textvariable, width=8):
        e = tk.Entry(parent, textvariable=textvariable, bg=BG_INPUT, fg=FG_TEXT,
                     insertbackground=FG_TEXT, relief="flat", width=width,
                     font=("Segoe UI", 10), justify="center")
        return e

    def _make_grid(self, parent, rows=2, cols=2):
        grid = tk.Frame(parent, bg=BG_MAIN)
        grid.pack(fill="both", expand=True, pady=(8, 0))
        for c in range(cols):
            grid.columnconfigure(c, weight=1)
        for r in range(rows):
            grid.rowconfigure(r, weight=1)
        return grid

    # ==================================================================
    # MAIN TAB — the settings most people need right away
    # ==================================================================
    def _build_main_tab(self, parent):
        grid = self._make_grid(parent, rows=2, cols=2)

        self._build_click_speed(grid).grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self._build_hotkey(grid).grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self._build_clicker_type(grid).grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(6, 0))

    # ==================================================================
    # ADVANCED TAB — power-user settings
    # ==================================================================
    def _build_advanced_tab(self, parent):
        grid = self._make_grid(parent, rows=2, cols=2)

        self._build_limits(grid).grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 6))
        self._build_duty_cycle(grid).grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 6))
        self._build_randomization(grid).grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=6)
        self._build_double_click(grid).grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=6)

    # ------------------------------------------------------------------
    # Section: Click Speed
    # ------------------------------------------------------------------
    def _build_click_speed(self, parent):
        s = Section(parent, "Click Speed", "⚡")

        self.speed_mode = ToggleButtonGroup(s.body, ["Rate", "Interval"], default_index=0,
                                             command=self._on_speed_mode_change)
        self.speed_mode.pack(anchor="e", pady=(0, 10))

        s.add_hint("Changes how fast the autoclicker clicks.")

        row = tk.Frame(s.body, bg=BG_PANEL)
        row.pack(fill="x")

        self.rate_value = tk.StringVar(value="25")
        self.rate_unit = tk.StringVar(value="Second")
        self.interval_ms = tk.StringVar(value="40")

        self.rate_row = tk.Frame(row, bg=BG_PANEL)
        tk.Label(self.rate_row, text="Clicks Per", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self._entry(self.rate_row, self.rate_value).pack(side="left", padx=6)
        unit_box = ttk.Combobox(self.rate_row, textvariable=self.rate_unit,
                                 values=["Second", "Minute", "Hour"], width=8,
                                 state="readonly")
        unit_box.pack(side="left")

        self.interval_row = tk.Frame(row, bg=BG_PANEL)
        tk.Label(self.interval_row, text="Interval", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self._entry(self.interval_row, self.interval_ms).pack(side="left", padx=6)
        tk.Label(self.interval_row, text="ms", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        self.rate_row.pack(anchor="w")
        return s

    def _on_speed_mode_change(self, index):
        self.interval_row.pack_forget()
        self.rate_row.pack_forget()
        if index == 0:
            self.rate_row.pack(anchor="w")
        else:
            self.interval_row.pack(anchor="w")

    def _get_interval_seconds(self):
        """Compute the base click interval in seconds from the current mode."""
        try:
            if self.speed_mode.get() == 0:  # Rate mode
                value = float(self.rate_value.get())
                unit = self.rate_unit.get()
                if unit == "Second":
                    cps = value
                elif unit == "Minute":
                    cps = value / 60.0
                else:  # Hour
                    cps = value / 3600.0
                return 1.0 / cps if cps > 0 else 0.04
            else:  # Interval mode (ms)
                ms = float(self.interval_ms.get())
                return max(ms, 1) / 1000.0
        except (ValueError, ZeroDivisionError):
            return 0.04

    # ------------------------------------------------------------------
    # Section: Hotkey
    # ------------------------------------------------------------------
    def _build_hotkey(self, parent):
        s = Section(parent, "Hotkey", "⌘")

        self.hotkey_mode = ToggleButtonGroup(s.body, ["Toggle", "Hold"], default_index=0)
        self.hotkey_mode.pack(anchor="e", pady=(0, 10))

        s.add_hint("Hold the hotkey to click. Release to stop.")

        row = tk.Frame(s.body, bg=BG_PANEL)
        row.pack(fill="x")

        self.hotkey_display = tk.StringVar(value=self.hotkey)
        entry = tk.Entry(row, textvariable=self.hotkey_display, bg=BG_INPUT, fg=FG_TEXT,
                          relief="flat", font=("Segoe UI", 10), justify="center",
                          state="readonly", readonlybackground=BG_INPUT, width=12)
        entry.pack(side="left", fill="x", expand=True)

        self.edit_hotkey_btn = tk.Button(
            row, text="Edit Hotkey", bg=BG_INPUT, fg=FG_TEXT, bd=0, relief="flat",
            cursor="hand2", font=("Segoe UI", 9, "bold"), padx=10, pady=6,
            command=self._begin_capture_hotkey
        )
        self.edit_hotkey_btn.pack(side="left", padx=(8, 0))
        return s

    def _begin_capture_hotkey(self):
        self.capturing_hotkey = True
        self.hotkey_display.set("Press any key...")
        self.edit_hotkey_btn.configure(state="disabled")

    def _finish_capture_hotkey(self, key):
        self.hotkey = key_to_string(key)
        self.hotkey_display.set(self.hotkey)
        if self.running:
            self.start_stop_btn.configure(text=f"Stop ({self.hotkey.upper()})")
        else:
            self.start_stop_btn.configure(text=f"Start ({self.hotkey.upper()})")
        self.capturing_hotkey = False
        self.edit_hotkey_btn.configure(state="normal")

    # ------------------------------------------------------------------
    # Section: Clicker Type (Main tab — basic mouse/keyboard choice)
    # ------------------------------------------------------------------
    def _build_clicker_type(self, parent):
        s = Section(parent, "Clicker Type", "🖱")

        self.input_mode = ToggleButtonGroup(s.body, ["Mouse", "Keyboard"], default_index=0,
                                             command=self._on_input_mode_change)
        self.input_mode.pack(anchor="e", pady=(0, 10))

        s.add_hint("Select the mouse button or keyboard key the autoclicker clicks.")

        self.mouse_options = tk.Frame(s.body, bg=BG_PANEL)
        self.mouse_button_toggle = ToggleButtonGroup(self.mouse_options,
                                                       ["Left", "Middle", "Right"],
                                                       default_index=0)
        self.mouse_button_toggle.pack(anchor="w")

        self.keyboard_options = tk.Frame(s.body, bg=BG_PANEL)
        row = tk.Frame(self.keyboard_options, bg=BG_PANEL)
        row.pack(fill="x")
        tk.Label(row, text="Key to press:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")
        self.keyboard_key = tk.StringVar(value="e")
        self._entry(row, self.keyboard_key, width=6).pack(side="left", padx=8)

        self.mouse_options.pack(fill="x")
        return s

    def _on_input_mode_change(self, index):
        self.mouse_options.pack_forget()
        self.keyboard_options.pack_forget()
        if index == 0:
            self.mouse_options.pack(fill="x")
        else:
            self.keyboard_options.pack(fill="x")

    # ==================================================================
    # CPS TEST TAB — test how many clicks per second you can do
    # ==================================================================
    def _build_cps_tab(self, parent):
        # ---------------- CPS test state ----------------
        self.cps_test_running = False
        self.cps_test_duration = tk.StringVar(value="5")
        self.cps_test_clicks = 0
        self.cps_test_start_time = None
        self.cps_test_after_id = None

        wrapper = tk.Frame(parent, bg=BG_MAIN)
        wrapper.pack(fill="both", expand=True, pady=(8, 0))

        # --- Settings row (duration choice) ---
        settings_row = tk.Frame(wrapper, bg=BG_MAIN)
        settings_row.pack(fill="x", pady=(0, 10))

        tk.Label(settings_row, text="Test duration:", bg=BG_MAIN, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))

        self.cps_duration_toggle = ToggleButtonGroup(
            settings_row, ["5s", "10s", "Custom"], default_index=0,
            command=self._on_cps_duration_change
        )
        self.cps_duration_toggle.pack(side="left")

        self.cps_custom_row = tk.Frame(settings_row, bg=BG_MAIN)
        self._entry(self.cps_custom_row, self.cps_test_duration, width=5).pack(side="left", padx=(8, 4))
        tk.Label(self.cps_custom_row, text="sec", bg=BG_MAIN, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left")

        # --- Main test card ---
        card = tk.Frame(wrapper, bg=BG_PANEL, highlightbackground=BORDER,
                         highlightthickness=1, bd=0)
        card.pack(fill="both", expand=True)

        stats_row = tk.Frame(card, bg=BG_PANEL)
        stats_row.pack(fill="x", padx=20, pady=(18, 6))

        self.cps_time_label = tk.Label(stats_row, text="Time: 5.0s", bg=BG_PANEL,
                                        fg=FG_TEXT, font=("Segoe UI", 11, "bold"))
        self.cps_time_label.pack(side="left")

        self.cps_clicks_label = tk.Label(stats_row, text="Clicks: 0", bg=BG_PANEL,
                                          fg=FG_TEXT, font=("Segoe UI", 11, "bold"))
        self.cps_clicks_label.pack(side="left", padx=(20, 0))

        self.cps_live_label = tk.Label(stats_row, text="CPS: 0.0", bg=BG_PANEL,
                                        fg=ACCENT_GREEN, font=("Segoe UI", 11, "bold"))
        self.cps_live_label.pack(side="right")

        # Big clickable zone
        self.cps_click_zone = tk.Button(
            card, text="Press Start, then click here as fast as you can!",
            bg=BG_INPUT, fg=FG_MUTED, font=("Segoe UI", 13, "bold"),
            bd=0, relief="flat", cursor="hand2", wraplength=380,
            command=self._register_cps_click, state="disabled"
        )
        self.cps_click_zone.pack(fill="both", expand=True, padx=20, pady=(6, 14))

        # --- Controls / result row ---
        bottom_row = tk.Frame(card, bg=BG_PANEL)
        bottom_row.pack(fill="x", padx=20, pady=(0, 18))

        self.cps_start_btn = tk.Button(
            bottom_row, text="Start Test", bg=ACCENT_GREEN, fg="#0d1f12",
            font=("Segoe UI", 10, "bold"), bd=0, relief="flat", cursor="hand2",
            padx=16, pady=8, command=self._start_cps_test
        )
        self.cps_start_btn.pack(side="left")

        self.cps_result_label = tk.Label(bottom_row, text="", bg=BG_PANEL, fg=FG_MUTED,
                                          font=("Segoe UI", 9), justify="right")
        self.cps_result_label.pack(side="right")

    def _on_cps_duration_change(self, index):
        if index == 2:  # Custom
            self.cps_custom_row.pack(side="left")
        else:
            self.cps_custom_row.pack_forget()

    def _get_cps_test_duration(self):
        idx = self.cps_duration_toggle.get()
        if idx == 0:
            return 5.0
        if idx == 1:
            return 10.0
        try:
            return max(1.0, float(self.cps_test_duration.get()))
        except ValueError:
            return 5.0

    def _start_cps_test(self):
        if self.cps_test_running:
            return
        self.cps_test_running = True
        self.cps_test_clicks = 0
        self.cps_test_total_duration = self._get_cps_test_duration()
        self.cps_test_start_time = time.time()

        self.cps_start_btn.configure(state="disabled")
        self.cps_result_label.configure(text="")
        self.cps_click_zone.configure(
            state="normal", bg=ACCENT_GREEN, fg="#0d1f12", text="CLICK! CLICK! CLICK!"
        )
        self._tick_cps_test()

    def _register_cps_click(self):
        if not self.cps_test_running:
            return
        self.cps_test_clicks += 1

    def _tick_cps_test(self):
        elapsed = time.time() - self.cps_test_start_time
        remaining = max(0.0, self.cps_test_total_duration - elapsed)
        cps = self.cps_test_clicks / elapsed if elapsed > 0 else 0.0

        self.cps_time_label.configure(text=f"Time: {remaining:0.1f}s")
        self.cps_clicks_label.configure(text=f"Clicks: {self.cps_test_clicks}")
        self.cps_live_label.configure(text=f"CPS: {cps:0.1f}")

        if remaining <= 0:
            self._finish_cps_test()
        else:
            self.cps_test_after_id = self.root.after(50, self._tick_cps_test)

    def _finish_cps_test(self):
        self.cps_test_running = False
        total_time = self.cps_test_total_duration
        final_cps = self.cps_test_clicks / total_time if total_time > 0 else 0.0

        self.cps_click_zone.configure(
            state="disabled", bg=BG_INPUT, fg=FG_MUTED,
            text="Press Start, then click here as fast as you can!"
        )
        self.cps_start_btn.configure(state="normal")
        self.cps_time_label.configure(text=f"Time: 0.0s")
        self.cps_result_label.configure(
            text=f"Result: {self.cps_test_clicks} clicks in {total_time:0.1f}s  →  {final_cps:0.2f} CPS",
            fg=ACCENT_GREEN
        )

    # ------------------------------------------------------------------
    # Section: Limits (Advanced)
    # ------------------------------------------------------------------
    def _build_limits(self, parent):
        s = Section(parent, "Limits", "◔")

        self.limits_toggle = ToggleButtonGroup(s.body, ["Off", "On"], default_index=0)
        self.limits_toggle.pack(anchor="e", pady=(0, 10))

        s.add_hint("Stop automatically after a set number of clicks or time.")

        row = tk.Frame(s.body, bg=BG_PANEL)
        row.pack(fill="x")

        self.limit_value = tk.StringVar(value="1000")
        self._entry(row, self.limit_value, width=10).pack(side="left")

        self.limit_type_toggle = ToggleButtonGroup(row, ["Clicks", "Time (s)"], default_index=0)
        self.limit_type_toggle.pack(side="left", padx=(8, 0))
        return s

    # ------------------------------------------------------------------
    # Section: Duty Cycle (Advanced)
    # ------------------------------------------------------------------
    def _build_duty_cycle(self, parent):
        s = Section(parent, "Duty Cycle", "⧗")

        self.duty_mode = ToggleButtonGroup(s.body, ["Click", "Hold"], default_index=0)
        self.duty_mode.pack(anchor="e", pady=(0, 10))

        s.add_hint("Controls how long the button is held during each click.")

        row = tk.Frame(s.body, bg=BG_PANEL)
        row.pack(fill="x")
        self.hold_duration_pct = tk.StringVar(value="5")
        self._entry(row, self.hold_duration_pct, width=6).pack(side="left")
        tk.Label(row, text="%  hold duration", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
        return s

    # ------------------------------------------------------------------
    # Section: Speed Randomization (Advanced)
    # ------------------------------------------------------------------
    def _build_randomization(self, parent):
        s = Section(parent, "Speed Randomization", "⟲")

        self.random_toggle = ToggleButtonGroup(s.body, ["Off", "On"], default_index=1)
        self.random_toggle.pack(anchor="e", pady=(0, 10))

        s.add_hint("Randomizes your click speed by the given percentage.")

        row = tk.Frame(s.body, bg=BG_PANEL)
        row.pack(fill="x")
        self.random_pct = tk.StringVar(value="0")
        self._entry(row, self.random_pct, width=6).pack(side="left")
        tk.Label(row, text="%", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=(6, 0))
        return s

    # ------------------------------------------------------------------
    # Section: Double Click (Advanced)
    # ------------------------------------------------------------------
    def _build_double_click(self, parent):
        s = Section(parent, "Double Click", "⎘")

        self.double_click_toggle = ToggleButtonGroup(s.body, ["Off", "On"], default_index=0)
        self.double_click_toggle.pack(anchor="e", pady=(0, 10))

        s.add_hint("Fires a second click right after the first one, mouse mode only.")
        return s

    # ------------------------------------------------------------------
    # Hotkey listener (global, works even when window isn't focused)
    # ------------------------------------------------------------------
    def _start_hotkey_listener(self):
        def on_press(key):
            if self.capturing_hotkey:
                self.root.after(0, self._finish_capture_hotkey, key)
                return
            name = key_to_string(key)
            if name.lower() == self.hotkey.lower():
                if name not in self._pressed_hotkeys:
                    self._pressed_hotkeys.add(name)
                    mode = self.hotkey_mode.get()  # 0=Toggle, 1=Hold
                    if mode == 0:
                        self.root.after(0, self.toggle_clicking)
                    else:
                        if not self.running:
                            self.root.after(0, self.start_clicking)

        def on_release(key):
            name = key_to_string(key)
            self._pressed_hotkeys.discard(name)
            if name.lower() == self.hotkey.lower():
                mode = self.hotkey_mode.get()
                if mode == 1 and self.running:  # Hold mode
                    self.root.after(0, self.stop_clicking)

        self._hotkey_listener = KeyListener(on_press=on_press, on_release=on_release)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()

    # ------------------------------------------------------------------
    # Start / Stop control
    # ------------------------------------------------------------------
    def toggle_clicking(self):
        if self.running:
            self.stop_clicking()
        else:
            self.start_clicking()

    def start_clicking(self):
        if self.running:
            return
        self.running = True
        self.clicks_done = 0
        self.start_time = time.time()
        self.status_label.configure(text="● Running", fg=ACCENT_GREEN)
        self.start_stop_btn.configure(text=f"Stop ({self.hotkey.upper()})",
                                       bg=DANGER, fg="#2a0d0d")
        self.click_thread = threading.Thread(target=self._click_loop, daemon=True)
        self.click_thread.start()
        self._update_counter_label()

    def stop_clicking(self):
        self.running = False
        self.status_label.configure(text="● Stopped", fg=DANGER)
        self.start_stop_btn.configure(text=f"Start ({self.hotkey.upper()})",
                                       bg=ACCENT_GREEN, fg="#0d1f12")

    def _update_counter_label(self):
        self.counter_label.configure(text=f"Clicks: {self.clicks_done}")
        if self.running:
            self.root.after(150, self._update_counter_label)

    # ------------------------------------------------------------------
    # Click loop (runs in a background thread)
    # ------------------------------------------------------------------
    def _click_loop(self):
        while self.running:
            # --- Limits check ---
            if self.limits_toggle.get() == 1:  # On
                try:
                    limit_val = float(self.limit_value.get())
                except ValueError:
                    limit_val = 0
                if self.limit_type_toggle.get() == 0:  # Clicks
                    if self.clicks_done >= limit_val:
                        self.root.after(0, self.stop_clicking)
                        break
                else:  # Time
                    if time.time() - self.start_time >= limit_val:
                        self.root.after(0, self.stop_clicking)
                        break

            interval = self._get_interval_seconds()

            # --- Speed randomization ---
            if self.random_toggle.get() == 1:  # On
                try:
                    pct = float(self.random_pct.get()) / 100.0
                except ValueError:
                    pct = 0
                interval = max(0.001, interval * (1 + random.uniform(-pct, pct)))

            self._perform_click(interval)
            self.clicks_done += 1

            time.sleep(interval)

    def _perform_click(self, interval):
        """Perform a single click/keypress, honoring duty cycle (hold %) settings."""
        try:
            hold_pct = max(0.0, min(100.0, float(self.hold_duration_pct.get()))) / 100.0
        except ValueError:
            hold_pct = 0.0
        hold_time = interval * hold_pct if self.duty_mode.get() == 1 else 0.0

        if self.input_mode.get() == 0:  # Mouse
            btn_index = self.mouse_button_toggle.get()
            button = [MouseButton.left, MouseButton.middle, MouseButton.right][btn_index]

            def click_once():
                if hold_time > 0:
                    mouse.press(button)
                    time.sleep(hold_time)
                    mouse.release(button)
                else:
                    mouse.click(button)

            click_once()
            if self.double_click_toggle.get() == 1:  # double click on
                time.sleep(0.02)
                click_once()
        else:  # Keyboard
            key_str = self.keyboard_key.get() or "e"
            key = string_to_key(key_str)
            if hold_time > 0:
                keyboard.press(key)
                time.sleep(hold_time)
                keyboard.release(key)
            else:
                keyboard.press(key)
                keyboard.release(key)

    def _on_close(self):
        self.running = False
        self.cps_test_running = False
        if self.cps_test_after_id:
            try:
                self.root.after_cancel(self.cps_test_after_id)
            except Exception:
                pass
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self.root.destroy()


# ==========================================================================
# Splash screen — a short animated intro shown before the main GUI appears
# ==========================================================================
def _lerp_color(c1, c2, t):
    """Linearly interpolate between two '#rrggbb' colors, t in [0, 1]."""
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = round(r1 + (r2 - r1) * t)
    g = round(g1 + (g2 - g1) * t)
    b = round(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _ease_out_cubic(t):
    return 1 - (1 - t) ** 3


class SplashScreen:
    """Animated intro: a bolt icon rings into view, the title fades in
    letter by letter, and a progress bar fills, then the callback runs."""

    WIDTH = 420
    HEIGHT = 280
    TOTAL_MS = 2000  # total animation time in ms
    FPS_MS = 16       # ~60 fps

    def __init__(self, root, on_done):
        self.root = root
        self.on_done = on_done

        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.configure(bg=BG_MAIN)
        self.win.attributes("-topmost", True)
        self._center_window()

        self.canvas = tk.Canvas(self.win, width=self.WIDTH, height=self.HEIGHT,
                                 bg=BG_MAIN, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.start_ms = time.time() * 1000
        self._animate()

    def _center_window(self):
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = (sh - self.HEIGHT) // 2
        self.win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    def _animate(self):
        now = time.time() * 1000
        t = (now - self.start_ms) / self.TOTAL_MS  # 0..1 overall progress

        self.canvas.delete("all")
        cx = self.WIDTH // 2
        ring_cy = 95     # center of the ring/bolt icon
        title_y = 192    # baseline for the "NexoClicker" title
        bar_y = 228      # loading bar position
        subtitle_y = 252  # "Starting up..." position

        # --- Phase 1 (0.0 - 0.45): ring expands + bolt fades/scales in ---
        ring_t = _ease_out_cubic(min(1.0, t / 0.45))
        ring_radius = 26 + ring_t * 32  # max radius 58, bottom edge stays well above the title
        ring_color = _lerp_color(BG_PANEL, ACCENT_GREEN, ring_t)
        ring_width = 3 + (1 - ring_t) * 4
        self.canvas.create_oval(cx - ring_radius, ring_cy - ring_radius,
                                 cx + ring_radius, ring_cy + ring_radius,
                                 outline=ring_color, width=ring_width)

        bolt_t = _ease_out_cubic(min(1.0, max(0.0, (t - 0.05) / 0.35)))
        bolt_color = _lerp_color(BG_MAIN, ACCENT_GREEN, bolt_t)
        # Keep the bolt comfortably inside the ring at all times (bolt glyphs
        # render taller than their point size, so cap well below ring_radius).
        bolt_size = int(14 + bolt_t * 14)
        if bolt_t > 0:
            self.canvas.create_text(cx, ring_cy, text="⚡", font=("Segoe UI", bolt_size, "bold"),
                                     fill=bolt_color)

        # --- Phase 2 (0.35 - 0.75): title fades in letter by letter ---
        title = "NexoClicker"
        title_t = min(1.0, max(0.0, (t - 0.35) / 0.4))
        visible_chars = int(len(title) * _ease_out_cubic(title_t))
        shown = title[:visible_chars]
        fade_t = min(1.0, title_t * 1.4)
        title_color = _lerp_color(BG_MAIN, FG_TEXT, fade_t)
        if shown:
            self.canvas.create_text(cx, title_y, text=shown,
                                     font=("Segoe UI", 20, "bold"), fill=title_color)

        # --- Phase 3 (0.5 - 1.0): loading bar fills ---
        bar_t = _ease_out_cubic(min(1.0, max(0.0, (t - 0.5) / 0.5)))
        bar_w, bar_h = 260, 4
        bx = cx - bar_w // 2
        self.canvas.create_rectangle(bx, bar_y, bx + bar_w, bar_y + bar_h,
                                      outline="", fill=BG_INPUT)
        self.canvas.create_rectangle(bx, bar_y, bx + bar_w * bar_t, bar_y + bar_h,
                                      outline="", fill=ACCENT_GREEN)

        subtitle_color = _lerp_color(BG_MAIN, FG_MUTED, bar_t)
        self.canvas.create_text(cx, subtitle_y, text="Starting up...",
                                 font=("Segoe UI", 9), fill=subtitle_color)

        if t < 1.0:
            self.win.after(self.FPS_MS, self._animate)
        else:
            self.win.after(150, self._finish)

    def _finish(self):
        self.win.destroy()
        self.on_done()


def main():
    root = tk.Tk()
    root.withdraw()  # hide the main window until the splash animation is done

    def launch_main_app():
        root.deiconify()
        NexoClickerApp(root)

    SplashScreen(root, on_done=launch_main_app)
    root.mainloop()


if __name__ == "__main__":
    main()