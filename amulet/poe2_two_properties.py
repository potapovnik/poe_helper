# -*- coding: utf-8 -*-
"""
PoE 2 — поиск двух свойств на одном предмете.

F6  — запуск
F7  — остановка
F10 — аварийная остановка и выход

Свойства задаются в settings.txt рядом с этим скриптом.
Все координаты заданы в физических пикселях экрана и НЕ масштабируются.
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

import pyautogui
import pyperclip
import pydirectinput


# ----------------------------- КООРДИНАТЫ -----------------------------

# Все координаты — физические пиксели экрана, без масштабирования.
CURRENCY_CHAOS = (85, 588)          # Сфера хаоса
CURRENCY_PERFECT_EXALTED = (238, 498)  # Perfect Exalted Orb («пэкз»)
CURRENCY_ANNUL = (529, 238)         # Сфера отмены

ITEM_POINT = (444, 603)             # Предмет, который перековываем

# ------------------------------- ЗАДЕРЖКИ ------------------------------

COPY_DELAY = 0.20                   # Сохранено из предыдущей программы
ITEM_CLICK_HOLD = 0.15
CURRENCY_CLICK_HOLD = 0.10
AFTER_CURRENCY_CLICK_DELAY = 0.15
AFTER_ITEM_CLICK_DELAY = 0.12
AFTER_ANNUL_DELAY = 0.20
CLIPBOARD_RETRIES = 3
START_COUNTDOWN = 3

START_KEY = 0x75   # F6
STOP_KEY = 0x76    # F7
EMERGENCY_KEY = 0x79  # F10

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "settings.txt"

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01
pydirectinput.PAUSE = 0.01

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()


def move_to(point):
    """Перемещение к точным физическим координатам экрана — без масштабирования."""
    pyautogui.moveTo(point[0], point[1], duration=0.12, tween=pyautogui.easeInOutQuad)


def click(button="left", point=None, hold=ITEM_CLICK_HOLD):
    if point is not None:
        move_to(point)
    pydirectinput.mouseDown(button=button)
    try:
        time.sleep(hold)
    finally:
        pydirectinput.mouseUp(button=button)


def click_currency(point, name):
    if not running:
        return False
    move_to(point)
    click(button="right", hold=CURRENCY_CLICK_HOLD)
    time.sleep(AFTER_CURRENCY_CLICK_DELAY)
    print(f"[ВАЛЮТА] ПКМ: {name} ({point[0]}, {point[1]})")
    return running


def click_item():
    """ЛКМ по предмету в точных физических координатах экрана — без масштабирования."""
    if not running:
        return
    pyautogui.moveTo(ITEM_POINT[0], ITEM_POINT[1], duration=0)
    click(button="left", hold=ITEM_CLICK_HOLD)
    time.sleep(AFTER_ITEM_CLICK_DELAY)


def read_item_text():
    """Ctrl+C по наведённому предмету и чтение текста из буфера обмена."""
    marker = "__POE2_TWO_MOD_MARKER__"
    for attempt in range(1, CLIPBOARD_RETRIES + 1):
        if not running:
            return ""

        try:
            pyperclip.copy(marker)
            pydirectinput.keyDown("ctrl")
            try:
                pydirectinput.keyDown("c")
                time.sleep(0.04)
            finally:
                pydirectinput.keyUp("c")
                pydirectinput.keyUp("ctrl")

            time.sleep(COPY_DELAY)
            copied = pyperclip.paste()
            if copied and copied != marker:
                return str(copied)

            print(f"[БУФЕР] Ctrl+C не вернул описание ({attempt}/{CLIPBOARD_RETRIES}).")
        except Exception as exc:
            print(f"[БУФЕР][ОШИБКА] {exc}")
            time.sleep(0.1)

    return ""


def normalize(text):
    return " ".join(text.casefold().replace("ё", "е").split())


def load_settings():
    if not SETTINGS_FILE.exists():
        raise FileNotFoundError(
            f"Не найден {SETTINGS_FILE.name}. Создай его рядом со скриптом."
        )

    values = {}
    for raw_line in SETTINGS_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().upper()] = value.strip()

    prop1 = values.get("PROPERTY_1", "")
    prop2 = values.get("PROPERTY_2", "")
    if not prop1 or not prop2:
        raise ValueError(
            "В settings.txt должны быть заполнены PROPERTY_1 и PROPERTY_2."
        )

    print(f"[НАСТРОЙКА] Первое свойство: {prop1}")
    print(f"[НАСТРОЙКА] Второе свойство: {prop2}")
    return normalize(prop1), normalize(prop2)


def contains_property(item_text, property_text):
    return bool(item_text) and property_text in normalize(item_text)


def release_all():
    for key in ("shift", "ctrl", "alt"):
        try:
            pydirectinput.keyUp(key)
        except Exception:
            pass
    for button in ("left", "right", "middle"):
        try:
            pydirectinput.mouseUp(button=button)
        except Exception:
            pass


def apply_chaos_until_first_property(property1):
    """
    Один раз зажимает Shift и применяет ПКМ по сфере хаоса.
    Затем, не возвращаясь к сфере, повторяет ЛКМ по предмету
    с Ctrl+C после каждого применения, пока не найдёт первое свойство.
    """
    print("[ХАОС] Зажимаю Shift и один раз выбираю сферу хаоса.")
    pydirectinput.keyDown("shift")
    try:
        if not click_currency(CURRENCY_CHAOS, "Сфера хаоса"):
            return False

        # После ПКМ по хаосу курсор переходит на предмет.
        # Shift остаётся зажатым на всём протяжении повторных кликов.
        while running:
            click_item()  # Предмет: точные координаты (444, 603), без масштабирования.
            item_text = read_item_text()
            if not item_text:
                print("[СТОП] Не удалось прочитать предмет. Не продолжаю тратить валюту.")
                return False

            if contains_property(item_text, property1):
                print("[НАЙДЕНО] Первое свойство найдено. Отпускаю Shift.")
                return True

            print("[ХАОС] Первого свойства пока нет — повторяю ЛКМ по предмету.")
    finally:
        pydirectinput.keyUp("shift")


def apply_perfect_exalted(property1, property2):
    """
    Добавляет второе свойство пэкзом.
    При неудаче отменяет добавленное свойство сферой отмены.
    Если первое свойство осталось — повторяет пэкз.
    Если исчезло — возвращает управление циклу хаоса.
    """
    while running:
        if not click_currency(CURRENCY_PERFECT_EXALTED, "Perfect Exalted Orb"):
            return "stop"

        click_item()
        item_text = read_item_text()
        if not item_text:
            print("[СТОП] Не удалось прочитать результат пэкза.")
            return "stop"

        if contains_property(item_text, property2):
            print("[УСПЕХ] Второе свойство найдено. Цикл завершён.")
            return "success"

        print("[ПЭКЗ] Второе свойство не совпало. Применяю сферу отмены.")
        if not click_currency(CURRENCY_ANNUL, "Сфера отмены"):
            return "stop"

        click_item()
        time.sleep(AFTER_ANNUL_DELAY)
        after_annul_text = read_item_text()
        if not after_annul_text:
            print("[СТОП] Не удалось прочитать предмет после сферы отмены.")
            return "stop"

        if contains_property(after_annul_text, property1):
            print("[ОТМЕНА] Первое свойство сохранилось — повторяю пэкз.")
            continue

        print("[ОТМЕНА] Первое свойство исчезло — возвращаюсь к сфере хаоса.")
        return "reroll"

    return "stop"


def run():
    global running
    property1, property2 = load_settings()

    print("\nПроверь: игра открыта, тайник виден, предмет находится по координатам (444, 603).")
    for remaining in range(START_COUNTDOWN, 0, -1):
        if not running:
            return
        print(f"Старт через {remaining}...")
        time.sleep(1)

    while running:
        first_found = apply_chaos_until_first_property(property1)
        if not running or not first_found:
            break

        result = apply_perfect_exalted(property1, property2)
        if result == "success":
            break
        if result == "stop":
            break
        # result == "reroll": новый проход хаосом, Shift будет зажат заново.


def start_cycle():
    global running, busy
    with state_lock:
        if busy:
            print("[ИНФО] Программа уже работает.")
            return
        busy = True

    try:
        run()
    except pyautogui.FailSafeException:
        print("[АВАРИЙНО] Сработал PyAutoGUI failsafe.")
    except Exception as exc:
        print(f"[ОШИБКА] {type(exc).__name__}: {exc}")
    finally:
        release_all()
        running = False
        with state_lock:
            busy = False
        print("[СОСТОЯНИЕ] Программа остановлена.")


def request_start():
    global running
    if busy:
        print("[ИНФО] Программа уже работает.")
        return
    running = True
    threading.Thread(target=start_cycle, daemon=True).start()


def request_stop():
    global running
    running = False
    release_all()
    print("\n[СТОП] Запрошена остановка.")


def request_emergency_exit():
    global running, exit_requested
    running = False
    exit_requested = True
    release_all()
    print("\n[АВАРИЙНО] F10 — остановка и выход.")


def main():
    global exit_requested
    if sys.platform != "win32":
        raise RuntimeError("Глобальные клавиши F6/F7/F10 доступны только в Windows.")

    print("PoE 2 — поиск двух свойств")
    print("F6 — запуск | F7 — остановка | F10 — остановка и выход")
    print("Перемещение курсора в левый верхний угол также остановит действия (failsafe).")
    print(f"Файл настроек: {SETTINGS_FILE}")

    user32 = ctypes.windll.user32
    keys = {"f6": START_KEY, "f7": STOP_KEY, "f10": EMERGENCY_KEY}
    previous = {name: False for name in keys}

    try:
        while not exit_requested:
            for name, code in keys.items():
                down = bool(user32.GetAsyncKeyState(code) & 0x8000)
                pressed = down and not previous[name]
                previous[name] = down
                if pressed:
                    if name == "f6":
                        request_start()
                    elif name == "f7":
                        request_stop()
                    elif name == "f10":
                        request_emergency_exit()
                        break
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        request_stop()
        release_all()
        print("Программа завершена.")


if __name__ == "__main__":
    main()
