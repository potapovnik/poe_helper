"""
Windows keyboard event diagnostic logger.

Run this script alongside the main PoE helper.
It records keyboard events reported by the `keyboard` library and, at the
same moment, asks Windows whether left/right Alt is currently down.

Press ESC to stop the logger.
The log is written to key_state_log.txt in this script's folder.
"""

import ctypes
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

import keyboard

# Windows virtual-key codes
VK_LMENU = 0xA4  # Left Alt
VK_RMENU = 0xA5  # Right Alt

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

LOG_FILE = Path(__file__).with_name("key_state_log.txt")
log_lock = Lock()


def is_key_pressed(vk_code):
    # The high bit indicates that the key is currently down.
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)


def write_log(message):
    with log_lock:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(message + "\n")


def on_key_event(event):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    # Sample the actual asynchronous key state reported by Windows.
    left_alt = is_key_pressed(VK_LMENU)
    right_alt = is_key_pressed(VK_RMENU)

    line = (
        f"[{timestamp}] "
        f"{event.name!s} | {event.event_type} | "
        f"Windows Alt: L={left_alt}, R={right_alt}"
    )
    write_log(line)


def main():
    write_log("")
    write_log("=" * 72)
    write_log(
        f"Logger started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}"
    )
    write_log("Press ESC in any application to stop logging.")
    print("Keyboard diagnostic logger is running.")
    print(f"Log file: {LOG_FILE}")
    print("Press ESC to stop. Keep this window open while testing.")

    hook = keyboard.hook(on_key_event)

    try:
        keyboard.wait("esc")
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.unhook(hook)
        write_log(
            f"Logger stopped: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}"
        )
        print("Logger stopped.")


if __name__ == "__main__":
    main()
