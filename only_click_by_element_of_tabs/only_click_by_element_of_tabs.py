"""PoE 2 stash-tab grid clicker.

Select stash tabs at startup, then press F6 to click every grid item.
F7 pauses/stops the current run; F10 emergency-stops and exits.
No item inspection, target checks, clipboard access, or log file is used.
"""

import ctypes
import sys
import threading
import time

import pyautogui
import pydirectinput


# ---------- SETTINGS ----------
COLUMNS = 12
ROWS = 8

# Confirmed grid spacing from the user's screenshot.
MOVE_RIGHT_PIXELS = 65
MOVE_DOWN_PIXELS = 65
MOVE_DURATION = 0.15

# Reference screenshot coordinates; scaled to current screen resolution.
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

CLICK_HOLD_DURATION = 0.15  # How long the mouse button stays pressed.
CLICK_DELAY = 0.1          # Wait after releasing the click before moving on.
TAB_SWITCH_DELAY = 0.3     # Wait after selecting a stash tab.
TAB_CLICK_HOLD_DURATION = 0.15  # Keep the tab click registered by the game.
# -----------------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01
pydirectinput.PAUSE = 0.01

running = False
busy = False
exit_requested = False
selected_tabs = [1, 2, 3, 4, 5, 6]
state_lock = threading.Lock()


def get_screen_scale():
    width, height = pyautogui.size()
    scale = (width / REFERENCE_SCREEN_WIDTH, height / REFERENCE_SCREEN_HEIGHT)
    print(
        f"Screen: {width}x{height}; coordinate scale: "
        f"x{scale[0]:.3f}, y{scale[1]:.3f}"
    )
    return scale


def scaled_point(point, scale):
    return round(point[0] * scale[0]), round(point[1] * scale[1])


def select_tabs():
    """Accept tab lists/ranges, e.g. 1,3,5-6. Empty input selects all."""
    while True:
        print(
            "\nChoose stash tabs before starting. Examples: 1-6, 1,3,5-6.\n"
            "Press Enter for all tabs 1-6."
        )
        try:
            raw = input("Tabs to process (1-6): ").strip()
        except KeyboardInterrupt:
            print("\nStartup cancelled.")
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


def stop():
    global running
    running = False
    print("\nStop requested.")


def release_modifiers():
    for key in ("shift", "ctrl", "alt"):
        try:
            pydirectinput.keyUp(key)
        except Exception:
            pass


def click_item():
    """Hold the mouse button for CLICK_HOLD_DURATION, then release it."""
    pyautogui.mouseDown()
    try:
        time.sleep(CLICK_HOLD_DURATION)
    finally:
        pyautogui.mouseUp()


def move_smooth(dx, dy):
    if running:
        pyautogui.moveRel(
            dx,
            dy,
            duration=MOVE_DURATION,
            tween=pyautogui.easeInOutQuad,
        )


def process_tab(tab_number, scale):
    global running
    if not running:
        return

    # Shift is held continuously for the entire run, including tab changes.
    tab_x, tab_y = scaled_point(TAB_BUTTONS[tab_number], scale)
    print(f"\n===== Stash tab {tab_number} =====")

    # Use PyDirectInput for the tab click as well as game item input.
    # PyAutoGUI can move/hover correctly while its click is ignored by some games.
    pydirectinput.moveTo(tab_x, tab_y, duration=0.10)
    pydirectinput.mouseDown(button="left")
    try:
        time.sleep(TAB_CLICK_HOLD_DURATION)
    finally:
        pydirectinput.mouseUp(button="left")
    time.sleep(TAB_SWITCH_DELAY)

    if not running:
        return

    first_x, first_y = scaled_point(GRID_FIRST_ITEM, scale)
    pyautogui.moveTo(first_x, first_y, duration=0.15)

    for row in range(1, ROWS + 1):
        if not running:
            break
        for column in range(1, COLUMNS + 1):
            if not running:
                break

            click_item()
            time.sleep(CLICK_DELAY)

            if not running:
                break
            if column < COLUMNS:
                move_smooth(MOVE_RIGHT_PIXELS, 0)

        if running and row < ROWS:
            if COLUMNS > 1:
                move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)
            move_smooth(0, MOVE_DOWN_PIXELS)


def start():
    global running, busy
    with state_lock:
        if busy:
            print("Already running.")
            return
        busy = True

    try:
        scale = get_screen_scale()
        print(
            f"Starting tabs {selected_tabs}; grid {COLUMNS}x{ROWS}; "
            f"click hold {CLICK_HOLD_DURATION}s; post-click delay {CLICK_DELAY}s; "
            f"tab delay {TAB_SWITCH_DELAY}s."
        )
        running = True
        # Press Shift once and keep it down across every selected tab.
        pydirectinput.keyDown("shift")
        time.sleep(0.05)

        # select_tabs() returns a sorted, duplicate-free list. Start with its
        # smallest requested number; never process an implicit first tab.
        tabs_to_process = sorted(set(selected_tabs))
        for tab_number in tabs_to_process:
            if not running:
                break
            process_tab(tab_number, scale)
        if running:
            print("All selected tabs finished.")
    except pyautogui.FailSafeException:
        print("PyAutoGUI failsafe triggered.")
    except Exception as exc:
        print(f"Stopped due to error: {exc}")
    finally:
        release_modifiers()
        running = False
        with state_lock:
            busy = False
        print("Stopped. Press F6 to start again.")


def request_start():
    threading.Thread(target=start, daemon=True).start()


def emergency_stop():
    global exit_requested, running
    running = False
    exit_requested = True
    release_modifiers()
    print("\nEMERGENCY STOP: F10 pressed. Exiting.")


def main():
    global selected_tabs
    print("PoE 2 stash-tab clicker (no target checks, no log file)")
    print(f"Grid: {COLUMNS} columns x {ROWS} rows")
    print(f"Grid spacing: {MOVE_RIGHT_PIXELS}x{MOVE_DOWN_PIXELS}px")
    print("Shift is held while clicking grid items.")

    selected_tabs = select_tabs()
    if selected_tabs is None:
        return

    selected_tabs = sorted(set(selected_tabs))
    print(f"Selected tabs (processing order): {selected_tabs}")
    print("F6 = start; F7 = stop; F10 = emergency stop and exit.")

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
        release_modifiers()
        print("Exited.")


if __name__ == "__main__":
    main()
