"""
PoE 2 — extended Alt-key diagnostic

Run this alongside key_state_monitor.py.
It writes alt_diagnostic_log.txt next to this script.

The test suite is deliberately divided into stages. Stages that click
the game item require explicit confirmation because each click may spend
one unit of the selected currency.

Requirements:
    pip install pyautogui pyperclip keyboard

Windows only (uses GetAsyncKeyState).
"""

import ctypes
import threading
import time
from datetime import datetime
from pathlib import Path

import keyboard
import pyautogui
import pyperclip


# ---------- SETTINGS ----------
COPY_REPEATS = 3
SHIFT_HOLD_SECONDS = 3
MOVE_TEST_PIXELS = 8
MOVE_TEST_DURATION = 0.20
LOG_FILE = Path(__file__).with_name("alt_diagnostic_log.txt")
# ------------------------------


# Windows key-state API
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short

VK_LMENU = 0xA4
VK_RMENU = 0xA5

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.03

log_lock = threading.Lock()
stop_event = threading.Event()
hook_installed = False
hotkeys_installed = False


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def alt_state():
    left = bool(user32.GetAsyncKeyState(VK_LMENU) & 0x8000)
    right = bool(user32.GetAsyncKeyState(VK_RMENU) & 0x8000)
    return f"L={left}, R={right}"


def log(message):
    line = f"[{timestamp()}] {message} | Windows Alt: {alt_state()}"
    with log_lock:
        print(line, flush=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def pause_for_stage(title, detail=""):
    print("\n" + "=" * 68)
    print(title)
    if detail:
        print(detail)
    answer = input("Нажми Enter для выполнения или введи s для пропуска: ")
    return answer.strip().lower() != "s"


def yes_no(prompt):
    return input(prompt + " [y/N]: ").strip().lower() in ("y", "yes", "д", "да")


def copy_once(label):
    log(label + " — BEFORE Ctrl+C")
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.15)
    text = pyperclip.paste()
    log(label + " — AFTER Ctrl+C; clipboard length=" + str(len(text)))
    return text


def stage_idle():
    log("STAGE 0 START — idle for 5 seconds")
    for second in range(5):
        time.sleep(1)
        log(f"Idle second {second + 1}/5")
    log("STAGE 0 END")


def stage_ctrl_c():
    log("STAGE 1 START — Ctrl+C without Shift")
    for i in range(COPY_REPEATS):
        copy_once(f"Ctrl+C repeat {i + 1}/{COPY_REPEATS}")
        time.sleep(0.5)
    log("STAGE 1 END")


def stage_shift_only():
    log("STAGE 2 START — Shift held, no other automation")
    pyautogui.keyDown("shiftleft")
    try:
        for second in range(SHIFT_HOLD_SECONDS):
            time.sleep(1)
            log(f"Shift-only second {second + 1}/{SHIFT_HOLD_SECONDS}")
    finally:
        pyautogui.keyUp("shiftleft")
        log("Shift released — stage 2")
    log("STAGE 2 END")


def stage_shift_ctrl_c():
    log("STAGE 3 START — Shift held during Ctrl+C")
    pyautogui.keyDown("shiftleft")
    try:
        for i in range(COPY_REPEATS):
            copy_once(f"Shift+Ctrl+C repeat {i + 1}/{COPY_REPEATS}")
            time.sleep(0.5)
    finally:
        pyautogui.keyUp("shiftleft")
        log("Shift released — stage 3")
    log("STAGE 3 END")


def stage_shift_click():
    log("STAGE 4 START — Shift+one click")
    pyautogui.keyDown("shiftleft")
    try:
        log("Immediately before Shift+click")
        pyautogui.click()
        log("Immediately after Shift+click")
        time.sleep(1)
    finally:
        pyautogui.keyUp("shiftleft")
        log("Shift released — stage 4")
    log("STAGE 4 END")


def stage_click_then_copy():
    log("STAGE 5 START — Shift+click followed by Ctrl+C")
    pyautogui.keyDown("shiftleft")
    try:
        log("Immediately before click")
        pyautogui.click()
        log("Immediately after click")
        time.sleep(0.15)
        copy_once("After Shift+click")
    finally:
        pyautogui.keyUp("shiftleft")
        log("Shift released — stage 5")
    log("STAGE 5 END")


def stage_mouse_move():
    log("STAGE 6 START — small smooth mouse movement, no keys/clicks")
    pyautogui.moveRel(
        MOVE_TEST_PIXELS, 0,
        duration=MOVE_TEST_DURATION,
        tween=pyautogui.easeInOutQuad,
    )
    log("Mouse moved right")
    pyautogui.moveRel(
        -MOVE_TEST_PIXELS, 0,
        duration=MOVE_TEST_DURATION,
        tween=pyautogui.easeInOutQuad,
    )
    log("Mouse returned to original position")
    log("STAGE 6 END")


def worker_test_cycle():
    """A minimal click-and-copy cycle, executed from a worker thread."""
    log("Worker thread started")
    pyautogui.keyDown("shiftleft")
    try:
        log("Worker: before click")
        pyautogui.click()
        log("Worker: after click")
        time.sleep(0.15)
        copy_once("Worker: Ctrl+C after click")
    finally:
        pyautogui.keyUp("shiftleft")
        log("Worker: Shift released")
    log("Worker thread finished")


def stage_worker_thread():
    log("STAGE 7 START — click+copy cycle in a separate thread")
    worker = threading.Thread(target=worker_test_cycle, name="diagnostic-worker")
    worker.start()
    worker.join()
    log("STAGE 7 END")


def keyboard_event_callback(event):
    # Keep the log readable: record modifier keys, test hotkeys and unknown events.
    name = str(getattr(event, "name", None)).lower()
    if name in {
        "alt", "left alt", "right alt", "ctrl", "left ctrl", "right ctrl",
        "shift", "left shift", "right shift", "f6", "f7", "f10", "none",
    }:
        event_type = getattr(event, "event_type", "?")
        scan_code = getattr(event, "scan_code", "?")
        log(f"keyboard hook: {name} {event_type}, scan_code={scan_code}")


def hotkey_callback(name):
    log(f"keyboard.add_hotkey callback fired: {name}")


def stage_keyboard_listener():
    global hook_installed, hotkeys_installed

    log("STAGE 8 START — keyboard hook + F6/F7/F10 hotkey listeners + worker")
    keyboard.hook(keyboard_event_callback)
    hook_installed = True

    keyboard.add_hotkey("f6", lambda: hotkey_callback("F6"))
    keyboard.add_hotkey("f7", lambda: hotkey_callback("F7"))
    keyboard.add_hotkey("f10", lambda: hotkey_callback("F10"))
    hotkeys_installed = True

    try:
        print("\nОбработчики keyboard активны.")
        print("Во время теста можно один раз нажать F6, F7 и F10 по отдельности.")
        print("Они только запишут событие в лог и НЕ запустят/остановят игру.")
        if yes_no("Запустить один цикл Shift+клик+Ctrl+C в отдельном потоке?"):
            stage_worker_thread()
        else:
            log("Worker cycle skipped in stage 8")
        input("Нажми Enter, когда закончишь проверять F6/F7/F10...")
    finally:
        keyboard.unhook_all()
        hook_installed = False
        hotkeys_installed = False
        log("keyboard hooks and hotkeys removed")
    log("STAGE 8 END")


def main():
    # Start a fresh log for this run.
    LOG_FILE.write_text(
        "PoE 2 extended Alt diagnostic\n"
        f"Started: {timestamp()}\n"
        "Each line includes a sampled Windows Alt state.\n\n",
        encoding="utf-8",
    )

    print("PoE 2 — расширенная диагностика Alt")
    print("Желательно одновременно оставить запущенным key_state_monitor.py.")
    print("Лог этой программы:", LOG_FILE)
    print()
    print("Важно:")
    print("- Ctrl+C проверяется без Shift отдельно.")
    print("- Каждый этап с кликом может потратить валюту.")
    print("- Этапы с кликом выполняются только после отдельного подтверждения.")
    print("- Для этапов Ctrl+C наведи курсор на предмет, чтобы игра скопировала его.")
    print("- Для этапов с кликом заранее проверь выбранную валюту и предмет.")
    print("- Перемещение мыши в верхний левый угол активирует аварийную остановку.")

    log("DIAGNOSTIC START")
    log("Initial state")

    try:
        if pause_for_stage("ЭТАП 0 — покой", "Ничего не нажимай 5 секунд."):
            stage_idle()

        if pause_for_stage("ЭТАП 1 — Ctrl+C без Shift",
                           "Будет 3 копирования. Курсор должен быть над предметом."):
            stage_ctrl_c()

        if pause_for_stage("ЭТАП 2 — только Shift",
                           "Shift будет удерживаться 3 секунды."):
            stage_shift_only()

        if pause_for_stage("ЭТАП 3 — Shift + Ctrl+C",
                           "Shift будет удерживаться во время 3 копирований."):
            stage_shift_ctrl_c()

        if pause_for_stage("ЭТАП 4 — Shift + один клик",
                           "ВНИМАНИЕ: один клик может потратить валюту."):
            if yes_no("Подтверждаешь один клик по предмету?"):
                stage_shift_click()
            else:
                log("STAGE 4 skipped by user")

        if pause_for_stage("ЭТАП 5 — Shift + клик + Ctrl+C",
                           "ВНИМАНИЕ: один клик может потратить валюту."):
            if yes_no("Подтверждаешь один клик по предмету?"):
                stage_click_then_copy()
            else:
                log("STAGE 5 skipped by user")

        if pause_for_stage("ЭТАП 6 — плавное движение мыши",
                           "Курсор сдвинется на 8 пикселей и вернётся обратно."):
            stage_mouse_move()

        if pause_for_stage("ЭТАП 7 — отдельный поток",
                           "ВНИМАНИЕ: один клик может потратить валюту."):
            if yes_no("Подтверждаешь один клик в отдельном потоке?"):
                stage_worker_thread()
            else:
                log("STAGE 7 skipped by user")

        if pause_for_stage("ЭТАП 8 — keyboard hooks + hotkeys",
                           "Проверяется сочетание обработчиков keyboard и потока."):
            stage_keyboard_listener()

    except pyautogui.FailSafeException:
        log("FAILSAFE triggered — mouse moved to screen corner")
    except KeyboardInterrupt:
        log("Interrupted by Ctrl+C in console")
    except Exception as exc:
        log(f"ERROR: {type(exc).__name__}: {exc}")
    finally:
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        log("DIAGNOSTIC FINISHED")
        print("\nГотово. Пришли оба файла:")
        print("1) alt_diagnostic_log.txt")
        print("2) key_state_log.txt (из внешнего монитора)")


if __name__ == "__main__":
    main()

