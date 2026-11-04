"""
PoE 2 grid currency spammer

1. Hover the first item and select the currency manually.
2. Put the cursor over the FIRST item (top-left of the grid).
3. Set COLUMNS and ROWS below.
4. Press F6 to start; F7 stops; F10 exits.

Shift is held continuously during the whole run and released only on exit/stop.
"""

import time
import threading

import keyboard
import pyautogui
import pyperclip

# ---------- USER SETTINGS ----------

TARGET_FILE = "target.txt"

COLUMNS = 2             # N: number of columns
ROWS = 2                # M: number of rows

MOVE_RIGHT_PIXELS = 70  # Distance between item centers horizontally
MOVE_DOWN_PIXELS = 70   # Distance between item centers vertically
MOVE_DURATION = 0.25    # Smooth mouse movement duration, in seconds

TARGET_MODE = "ANY"     # "ALL" = every target in target.txt; "ANY" = at least one

MAX_ATTEMPTS = 50     # Safety cap for EACH item
CLICK_DELAY = 0.15      # Delay after each currency use
COPY_DELAY = 0.15       # Original working Ctrl+C delay

# -----------------------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.03

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()


def load_targets():
    with open(TARGET_FILE, "r", encoding="utf-8-sig") as f:
        return [
            line.strip().casefold()
            for line in f
            if line.strip()
        ]


def read_item_text():
    # Keep the exact clipboard method from the original working script.
    pyautogui.hotkey("ctrl", "c")
    time.sleep(COPY_DELAY)

    text = pyperclip.paste()
    print("Р‘СѓС„РµСЂ РѕР±РјРµРЅР°:", repr(text[:100]))

    if not text.strip():
        return None

    return text


def check_targets(text, targets):
    """Return found and missing targets according to TARGET_MODE."""
    lowered_text = text.casefold()
    found = [target for target in targets if target in lowered_text]
    missing = [target for target in targets if target not in lowered_text]

    if TARGET_MODE == "ALL":
        success = len(missing) == 0
    elif TARGET_MODE == "ANY":
        success = len(found) > 0
    else:
        raise ValueError('TARGET_MODE must be either "ALL" or "ANY".')

    return success, found, missing


def stop():
    global running
    running = False
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
        print(f"Target condition already satisfied. Found: {found}")
        return True

    if TARGET_MODE == "ALL":
        print(f"Missing targets: {missing}")

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
            print(f"TARGET CONDITION SATISFIED: {found}")
            return True

        if TARGET_MODE == "ALL":
            print(f"Still missing: {missing}")

    if item_attempts >= MAX_ATTEMPTS:
        print(
            f"Safety limit reached at row {row_number}, "
            f"column {column_number}."
        )

    return False


def start():
    global running, busy

    with state_lock:
        if busy:
            print("Already running.")
            return
        busy = True

    total_attempts_note = "See per-item attempt counts above."

    try:
        targets = load_targets()

        if not targets:
            print("Targets is empty. Add values to target.txt.")
            return

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
        print(f"Target mode: {TARGET_MODE}")
        print("Place the cursor over the TOP-LEFT item before pressing F6.")

        running = True

        # Hold Shift once for the entire grid. Do not release it between items.
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
                    time.sleep(0.70)

            # After the last column, return to the first column and move down.
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
        # Shift is released only once, after the whole run or a stop/error.
        try:
            pyautogui.keyUp("shiftleft")
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
    print("PoE 2 grid currency spammer")
    print(f'Target text: "{load_targets()}"')
    print(f"Grid: {COLUMNS} columns x {ROWS} rows")
    print(f"Target mode: {TARGET_MODE}")
    print("1) Select the currency manually.")
    print("2) Put the cursor over the TOP-LEFT item.")
    print("3) F6 = start, F7 = stop, F10 = exit.")
    print("Shift stays held for the whole run.")

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
