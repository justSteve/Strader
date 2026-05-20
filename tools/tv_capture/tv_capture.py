"""
TV Screenshot Capture — process-based window detection.

Finds TradingView by process name (not window title), brings it
to foreground, captures its monitor, restores previous window.
Every 5 minutes during market hours.

Requires: pip install mss Pillow pywin32
Run on Windows side (not WSL).
"""

import ctypes
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import mss
import mss.tools
from mss import MSS
import win32con
import win32gui
import win32process
from pynput import keyboard

# --- Configuration ---
CAPTURE_INTERVAL_SEC = 300
SCREENSHOT_DIR = Path(r"C:\Tools\ScreenCaps\TradingView")
PROCESS_NAME = "tradingview.exe"
FLASH_DELAY_SEC = 0.3
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)
MARKET_TZ = "US/Central"

# --- Logging ---
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = SCREENSHOT_DIR / "tv_capture.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(open("CON", "w", encoding="utf-8")),
    ],
)
log = logging.getLogger("tv_capture")


def get_process_name(hwnd):
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return ""
        buf = ctypes.create_unicode_buffer(512)
        size = ctypes.c_uint(512)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buf, ctypes.byref(size))
        ctypes.windll.kernel32.CloseHandle(handle)
        return buf.value.lower().split("\\")[-1]
    except Exception:
        return ""


def find_tv_window():
    result = []

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if get_process_name(hwnd) == PROCESS_NAME:
                title = win32gui.GetWindowText(hwnd)
                result.append((hwnd, title))

    win32gui.EnumWindows(enum_handler, None)
    if result:
        log.info("Found: %s", [(t) for _, t in result])
        titled = [(h, t) for h, t in result if t.strip()]
        if titled:
            return titled[0][0]
        return result[0][0]
    log.error("No window found for process '%s'", PROCESS_NAME)
    return None


def get_monitor_for_window(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    with MSS() as sct:
        for i, mon in enumerate(sct.monitors[1:], start=1):
            if (mon['left'] <= cx < mon['left'] + mon['width'] and
                    mon['top'] <= cy < mon['top'] + mon['height']):
                return i
    return 1


def is_market_hours():
    now = datetime.now(ZoneInfo(MARKET_TZ))
    open_time = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0)
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0)
    return now.weekday() < 5 and open_time <= now <= close_time


def capture():
    prev_hwnd = win32gui.GetForegroundWindow()
    tv_hwnd = find_tv_window()

    if not tv_hwnd:
        return False

    try:
        win32gui.SetForegroundWindow(tv_hwnd)
    except Exception:
        ctypes.windll.user32.AllowSetForegroundWindow(
            win32process.GetCurrentProcessId())
        win32gui.ShowWindow(tv_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(tv_hwnd)

    time.sleep(FLASH_DELAY_SEC)

    monitor_idx = get_monitor_for_window(tv_hwnd)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filepath = SCREENSHOT_DIR / f"ES_{timestamp}.png"

    with MSS() as sct:
        monitor = sct.monitors[monitor_idx]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=str(filepath))

    log.info("Saved: %s", filepath.name)

    if prev_hwnd and prev_hwnd != tv_hwnd:
        try:
            win32gui.SetForegroundWindow(prev_hwnd)
        except Exception:
            pass

    return True


HOTKEY = keyboard.HotKey(
    keyboard.HotKey.parse("<ctrl>+<shift>+s"),
    lambda: threading.Thread(target=_hotkey_capture, daemon=True).start(),
)


def _hotkey_capture():
    log.info("Hotkey triggered — capturing")
    try:
        capture()
    except Exception:
        log.exception("Hotkey capture failed")


def _on_press(key):
    HOTKEY.press(HOTKEY._listener.canonical(key))


def _on_release(key):
    HOTKEY.release(HOTKEY._listener.canonical(key))


def main():
    log.info("TV Capture starting (process=%s, every %ds, hotkey=Ctrl+Shift+S)",
             PROCESS_NAME, CAPTURE_INTERVAL_SEC)
    log.info("Output: %s", SCREENSHOT_DIR)

    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    HOTKEY._listener = listener
    listener.start()
    log.info("Hotkey listener active: Ctrl+Shift+S")

    log.info("Initial capture...")
    capture()

    while True:
        time.sleep(CAPTURE_INTERVAL_SEC)
        if is_market_hours():
            try:
                capture()
            except Exception:
                log.exception("Capture failed")
        else:
            log.debug("Outside market hours")


if __name__ == "__main__":
    main()
