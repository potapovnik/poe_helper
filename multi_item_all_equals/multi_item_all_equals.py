"""
PoE 2 grid currency spammer

Keyboard injection:
- pydirectinput is used for Shift, Ctrl+C, and Alt release.
- keyboard handles F6/F7; Windows API polling handles emergency F10.
- PyAutoGUI remains responsible for mouse clicks and smooth grid movement.

Files (all next to this script):
- target.txt          : one desired property per line.
- stop_if_present.txt : one "stop" property per line. Exactly one match -> move on.
- not_target.txt      : one "blocked" property per line. Any match -> keep rerolling,
                        regardless of target/stop matches.

Item logic (priority order):
  1. Any not_target.txt property present -> reroll (blocked), no matter what else.
  2. Otherwise REQUIRED_TARGETS matches from target.txt -> next item.
  3. Otherwise exactly one match from stop_if_present.txt -> next item.
  4. Otherwise keep clicking until (1), (2) or (3) becomes true, or MAX_ATTEMPTS.

Shift stays held across the entire grid run.
"""

import time
import threading
import os
import ctypes

import keyboard
import pyautogui
import pydirectinput
import pyperclip


# ---------- SETTINGS ----------
TARGET_FILE = "target.txt"
STOP_FILE = "stop_if_present.txt"
NOT_TARGET_FILE = "not_target.txt"

COLUMNS = 9
ROWS = 1

MOVE_RIGHT_PIXELS = 70
MOVE_DOWN_PIXELS = 70
MOVE_DURATION = 0.25

REQUIRED_TARGETS = 2

MAX_ATTEMPTS = 200
CLICK_DELAY = 0.15
COPY_DELAY = 0.15
# -----------------------------

# Keep PyAutoGUI for mouse movement/clicks and its corner failsafe.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.025

# PyDirectInput has its own pause; keep it short for this automation.
pydirectinput.PAUSE = 0.025

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()


# ---------- TARGET LOG ----------
# One persistent file; each unique target set is written only once.
LOG_DIR = "logs"
TARGET_LOG_FILE = "target_values.txt"
LOG_SEPARATOR = "------------------------------------------------------------"
log_lock = threading.Lock()


def save_targets_to_log(targets):
    """Append target values only, skipping sets already present (order/case-insensitive)."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), LOG_DIR)
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


def load_lines(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        lines = [line.strip().casefold() for line in f if line.strip()]
    # Duplicate lines count as one property.
    return list(dict.fromkeys(lines))


def load_targets():
    return load_lines(TARGET_FILE)


def load_stop_targets():
    if not os.path.exists(STOP_FILE):
        return []
    return load_lines(STOP_FILE)


def load_not_targets():
    if not os.path.exists(NOT_TARGET_FILE):
        return []
    return load_lines(NOT_TARGET_FILE)


def release_ctrl_and_alt():
    """Best-effort release of Ctrl and Alt to avoid stuck modifier states."""
    try:
        pydirectinput.keyUp("ctrl")
    finally:
        # Explicitly release Alt after every Ctrl+C, as requested.
        pydirectinput.keyUp("alt")


def read_item_text():
    """
    Copy the hovered item's tooltip using PyDirectInput.
    Alt is explicitly released after every Ctrl+C sequence.
    """
    try:
        pydirectinput.keyDown("ctrl")
        time.sleep(0.03)
        pydirectinput.press("c")
        time.sleep(0.03)
    finally:
        release_ctrl_and_alt()

    time.sleep(COPY_DELAY)
    text = pyperclip.paste()
    print("Буфер обмена:", repr(text[:100]))
    return text if text.strip() else None


def check_targets(text, targets):
    lowered = text.casefold()
    found = [target for target in targets if target in lowered]
    missing = [target for target in targets if target not in lowered]
    return found, missing


def find_matches(text, patterns):
    """Return all patterns present as substrings in text."""
    if not patterns:
        return []
    lowered = text.casefold()
    return [p for p in patterns if p in lowered]


def stop():
    global running
    running = False
    print("\nStop requested. Releasing Shift...")


def move_smooth(dx, dy):
    if running:
        pyautogui.moveRel(
            dx,
            dy,
            duration=MOVE_DURATION,
            tween=pyautogui.easeInOutQuad
        )


def process_item(row_number, column_number, targets, stop_targets, not_targets):
    """Return NEXT, ERROR or LIMIT.

    Priority:
      1. target_count >= 1 AND stop_count == 1 -> NEXT (regardless of not_target).
      2. stop_count == 1 AND no not_target match -> NEXT.
      3. Otherwise keep clicking until (1) or (2), or MAX_ATTEMPTS.
    """
    global running
    attempts = 0

    print(f"\n--- Row {row_number}/{ROWS}, column {column_number}/{COLUMNS} ---")

    text = read_item_text()
    if text is None:
        print("Could not read item tooltip. Stopping grid.")
        return "ERROR"

    found, missing = check_targets(text, targets)
    count = len(found)
    stop_found = find_matches(text, stop_targets)
    stop_count = len(stop_found)
    not_found = find_matches(text, not_targets)

    print(f"Found {count}/{len(targets)} target properties: {found}")
    if stop_targets:
        print(f"Stop-list matches: {stop_count} {stop_found}")
    if not_targets:
        print(f"Not-target matches: {len(not_found)} {not_found}")

    if count >= 1 and stop_targets and stop_count == 1:
        print("Target + stop condition met; moving on.")
        return "NEXT"

    if stop_targets and stop_count == 1 and not (not_targets and not_found):
        print("Stop-only condition met; moving on.")
        return "NEXT"

    print(f"Need either 1 target + 1 stop, or 1 stop with no not-target. Missing: {missing}")

    while running and attempts < MAX_ATTEMPTS:
        pyautogui.click()
        attempts += 1
        time.sleep(CLICK_DELAY)

        text = read_item_text()
        if text is None:
            print("Could not read updated tooltip. Stopping grid.")
            return "ERROR"

        found, missing = check_targets(text, targets)
        count = len(found)
        stop_found = find_matches(text, stop_targets)
        stop_count = len(stop_found)
        not_found = find_matches(text, not_targets)

        extra = f" | stop {stop_count}: {stop_found}" if stop_targets else ""
        extra += f" | not-target {len(not_found)}: {not_found}" if not_targets else ""
        print(
            f"Attempt {attempts}/{MAX_ATTEMPTS}: "
            f"found {count}/{len(targets)}: {found}{extra}"
        )

        if count >= 1 and stop_targets and stop_count == 1:
            print("Target + stop condition met; moving on.")
            return "NEXT"

        if stop_targets and stop_count == 1 and not (not_targets and not_found):
            print("Stop-only condition met; moving on.")
            return "NEXT"

        print(f"Still rerolling. Missing: {missing}")

    if attempts >= MAX_ATTEMPTS:
        print("Safety limit reached. Stopping grid.")
        return "LIMIT"

    return "NEXT"


def start():
    global running, busy

    with state_lock:
        if busy:
            print("Already running.")
            return
        busy = True

    shift_pressed = False

    try:
        targets = load_targets()
        if not targets:
            print("target.txt is empty. Add one property per line.")
            return

        stop_targets = load_stop_targets()
        if stop_targets:
            print(f"Loaded {len(stop_targets)} stop-list properties from {STOP_FILE}.")
        else:
            print(f"No stop-list file ({STOP_FILE}); stop-list logic disabled.")

        not_targets = load_not_targets()
        if not_targets:
            print(f"Loaded {len(not_targets)} not-target properties from {NOT_TARGET_FILE}.")
        else:
            print(f"No not-target file ({NOT_TARGET_FILE}); not-target logic disabled.")

        save_targets_to_log(targets)

        if COLUMNS < 1 or ROWS < 1:
            print("COLUMNS and ROWS must both be at least 1.")
            return

        if REQUIRED_TARGETS < 1 or REQUIRED_TARGETS > len(targets):
            print(
                f"REQUIRED_TARGETS must be between 1 and {len(targets)} "
                f"(number of unique target lines)."
            )
            return

        print(
            f"Starting grid: {COLUMNS} columns x {ROWS} rows "
            f"({COLUMNS * ROWS} items)."
        )
        print(f"Loaded target properties: {len(targets)}")
        print(f"Required properties per item: {REQUIRED_TARGETS}")
        print("Place the cursor over the TOP-LEFT item before pressing F6.")

        running = True
        pydirectinput.keyDown("shift")
        shift_pressed = True
        time.sleep(0.10)
        print("Shift held for the entire run.")

        for row in range(1, ROWS + 1):
            if not running:
                break

            for column in range(1, COLUMNS + 1):
                if not running:
                    break

                result = process_item(row, column, targets, stop_targets, not_targets)

                if not running:
                    break
                if result == "ERROR":
                    print("Could not read item. Stopping grid.")
                    return
                if result == "LIMIT":
                    print("Attempt limit reached. Stopping grid.")
                    return

                if column < COLUMNS:
                    move_smooth(MOVE_RIGHT_PIXELS, 0)
                    time.sleep(0.20)

            if running and row < ROWS:
                if COLUMNS > 1:
                    move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)
                move_smooth(0, MOVE_DOWN_PIXELS)
                time.sleep(0.20)

        print("\nGrid sequence finished.")

    except pyautogui.FailSafeException:
        print("PyAutoGUI failsafe triggered.")
    except Exception as exc:
        print(f"Stopped due to error: {exc}")
    finally:
        if shift_pressed:
            try:
                pydirectinput.keyUp("shift")
            except Exception:
                pass

        # Also make sure modifiers are not left held when the run ends.
        try:
            pydirectinput.keyUp("ctrl")
            pydirectinput.keyUp("alt")
        except Exception:
            pass

        running = False
        with state_lock:
            busy = False
        print("Stopped. Press F6 to start again.")


def request_start():
    threading.Thread(target=start, daemon=True).start()


def request_exit():
    """F10: request an emergency stop and exit the application."""
    global exit_requested, running
    running = False
    exit_requested = True
    print("\nEMERGENCY STOP: F10 pressed. Releasing keys and exiting...")
    # If no worker is active, release modifiers immediately.
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
    print(f'Target text: "{load_targets()}"')

    stop_targets = load_stop_targets()
    print(f'Stop-list ({STOP_FILE}): "{stop_targets}"' if stop_targets else "Stop-list: disabled")

    not_targets = load_not_targets()
    print(f'Not-target ({NOT_TARGET_FILE}): "{not_targets}"' if not_targets else "Not-target: disabled")

    print(f"Grid: {COLUMNS} columns x {ROWS} rows")
    print(f"Required target properties: {REQUIRED_TARGETS}")
    print("F6 = start, F7 = stop, F10 = emergency stop and exit.")
    print("F10 is monitored directly through Windows API.")

    # Keep existing F6/F7 behavior; F10 is polled separately because
    # the keyboard hook was unreliable in the previous version.
    keyboard.add_hotkey("f6", request_start)
    keyboard.add_hotkey("f7", stop)

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
        print("Exited.")


if __name__ == "__main__":
    main()