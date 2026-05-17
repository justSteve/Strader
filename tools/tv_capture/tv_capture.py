"""
TV Screenshot Capture — flash-and-snap tray app.

Runs in Windows system tray. Every 5 minutes during market hours,
prompts for capture. User hits Ctrl+Shift+S or auto-captures after 30s.

Requires: pip install -r requirements.txt
Run on Windows side (not WSL).
"""

import ctypes
import threading
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import mss
import mss.tools
import pystray
import win32con
import win32gui
import win32process
from PIL import Image
from pynput import keyboard
from winotify import Notification, audio

# --- Configuration ---
CAPTURE_INTERVAL_SEC = 300
GRACE_PERIOD_SEC = 30
HOTKEY = {keyboard.Key.ctrl_l, keyboard.Key.shift, keyboard.KeyCode.from_char('s')}
SCREENSHOT_DIR = Path(r"C:\Tools\ScreenCaps\TradingView")
TV_WINDOW_TITLE_FRAGMENT = "TradingView"
FLASH_DELAY_SEC = 0.3
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)
MARKET_TZ = "US/Central"

# --- State ---
capture_due = threading.Event()
current_keys = set()
tray_icon = None
running = True


def find_tv_window():
    result = []

    def enum_handler(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if TV_WINDOW_TITLE_FRAGMENT.lower() in title.lower():
                result.append(hwnd)

    win32gui.EnumWindows(enum_handler, None)
    return result[0] if result else None


def get_monitor_for_window(hwnd):
    rect = win32gui.GetWindowRect(hwnd)
    win_center_x = (rect[0] + rect[2]) // 2
    win_center_y = (rect[1] + rect[3]) // 2
    with mss.mss() as sct:
        for i, mon in enumerate(sct.monitors[1:], start=1):
            if (mon['left'] <= win_center_x < mon['left'] + mon['width'] and
                    mon['top'] <= win_center_y < mon['top'] + mon['height']):
                return i
    return 1


def capture_screenshot():
    prev_hwnd = win32gui.GetForegroundWindow()
    tv_hwnd = find_tv_window()

    if not tv_hwnd:
        notify("TV Capture", "TradingView window not found!")
        return

    try:
        win32gui.SetForegroundWindow(tv_hwnd)
    except Exception:
        ctypes.windll.user32.AllowSetForegroundWindow(win32process.GetCurrentProcessId())
        win32gui.ShowWindow(tv_hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(tv_hwnd)

    time.sleep(FLASH_DELAY_SEC)

    monitor_idx = get_monitor_for_window(tv_hwnd)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = SCREENSHOT_DIR / f"tv_{timestamp}.png"

    with mss.mss() as sct:
        monitor = sct.monitors[monitor_idx]
        img = sct.grab(monitor)
        mss.tools.to_png(img.rgb, img.size, output=str(filepath))

    if prev_hwnd and prev_hwnd != tv_hwnd:
        try:
            win32gui.SetForegroundWindow(prev_hwnd)
        except Exception:
            pass

    capture_due.clear()
    notify("TV Capture", f"Saved: {filepath.name}")


def notify(title, message):
    try:
        toast = Notification(app_id="TV Capture", title=title, msg=message)
        toast.set_audio(audio.Default, loop=False)
        toast.show()
    except Exception:
        pass


def is_market_hours():
    now = datetime.now(ZoneInfo(MARKET_TZ))
    open_time = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0)
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0)
    return now.weekday() < 5 and open_time <= now <= close_time


def timer_loop():
    while running:
        time.sleep(CAPTURE_INTERVAL_SEC)
        if not running:
            break
        if not is_market_hours():
            continue
        capture_due.set()
        notify("TV Capture", f"Screenshot due — Ctrl+Shift+S or auto in {GRACE_PERIOD_SEC}s")
        deadline = time.time() + GRACE_PERIOD_SEC
        while capture_due.is_set() and time.time() < deadline and running:
            time.sleep(0.5)
        if capture_due.is_set() and running:
            capture_screenshot()


def on_key_press(key):
    current_keys.add(key)
    if all(k in current_keys for k in HOTKEY):
        current_keys.clear()
        threading.Thread(target=capture_screenshot, daemon=True).start()


def on_key_release(key):
    current_keys.discard(key)


def create_tray_icon():
    img = Image.new('RGB', (64, 64), color=(34, 139, 34))
    menu = pystray.Menu(
        pystray.MenuItem("Capture Now", lambda: threading.Thread(target=capture_screenshot, daemon=True).start()),
        pystray.MenuItem("Quit", quit_app),
    )
    return pystray.Icon("tv_capture", img, "TV Capture", menu)


def quit_app(icon=None, item=None):
    global running
    running = False
    if tray_icon:
        tray_icon.stop()


def main():
    global tray_icon

    print(f"TV Capture starting...")
    print(f"  Hotkey: Ctrl+Shift+S")
    print(f"  Interval: {CAPTURE_INTERVAL_SEC}s")
    print(f"  Output: {SCREENSHOT_DIR}")

    listener = keyboard.Listener(on_press=on_key_press, on_release=on_key_release)
    listener.start()

    timer_thread = threading.Thread(target=timer_loop, daemon=True)
    timer_thread.start()

    tray_icon = create_tray_icon()
    tray_icon.run()

    listener.stop()
    print("TV Capture stopped.")


if __name__ == "__main__":
    main()
