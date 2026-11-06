# -*- coding: utf-8 -*-
"""
PoE 2 — объединённые первый и второй блоки обработки плиток.

Блок 1: Сфера трансмутации -> вся сетка; затем Сфера усиления -> вся сетка.
Блок 2:
  1) Сфера царей: Ctrl+C подсказки, совпадения со строками magic_tqrget.txt
     кликаются ЛКМ и записываются в rare_tablet по зелёным вкладкам.
  2) Сфера возвышения: повторно кликаются только позиции rare_tablet.
  3) Сфера алхимии: кликаются все позиции, которых нет в rare_tablet.
Shift отпускается после каждого прохода.
"""

import ctypes
import sys
import threading
import time
from pathlib import Path

import pyperclip

# Устанавливаем DPI awareness до импорта библиотек управления мышью.
# Это помогает согласовать координаты с физическими пикселями при Windows 150%.
if sys.platform == "win32":
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import pyautogui
import pydirectinput


# =============================== НАСТРОЙКИ ===============================

# Эталонное разрешение, на котором были согласованы координаты.
REFERENCE_SCREEN_WIDTH = 1650
REFERENCE_SCREEN_HEIGHT = 927

# --- Навигация по вертикальному списку вкладок справа от тайника ---
# Координаты ориентировочные по присланному скриншоту.
RIGHT_TAB_CURRENCY = (627, 192)
RIGHT_TAB_TILES = (627, 292)

# --- Центральные вкладки внутри раздела «Плитки» ---
CENTER_TAB_TILES = (286, 138)

# После перехода в центральную вкладку «Плитки» выбираем пятый значок
# в верхнем ряду над зелёными вкладками (слева направо).
INITIAL_TILE_ICON = 5
TILE_ICON_BUTTONS = {
    1: (73, 204),
    2: (126, 204),
    3: (178, 204),
    4: (230, 204),
    5: (283, 204),
    6: (335, 204),
    7: (387, 204),
    8: (439, 204),
    9: (491, 204),
}

# --- Координаты валют в валютной вкладке ---
# Сфера трансмутации (количество 3111 на пользовательском скриншоте).
CURRENCY_TRANSMUTATION = (53, 155)

# Сфера усиления (количество 4712 на пользовательском скриншоте).
CURRENCY_AUGMENTATION = (53, 205)
# По расположению валют на скриншоте пользователя:
CURRENCY_KINGS = (53, 255)       # Сфера царей, 4457
CURRENCY_EXALTED = (53, 305)     # Сфера возвышения, 4678
CURRENCY_ALCHEMY = (226, 155)   # Сфера алхимии, 106
CURRENCY_CHAOS = (53, 405)     # Сфера хаоса, 51 (координата по текущему скриншоту)

# --- Настройки третьего блока ---
TARGET_FILE = Path(__file__).with_name("target.txt")
TARGET_PROPERTIES_REQUIRED = 3  # Сколько свойств из target.txt нужно получить

# Файл со свойствами: по одному значению на строку, рядом со скриптом.
MAGIC_TARGET_FILE = Path(__file__).with_name("magic_tqrget.txt")
COPY_DELAY = 0.25

# --- Зелёные вкладки 1–6 ---
TAB_BUTTONS = {
    1: (159, 257),
    2: (211, 257),
    3: (263, 257),
    4: (315, 257),
    5: (367, 257),
    6: (419, 257),
}

# --- Сетка предметов внутри каждой зелёной вкладки ---
DEFAULT_COLUMNS = 12
DEFAULT_ROWS = 5
GRID_FIRST_ITEM = (56, 299)
MOVE_RIGHT_PIXELS = 65
MOVE_DOWN_PIXELS = 65
# Скорость перемещения курсора между интерфейсными элементами (секунды).
# Увеличивай значение, если хочешь визуально отслеживать движение мыши.
MOUSE_MOVE_DURATION = 1.00

# Пауза после наведения на важные элементы, чтобы успеть проверить координаты.
# Во время этой паузы клик ещё НЕ выполняется.
AFTER_UI_HOVER_PAUSE = 3.0
AFTER_CURRENCY_HOVER_PAUSE = 3.0

# Скорость перемещения по сетке предметов (секунды на один шаг).
GRID_MOVE_DURATION = 0.35

# --- Задержки ---
UI_CLICK_HOLD = 0.10
ITEM_CLICK_HOLD = 0.15
AFTER_ITEM_CLICK_DELAY = 0.10
AFTER_CURRENCY_CLICK_DELAY = 0.35
AFTER_NAVIGATION_DELAY = 0.45
AFTER_GREEN_TAB_DELAY = 0.30
START_COUNTDOWN = 3

# --- Клавиши управления ---
START_KEY = 0x75       # F6
STOP_KEY = 0x76        # F7
EMERGENCY_KEY = 0x79   # F10

# ==========================================================================

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01
pydirectinput.PAUSE = 0.01

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()

ROWS = DEFAULT_ROWS
COLUMNS = DEFAULT_COLUMNS
SELECTED_TABS = [1, 2, 3, 4, 5, 6]
rare_tablet = {}


def get_screen_scale():
    width, height = pyautogui.size()
    sx = width / REFERENCE_SCREEN_WIDTH
    sy = height / REFERENCE_SCREEN_HEIGHT
    print(
        f"Экран: {width}x{height}; масштаб координат: "
        f"x={sx:.3f}, y={sy:.3f}"
    )
    return sx, sy


def scaled_point(point, scale):
    return round(point[0] * scale[0]), round(point[1] * scale[1])


def move_to(point, scale, duration=None):
    x, y = scaled_point(point, scale)
    if duration is None:
        duration = MOUSE_MOVE_DURATION
    # PyAutoGUI действительно выполняет плавное перемещение за duration секунд.
    pyautogui.moveTo(
        x, y,
        duration=duration,
        tween=pyautogui.easeInOutQuad,
    )


def click_at(point, scale, button="left", hold=UI_CLICK_HOLD):
    """Клик по точке, заданной в координатах эталонного скриншота."""
    if not running:
        return
    move_to(point, scale)
    time.sleep(AFTER_UI_HOVER_PAUSE)
    if not running:
        return
    pydirectinput.mouseDown(button=button)
    try:
        time.sleep(hold)
    finally:
        pydirectinput.mouseUp(button=button)


def click_item():
    """ЛКМ по текущей ячейке сетки."""
    if not running:
        return
    pydirectinput.mouseDown(button="left")
    try:
        time.sleep(ITEM_CLICK_HOLD)
    finally:
        pydirectinput.mouseUp(button="left")
    time.sleep(AFTER_ITEM_CLICK_DELAY)


def hold_shift():
    pydirectinput.keyDown("shift")
    time.sleep(0.12)
    print("[КЛАВИАТУРА] Shift зажат.")


def release_shift():
    try:
        pydirectinput.keyUp("shift")
    except Exception:
        pass
    print("[КЛАВИАТУРА] Shift отпущен.")


def release_all_inputs():
    release_shift()
    for button in ("left", "right", "middle"):
        try:
            pydirectinput.mouseUp(button=button)
        except Exception:
            pass


def open_currency_tab(scale):
    if not running:
        return
    print("[НАВИГАЦИЯ] Открываю вертикальную вкладку «Валюта».")
    click_at(RIGHT_TAB_CURRENCY, scale)
    time.sleep(AFTER_NAVIGATION_DELAY)


def apply_currency(currency_name, currency_point, scale, shift_before_hover):
    """
    Открывает валютную вкладку и применяет валюту ПКМ.
    Порядок Shift/наведения задаётся отдельно для каждого прохода.
    Shift остаётся зажатым до завершения обработки плиток.
    """
    if not running:
        return False

    open_currency_tab(scale)

    if shift_before_hover:
        hold_shift()
        if not running:
            return False

    print(f"[ВАЛЮТА] Навожу на {currency_name}: {currency_point}.")
    move_to(currency_point, scale)
    print(f"[ПРОВЕРКА] Пауза {AFTER_CURRENCY_HOVER_PAUSE:.1f} сек. перед ПКМ.")
    time.sleep(AFTER_CURRENCY_HOVER_PAUSE)
    if not running:
        return False

    if not shift_before_hover:
        hold_shift()
        if not running:
            return False

    print(f"[ВАЛЮТА] ПКМ по предмету «{currency_name}».")
    pydirectinput.mouseDown(button="right")
    try:
        time.sleep(UI_CLICK_HOLD)
    finally:
        pydirectinput.mouseUp(button="right")

    time.sleep(AFTER_CURRENCY_CLICK_DELAY)
    return True


def open_tiles_and_initial_tab(scale):
    """Переход: вертикальная «Плитки» -> центральная «Плитки» -> значок №5 сверху."""
    if not running:
        return

    print("[НАВИГАЦИЯ] Открываю вертикальную вкладку «Плитки».")
    click_at(RIGHT_TAB_TILES, scale)
    time.sleep(AFTER_NAVIGATION_DELAY)

    if not running:
        return

    print("[НАВИГАЦИЯ] Выбираю центральную вкладку «Плитки».")
    click_at(CENTER_TAB_TILES, scale)
    time.sleep(AFTER_NAVIGATION_DELAY)

    if not running:
        return

    print(f"[НАВИГАЦИЯ] Выбираю верхний значок плитки №{INITIAL_TILE_ICON}.")
    click_at(TILE_ICON_BUTTONS[INITIAL_TILE_ICON], scale)
    time.sleep(AFTER_GREEN_TAB_DELAY)


def move_smooth(dx, dy):
    if not running:
        return
    pyautogui.moveRel(
        dx,
        dy,
        duration=GRID_MOVE_DURATION,
        tween=pyautogui.easeInOutQuad,
    )


def process_one_green_tab(tab_number, scale):
    """Открывает одну зелёную вкладку и кликает по сетке слева направо, сверху вниз."""
    if not running:
        return

    print(f"\n[ВКЛАДКА] Обрабатываю зелёную вкладку №{tab_number}.")
    click_at(TAB_BUTTONS[tab_number], scale)
    time.sleep(AFTER_GREEN_TAB_DELAY)

    if not running:
        return

    first_x, first_y = scaled_point(GRID_FIRST_ITEM, scale)
    pyautogui.moveTo(
        first_x,
        first_y,
        duration=MOUSE_MOVE_DURATION,
        tween=pyautogui.easeInOutQuad,
    )
    time.sleep(AFTER_UI_HOVER_PAUSE)
    if not running:
        return

    for row in range(1, ROWS + 1):
        if not running:
            break

        print(f"[СЕТКА] Строка {row}/{ROWS}.")
        for column in range(1, COLUMNS + 1):
            if not running:
                break

            click_item()

            if not running:
                break

            if column < COLUMNS:
                move_smooth(MOVE_RIGHT_PIXELS, 0)

        # Возвращаемся к первому столбцу и опускаемся на следующую строку.
        if running and row < ROWS:
            if COLUMNS > 1:
                move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)
            move_smooth(0, MOVE_DOWN_PIXELS)


def process_selected_green_tabs(scale):
    """Один и тот же список вкладок и одна сетка используются для обеих валют."""
    for tab_number in SELECTED_TABS:
        if not running:
            break
        process_one_green_tab(tab_number, scale)


def run_currency_pass(currency_name, currency_point, scale, shift_before_hover):
    """Полный проход одной валюты: применить валюту, открыть плитки, обработать вкладки."""
    if not running:
        return

    print("\\n" + "=" * 58)
    print(f"[ЭТАП] Начинаю проход: {currency_name}")
    print("=" * 58)

    if not apply_currency(currency_name, currency_point, scale, shift_before_hover):
        return

    open_tiles_and_initial_tab(scale)
    if not running:
        return

    process_selected_green_tabs(scale)

    if running:
        release_shift()
        print(f"[ЭТАП] Проход «{currency_name}» завершён.")



def load_magic_targets():
    if not MAGIC_TARGET_FILE.exists():
        raise FileNotFoundError(
            f"Не найден файл {MAGIC_TARGET_FILE.name}. "
            "Положи его рядом с программой."
        )
    values = [line.strip().casefold() for line in MAGIC_TARGET_FILE.read_text(
        encoding="utf-8-sig"
    ).splitlines() if line.strip()]
    if not values:
        raise ValueError(f"Файл {MAGIC_TARGET_FILE.name} пуст.")
    print(f"[ФИЛЬТР] Загружено свойств: {len(values)}")
    return values


def read_hovered_item_text():
    """Копирует подсказку предмета через Ctrl+C и возвращает текст буфера."""
    marker = "__POE2_CLIPBOARD_MARKER__"
    try:
        pyperclip.copy(marker)
        pyautogui.hotkey("ctrl", "c")
        time.sleep(COPY_DELAY)
        copied = pyperclip.paste()
        if not copied or copied == marker:
            return ""
        return str(copied)
    except Exception as exc:
        print(f"[БУФЕР] Не удалось прочитать буфер обмена: {exc}")
        return ""


def item_matches_targets(item_text, targets):
    normalized = " ".join(item_text.casefold().split())
    return any(target in normalized for target in targets)


def grid_position(row, column):
    return f"{row}.{column}"


def move_to_grid_position(row, column, scale):
    x = GRID_FIRST_ITEM[0] + (column - 1) * MOVE_RIGHT_PIXELS
    y = GRID_FIRST_ITEM[1] + (row - 1) * MOVE_DOWN_PIXELS
    move_to((x, y), scale, duration=GRID_MOVE_DURATION)


def process_grid_for_kings(tab_number, scale, targets):
    """Проверяет всю сетку, кликает совпадения и заполняет rare_tablet."""
    rare_tablet[tab_number] = []
    click_at(TAB_BUTTONS[tab_number], scale)
    time.sleep(AFTER_GREEN_TAB_DELAY)
    for row in range(1, ROWS + 1):
        for column in range(1, COLUMNS + 1):
            if not running:
                return
            move_to_grid_position(row, column, scale)
            item_text = read_hovered_item_text()
            if item_matches_targets(item_text, targets):
                pos = grid_position(row, column)
                print(f"[СОВПАДЕНИЕ] Вкладка {tab_number}, позиция {pos}")
                click_item()
                rare_tablet[tab_number].append(pos)
    print(f"[RARE] Вкладка {tab_number}: {rare_tablet[tab_number]}")


def process_saved_positions(tab_number, scale):
    """Обрабатывает только позиции, записанные на этой зелёной вкладке."""
    positions = set(rare_tablet.get(tab_number, []))
    click_at(TAB_BUTTONS[tab_number], scale)
    time.sleep(AFTER_GREEN_TAB_DELAY)
    for row in range(1, ROWS + 1):
        for column in range(1, COLUMNS + 1):
            if not running:
                return
            if grid_position(row, column) in positions:
                move_to_grid_position(row, column, scale)
                click_item()


def process_unmatched_positions(tab_number, scale):
    """Обрабатывает все ячейки, отсутствующие в rare_tablet этой вкладки."""
    positions = set(rare_tablet.get(tab_number, []))
    click_at(TAB_BUTTONS[tab_number], scale)
    time.sleep(AFTER_GREEN_TAB_DELAY)
    for row in range(1, ROWS + 1):
        for column in range(1, COLUMNS + 1):
            if not running:
                return
            if grid_position(row, column) not in positions:
                move_to_grid_position(row, column, scale)
                click_item()


def run_selected_tabs(processor, scale, *args):
    for tab_number in SELECTED_TABS:
        if not running:
            break
        processor(tab_number, scale, *args)


def run_second_block(scale):
    global rare_tablet
    targets = load_magic_targets()
    rare_tablet = {}

    print("\n[БЛОК 2 / ПРОХОД 1] Сфера царей: отбор по magic_tqrget.txt")
    if not apply_currency("Сфера царей", CURRENCY_KINGS, scale, shift_before_hover=False):
        return
    open_tiles_and_initial_tab(scale)
    run_selected_tabs(process_grid_for_kings, scale, targets)
    if not running:
        return
    release_shift()

    print("\n[БЛОК 2 / ПРОХОД 2] Сфера возвышения: только rare_tablet")
    if not apply_currency("Сфера возвышения", CURRENCY_EXALTED, scale, shift_before_hover=False):
        return
    open_tiles_and_initial_tab(scale)
    run_selected_tabs(process_saved_positions, scale)
    if not running:
        return
    release_shift()

    print("\n[БЛОК 2 / ПРОХОД 3] Сфера алхимии: всё вне rare_tablet")
    if not apply_currency("Сфера алхимии", CURRENCY_ALCHEMY, scale, shift_before_hover=False):
        return
    open_tiles_and_initial_tab(scale)
    run_selected_tabs(process_unmatched_positions, scale)
    if running:
        release_shift()
        print("[БЛОК 2] Завершён.")



def load_target_properties():
    """Загружает свойства для третьего блока: по одному на строку target.txt."""
    if not TARGET_FILE.exists():
        raise FileNotFoundError(
            f"Не найден файл {TARGET_FILE.name}. Положи его рядом с программой."
        )
    values = [
        line.strip().casefold()
        for line in TARGET_FILE.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    if not values:
        raise ValueError(f"Файл {TARGET_FILE.name} пуст.")
    print(f"[TARGET] Загружено свойств: {len(values)}")
    print(f"[TARGET] Требуемое количество свойств: {TARGET_PROPERTIES_REQUIRED}")
    return values


def count_target_matches(item_text, targets):
    """Считает число уникальных целевых строк, присутствующих в подсказке предмета."""
    normalized = " ".join(item_text.casefold().split())
    return sum(1 for target in set(targets) if target in normalized)


def process_grid_with_chaos(tab_number, scale, targets):
    """
    Проходит всю сетку. Если найдено от 1 до REQUIRED-1 целевых свойств,
    применяет хаос повторно до достижения порога или исчезновения всех совпадений.
    """
    click_at(TAB_BUTTONS[tab_number], scale)
    time.sleep(AFTER_GREEN_TAB_DELAY)

    for row in range(1, ROWS + 1):
        for column in range(1, COLUMNS + 1):
            if not running:
                return

            move_to_grid_position(row, column, scale)
            item_text = read_hovered_item_text()
            match_count = count_target_matches(item_text, targets)

            if match_count == 0:
                continue

            print(
                f"[ХАОС] Вкладка {tab_number}, позиция {row}.{column}: "
                f"найдено свойств {match_count}/{TARGET_PROPERTIES_REQUIRED}."
            )

            while running and 0 < match_count < TARGET_PROPERTIES_REQUIRED:
                click_item()
                # После применения хаоса заново копируем изменившуюся подсказку.
                item_text = read_hovered_item_text()
                new_match_count = count_target_matches(item_text, targets)

                print(
                    f"[ХАОС] После перековки {row}.{column}: "
                    f"{new_match_count}/{TARGET_PROPERTIES_REQUIRED}."
                )

                # Если буфер не обновился/не удалось скопировать текст,
                # не повторяем клики вслепую.
                if not item_text:
                    print("[ХАОС] Не удалось получить текст после клика; предмет пропущен.")
                    break

                match_count = new_match_count

            if not running:
                return


def run_third_block(scale):
    targets = load_target_properties()

    print("\n[БЛОК 3] Сфера хаоса: поиск целевых свойств и повторная перековка.")
    # На случай, если предыдущий блок завершился до штатного отпускания Shift.
    release_shift()

    if not apply_currency(
        "Сфера хаоса", CURRENCY_CHAOS, scale, shift_before_hover=False
    ):
        return

    open_tiles_and_initial_tab(scale)
    run_selected_tabs(process_grid_with_chaos, scale, targets)

    if running:
        release_shift()
        print("[БЛОК 3] Завершён.")

def start_cycle():
    global running, busy

    with state_lock:
        if busy:
            print("[ИНФО] Цикл уже выполняется.")
            return
        busy = True

    try:
        scale = get_screen_scale()
        print("\nПроверь, что игра открыта, тайник виден и выбран нужный персонаж.")
        for remaining in range(START_COUNTDOWN, 0, -1):
            if not running:
                print("[СТОП] Запуск отменён во время обратного отсчёта.")
                return
            print(f"Старт через {remaining}...")
            time.sleep(1)

        if not running:
            return

        # Проход 1: Сфера трансмутации.
        run_currency_pass(
            "Сфера трансмутации",
            CURRENCY_TRANSMUTATION,
            scale,
            shift_before_hover=True,
        )

        if not running:
            return

        # После первого прохода Shift уже отпущен.
        # Повторно открываем валюту, выбираем сферу усиления и повторяем цикл.
        run_currency_pass(
            "Сфера усиления",
            CURRENCY_AUGMENTATION,
            scale,
            shift_before_hover=False,
        )

        if not running:
            return

        # Блок 2: царей -> возвышения по rare_tablet -> алхимия по дополнению.
        run_second_block(scale)

        if not running:
            return

        # Блок 3: Сфера хаоса по target.txt.
        run_third_block(scale)

        if running:
            print("\n[ГОТОВО] Все три блока завершены.")

    except pyautogui.FailSafeException:
        print("[ОСТАНОВКА] Сработал PyAutoGUI failsafe (курсор в верхнем левом углу).")
    except Exception as exc:
        print(f"[ОШИБКА] {type(exc).__name__}: {exc}")
    finally:
        release_all_inputs()
        running = False
        with state_lock:
            busy = False
        print("[СОСТОЯНИЕ] Цикл остановлен.")


def request_start():
    global running
    if busy:
        print("[ИНФО] Цикл уже выполняется.")
        return
    running = True
    threading.Thread(target=start_cycle, daemon=True).start()


def request_stop():
    global running
    running = False
    print("\n[СТОП] Запрошена остановка. Текущие нажатия будут отпущены.")


def request_emergency_exit():
    global running, exit_requested
    running = False
    exit_requested = True
    release_all_inputs()
    print("\n[АВАРИЙНО] F10 — немедленная остановка и выход.")


def parse_tabs(raw):
    """Примеры: 1-6 или 1,3,5-6."""
    if not raw.strip():
        return [1, 2, 3, 4, 5, 6]

    selected = set()
    for part in raw.split(","):
        part = part.strip()
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


def ask_positive_int(prompt, default):
    raw = input(f"{prompt} [{default}]: ").strip()
    if not raw:
        return default
    value = int(raw)
    if value < 1:
        raise ValueError("Значение должно быть не меньше 1.")
    return value


def configure():
    global ROWS, COLUMNS, SELECTED_TABS

    print("Настройка сетки и зелёных вкладок.")
    COLUMNS = ask_positive_int("Количество столбцов", DEFAULT_COLUMNS)
    ROWS = ask_positive_int("Количество строк", DEFAULT_ROWS)

    while True:
        raw = input(
            "Зелёные вкладки (например 1-6 или 1,3,5-6; Enter = все): "
        ).strip()
        try:
            SELECTED_TABS = parse_tabs(raw)
            break
        except (ValueError, TypeError):
            print("Неверный ввод. Доступны вкладки 1–6.")

    print(f"\nСетка: {COLUMNS} столбцов x {ROWS} строк.")
    print(f"Зелёные вкладки для обработки: {SELECTED_TABS}")


def main():
    global exit_requested

    if sys.platform != "win32":
        raise RuntimeError("Глобальные клавиши F6/F7/F10 доступны только в Windows.")

    print("PoE 2 — объединённые три блока обработки плиток")
    configure()

    print("\nУправление:")
    print("F6  — запустить оба блока последовательно")
    print("F7  — остановить цикл")
    print("F10 — аварийная остановка и выход")
    print("PyAutoGUI failsafe: перемести курсор в верхний левый угол экрана.")
    print("\nПоложи magic_tqrget.txt и target.txt рядом со скриптом. Перед тестом оставь открытым тайник. Начинай с короткого списка вкладок.")

    user32 = ctypes.windll.user32
    key_codes = {"f6": START_KEY, "f7": STOP_KEY, "f10": EMERGENCY_KEY}
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
                        request_stop()
                    elif name == "f10":
                        request_emergency_exit()
                        break

            time.sleep(0.02)

    except KeyboardInterrupt:
        pass
    finally:
        request_stop()
        release_all_inputs()
        print("Программа завершена.")


if __name__ == "__main__":
    main()
