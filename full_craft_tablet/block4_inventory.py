# -*- coding: utf-8 -*-
"""Блок 4: отбор 60 предметов без целевых свойств, перековка и возврат в тайник."""
from __future__ import annotations

import time
from pathlib import Path

import pyautogui
import pyperclip
import pydirectinput

# Координаты верстака — эталон прежней программы.
REFORGE_REFERENCE_SIZE = (2560, 1440)
# Координаты инвентаря сняты непосредственно со скриншота 2048x1152.
INVENTORY_REFERENCE_SIZE = (2048, 1152)
REFORGE_BUTTON = (838, 1154)
REFORGE_OUTPUT = (838, 541)
# Центры первых ячеек каждой строки инвентаря для рефорджа.
# Первая строка сохранена; координаты строк 2–5 заданы пользователем.
INVENTORY_ROW_STARTS = (
    (1731, 821),
    (1726, 883),
    (1727, 957),
    (1733, 1028),
    (1735, 1102),
)
INVENTORY_CELL_W = 71
INVENTORY_CELL_H = 71
INVENTORY_COLUMNS = 12
INVENTORY_ROWS = 5

# Сетка инвентаря справа для блока 5: 4 столбца x 5 строк.
BLOCK5_INVENTORY_FIRST = (1731, 821)
BLOCK5_INVENTORY_CELL_W = 71
BLOCK5_INVENTORY_CELL_H = 71

# Задержки и количество циклов — как в прежней программе перековки.
CLICK_DELAY = 0.4
FORGE_DELAY = 0.1
OUTPUT_DELAY = 1.2
BATCH_DELAY = 0.3
MOVE_DURATION = 0.2
REFORGE_MOVE_DURATION = 0.4
CLICK_DURATION = 0.1
COPY_DELAY = 0.25
REQUIRED_ITEMS = 60


def _screen_scale():
    width, height = pyautogui.size()
    return width / REFORGE_REFERENCE_SIZE[0], height / REFORGE_REFERENCE_SIZE[1]


def _scaled(point, scale):
    return round(point[0] * scale[0]), round(point[1] * scale[1])


def _move(point, scale, duration=MOVE_DURATION):
    x, y = _scaled(point, scale)
    pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)


def _read_hovered_item_text():
    marker = "__POE2_BLOCK4_CLIPBOARD_MARKER__"
    try:
        pyperclip.copy(marker)
        pydirectinput.keyDown("ctrl")
        try:
            pydirectinput.keyDown("c")
            time.sleep(0.03)
        finally:
            pydirectinput.keyUp("c")
            pydirectinput.keyUp("ctrl")
        time.sleep(COPY_DELAY)
        copied = pyperclip.paste()
        if not copied or copied == marker:
            return ""
        return str(copied)
    except Exception as exc:
        print(f"[БЛОК 4][БУФЕР] Ошибка чтения: {exc}")
        return ""


def _count_matches(text, targets):
    normalized = " ".join(text.casefold().split())
    return sum(1 for target in set(targets) if target in normalized)


def _click(button="left", x=None, y=None):
    """Нажатие мыши с заданной длительностью удержания."""
    if x is not None and y is not None:
        pyautogui.moveTo(x, y, duration=0)
    pydirectinput.mouseDown(button=button)
    try:
        time.sleep(CLICK_DURATION)
    finally:
        pydirectinput.mouseUp(button=button)


def _scan_for_60(main, targets, start_cursor=0):
    """Один проход: проверяет ячейку и сразу Ctrl-кликом выбирает подходящий предмет."""
    cursor = start_cursor
    scale = main.get_screen_scale()
    cells_per_tab = main.ROWS * main.COLUMNS
    total_cells = len(main.SELECTED_TABS) * cells_per_tab
    selected_count = 0
    last_tab_index = None
    # Храним только хвост из 1–2 последних выбранных ячеек, чтобы при конце
    # сетки вернуть неполную группу в тайник. Полный список кандидатов не создаётся.
    pending_tail = []

    while cursor < total_cells and selected_count < REQUIRED_ITEMS and main.running:
        tab_index, cell_index = divmod(cursor, cells_per_tab)
        tab = main.SELECTED_TABS[tab_index]
        row, col = divmod(cell_index, main.COLUMNS)
        row += 1
        col += 1
        if tab_index != last_tab_index:
            main.click_at(main.TAB_BUTTONS[tab], scale)
            time.sleep(main.AFTER_GREEN_TAB_DELAY)
            last_tab_index = tab_index

        main.move_to_grid_position(row, col, scale)
        item_text = _read_hovered_item_text()
        matches = _count_matches(item_text, targets) if item_text else 0

        # Только непустой текст без целевых свойств считается подходящим.
        # Выбор выполняется сразу на текущей ячейке, без второго полного обхода.
        if item_text and matches == 0:
            pydirectinput.keyDown("ctrl")
            try:
                _click()
                time.sleep(0.15)
            finally:
                pydirectinput.keyUp("ctrl")
            selected_count += 1
            pending_tail.append((tab, row, col))
            if len(pending_tail) > 2:
                pending_tail.pop(0)
            print(
                f"[БЛОК 4] Сразу выбран предмет {selected_count}/{REQUIRED_ITEMS}: "
                f"вкладка {tab}, ячейка {row}.{col}."
            )

        cursor += 1

    # Для рефорджа нужны полные тройки. Если в конце остались 1–2 предмета,
    # снимаем их выделение и возвращаем в тайник; повторного сканирования нет.
    remainder = selected_count % 3
    if remainder and main.running:
        scale = main.get_screen_scale()
        for tab, row, col in pending_tail[-remainder:]:
            if tab != last_tab_index:
                main.click_at(main.TAB_BUTTONS[tab], scale)
                time.sleep(main.AFTER_GREEN_TAB_DELAY)
                last_tab_index = tab
            main.move_to_grid_position(row, col, scale)
            pydirectinput.keyDown("ctrl")
            try:
                _click()
                time.sleep(0.15)
            finally:
                pydirectinput.keyUp("ctrl")
        selected_count -= remainder
        print(f"[БЛОК 4] Возвращены в тайник {remainder} предмета(ов): неполная группа.")

    return selected_count, cursor, total_cells


def _run_reforge_batches(main, batch_count):
    scale = _screen_scale()
    pydirectinput.keyDown("ctrl")
    try:
        for batch in range(batch_count):
            if not main.running:
                print("[БЛОК 4][СТОП] Перековка прервана пользователем.")
                break
            for slot in range(3):
                if not main.running:
                    break
                row = (batch * 3 + slot) // INVENTORY_COLUMNS
                col = (batch * 3 + slot) % INVENTORY_COLUMNS
                row_start_x, row_start_y = INVENTORY_ROW_STARTS[row]
                point = (
                    row_start_x + col * INVENTORY_CELL_W,
                    row_start_y,
                )
                # Для сетки инвентаря используем координаты скриншота напрямую:
                # не применяем масштаб верстака повторно.
                pyautogui.moveTo(
                    point[0], point[1],
                    duration=MOVE_DURATION,
                    tween=pyautogui.easeInOutQuad,
                )
                # Небольшая пауза перед первым кликом каждой строки,
                # чтобы игра успела обработать переход курсора на новую строку.
                if col == 0:
                    time.sleep(0.3)
                _click()
                time.sleep(0.15)
                time.sleep(CLICK_DELAY)
            _move(REFORGE_BUTTON, scale, duration=REFORGE_MOVE_DURATION)
            _click()
            time.sleep(0.15)
            time.sleep(FORGE_DELAY)
            _move(REFORGE_OUTPUT, scale, duration=REFORGE_MOVE_DURATION)
            time.sleep(OUTPUT_DELAY)
            _click()
            time.sleep(0.15)
            time.sleep(BATCH_DELAY)
            print(f"[БЛОК 4][ПЕРЕКОВКА] Пакет {batch + 1}/{batch_count} завершён.")
    finally:
        pydirectinput.keyUp("ctrl")


def run_block4(main, start_cursor=0):
    """Отбирает следующую партию, выполняет рефордж и возвращает курсор сканирования."""
    print("\n[БЛОК 4] Отбор следующих предметов без свойств из target.txt.")
    targets = main.load_target_properties()
    main.release_shift(force=True)

    selected, next_cursor, total_cells = _scan_for_60(main, targets, start_cursor)
    time.sleep(0.4)
    if not main.running:
        return next_cursor, 0, total_cells
    if selected == 0:
        print("[БЛОК 4][КОНЕЦ] Больше нет полной тройки подходящих предметов.")
        return next_cursor, 0, total_cells

    batch_count = selected // 3

    pydirectinput.press("esc")
    time.sleep(0.3)

    import poe2_target_clicker as clicker
    pydirectinput.PAUSE = 0.01
    if not clicker.move_to_target("Верстак для перековки"):
        print("[БЛОК 4][ОШИБКА] Не удалось открыть верстак. Остановка блока.")
        return next_cursor, 0, total_cells
    time.sleep(2.0)

    print(f"[БЛОК 4] Запускаю перековку {batch_count} пакетов по 3 предмета.")
    _run_reforge_batches(main, batch_count)

    # После завершения рефорджа ждём 1 секунду, затем закрываем верстак.
    time.sleep(1.0)
    pydirectinput.press("esc")
    time.sleep(0.3)

    position = clicker.wait_for_target("Дориани")
    if position is None:
        print("[БЛОК 4][ОШИБКА] Не удалось найти Дориани после перековки.")
        return next_cursor, 0, total_cells
    doriani_x, doriani_y = position
    _click(x=doriani_x, y=doriani_y)
    if not clicker.wait_for_interaction("Дориани"):
        print("[БЛОК 4][ОШИБКА] Окно Дориани не открылось.")
        return next_cursor, 0, total_cells
    time.sleep(1.0)

    pydirectinput.keyDown("ctrl")
    try:
        _click(x=doriani_x, y=doriani_y)
        time.sleep(0.15)
    finally:
        pydirectinput.keyUp("ctrl")

    pydirectinput.press("esc")
    time.sleep(0.3)
    if not clicker.move_to_target("Тайник"):
        print("[БЛОК 4][ОШИБКА] Не удалось вернуться к тайнику.")
        return next_cursor, 0, total_cells
    time.sleep(2.0)
    main.open_currency_tab(main.get_screen_scale())
    print(f"[БЛОК 4] Завершён. Выбрано {selected}, создано {batch_count} предметов. Курсор: {next_cursor}/{total_cells}.")
    return next_cursor, batch_count, total_cells


def run_block5(main, item_count=20):
    """Блок 5: Дориани -> тайник -> 20 предметов сферой возвышения."""
    print(f"\n[БЛОК 5] Начинаю обработку {item_count} предметов сферой возвышения.")
    import poe2_target_clicker as clicker
    pydirectinput.PAUSE = 0.01
    scale = main.get_screen_scale()

    # 1. Закрыть текущее окно и найти Дориани.
    pydirectinput.press("esc")
    time.sleep(0.2)
    position = clicker.wait_for_target("Дориани")
    if position is None:
        print("[БЛОК 5][ОШИБКА] Не удалось найти Дориани.")
        return False
    doriani_x, doriani_y = position
    _click(x=doriani_x, y=doriani_y)

    # 2. Подождать 1 секунду и проверить, что окно действительно открылось.
    time.sleep(1.0)
    if not clicker.wait_for_interaction("Дориани"):
        print("[БЛОК 5][ОШИБКА] Не подтверждено открытие окна Дориани.")
        return False

    # 3. Повторный Ctrl+ЛКМ по тем же координатам.
    pydirectinput.keyDown("ctrl")
    try:
        _click(x=doriani_x, y=doriani_y)
        time.sleep(0.15)
    finally:
        pydirectinput.keyUp("ctrl")

    time.sleep(0.4)

    # 4. Найти и открыть тайник.
    if not clicker.move_to_target("Тайник"):
        print("[БЛОК 5][ОШИБКА] Не удалось открыть тайник.")
        return False
    time.sleep(2.0)

    # 6. Перейти на валютную вкладку и навести курсор на сферу возвышения.
    main.open_currency_tab(scale)
    main.move_to(main.CURRENCY_EXALTED, scale)
    time.sleep(0.3)

    # 7. Shift + ПКМ по сфере возвышения.
    pydirectinput.keyDown("shift")
    try:
        _click(button="right")
        time.sleep(0.15)

        # 8. Shift удерживается: обычный ЛКМ по сетке инвентаря СПРАВА,
        # начиная с центра первого слота (1731, 821), 4 столбца x 5 строк.
        print(f"[БЛОК 5] Shift зажат: прохожу {item_count} ячеек.")
        for index in range(item_count):
            if not main.running:
                return False
            row, col = divmod(index, 4)
            inventory_point = (
                BLOCK5_INVENTORY_FIRST[0] + col * BLOCK5_INVENTORY_CELL_W,
                BLOCK5_INVENTORY_FIRST[1] + row * BLOCK5_INVENTORY_CELL_H,
            )
            pyautogui.moveTo(
                inventory_point[0], inventory_point[1],
                duration=MOVE_DURATION,
                tween=pyautogui.easeInOutQuad,
            )
            _click()
            time.sleep(0.15)
    finally:
        pydirectinput.keyUp("shift")

    # 9. Ctrl + обычный ЛКМ по тем же 20 ячейкам справа в инвентаре.
    print(f"[БЛОК 5] Ctrl зажат: повторно кликаю {item_count} ячеек.")
    pydirectinput.keyDown("ctrl")
    try:
        for index in range(item_count):
            if not main.running:
                return False
            row, col = divmod(index, 4)
            inventory_point = (
                BLOCK5_INVENTORY_FIRST[0] + col * BLOCK5_INVENTORY_CELL_W,
                BLOCK5_INVENTORY_FIRST[1] + row * BLOCK5_INVENTORY_CELL_H,
            )
            pyautogui.moveTo(
                inventory_point[0], inventory_point[1],
                duration=MOVE_DURATION,
                tween=pyautogui.easeInOutQuad,
            )
            _click()
            time.sleep(0.15)
    finally:
        pydirectinput.keyUp("ctrl")

    print("[БЛОК 5] Завершён.")
    return True
