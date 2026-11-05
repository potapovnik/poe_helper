"""
PoE 2 grid currency spammer

Keyboard injection:
- pydirectinput is used for Shift, Ctrl+C, and Alt release.
- Windows GetAsyncKeyState monitors F6/F7/F10 globally.
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
import ctypes
import sys
from pathlib import Path

import pyautogui
import pydirectinput
import pyperclip


# ---------- SETTINGS ----------
TARGET_FILE = "target.txt"

COLUMNS = 12
ROWS = 5

MOVE_RIGHT_PIXELS = 65
MOVE_DOWN_PIXELS = 65
MOVE_DURATION = 0.25

# Coordinates measured from the supplied 1650x927 screenshot.
# Automatically scaled to the actual desktop resolution (including 150% scaling).
REFERENCE_SCREEN_WIDTH = 1650
REFERENCE_SCREEN_HEIGHT = 927

TAB_BUTTONS = {
    1: (159, 257),
    2: (211, 257),
    3: (263, 257),
    4: (315, 257),
    5: (367, 257),
    6: (419, 257),
}
GRID_FIRST_ITEM = (56, 299)
TAB_SWITCH_DELAY = 0.6

REQUIRED_TARGETS = 2

MAX_ATTEMPTS = 60
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
selected_tabs = [1, 2, 3, 4, 5, 6]
state_lock = threading.Lock()


LOG_DIR = Path(__file__).resolve().parent / "logs"
TARGET_LOG_PATH = LOG_DIR / "target_values.txt"


def append_targets_to_log(targets):
    """Append only the current target values, separated from other runs."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    separator = "-" * 60
    with TARGET_LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(separator + "\n")
        for target in targets:
            log_file.write(target + "\n")
        log_file.write(separator + "\n\n")


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
    print("Буфер обмена:", repr(text[:100]))
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
        if not running:
            return "NEXT"
        pyautogui.click()
        attempts += 1
        time.sleep(CLICK_DELAY)
        if not running:
            return "NEXT"

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


def get_screen_scale():
    screen_width, screen_height = pyautogui.size()
    scale = (
        screen_width / REFERENCE_SCREEN_WIDTH,
        screen_height / REFERENCE_SCREEN_HEIGHT,
    )
    print(
        f"Screen: {screen_width}x{screen_height}; "
        f"coordinate scale: x{scale[0]:.3f}, y{scale[1]:.3f}"
    )
    return scale


def scaled_point(point, scale):
    return round(point[0] * scale[0]), round(point[1] * scale[1])


def select_tabs():
    """Blank input selects all tabs. Supports lists and ranges, e.g. 1,3-5."""
    while True:
        print(
            "\nBefore F6 becomes active, choose the tabs here and press Enter.\n"
            "Examples: 1-6 = all tabs; 1,3,5 = selected tabs; blank + Enter = all tabs.",
            flush=True,
        )
        try:
            raw = input("Tabs to process (1-6): ").strip()
        except KeyboardInterrupt:
            print("\nStartup cancelled (Ctrl+C). No tabs were processed.")
            return None
        if not raw:
            return [1, 2, 3, 4, 5, 6]

        selected = set()
        try:
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    raise ValueError
                if "-" in part:
                    first, last = map(int, part.split("-", 1))
                    if first > last:
                        raise ValueError
                    selected.update(range(first, last + 1))
                else:
                    selected.add(int(part))

            if not selected or any(number not in TAB_BUTTONS for number in selected):
                raise ValueError
            return sorted(selected)
        except ValueError:
            print("Invalid selection. Use numbers 1-6, e.g. 1,3,5-6.")


def process_tab(tab_number, targets, scale):
    """Switch to one tab, move to its first item, and process the grid."""
    global running

    if not running:
        return "STOPPED"

    # Avoid Shift being held while clicking the tab selector.
    pydirectinput.keyUp("shift")
    tab_x, tab_y = scaled_point(TAB_BUTTONS[tab_number], scale)
    print(f"\n===== Stash tab {tab_number}: click ({tab_x}, {tab_y}) =====")
    pyautogui.click(tab_x, tab_y)
    time.sleep(TAB_SWITCH_DELAY)

    if not running:
        return "STOPPED"

    first_x, first_y = scaled_point(GRID_FIRST_ITEM, scale)
    pyautogui.moveTo(first_x, first_y, duration=0.15)
    time.sleep(0.15)
    pydirectinput.keyDown("shift")
    time.sleep(0.10)

    for row in range(1, ROWS + 1):
        if not running:
            break

        for column in range(1, COLUMNS + 1):
            if not running:
                break

            result = process_item(row, column, targets)
            if not running:
                break
            if result in ("ERROR", "LIMIT"):
                print(f"Stopping on stash tab {tab_number}: {result}")
                return result

            if column < COLUMNS:
                move_smooth(MOVE_RIGHT_PIXELS, 0)
                time.sleep(0.20)

        if running and row < ROWS:
            if COLUMNS > 1:
                move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)
            move_smooth(0, MOVE_DOWN_PIXELS)
            time.sleep(0.20)

    return "DONE"


def start():
    global running, busy

    with state_lock:
        if busy:
            print("Already running.")
            return
        busy = True

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

        # All runs append only target values to the same fixed log file.
        append_targets_to_log(targets)

        tabs = selected_tabs
        scale = get_screen_scale()

        print(
            f"Starting tabs {tabs}; each grid: {COLUMNS} columns x {ROWS} rows "
            f"({COLUMNS * ROWS} items)."
        )
        print(f"Loaded target properties: {len(targets)}")
        print(f"Required properties per item: {REQUIRED_TARGETS}")
        print("The cursor will be positioned automatically at the first item.")

        running = True
        for tab_number in tabs:
            if not running:
                break

            result = process_tab(tab_number, targets, scale)
            if result in ("ERROR", "LIMIT"):
                break

            if running:
                pydirectinput.keyUp("shift")
                time.sleep(0.25)

        if running:
            print("\nSelected stash tabs finished.")

    except pyautogui.FailSafeException:
        print("PyAutoGUI failsafe triggered.")
    except Exception as exc:
        print(f"Stopped due to error: {exc}")
    finally:
        for key in ("shift", "ctrl", "alt"):
            try:
                pydirectinput.keyUp(key)
            except Exception:
                pass

        running = False
        with state_lock:
            busy = False
        print("Stopped. Press F6 to start again.")



def request_start():
    threading.Thread(target=start, daemon=True).start()


def emergency_stop():
    """Immediately request stop and terminate the script (F10)."""
    global exit_requested, running
    running = False
    exit_requested = True
    # Release modifiers immediately as well as in start()'s finally block.
    for key in ("shift", "ctrl", "alt"):
        try:
            pydirectinput.keyUp(key)
        except Exception:
            pass
    print("\nEMERGENCY STOP: F10 pressed. Releasing keys and exiting...")


def main():
    global selected_tabs

    print("PoE 2 grid currency spammer — PyDirectInput keyboard")
    print(f'Target text: "{load_targets()}"')
    print(f"Grid: {COLUMNS} columns x {ROWS} rows")
    print(f"Movement step: {MOVE_RIGHT_PIXELS} x {MOVE_DOWN_PIXELS} pixels")
    print(f"Required target properties: {REQUIRED_TARGETS}")
    print("1) Select the currency manually.")
    selected_tabs = select_tabs()
    if selected_tabs is None:
        return
    print(f"Selected stash tabs: {selected_tabs}")
    print("2) Put the cursor anywhere; the script positions it automatically.")
    print("3) F6 = start, F7 = stop, F10 = EMERGENCY STOP + exit.")
    print("Hotkeys are monitored through the Windows API.")

    if sys.platform != "win32":
        raise RuntimeError("Global F6/F7/F10 monitoring requires Windows.")

    user32 = ctypes.windll.user32
    key_codes = {"f6": 0x75, "f7": 0x76, "f10": 0x79}
    previous = {name: False for name in key_codes}

    try:
        while not exit_requested:
            for name, virtual_key in key_codes.items():
                is_down = bool(user32.GetAsyncKeyState(virtual_key) & 0x8000)
                just_pressed = is_down and not previous[name]
                previous[name] = is_down

                if just_pressed:
                    if name == "f6":
                        request_start()
                    elif name == "f7":
                        stop()
                    elif name == "f10":
                        emergency_stop()
                        break
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        stop()
        for key in ("shift", "ctrl", "alt"):
            try:
                pydirectinput.keyUp(key)
            except Exception:
                pass
        print("Exited.")


if __name__ == "__main__":
    main()
