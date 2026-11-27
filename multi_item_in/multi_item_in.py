"""
PoE 2 grid currency spammer

1. Hover the first item and select the currency manually.
2. Put the cursor over the FIRST item (top-left of the grid).
3. Set COLUMNS and ROWS in config.json (or leave defaults).
4. Press F6 to start or stop; F10 performs an emergency stop and exits.

All settings live in config.json next to this script.
Defaults are kept in code; values from config.json override them.
If config.json is missing, it is created with default values on first run.
If a key is missing in config.json, the built-in default is used.

Shift is held continuously during the whole run and released only on exit/stop.
"""

import time
import threading
import os
import json
import ctypes
import re
from datetime import datetime
from queue import Queue

import keyboard
import pyautogui
import pydirectinput
import pyperclip

# ---------- DEFAULT SETTINGS (fallbacks if config.json lacks a key) ----------

DEFAULT_CONFIG = {
    "TARGET_FILE": "target.txt",

    "COLUMNS": 1,
    "ROWS": 1,

    "MOVE_RIGHT_PIXELS": 65,
    "MOVE_DOWN_PIXELS": 65,
    "MOVE_DURATION": 0.20,

    # Сколько совпадений из target.txt должно быть в тексте.
    # TARGET_REQUIRED = 1 -> "ANY"; = N -> "ALL"; = 2 при трёх целях -> "2 из 3".
    # TARGET_EXACT = True -> строго ровно N (не больше).
    "TARGET_REQUIRED": 2,
    "TARGET_EXACT": False,

    "MAX_ATTEMPTS": 1000,
    "CLICK_DELAY": 0.10,
    "COPY_DELAY": 0.20,

    "LOG_DIR": "logs",
    "TARGET_LOG_FILE": "target_values.txt",
    "CLIPBOARD_LOG_FILE": "clipboard_text.txt",
}

CONFIG_FILE = "config.json"
LOG_SEPARATOR = "------------------------------------------------------------"

# ---------- CONFIG LOADING ----------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, CONFIG_FILE)


def _to_bool(value):
    """Robust bool conversion for JSON values like true / "true" / 1 / "yes"."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def load_config():
    """Load config.json, creating it with defaults if missing.

    Priority:
      1. value from config.json
      2. value from DEFAULT_CONFIG
    Unknown keys in config.json are ignored (and reported).
    """

    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            print(f"Created default config: {CONFIG_PATH}")
        except Exception as exc:
            print(f"Could not create {CONFIG_PATH}: {exc}. Using built-in defaults.")
            return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            print("Config root must be a JSON object; using built-in defaults.")
            return DEFAULT_CONFIG.copy()
    except Exception as exc:
        print(f"Config load error ({exc}); using built-in defaults.")
        return DEFAULT_CONFIG.copy()

    merged = DEFAULT_CONFIG.copy()
    for key, value in raw.items():
        if key in DEFAULT_CONFIG:
            merged[key] = value
        else:
            print(f"Ignoring unknown config key: {key}")
    return merged


CFG = load_config()

# ---------- EFFECTIVE SETTINGS ----------

TARGET_FILE = str(CFG["TARGET_FILE"])
# Resolve relative TARGET_FILE against the script folder, so double-click from anywhere works.
if not os.path.isabs(TARGET_FILE):
    TARGET_FILE = os.path.join(SCRIPT_DIR, TARGET_FILE)

COLUMNS = int(CFG["COLUMNS"])
ROWS = int(CFG["ROWS"])

MOVE_RIGHT_PIXELS = int(CFG["MOVE_RIGHT_PIXELS"])
MOVE_DOWN_PIXELS = int(CFG["MOVE_DOWN_PIXELS"])
MOVE_DURATION = float(CFG["MOVE_DURATION"])

TARGET_REQUIRED = int(CFG["TARGET_REQUIRED"])
TARGET_EXACT = _to_bool(CFG["TARGET_EXACT"])

MAX_ATTEMPTS = int(CFG["MAX_ATTEMPTS"])
CLICK_DELAY = float(CFG["CLICK_DELAY"])
COPY_DELAY = float(CFG["COPY_DELAY"])

LOG_DIR = str(CFG["LOG_DIR"])
TARGET_LOG_FILE = str(CFG["TARGET_LOG_FILE"])
CLIPBOARD_LOG_FILE = str(CFG["CLIPBOARD_LOG_FILE"])

# -----------------------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.025
pydirectinput.PAUSE = 0.025

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()
toggle_lock = threading.Lock()
stop_event = threading.Event()


# ---------- TARGET LOG ----------

log_lock = threading.Lock()
clipboard_queue = Queue()


def clipboard_log_worker():
    """Write clipboard snapshots asynchronously so game automation is not delayed."""
    log_dir = os.path.join(SCRIPT_DIR, LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, CLIPBOARD_LOG_FILE)
    while True:
        item = clipboard_queue.get()
        if item is None:
            clipboard_queue.task_done()
            break
        timestamp, copied_text = item
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n[{timestamp}]\n{copied_text.rstrip()}\n")
        except Exception as exc:
            print(f"Clipboard log write error: {exc}")
        finally:
            clipboard_queue.task_done()


clipboard_logger_thread = threading.Thread(target=clipboard_log_worker, daemon=True)
clipboard_logger_thread.start()


def save_targets_to_log(targets):
    """Append target values only, skipping sets already present (order/case-insensitive)."""

    log_dir = os.path.join(SCRIPT_DIR, LOG_DIR)
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, TARGET_LOG_FILE)

    current = [value.strip() for value in targets if value.strip()]
    if not current:
        return

    new_key = tuple(sorted(set(value.casefold() for value in current)))

    with log_lock:
        existing_keys = set()

        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8-sig") as log_file:
                block = []

                for raw_line in log_file:
                    line = raw_line.strip()

                    if line == LOG_SEPARATOR:
                        values = [item.casefold() for item in block if item]
                        if values:
                            existing_keys.add(tuple(sorted(set(values))))
                        block = []
                    elif line:
                        block.append(line)

                values = [item.casefold() for item in block if item]
                if values:
                    existing_keys.add(tuple(sorted(set(values))))

        if new_key in existing_keys:
            print("Target set already exists in log; skipping log entry.")
            return

        with open(log_path, "a", encoding="utf-8") as log_file:
            if os.path.exists(log_path) and os.path.getsize(log_path) > 0:
                log_file.write("\n")

            log_file.write(LOG_SEPARATOR + "\n")

            for value in current:
                log_file.write(value + "\n")

            log_file.write(LOG_SEPARATOR + "\n")

        print(f"New target set saved to {log_path}.")


# -------------------------------

def load_targets():
    with open(TARGET_FILE, "r", encoding="utf-8-sig") as f:
        return [
            line.strip().casefold()
            for line in f
            if line.strip()
        ]


def release_ctrl_and_alt():
    """Best-effort release of Ctrl and Alt to avoid stuck modifier states."""

    try:
        pydirectinput.keyUp("ctrl")
    finally:
        pydirectinput.keyUp("alt")


def read_item_text():
    # Clear clipboard before copying so stale content cannot be mistaken for a fresh read.
    pyperclip.copy("")
    try:
        pydirectinput.keyDown("ctrl")
        pydirectinput.press("c")
        time.sleep(0.01)
        pydirectinput.keyUp("ctrl")
    finally:
        release_ctrl_and_alt()

    # Poll briefly for clipboard content, instead of always waiting the full delay.
    deadline = time.monotonic() + max(COPY_DELAY, 0.25)
    text = ""
    while time.monotonic() < deadline:
        text = pyperclip.paste()
        if text.strip():
            break
        time.sleep(0.01)

    print("Буфер обмена:", repr(text[:100]))
    if not text.strip():
        return None

    # Log in a background queue; file I/O does not block the main loop.
    clipboard_queue.put((datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), text))
    return text


def mask_to_regex(mask):
    """Custom target masks: . and * = one arbitrary character; ? = any length.
    All other characters (including parentheses, +, %, brackets) are literal.
    """
    parts = []
    for char in mask:
        if char in (".", "*"):
            parts.append(".")
        elif char == "?":
            parts.append(".*")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def check_targets(text, targets):
    """Match custom masks; success if found_count >= TARGET_REQUIRED
    (or exactly == TARGET_REQUIRED when TARGET_EXACT is True)."""

    if TARGET_REQUIRED < 1:
        raise ValueError("TARGET_REQUIRED must be >= 1.")

    lowered_text = text.casefold()
    found = []
    missing = []
    for target in targets:
        lowered_target = target.casefold()
        if any(char in lowered_target for char in (".", "*", "?")):
            matched = re.search(mask_to_regex(lowered_target), lowered_text) is not None
        else:
            matched = lowered_target in lowered_text
        (found if matched else missing).append(target)

    if TARGET_EXACT:
        success = len(found) == TARGET_REQUIRED
    else:
        success = len(found) >= TARGET_REQUIRED

    return success, found, missing


def stop():
    global running
    running = False
    stop_event.set()
    print("\nStop requested. Releasing Shift...")


def move_smooth(dx, dy):
    """Move the cursor along a visible path instead of jumping instantly."""

    if not running:
        return

    pyautogui.moveRel(
        dx,
        dy,
        duration=MOVE_DURATION,
        tween=pyautogui.easeInOutQuad
    )


def process_item(row_number, column_number, targets):
    """Search one item. Return True if a target was found."""

    global running

    item_attempts = 0

    print(f"\n--- Row {row_number}/{ROWS}, column {column_number}/{COLUMNS} ---")

    # Check whether the desired text is already present.
    text = read_item_text()

    if text is None:
        print("Could not read item tooltip. Stopping.")
        return False

    success, found, missing = check_targets(text, targets)

    if success:
        print(
            f"Target condition already satisfied: "
            f"found {len(found)}/{len(targets)} (required {TARGET_REQUIRED}). Found: {found}"
        )
        return True

    print(f"Found {len(found)}/{len(targets)} (required {TARGET_REQUIRED}). Missing: {missing}")

    while running and item_attempts < MAX_ATTEMPTS:
        pyautogui.click()

        item_attempts += 1
        time.sleep(CLICK_DELAY)

        text = read_item_text()

        if text is None:
            print("Could not read updated tooltip; stopping.")
            return False

        print(
            f"Row {row_number}, column {column_number}: "
            f"attempt {item_attempts}/{MAX_ATTEMPTS}"
        )

        success, found, missing = check_targets(text, targets)

        if success:
            print(
                f"TARGET CONDITION SATISFIED: found {len(found)}/{len(targets)} "
                f"(required {TARGET_REQUIRED}). Found: {found}"
            )
            return True

        print(f"Found {len(found)}/{len(targets)}. Still missing: {missing}")

    if item_attempts >= MAX_ATTEMPTS:
        print(
            f"Safety limit reached at row {row_number}, "
            f"column {column_number}."
        )

    return False


def start():
    global running, busy

    # busy is reserved synchronously by toggle_start_stop before this worker starts.
    try:
        targets = load_targets()

        if not targets:
            print("Targets is empty. Add values to target.txt.")
            return

        if TARGET_REQUIRED < 1:
            print("TARGET_REQUIRED must be at least 1.")
            return

        if TARGET_REQUIRED > len(targets):
            print(
                f"TARGET_REQUIRED={TARGET_REQUIRED} exceeds {len(targets)} "
                f"targets in {TARGET_FILE}."
            )
            return

        save_targets_to_log(targets)

        if COLUMNS < 1 or ROWS < 1:
            print("COLUMNS and ROWS must both be at least 1.")
            return

        print(
            f"\nStarting grid: {COLUMNS} columns x {ROWS} rows "
            f"({COLUMNS * ROWS} items)."
        )

        print(
            f"Grid spacing: {MOVE_RIGHT_PIXELS}px horizontally, "
            f"{MOVE_DOWN_PIXELS}px vertically."
        )

        print(f"Smooth movement duration: {MOVE_DURATION}s.")
        mode_text = "exactly" if TARGET_EXACT else "at least"
        print(
            f"Target requirement: {mode_text} {TARGET_REQUIRED} of {len(targets)}."
        )
        print("Place the cursor over the TOP-LEFT item before pressing F6.")

        if stop_event.is_set():
            print("Start cancelled by F6 stop request.")
            return
        running = True

        # Hold Shift once for the entire grid.
        pyautogui.keyDown("shiftleft")
        time.sleep(0.10)
        print("Shift held for the entire run.")

        for row in range(1, ROWS + 1):
            if not running:
                break

            for column in range(1, COLUMNS + 1):
                if not running:
                    break

                found = process_item(row, column, targets)

                if not running:
                    break

                if not found:
                    print("No target found or item could not be read. Stopping grid.")
                    return

                # Move to the next item in this row.
                if column < COLUMNS:
                    move_smooth(MOVE_RIGHT_PIXELS, 0)
                    time.sleep(0.10)

            # Return to first column and move down.
            if running and row < ROWS:
                if COLUMNS > 1:
                    move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)

                move_smooth(0, MOVE_DOWN_PIXELS)
                time.sleep(0.10)

        print("\nGrid sequence finished.")

    except pyautogui.FailSafeException:
        print("PyAutoGUI failsafe triggered.")

    except Exception as exc:
        print(f"Stopped due to error: {exc}")

    finally:
        # Shift is released only once, after the whole run or a stop/error.
        try:
            pyautogui.keyUp("shiftleft")
        except Exception:
            pass

        running = False

        with state_lock:
            busy = False

        print("Stopped. Press F6 to start again.")


def toggle_start_stop():
    """F6 toggles: reserve the worker slot immediately, or stop an active worker."""
    global running, busy
    with toggle_lock:
        if busy:
            stop()
            return
        # Reserve the slot synchronously so a quick second F6 cannot race startup.
        with state_lock:
            busy = True
        stop_event.clear()
        threading.Thread(target=start, daemon=True).start()


def request_exit():
    """F10: request an emergency stop and exit the application."""

    global exit_requested, running

    running = False
    exit_requested = True

    print("\nEMERGENCY STOP: F10 pressed. Releasing keys and exiting...")

    if not busy:
        for key in ("shift", "ctrl", "alt"):
            try:
                pydirectinput.keyUp(key)
            except Exception:
                try:
                    pyautogui.keyUp(key)
                except Exception:
                    pass


def main():
    print("PoE 2 grid currency spammer")
    print(f"Config: {CONFIG_PATH}")
    print(f'Target file: "{TARGET_FILE}"')
    print(f'Target text: "{load_targets()}"')
    print(f"Grid: {COLUMNS} columns x {ROWS} rows")
    mode_text = "exactly" if TARGET_EXACT else "at least"
    print(f"Target requirement: {mode_text} {TARGET_REQUIRED} of the loaded targets.")
    print("F6 = start/stop toggle, F10 = emergency stop and exit.")
    print("F10 is monitored directly through Windows API.")

    keyboard.add_hotkey("f6", toggle_start_stop)

    user32 = ctypes.windll.user32
    f10_vk = 0x79
    f10_was_down = False

    try:
        while not exit_requested:
            f10_is_down = bool(user32.GetAsyncKeyState(f10_vk) & 0x8000)

            if f10_is_down and not f10_was_down:
                request_exit()

            f10_was_down = f10_is_down
            time.sleep(0.02)

    except KeyboardInterrupt:
        pass

    finally:
        stop()
        keyboard.unhook_all()

        for key in ("shift", "ctrl", "alt"):
            try:
                pydirectinput.keyUp(key)
            except Exception:
                try:
                    pyautogui.keyUp(key)
                except Exception:
                    pass

        clipboard_queue.put(None)
        clipboard_logger_thread.join(timeout=2.0)
        print("Exited.")


if __name__ == "__main__":
    main()