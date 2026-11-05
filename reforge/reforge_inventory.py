import math
import threading
import time
import ctypes

import keyboard

# Make Windows report physical screen pixels despite 150% display scaling.
# This is set before pydirectinput is imported or used.
try:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass

import pydirectinput

# Coordinates measured from the latest screenshot (2048x1151)
# and scaled to the desktop resolution (2560x1440).
# GRID_START is the center of the top-left inventory cell.
GRID_START = (1728, 818)
CELL_WIDTH = 70
CELL_HEIGHT = 70
GRID_COLUMNS = 12
GRID_ROWS = 5

# Reforge window coordinates on the 2560x1440 desktop.
FORGE_BUTTON = (838, 1154)
OUTPUT_SLOT = (838, 541)

# Delays (seconds)
CLICK_DELAY = 0.2
FORGE_DELAY = 0.3
OUTPUT_DELAY = 0.7
BATCH_DELAY = 0.3

# Smooth mouse movement settings
MAX_MOVE_DURATION = 0.2
MIN_MOVE_DURATION = 0.04
MOVE_SPEED = 3000

start_event = threading.Event()
exit_event = threading.Event()

pydirectinput.PAUSE = 0


def request_exit():
    """Request program exit, including when waiting for F6."""
    exit_event.set()
    start_event.set()


def smooth_move(x, y):
    """Move the mouse smoothly; calculated duration is capped at 0.2 seconds."""
    start_x, start_y = pydirectinput.position()
    distance = math.hypot(x - start_x, y - start_y)

    if distance == 0:
        return

    duration = min(
        MAX_MOVE_DURATION,
        max(MIN_MOVE_DURATION, distance / MOVE_SPEED),
    )

    steps = max(2, min(20, int(distance / 25) + 1))
    start_time = time.perf_counter()

    for step in range(1, steps + 1):
        if exit_event.is_set():
            return

        t = step / steps
        eased_t = t * t * (3 - 2 * t)

        current_x = round(start_x + (x - start_x) * eased_t)
        current_y = round(start_y + (y - start_y) * eased_t)
        pydirectinput.moveTo(current_x, current_y)

        target_time = start_time + duration * t
        remaining = target_time - time.perf_counter()
        if remaining > 0:
            time.sleep(remaining)


def get_coordinates(row, col):
    """Return the center coordinates of an inventory cell (zero-based)."""
    return (
        GRID_START[0] + col * CELL_WIDTH,
        GRID_START[1] + row * CELL_HEIGHT,
    )


def wait_delay(seconds):
    """Wait unless the user requests program exit."""
    return exit_event.wait(seconds)


def process_inventory():
    print("Waiting for start. F6 = start, F10 = exit.")
    start_event.wait()

    if exit_event.is_set():
        return

    print("Starting inventory processing...")
    pydirectinput.keyDown("ctrl")

    try:
        total_items = GRID_ROWS * GRID_COLUMNS

        for i in range(0, total_items, 3):
            if exit_event.is_set():
                break

            # Ctrl-click the next three items.
            for j in range(3):
                if exit_event.is_set():
                    break

                index = i + j
                row = index // GRID_COLUMNS
                col = index % GRID_COLUMNS
                x, y = get_coordinates(row, col)

                smooth_move(x, y)
                if exit_event.is_set():
                    break

                pydirectinput.click()
                if wait_delay(CLICK_DELAY):
                    break

            if exit_event.is_set():
                break

            # Click the Reforge button.
            smooth_move(*FORGE_BUTTON)
            if exit_event.is_set():
                break

            pydirectinput.click()
            if wait_delay(FORGE_DELAY):
                break

            # Move to the output slot and wait for the result.
            smooth_move(*OUTPUT_SLOT)
            if exit_event.is_set():
                break

            if wait_delay(OUTPUT_DELAY):
                break

            # Ctrl is still held, so this click takes the result.
            pydirectinput.click()
            if wait_delay(BATCH_DELAY):
                break

            print(f"Processed items: {i + 3}/{total_items}")

    finally:
        pydirectinput.keyUp("ctrl")

    print("Processing finished.")


keyboard.add_hotkey("f6", start_event.set)
keyboard.add_hotkey("f10", request_exit)

try:
    process_inventory()
finally:
    pydirectinput.keyUp("ctrl")
    keyboard.unhook_all()
    print("Program closed.")