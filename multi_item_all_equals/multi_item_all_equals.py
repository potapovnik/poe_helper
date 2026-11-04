"""
PoE 2 grid currency spammer

Keyboard injection:
- pydirectinput is used for Shift, Ctrl+C, and Alt release.
- keyboard remains responsible for listening to F6/F7/F10 hotkeys.
- PyAutoGUI remains responsible for mouse clicks and smooth grid movement.

target.txt: one desired property per line.
REQUIRED_TARGETS: number of different target lines required on an item.

Item logic:
- REQUIRED_TARGETS or more matching properties -> next item.
- Zero matching properties -> skip item immediately.
- Between 1 and REQUIRED_TARGETS - 1 -> keep rerolling.
- After every Ctrl+C, send Alt key-up as requested.
- Shift stays held across the entire grid run.
"""

import time
import threading

import keyboard
import pyautogui
import pydirectinput
import pyperclip


# ---------- SETTINGS ----------
TARGET_FILE = "target.txt"

COLUMNS = 12
ROWS = 8

MOVE_RIGHT_PIXELS = 70
MOVE_DOWN_PIXELS = 70
MOVE_DURATION = 0.25

REQUIRED_TARGETS = 2

MAX_ATTEMPTS = 80
CLICK_DELAY = 0.15
COPY_DELAY = 0.15
# -----------------------------

# Keep PyAutoGUI for mouse movement/clicks and its corner failsafe.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.03

# PyDirectInput has its own pause; keep it short for this automation.
pydirectinput.PAUSE = 0.03

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()


def load_targets():
    with open(TARGET_FILE, "r", encoding="utf-8-sig") as f:
        lines = [line.strip().casefold() for line in f if line.strip()]
    # Duplicate lines count as one property.
    return list(dict.fromkeys(lines))


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


def process_item(row_number, column_number, targets):
    """Return NEXT, ERROR or LIMIT."""
    global running
    attempts = 0

    print(f"\n--- Row {row_number}/{ROWS}, column {column_number}/{COLUMNS} ---")

    text = read_item_text()
    if text is None:
        print("Could not read item tooltip. Stopping grid.")
        return "ERROR"

    found, missing = check_targets(text, targets)
    count = len(found)
    print(f"Found {count}/{len(targets)} target properties: {found}")

    if count == 0:
        print("No target properties. Skipping to the next item.")
        return "NEXT"

    if count >= REQUIRED_TARGETS:
        print("Required number already reached.")
        return "NEXT"

    print(f"Need {REQUIRED_TARGETS - count} more. Missing: {missing}")

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

        print(
            f"Attempt {attempts}/{MAX_ATTEMPTS}: "
            f"found {count}/{len(targets)}: {found}"
        )

        if count == 0:
            print("No target properties remain. Skipping to the next item.")
            return "NEXT"

        if count >= REQUIRED_TARGETS:
            print("Required number reached.")
            return "NEXT"

        print(f"Still need {REQUIRED_TARGETS - count}. Missing: {missing}")

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

                result = process_item(row, column, targets)

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
                    time.sleep(0.70)

            if running and row < ROWS:
                if COLUMNS > 1:
                    move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)
                move_smooth(0, MOVE_DOWN_PIXELS)
                time.sleep(0.70)

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
    global exit_requested, running
    running = False
    exit_requested = True
    print("Exit requested.")


def main():
    print("PoE 2 grid currency spammer вЂ” PyDirectInput keyboard")
    print(f'Target text: "{load_targets()}"')
    print(f"Grid: {COLUMNS} columns x {ROWS} rows")
    print(f"Required target properties: {REQUIRED_TARGETS}")
    print("1) Select the currency manually.")
    print("2) Put the cursor over the TOP-LEFT item.")
    print("3) F6 = start, F7 = stop, F10 = exit.")
    print("Shift stays held for the whole run.")
    print("Keyboard injection: PyDirectInput; hotkey listener: keyboard.")

    keyboard.add_hotkey("f6", request_start)
    keyboard.add_hotkey("f7", stop)
    keyboard.add_hotkey("f10", request_exit)

    try:
        while not exit_requested:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        stop()
        keyboard.unhook_all()
        print("Exited.")


if __name__ == "__main__":
    main()
