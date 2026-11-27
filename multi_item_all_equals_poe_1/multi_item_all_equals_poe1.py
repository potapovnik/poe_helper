"""
PoE 2 grid currency spammer

Keyboard injection:
- pydirectinput is used for Shift, Ctrl+C, and Alt release.
- keyboard handles F6/F7; Windows API polling handles emergency F10.
- PyAutoGUI handles mouse clicks and grid movement.

target.txt and base.txt: one property per line; their matches count together.
At least one base.txt match and no not_target.txt matches triggers a currency sequence.
REQUIRED_TARGETS: total number of matching target.txt/base.txt lines required.

Item logic:
- REQUIRED_TARGETS or more matching target.txt/base.txt properties -> next item.
- A base.txt match without a not_target.txt match -> special currency sequence.
- All other cases -> keep rerolling.
- After every Ctrl+C, send Alt key-up as requested.
- Shift stays held during rerolls and is briefly released for the first currency action.
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
BASE_FILE = "base.txt"
NOT_TARGET_FILE = "not_target.txt"

COLUMNS = 12
ROWS = 12

MOVE_RIGHT_PIXELS = 59
MOVE_DOWN_PIXELS = 59
MOVE_DURATION = 0.25

# Screen coordinates for the stash controls shown in the 1919x1199 screenshot.
CURRENCY_TAB_POSITION = (508, 130)
STASH_TAB_2_POSITION = (145, 131)
CURRENCY_191_POSITION = (200, 305)
CURRENCY_71_POSITION = (137, 305)

REQUIRED_TARGETS = 2

MAX_ATTEMPTS = 100
CLICK_DELAY = 0.15
OTHER_CLICK_DELAY = 0.35
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
                log_file.write("\\n")
            log_file.write(LOG_SEPARATOR + "\\n")
            for value in current:
                log_file.write(value + "\\n")
            log_file.write(LOG_SEPARATOR + "\\n")
        print(f"New target set saved to {log_path}.")
# -------------------------------

def load_lines(filename):
    file_path = filename
    if not os.path.isabs(file_path):
        file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), file_path)
    with open(file_path, "r", encoding="utf-8-sig") as f:
        lines = [line.strip().casefold() for line in f if line.strip()]
    # Duplicate lines in a file count as one property.
    return list(dict.fromkeys(lines))


def load_targets():
    return load_lines(TARGET_FILE)


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
    print("Р‘СѓС„РµСЂ РѕР±РјРµРЅР°:", repr(text[:100]))
    return text if text.strip() else None


def check_targets(text, targets):
    lowered = text.casefold()
    found = [target for target in targets if target in lowered]
    missing = [target for target in targets if target not in lowered]
    return found, missing


def check_item_conditions(text, targets, base_lines, not_target_lines):
    target_found, _ = check_targets(text, targets)
    base_found, _ = check_targets(text, base_lines)
    not_target_found, _ = check_targets(text, not_target_lines)
    total_found = len(target_found) + len(base_found)
    has_required_matches = total_found >= REQUIRED_TARGETS
    base_condition = bool(base_found and not not_target_found)
    return (
        has_required_matches,
        base_condition,
        target_found,
        base_found,
        not_target_found,
    )


def stop():
    global running
    running = False
    print("\nStop requested. Releasing Shift...")


def use_base_currency(item_coordinates, targets, base_lines, not_target_lines):
    """Run the two-stage currency sequence; return NEXT, RETRY or ERROR."""
    print("Base condition found. Running the special currency sequence.")
    pyautogui.click(*CURRENCY_TAB_POSITION)
    time.sleep(OTHER_CLICK_DELAY)

    pydirectinput.keyUp("shift")
    pyautogui.click(*CURRENCY_191_POSITION, button="right")
    time.sleep(OTHER_CLICK_DELAY)
    pyautogui.click(*STASH_TAB_2_POSITION)
    time.sleep(OTHER_CLICK_DELAY)
    pyautogui.click(*item_coordinates)
    time.sleep(CLICK_DELAY)

    pydirectinput.keyDown("shift")
    text = read_item_text()
    if text is None:
        print("Could not read item after the first currency action.")
        return "ERROR"

    has_required_matches, base_condition, *_ = check_item_conditions(
        text, targets, base_lines, not_target_lines
    )
    if has_required_matches or base_condition:
        print("Item condition satisfied after the first currency action.")
        return "NEXT"

    print("Condition not satisfied; trying the second currency action.")
    pyautogui.moveTo(*CURRENCY_TAB_POSITION, duration=MOVE_DURATION)
    time.sleep(0.10)
    pyautogui.click(*CURRENCY_TAB_POSITION)
    time.sleep(OTHER_CLICK_DELAY)
    pydirectinput.keyDown("shift")
    pyautogui.click(*CURRENCY_71_POSITION, button="right")
    time.sleep(OTHER_CLICK_DELAY)
    pyautogui.click(*STASH_TAB_2_POSITION)
    time.sleep(OTHER_CLICK_DELAY)
    pyautogui.moveTo(*item_coordinates, duration=MOVE_DURATION)
    return "RETRY"


def process_item(row_number, column_number, targets, base_lines, not_target_lines,
                 item_coordinates):
    """Return NEXT, ERROR or LIMIT."""
    global running
    attempts = 0
    base_sequence_used = False

    print(f"\n--- Row {row_number}/{ROWS}, column {column_number}/{COLUMNS} ---")

    text = read_item_text()
    if text is None:
        print("Could not read item tooltip. Stopping grid.")
        return "ERROR"

    (
        has_required_matches,
        base_condition,
        target_found,
        base_found,
        not_target_found,
    ) = check_item_conditions(text, targets, base_lines, not_target_lines)
    count = len(target_found) + len(base_found)
    print(
        f"Found target={len(target_found)}, base={len(base_found)} "
        f"(required total: {REQUIRED_TARGETS}); "
        f"not_target={len(not_target_found)}."
    )

    if has_required_matches:
        print("Required match count reached. Moving to the next item.")
        return "NEXT"

    if base_condition:
        base_sequence_used = True
        result = use_base_currency(
            item_coordinates, targets, base_lines, not_target_lines
        )
        if result != "RETRY":
            return result

    print(f"Need {REQUIRED_TARGETS - count} more target/base matches; continuing rerolls.")

    while running and attempts < MAX_ATTEMPTS:
        pyautogui.click(*item_coordinates)
        attempts += 1
        time.sleep(CLICK_DELAY)

        text = read_item_text()
        if text is None:
            print("Could not read updated tooltip. Stopping grid.")
            return "ERROR"

        (
            has_required_matches,
            base_condition,
            target_found,
            base_found,
            not_target_found,
        ) = check_item_conditions(text, targets, base_lines, not_target_lines)
        count = len(target_found) + len(base_found)

        print(
            f"Attempt {attempts}/{MAX_ATTEMPTS}: target={len(target_found)}, "
            f"base={len(base_found)}, not_target={len(not_target_found)}"
        )

        if has_required_matches:
            print("Required match count reached. Moving to the next item.")
            return "NEXT"

        if base_condition:
            if base_sequence_used:
                print("Base condition satisfied. Moving to the next item.")
                return "NEXT"

            base_sequence_used = True
            result = use_base_currency(
                item_coordinates, targets, base_lines, not_target_lines
            )
            if result != "RETRY":
                return result

        print(f"Still need {REQUIRED_TARGETS - count} target/base matches.")

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
        base_lines = load_lines(BASE_FILE)
        not_target_lines = load_lines(NOT_TARGET_FILE)
        if not targets and not base_lines:
            print("target.txt and base.txt are both empty. Add properties to at least one.")
            return

        save_targets_to_log(targets)

        if COLUMNS < 1 or ROWS < 1:
            print("COLUMNS and ROWS must both be at least 1.")
            return

        available_matches = len(targets) + len(base_lines)
        if REQUIRED_TARGETS < 1 or REQUIRED_TARGETS > available_matches:
            print(
                f"REQUIRED_TARGETS must be between 1 and {available_matches} "
                f"(unique target.txt + base.txt lines)."
            )
            return

        print(
            f"Starting grid: {COLUMNS} columns x {ROWS} rows "
            f"({COLUMNS * ROWS} items)."
        )
        print(
            f"Loaded properties: target.txt={len(targets)}, "
            f"base.txt={len(base_lines)}, not_target.txt={len(not_target_lines)}"
        )
        print(f"Required target/base matches per item: {REQUIRED_TARGETS}")
        print("Place the cursor over the TOP-LEFT item before pressing F6.")

        grid_origin = pyautogui.position()
        running = True
        pydirectinput.keyDown("shift")
        shift_pressed = True
        time.sleep(0.10)
        print("Shift held during rerolls.")

        for row in range(1, ROWS + 1):
            if not running:
                break

            for column in range(1, COLUMNS + 1):
                if not running:
                    break

                coordinates = (
                    grid_origin[0] + (column - 1) * MOVE_RIGHT_PIXELS,
                    grid_origin[1] + (row - 1) * MOVE_DOWN_PIXELS,
                )
                pyautogui.moveTo(
                    *coordinates,
                    duration=MOVE_DURATION,
                    tween=pyautogui.easeInOutQuad,
                )
                result = process_item(
                    row, column, targets, base_lines, not_target_lines, coordinates
                )

                if not running:
                    break
                if result == "ERROR":
                    print("Could not read item. Stopping grid.")
                    return
                if result == "LIMIT":
                    print("Attempt limit reached. Stopping grid.")
                    return

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
    print(f'Base text: "{load_lines(BASE_FILE)}"')
    print(f'Not-target text: "{load_lines(NOT_TARGET_FILE)}"')
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
