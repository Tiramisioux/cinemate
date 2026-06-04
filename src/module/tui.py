"""
CineMate TUI  –  cinemate --tui
────────────────────────────────
Curses HUD for SSH sessions.
Shows camera state, full GPIO pin map, I2C devices, WAV/clip status.
Runs alongside the normal runtime; HDMI GUI + logs are unchanged.
"""
from __future__ import annotations

import collections
import curses
import json
import logging
import os
import re
import subprocess
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from module.cli_commands import CommandExecutor
    from module.cinepi_controller import CinePiController
    from module.dmesg_monitor import DmesgMonitor
    from module.gpio_input import ComponentInitializer
    from module.gpio_output import GPIOOutput
    from module.redis_controller import RedisController
    from module.ssd_monitor import SSDMonitor
    from module.usb_monitor import USBMonitor

from module.redis_controller import ParameterKey
from module.utils import Utils


# ── constants ─────────────────────────────────────────────────────────────

_LOG_CAPACITY  = 8
_POLL_HZ       = 10      # main loop tick rate
_SLOW_INTERVAL = 1.0     # CPU / temp re-read cadence (s)
_I2C_INTERVAL  = 15.0    # i2cdetect scan cadence (s)

# BCM GPIO roles that never change
_I2C_PINS  = frozenset({2, 3})
_UART_PINS = frozenset({14, 15})
_SPI_PINS  = frozenset({9, 10, 11})

# All BCM GPIO numbers exposed on the 40-pin header
_ALL_BCM = list(range(2, 28))

# I2C address → friendly device name
_I2C_KNOWN: dict[int, str] = {
    0x04: "GroveADC",
    0x08: "GroveADC",
    0x3C: "OLED",
    0x3D: "OLED",
    0x49: "QuadRotary",
    0x50: "EEPROM",
    0x68: "RTC/DS3231",
    0x6F: "RTC/PCF8523",
    0x76: "BME280",
    0x77: "BME280",
}

# Redis keys that emit a log line on transition.
# Tuple: (message when truthy, message when falsy).  None = silent.
_LOG_TRIGGERS: dict[str, tuple[str | None, str | None]] = {
    ParameterKey.IS_RECORDING.value:           ("REC started",       "REC stopped"),
    ParameterKey.IS_MOUNTED.value:             ("Media mounted",      "Media unmounted"),
    ParameterKey.STORAGE_PREROLL_ACTIVE.value: ("Preroll active",     "Preroll done"),
    ParameterKey.DROP_FRAME.value:             ("DROP FRAME",         None),
    ParameterKey.MEMORY_ALERT.value:           ("Memory alert",       None),
    # Redraw-only — no log entry
    ParameterKey.FRAMECOUNT.value:             (None, None),
    ParameterKey.BUFFER.value:                 (None, None),
    ParameterKey.IS_WRITING.value:             (None, None),
    ParameterKey.IS_BUFFERING.value:           (None, None),
    ParameterKey.RECORDING_TC_TOD.value:       (None, None),
    ParameterKey.RECORDING_TC_REC.value:       (None, None),
    ParameterKey.RECORDING_TIME.value:         (None, None),
    ParameterKey.WRITE_SPEED_TO_DRIVE.value:   (None, None),
    ParameterKey.FPS_ACTUAL.value:             (None, None),
}


# ── tiny value helpers ────────────────────────────────────────────────────

def _s(val, default="—") -> str:
    if val is None:
        return default
    v = str(val).strip()
    return v if v and v.lower() not in ("none", "null", "") else default


def _b(val) -> bool:
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "on")
    return bool(val)


def _i(val, default=0) -> int:
    try:
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _f(val, default=0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ── color pair indices ────────────────────────────────────────────────────
# Defined in _setup_colors(); referenced by integer throughout.
_CP_REC      = 1   # bright red text
_CP_OK       = 2   # green text
_CP_WARN     = 3   # yellow text
_CP_LABEL    = 4   # cyan text (dim labels)
_CP_VAL      = 5   # white bold text
_CP_MAGENTA  = 6   # magenta text (sync / SPI)
_CP_RECBG    = 7   # black-on-red banner
_CP_IDLEBG   = 8   # black-on-white banner
_CP_DIM      = 9   # dark grey (unassigned GPIO)
_CP_BLUE     = 10  # UART pins


# ═══════════════════════════════════════════════════════════════════════════
class CinemateTUI(threading.Thread):
    """
    Terminal heads-up display.
    Owns curses on the SSH stdin/stdout; never touches /dev/tty1 or the framebuffer.
    """

    def __init__(
        self,
        redis_controller:   "RedisController",
        cinepi_controller:  "CinePiController",
        ssd_monitor:        "SSDMonitor",
        dmesg_monitor:      "DmesgMonitor",
        usb_monitor:        "USBMonitor",
        gpio_input:         "ComponentInitializer",
        gpio_output:        "GPIOOutput",
        command_executor:   "CommandExecutor",
        settings:           dict,
    ):
        super().__init__(daemon=True, name="CinemateTUI")
        self.rc   = redis_controller
        self.cc   = cinepi_controller
        self.ssd  = ssd_monitor
        self.dmsg = dmesg_monitor
        self.usb  = usb_monitor
        self.gin  = gpio_input
        self.gout = gpio_output
        self.cmd  = command_executor
        self.cfg  = settings or {}

        self._stop   = threading.Event()
        self._dirty  = threading.Event()

        # Event log
        self._log: collections.deque[str] = collections.deque(maxlen=_LOG_CAPACITY)

        # Command-line input
        self._buf      = ""
        self._history: list[str] = []
        self._hist_idx = -1

        # Slow-refresh cache (CPU, temp, SSD info)
        self._slow:    dict = {}
        self._slow_ts: float = 0.0

        # I2C scan cache
        self._i2c_found:   set[int] = set()
        self._i2c_ts:      float = 0.0
        self._i2c_lock     = threading.Lock()

        # Previous Redis values for transition detection
        self._prev: dict[str, str] = {}

        # GPIO pin map derived from settings (built once)
        self._pin_map: dict[int, dict] = self._build_pin_map()

        # Subscribe for push redraws
        self.rc.redis_parameter_changed.subscribe(self._on_redis)

    # ── lifecycle ─────────────────────────────────────────────────────────

    def stop(self):
        self._stop.set()
        self._dirty.set()

    def _log_evt(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log.append(f"[{ts}] {msg}")

    # ── Redis push handler ────────────────────────────────────────────────

    def _on_redis(self, data):
        if not data:
            self._dirty.set()
            return

        key = data.get("key", "")
        val = data.get("value", "")
        prev = self._prev.get(key)
        self._prev[key] = val

        # Detect mic attach/detach via redis (if published), else fall through
        if key == "mic_connected":
            mic = _b(val)
            if mic != _b(prev or "0"):
                self._log_evt("Mic connected" if mic else "Mic disconnected")

        elif key in _LOG_TRIGGERS:
            truthy_msg, falsy_msg = _LOG_TRIGGERS[key]
            is_now  = _b(val)
            was_now = _b(prev) if prev is not None else is_now
            if is_now != was_now:
                msg = truthy_msg if is_now else falsy_msg
                if msg:
                    self._log_evt(msg)

        self._dirty.set()

    # ── GPIO pin map ──────────────────────────────────────────────────────

    def _build_pin_map(self) -> dict[int, dict]:
        """Build role table for BCM 2-27 from settings and hardware config."""
        pm: dict[int, dict] = {}

        # Fixed function pins
        for p in _I2C_PINS:
            pm[p] = {"role": "I2C", "group": "i2c"}
        for p in _UART_PINS:
            pm[p] = {"role": "UAR", "group": "uart"}
        for p in _SPI_PINS:
            pm[p] = {"role": "SPI", "group": "spi"}

        cfg = self.cfg

        # Buttons
        for btn in cfg.get("buttons", []):
            try:
                p = int(btn["pin"])
                action = ""
                for akey in ("press_action", "single_click_action", "hold_action"):
                    a = btn.get(akey)
                    if isinstance(a, dict):
                        action = a.get("method", "")
                        break
                    elif isinstance(a, str) and a.lower() not in ("none", ""):
                        action = a
                        break
                pm[p] = {"role": "BTN", "group": "button", "action": action}
            except (KeyError, ValueError, TypeError):
                pass

        # Two-way switches
        for sw in cfg.get("two_way_switches", []):
            try:
                p = int(sw["pin"])
                action = ""
                a = sw.get("state_on_action")
                if isinstance(a, dict):
                    action = a.get("method", "")
                pm[p] = {"role": "SW ", "group": "switch", "action": action}
            except (KeyError, ValueError, TypeError):
                pass

        # Three-way switches
        for sw in cfg.get("three_way_switches", []):
            for p in sw.get("pins", []):
                try:
                    pm[int(p)] = {"role": "SW3", "group": "switch"}
                except (ValueError, TypeError):
                    pass

        # Rotary encoders (GPIO-level, not I2C)
        for enc in cfg.get("rotary_encoders", []):
            for field, role in (("clk_pin", "CLK"), ("dt_pin", "DT "), ("button_pin", "EBT")):
                v = enc.get(field)
                if v and str(v).lower() not in ("none", ""):
                    try:
                        pm[int(v)] = {"role": role, "group": "encoder"}
                    except (ValueError, TypeError):
                        pass

        # GPIO outputs
        gpio_cfg = cfg.get("gpio_output", {})
        for p in gpio_cfg.get("rec_out_pin", []):
            try:
                pm[int(p)] = {"role": "ROU", "group": "rec_out"}
            except (ValueError, TypeError):
                pass

        rec_tone = gpio_cfg.get("rec_tone_pin")
        if rec_tone not in (None, "None", []):
            pins = rec_tone if isinstance(rec_tone, list) else [rec_tone]
            for p in pins:
                try:
                    pm[int(p)] = {"role": "RTO", "group": "rec_tone"}
                except (ValueError, TypeError):
                    pass

        return pm

    # ── I2C background scan ───────────────────────────────────────────────

    def _schedule_i2c_scan(self):
        """Kick off a background i2cdetect if the cache is stale."""
        now = time.monotonic()
        with self._i2c_lock:
            if now - self._i2c_ts < _I2C_INTERVAL:
                return
            self._i2c_ts = now  # prevent concurrent launches

        t = threading.Thread(target=self._run_i2c_scan, daemon=True)
        t.start()

    def _run_i2c_scan(self):
        try:
            result = subprocess.run(
                ["i2cdetect", "-y", "1"],
                capture_output=True, text=True, timeout=5,
            )
            found: set[int] = set()
            for line in result.stdout.splitlines():
                # Lines look like: "20: -- -- -- -- -- -- -- 27 ..."
                parts = line.split(":")
                if len(parts) < 2:
                    continue
                for token in parts[1].split():
                    token = token.strip()
                    if re.fullmatch(r"[0-9a-fA-F]{2}", token):
                        found.add(int(token, 16))
            with self._i2c_lock:
                self._i2c_found = found
        except Exception:
            pass
        self._dirty.set()

    # ── slow cache ────────────────────────────────────────────────────────

    def _refresh_slow(self, now: float):
        if now - self._slow_ts < _SLOW_INTERVAL:
            return
        self._slow_ts = now
        for key, fn in (("cpu", Utils.cpu_load), ("temp", Utils.cpu_temp), ("ram", Utils.memory_usage)):
            try:
                self._slow[key] = fn()
            except Exception:
                self._slow.setdefault(key, "?")

        # Detect mic change for log event
        mic_now = getattr(self.usb, "usb_mic", None) is not None
        mic_was = self._slow.get("_mic_prev")
        if mic_was is not None and mic_now != mic_was:
            self._log_evt("Mic connected" if mic_now else "Mic disconnected")
        self._slow["_mic_prev"] = mic_now

        # Detect undervoltage change for log
        volt_now = bool(getattr(self.dmsg, "undervoltage_flag", False))
        volt_was = self._slow.get("_volt_prev")
        if volt_was is not None and volt_now and not volt_was:
            self._log_evt("Undervoltage detected")
        self._slow["_volt_prev"] = volt_now

    # ── thread entry ──────────────────────────────────────────────────────

    def run(self):
        try:
            curses.wrapper(self._main)
        except Exception as exc:
            logging.warning("CinemateTUI exited: %s", exc)

    def _main(self, stdscr):
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        self._setup_colors()
        self._log_evt("TUI ready  (Tab: complete  Up/Down: history  Esc: clear)")

        # Seed prev-values from Redis cache
        for k in _LOG_TRIGGERS:
            v = self.rc.get_value(k)
            if v is not None:
                self._prev[k] = str(v)

        self._schedule_i2c_scan()

        while not self._stop.is_set():
            self._dirty.wait(timeout=1.0 / _POLL_HZ)
            self._dirty.clear()

            rows, cols = stdscr.getmaxyx()
            if rows < 16 or cols < 60:
                stdscr.erase()
                stdscr.addstr(0, 0, "Terminal too small — resize to at least 60×16")
                stdscr.refresh()
                continue

            now = time.monotonic()
            self._refresh_slow(now)
            self._schedule_i2c_scan()
            self._draw(stdscr, rows, cols)
            self._handle_key(stdscr)

        curses.curs_set(1)

    # ── color setup ───────────────────────────────────────────────────────

    def _setup_colors(self):
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(_CP_REC,     curses.COLOR_RED,     -1)
        curses.init_pair(_CP_OK,      curses.COLOR_GREEN,   -1)
        curses.init_pair(_CP_WARN,    curses.COLOR_YELLOW,  -1)
        curses.init_pair(_CP_LABEL,   curses.COLOR_CYAN,    -1)
        curses.init_pair(_CP_VAL,     curses.COLOR_WHITE,   -1)
        curses.init_pair(_CP_MAGENTA, curses.COLOR_MAGENTA, -1)
        curses.init_pair(_CP_RECBG,   curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(_CP_IDLEBG,  curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(_CP_DIM,     curses.COLOR_BLACK + 8 if hasattr(curses, "COLOR_BLACK") else curses.COLOR_WHITE, -1)
        curses.init_pair(_CP_BLUE,    curses.COLOR_BLUE,    -1)

    def _cp(self, pair: int, bold=False) -> int:
        a = curses.color_pair(pair)
        if bold:
            a |= curses.A_BOLD
        return a

    # ── safe draw ─────────────────────────────────────────────────────────

    def _put(self, win, y: int, x: int, text: str, attr: int = 0, width: int = 0):
        rows, cols = win.getmaxyx()
        if y < 0 or y >= rows or x < 0 or x >= cols:
            return
        if width:
            text = f"{text:<{width}}"[:width]
        text = text[:cols - x]
        if not text:
            return
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass

    def _hline(self, win, y: int, cols: int):
        self._put(win, y, 0, "─" * cols)

    def _sep(self, win, row: int, cols: int) -> int:
        self._hline(win, row, cols)
        return row + 1

    def _rget(self, key: ParameterKey, default="—") -> str:
        return _s(self.rc.get_value(key.value), default)

    # ── full frame ────────────────────────────────────────────────────────

    def _draw(self, win, rows: int, cols: int):
        win.erase()
        is_rec = _b(self.rc.get_value(ParameterKey.IS_RECORDING.value) or 0)

        row = 0
        row = self._s_header(win, row, cols, is_rec)
        row = self._sep(win, row, cols)
        row = self._s_params(win, row, cols)
        row = self._sep(win, row, cols)
        row = self._s_buffer(win, row, cols)
        row = self._sep(win, row, cols)
        row = self._s_clip_audio(win, row, cols)
        row = self._sep(win, row, cols)

        # GPIO bar — needs ≥ 6 free rows above log+input
        budget = rows - row - 4  # 1 sys + 1 sep + 2 log+input + 1 sep
        if budget >= 5:
            row = self._s_gpio(win, row, cols)
            row = self._sep(win, row, cols)
        if budget >= 6:
            row = self._s_i2c(win, row, cols)
            row = self._sep(win, row, cols)

        row = self._s_system(win, row, cols)
        row = self._sep(win, row, cols)

        log_rows = max(2, rows - row - 3)
        row = self._s_log(win, row, cols, log_rows)
        self._hline(win, rows - 2, cols)
        self._s_input(win, rows - 1, cols)

        win.refresh()

    # ── section: header ───────────────────────────────────────────────────

    def _s_header(self, win, row: int, cols: int, is_rec: bool) -> int:
        if is_rec:
            blink  = int(time.time() * 2) % 2 == 0
            badge  = " ● REC " if blink else "   REC "
            hattr  = self._cp(_CP_RECBG, bold=True)
        else:
            badge  = " ○ IDLE"
            hattr  = self._cp(_CP_IDLEBG)

        tc_tod  = self._rget(ParameterKey.RECORDING_TC_TOD, "00:00:00:00")
        rec_raw = self._rget(ParameterKey.RECORDING_TIME, "0")
        frames  = self._rget(ParameterKey.FRAMECOUNT, "0")

        try:
            s = int(float(rec_raw))
            elapsed = f"{s//3600:02d}:{(s % 3600)//60:02d}:{s % 60:02d}"
        except (ValueError, TypeError):
            elapsed = "00:00:00"

        try:
            cams = json.loads(self.rc.get_value(ParameterKey.CAMERAS.value) or "[]") or []
            cams.sort(key=lambda c: c.get("port", ""))
            sensor = cams[0].get("model", "").upper().replace("IMX", "") if cams else "—"
        except Exception:
            sensor = "—"

        date_str = time.strftime("%Y-%m-%d  %H:%M:%S")
        body = f"  TC {tc_tod}  {elapsed}  | FRAME {int(frames):>6}  |  {sensor}  |  {date_str}"
        self._put(win, row, 0, (badge + body).ljust(cols)[:cols], hattr)
        return row + 1

    # ── section: camera params ────────────────────────────────────────────

    def _s_params(self, win, row: int, cols: int) -> int:
        try:
            fps_val = str(round(float(self.rc.get_value(ParameterKey.FPS_USER.value) or 0)))
        except (TypeError, ValueError):
            fps_val = "—"

        try:
            sh = float(self.rc.get_value(ParameterKey.SHUTTER_A_ACTUAL.value) or 0)
            shutter = f"{sh:.1f}°"
        except (TypeError, ValueError):
            shutter = "—"

        iso = self._rget(ParameterKey.ISO)
        wb  = self._rget(ParameterKey.WB_USER)
        w   = self._rget(ParameterKey.WIDTH,     "0")
        h   = self._rget(ParameterKey.HEIGHT,    "0")
        bd  = self._rget(ParameterKey.BIT_DEPTH, "?")

        sync = getattr(self.cc, "shutter_a_sync_mode", 0) != 0

        fields = [
            ("FPS",     fps_val,           sync),
            ("SHUTTER", shutter,            sync),
            ("EI",      iso,                False),
            ("WB",      f"{wb} K",          False),
            ("RES",     f"{w}×{h} :{bd}b", False),
        ]
        col_w = cols // len(fields)
        for i, (lbl, val, hi) in enumerate(fields):
            x = i * col_w
            vattr = self._cp(_CP_OK, bold=True) if hi else self._cp(_CP_VAL, bold=True)
            self._put(win, row,     x, lbl, self._cp(_CP_LABEL), col_w - 1)
            self._put(win, row + 1, x, val, vattr,               col_w - 1)

        return row + 2

    # ── section: buffer / storage ─────────────────────────────────────────

    def _s_buffer(self, win, row: int, cols: int) -> int:
        buf_used  = _i(self.rc.get_value(ParameterKey.BUFFER.value),      0)
        buf_size  = _i(self.rc.get_value(ParameterKey.BUFFER_SIZE.value), 1) or 1
        preroll   = _b(self.rc.get_value(ParameterKey.STORAGE_PREROLL_ACTIVE.value) or 0)
        drop      = _b(self.rc.get_value(ParameterKey.DROP_FRAME.value) or 0)
        mounted   = _b(self.rc.get_value(ParameterKey.IS_MOUNTED.value) or 0)

        bar_w  = 16
        filled = min(bar_w, int((buf_used / buf_size) * bar_w))
        bar    = "█" * filled + "░" * (bar_w - filled)

        if mounted and self.ssd:
            space   = _f(getattr(self.ssd, "space_left", 0))
            wspeed  = _f(getattr(self.ssd, "write_speed_mb_s", 0))
            fsz     = _f(getattr(self.cc, "file_size", 0))
            fps_v   = _f(self.rc.get_value(ParameterKey.FPS_USER.value), 24)
            try:
                mins = (space * 1000 / (fsz * fps_v * 60)) if fsz and fps_v else 0
                disk_str  = f"{round(mins)} MIN"
            except ZeroDivisionError:
                disk_str = "—"
            write_str = f"{wspeed:.0f} MB/s"
        else:
            disk_str  = "NO DISK"
            write_str = ""

        pre_tag  = " [PREROLL]" if preroll else ""
        drop_tag = "  DROP !" if drop else ""
        line = f"BUF [{bar}] {buf_used}/{buf_size}  DISK {disk_str}  WRITE {write_str}{pre_tag}"

        buf_attr = self._cp(_CP_WARN, bold=True) if drop else (
            self._cp(_CP_LABEL) if preroll else self._cp(_CP_VAL)
        )
        self._put(win, row, 0, line, buf_attr)
        if drop:
            dx = min(cols - len(drop_tag) - 1, cols - 1)
            self._put(win, row, dx, drop_tag, self._cp(_CP_RECBG, bold=True))
        return row + 1

    # ── section: clip names + audio ───────────────────────────────────────

    def _s_clip_audio(self, win, row: int, cols: int) -> int:
        mid = max(cols // 2, 30)

        # --- clip names ---
        preroll = _b(self.rc.get_value(ParameterKey.STORAGE_PREROLL_ACTIVE.value) or 0)
        cam0_path = self.rc.get_value(ParameterKey.LAST_DNG_CAM0.value)
        cam1_path = self.rc.get_value(ParameterKey.LAST_DNG_CAM1.value)

        def _clip(path):
            if not path or preroll or "None" in str(path):
                return None
            stem = os.path.splitext(os.path.basename(path))[0]
            return re.sub(r"_cam[01]$", "", stem, flags=re.IGNORECASE)

        clip0 = _clip(cam0_path)
        clip1 = _clip(cam1_path)

        self._put(win, row, 0, "CLIP", self._cp(_CP_LABEL))
        cv = self._cp(_CP_VAL, bold=True)
        cl = self._cp(_CP_LABEL)
        if clip0 and clip1:
            self._put(win, row,     5, clip0[:mid - 6], cv)
            self._put(win, row + 1, 5, clip1[:mid - 6], cl)
        elif clip0 or clip1:
            self._put(win, row, 5, (clip0 or clip1)[:mid - 6], cv)

        # --- audio / WAV ---
        mic  = getattr(self.usb, "usb_mic", None)
        amon = getattr(self.usb, "audio_monitor", None) if self.usb else None

        self._put(win, row, mid, "AUD", self._cp(_CP_LABEL))
        ax = mid + 4

        if mic is not None:
            sr  = getattr(amon, "sample_rate", None) or getattr(amon, "audio_sample_rate", None)
            bd  = getattr(amon, "bit_depth", None)
            sr_str = "—"
            if sr:
                try:
                    sr_str = f"{int(round(sr / 1000))}kHz"
                except (TypeError, ValueError):
                    pass
            bd_str = f"{bd}b" if bd else "—"
            self._put(win, row, ax, f"{sr_str}  {bd_str}", self._cp(_CP_OK, bold=True))
        else:
            self._put(win, row, ax, "no mic", self._cp(_CP_DIM))

        # WAV saved indicator (last take)
        try:
            _, dng_count, wav_count = (self._slow.get("latest") or (None, 0, 0))
        except (TypeError, ValueError):
            dng_count = wav_count = 0
        is_active = any(_b(self.rc.get_value(k.value) or 0) for k in (
            ParameterKey.IS_RECORDING, ParameterKey.IS_WRITING, ParameterKey.IS_BUFFERING,
        ))
        wav_ok = not is_active and dng_count > 0 and wav_count > 0

        sync = _b(self.rc.get_value(ParameterKey.FRAMES_IN_SYNC.value) or 1)
        sync_str = "SYNC OK" if sync else "SYNC !!"
        wav_str  = "WAV  OK" if wav_ok else ("WAV  --" if not is_active else "WAV  ..")
        self._put(win, row + 1, mid,     sync_str,
                  self._cp(_CP_OK) if sync else self._cp(_CP_WARN, bold=True))
        self._put(win, row + 1, mid + 9, wav_str,
                  self._cp(_CP_OK) if wav_ok else self._cp(_CP_DIM))

        # VU meter (inline, compact)
        try:
            raw_vu = self.rc.rc.get("audio_vu")  # direct redis access
            if raw_vu:
                raw_vu = raw_vu.decode() if isinstance(raw_vu, bytes) else str(raw_vu)
                levels = [max(0, min(100, int(round(float(v))))) for v in raw_vu.split("|") if v.strip()]
                if levels:
                    bar_w = (cols - mid - 5) // len(levels) - 1
                    bar_w = max(4, min(bar_w, 14))
                    vus = []
                    for lv in levels[:2]:
                        filled = int((lv / 100) * bar_w)
                        color = ("█" * filled + "░" * (bar_w - filled))
                        vus.append(color)
                    vu_str = "  ".join(vus)
                    vu_attr = self._cp(_CP_OK) if max(levels) < 85 else self._cp(_CP_WARN, bold=True)
                    self._put(win, row + 2, mid, vu_str, vu_attr)
        except Exception:
            pass

        return row + 3

    # ── section: GPIO bar ─────────────────────────────────────────────────

    def _s_gpio(self, win, row: int, cols: int) -> int:
        """
        Two-row display of BCM GPIO 2-27.
        Row 0: pin numbers (colored by role / live state)
        Row 1: role label (BTN, SW, I2C, OUT …)
        Repeated for pins 2-14 on lines 0-1, pins 15-27 on lines 2-3.
        """
        is_rec = _b(self.rc.get_value(ParameterKey.IS_RECORDING.value) or 0)

        # Live button state lookup
        btn_states: dict[str, str] = {}
        for btn in getattr(self.gin, "smart_buttons_list", []) or []:
            try:
                state = btn.get_button_state()
                btn_states[str(btn.identifier)] = state.get("state", "released") \
                    if isinstance(state, dict) else str(state)
            except Exception:
                btn_states[str(btn.identifier)] = "released"

        def _pin_attr(bcm: int) -> tuple[str, int]:
            """Return (role_label, curses_attr) for a BCM pin number."""
            info = self._pin_map.get(bcm)
            if info is None:
                return "---", self._cp(_CP_DIM)

            group = info.get("group", "")
            role  = info.get("role", "---")

            if group == "i2c":
                return role, self._cp(_CP_LABEL, bold=True)

            if group == "uart":
                return role, self._cp(_CP_BLUE, bold=True)

            if group == "spi":
                return role, self._cp(_CP_MAGENTA)

            if group == "encoder":
                return role, self._cp(_CP_WARN)

            if group == "button":
                pressed = btn_states.get(str(bcm), "released") == "pressed"
                attr = self._cp(_CP_OK, bold=True) if pressed else self._cp(_CP_OK)
                return role, attr

            if group == "switch":
                # Infer switch state from associated Redis key where possible
                return role, self._cp(_CP_WARN)

            if group in ("rec_out", "rec_tone"):
                attr = self._cp(_CP_REC, bold=True) if is_rec else self._cp(_CP_DIM)
                return role, attr

            return "---", self._cp(_CP_DIM)

        prefix = "GPIO "
        cell_w = 4  # " 02" + separator space

        def _draw_half(start_row: int, pins: list[int]):
            self._put(win, start_row,     0, prefix, self._cp(_CP_LABEL))
            self._put(win, start_row + 1, 0, " " * len(prefix), 0)
            x = len(prefix)
            for bcm in pins:
                if x + cell_w > cols:
                    break
                role, attr = _pin_attr(bcm)
                num_str = f"{bcm:02d} "
                role_str = f"{role[:3]:<3} "
                self._put(win, start_row,     x, num_str,  attr)
                self._put(win, start_row + 1, x, role_str, attr)
                x += cell_w

        first_half  = _ALL_BCM[:13]   # BCM 2-14
        second_half = _ALL_BCM[13:]   # BCM 15-27

        _draw_half(row,     first_half)
        _draw_half(row + 2, second_half)

        return row + 4

    # ── section: I2C devices ──────────────────────────────────────────────

    def _s_i2c(self, win, row: int, cols: int) -> int:
        self._put(win, row, 0, "I2C ", self._cp(_CP_LABEL))
        x = 4

        with self._i2c_lock:
            detected = set(self._i2c_found)

        # Build list: configured devices from settings + detected from scan
        shown: dict[int, str] = {}

        cfg = self.cfg
        if cfg.get("i2c_oled", {}).get("enabled"):
            shown.setdefault(0x3C, "OLED")
        if cfg.get("quad_rotary_controller", {}).get("enabled"):
            shown.setdefault(0x49, "QuadRotary")
        if cfg.get("grove_base_hat_adc", {}).get("enabled"):
            shown.setdefault(0x08, "GroveADC")

        # Add anything found by scan
        for addr in sorted(detected):
            shown.setdefault(addr, _I2C_KNOWN.get(addr, f"0x{addr:02X}"))

        if not shown:
            self._put(win, row, x, "scanning...", self._cp(_CP_DIM))
            return row + 1

        for addr, name in sorted(shown.items()):
            ok      = addr in detected
            tag     = "[OK]" if ok else "[--]"
            attr    = self._cp(_CP_OK, bold=True) if ok else self._cp(_CP_DIM)
            entry   = f"0x{addr:02X} {name} {tag}   "
            if x + len(entry) > cols:
                break
            self._put(win, row, x, entry, attr)
            x += len(entry)

        return row + 1

    # ── section: system ───────────────────────────────────────────────────

    def _s_system(self, win, row: int, cols: int) -> int:
        cpu  = self._slow.get("cpu",  "?")
        temp = self._slow.get("temp", "?")
        ram  = self._slow.get("ram",  "?")

        lock = _b(getattr(self.cc, "parameters_lock", False))
        volt = bool(getattr(self.dmsg, "undervoltage_flag", False)) if self.dmsg else False

        flags = ""
        if lock: flags += "  LOCK"
        if volt: flags += "  VOLT!"

        left = f"SYS  CPU {cpu}  TEMP {temp}  RAM {ram}{flags}"
        self._put(win, row, 0, left, self._cp(_CP_VAL))

        # Battery (PiSugar)
        batt = getattr(self.cc, "_battery_monitor", None) or \
               getattr(self.cc, "battery_monitor",  None)
        if batt is None:
            # Try to find it via the attributes we know exist
            pass
        bat_level   = None
        bat_charging = False
        try:
            from module.battery_monitor import BatteryMonitor
            for attr in vars(self.cc).values():
                if isinstance(attr, BatteryMonitor):
                    bat_level   = attr.battery_level
                    bat_charging = attr.charging
                    break
        except Exception:
            pass

        if bat_level is not None:
            charging = "+" if bat_charging else " "
            bat_str  = f"  BAT {bat_level}%{charging}"
            self._put(win, row, len(left), bat_str,
                      self._cp(_CP_OK) if bat_charging else self._cp(_CP_WARN))

        return row + 1

    # ── section: log ─────────────────────────────────────────────────────

    def _s_log(self, win, row: int, cols: int, n_rows: int) -> int:
        lines = list(self._log)[-n_rows:]
        for i, line in enumerate(lines):
            self._put(win, row + i, 0, line, self._cp(_CP_LABEL), cols - 1)
        return row + n_rows

    # ── section: command input ────────────────────────────────────────────

    def _s_input(self, win, row: int, cols: int):
        prompt  = "> "
        max_buf = cols - len(prompt) - 2
        display = self._buf[-max_buf:] if len(self._buf) > max_buf else self._buf
        line    = prompt + display
        self._put(win, row, 0, line, self._cp(_CP_VAL, bold=True))
        try:
            curses.curs_set(1)
            win.move(row, min(len(line), cols - 1))
        except curses.error:
            pass

    # ── keyboard input ────────────────────────────────────────────────────

    def _handle_key(self, win):
        try:
            key = win.getch()
        except curses.error:
            return
        if key == curses.ERR:
            return

        if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
            self._submit()
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            self._buf = self._buf[:-1]
            self._dirty.set()
        elif key == curses.KEY_UP:
            if self._history:
                if self._hist_idx < 0:
                    self._hist_idx = len(self._history) - 1
                else:
                    self._hist_idx = max(0, self._hist_idx - 1)
                self._buf = self._history[self._hist_idx]
                self._dirty.set()
        elif key == curses.KEY_DOWN:
            if self._hist_idx >= 0:
                self._hist_idx += 1
                if self._hist_idx >= len(self._history):
                    self._hist_idx = -1
                    self._buf = ""
                else:
                    self._buf = self._history[self._hist_idx]
                self._dirty.set()
        elif key == 9:   # TAB
            self._tab_complete()
            self._dirty.set()
        elif key == 27:  # ESC
            self._buf = ""
            self._hist_idx = -1
            self._dirty.set()
        elif 32 <= key <= 126:
            self._buf += chr(key)
            self._hist_idx = -1
            self._dirty.set()

    def _submit(self):
        cmd = self._buf.strip()
        self._buf = ""
        self._hist_idx = -1
        self._dirty.set()
        if not cmd:
            return
        self._history.append(cmd)
        self._log_evt(f"> {cmd}")
        try:
            self.cmd.handle_received_data(cmd + "\n")
        except Exception as exc:
            self._log_evt(f"  error: {exc}")

    def _tab_complete(self):
        if not self.cmd:
            return
        buf = self._buf.lower()
        if not buf:
            return
        matches = [k for k in self.cmd.commands if k.startswith(buf)]
        if len(matches) == 1:
            self._buf = matches[0] + " "
        elif matches:
            common = os.path.commonprefix(matches)
            if len(common) > len(buf):
                self._buf = common
