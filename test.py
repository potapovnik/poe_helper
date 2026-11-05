"""
PoE 2 grid currency automation with GUI and global hotkeys.

Keyboard injection:
- PyDirectInput: Shift, Ctrl+C and Alt release.
- keyboard: global F6/F7/F10 hotkey listener.
- PyAutoGUI: mouse clicks and smooth movement.

The GUI lets you change all operational settings except delays/pauses.
"""

import os
import sys
import time
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

import keyboard
import pyautogui
import pydirectinput
import pyperclip


# ---------- SETTINGS / FIXED DELAYS ----------
TARGET_FILE = "target.txt"

COLUMNS = 1
ROWS = 1
MOVE_RIGHT_PIXELS = 70
MOVE_DOWN_PIXELS = 70
REQUIRED_TARGETS = 3
MAX_ATTEMPTS = 1300

# Delays are intentionally not exposed in the GUI.
MOVE_DURATION = 0.25
CLICK_DELAY = 0.15
COPY_DELAY = 0.15
STEP_DELAY = 0.20
# ---------------------------------------------

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.03
pydirectinput.PAUSE = 0.03

running = False
busy = False
exit_requested = False
state_lock = threading.Lock()

log_queue = queue.Queue()
control_queue = queue.Queue()
root = None
status_var = None
settings_vars = {}


class QueueWriter:
    """Redirect print output to the GUI without touching Tk from worker threads."""
    def write(self, text):
        if text:
            log_queue.put(text)

    def flush(self):
        pass


def log(message=""):
    print(message)


def load_targets():
    with open(TARGET_FILE, "r", encoding="utf-8-sig") as f:
        lines = [line.strip().casefold() for line in f if line.strip()]
    return list(dict.fromkeys(lines))


def release_ctrl_and_alt():
    try:
        pydirectinput.keyUp("ctrl")
    finally:
        pydirectinput.keyUp("alt")


def read_item_text():
    try:
        pydirectinput.keyDown("ctrl")
        time.sleep(0.03)
        pydirectinput.press("c")
        time.sleep(0.03)
    finally:
        release_ctrl_and_alt()

    time.sleep(COPY_DELAY)
    text = pyperclip.paste()
    log("Буфер обмена: " + repr(text[:100]))
    return text if text.strip() else None


def check_targets(text, targets):
    lowered = text.casefold()
    found = [target for target in targets if target in lowered]
    missing = [target for target in targets if target not in lowered]
    return found, missing


def stop():
    global running
    running = False
    log("Запрошена остановка. Shift будет отпущен после завершения текущего действия.")


def move_smooth(dx, dy):
    if running:
        pyautogui.moveRel(
            dx, dy,
            duration=MOVE_DURATION,
            tween=pyautogui.easeInOutQuad
        )


def process_item(row_number, column_number, targets):
    global running
    attempts = 0
    log(f"\n--- Строка {row_number}/{ROWS}, столбец {column_number}/{COLUMNS} ---")

    text = read_item_text()
    if text is None:
        log("Не удалось прочитать подсказку предмета. Остановка.")
        return "ERROR"

    found, missing = check_targets(text, targets)
    count = len(found)
    log(f"Найдено свойств: {count}/{len(targets)}: {found}")

    if count == 0:
        log("Целевых свойств нет. Переход к следующему предмету.")
        return "NEXT"

    if count >= REQUIRED_TARGETS:
        log("Необходимое количество свойств уже достигнуто.")
        return "NEXT"

    log(f"Нужно ещё {REQUIRED_TARGETS - count}. Не найдены: {missing}")

    while running and attempts < MAX_ATTEMPTS:
        pyautogui.click()
        attempts += 1
        time.sleep(CLICK_DELAY)

        text = read_item_text()
        if text is None:
            log("Не удалось прочитать обновлённую подсказку. Остановка.")
            return "ERROR"

        found, missing = check_targets(text, targets)
        count = len(found)
        log(f"Попытка {attempts}/{MAX_ATTEMPTS}: найдено {count}/{len(targets)}: {found}")

        if count == 0:
            log("Целевых свойств не осталось. Переход к следующему предмету.")
            return "NEXT"

        if count >= REQUIRED_TARGETS:
            log("Необходимое количество свойств достигнуто.")
            return "NEXT"

        log(f"Всё ещё нужно {REQUIRED_TARGETS - count}. Не найдены: {missing}")

    if attempts >= MAX_ATTEMPTS:
        log("Достигнут лимит попыток. Остановка сетки.")
        return "LIMIT"

    return "NEXT"


def start():
    global running, busy

    with state_lock:
        if busy:
            log("Программа уже выполняется.")
            return
        busy = True

    shift_pressed = False
    try:
        targets = load_targets()
        if not targets:
            log("Файл target.txt пуст. Добавьте по одному свойству на строку.")
            return

        if COLUMNS < 1 or ROWS < 1:
            log("Количество строк и столбцов должно быть не меньше 1.")
            return

        if REQUIRED_TARGETS < 1 or REQUIRED_TARGETS > len(targets):
            log(f"REQUIRED_TARGETS должно быть от 1 до {len(targets)}.")
            return

        log(f"Запуск сетки: {COLUMNS} столбцов x {ROWS} строк ({COLUMNS * ROWS} предметов).")
        log(f"Загружено целевых свойств: {len(targets)}")
        log(f"Необходимое количество свойств: {REQUIRED_TARGETS}")
        log("Перед F6 наведите курсор на ПЕРВЫЙ предмет в левом верхнем углу.")

        running = True
        pydirectinput.keyDown("shift")
        shift_pressed = True
        time.sleep(0.10)
        log("Shift зажат на всё время обработки сетки.")

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
                    log("Не удалось прочитать предмет. Остановка сетки.")
                    return
                if result == "LIMIT":
                    log("Достигнут лимит попыток. Остановка сетки.")
                    return

                if column < COLUMNS:
                    move_smooth(MOVE_RIGHT_PIXELS, 0)
                    time.sleep(STEP_DELAY)

            if running and row < ROWS:
                if COLUMNS > 1:
                    move_smooth(-MOVE_RIGHT_PIXELS * (COLUMNS - 1), 0)
                move_smooth(0, MOVE_DOWN_PIXELS)
                time.sleep(STEP_DELAY)

        log("\nОбработка сетки завершена.")

    except pyautogui.FailSafeException:
        log("Сработала защита PyAutoGUI (курсор в углу экрана).")
    except Exception as exc:
        log(f"Остановка из-за ошибки: {exc}")
    finally:
        if shift_pressed:
            try:
                pydirectinput.keyUp("shift")
            except Exception:
                pass

        try:
            pydirectinput.keyUp("ctrl")
            pydirectinput.keyUp("alt")
        except Exception:
            pass

        running = False
        with state_lock:
            busy = False
        log("Остановлено. Для нового запуска нажмите F6 или кнопку «Старт».")


def apply_gui_settings(show_errors=True):
    """Copy validated GUI values into the globals used by the worker."""
    global TARGET_FILE, COLUMNS, ROWS
    global MOVE_RIGHT_PIXELS, MOVE_DOWN_PIXELS, REQUIRED_TARGETS, MAX_ATTEMPTS

    try:
        target_path = settings_vars["target_file"].get().strip()
        if not target_path:
            raise ValueError("Укажите файл со свойствами.")

        columns = int(settings_vars["columns"].get())
        rows = int(settings_vars["rows"].get())
        right = int(settings_vars["move_right"].get())
        down = int(settings_vars["move_down"].get())
        required = int(settings_vars["required_targets"].get())
        attempts = int(settings_vars["max_attempts"].get())

        if columns < 1 or rows < 1:
            raise ValueError("Количество строк и столбцов должно быть не меньше 1.")
        if right < 0 or down < 0:
            raise ValueError("Смещения мыши не могут быть отрицательными.")
        if required < 1:
            raise ValueError("Необходимое количество свойств должно быть не меньше 1.")
        if attempts < 1:
            raise ValueError("Максимум попыток должен быть не меньше 1.")
        if not os.path.isfile(target_path):
            raise ValueError(f"Файл не найден:\n{target_path}")

        TARGET_FILE = target_path
        COLUMNS = columns
        ROWS = rows
        MOVE_RIGHT_PIXELS = right
        MOVE_DOWN_PIXELS = down
        REQUIRED_TARGETS = required
        MAX_ATTEMPTS = attempts
        return True

    except Exception as exc:
        if show_errors:
            messagebox.showerror("Ошибка настроек", str(exc), parent=root)
        else:
            log(f"Ошибка настроек: {exc}")
        return False


def request_start():
    if root is not None and threading.current_thread() is threading.main_thread():
        if not apply_gui_settings():
            return
    threading.Thread(target=start, daemon=True).start()


def request_stop():
    stop()


def request_exit():
    global exit_requested, running
    running = False
    exit_requested = True
    log("Запрошен выход из программы.")


def choose_target_file():
    selected = filedialog.askopenfilename(
        title="Выберите файл target.txt",
        filetypes=[("Текстовые файлы", "*.txt"), ("Все файлы", "*.*")]
    )
    if selected:
        settings_vars["target_file"].set(selected)


def drain_log_queue():
    if root is None:
        return

    # Process hotkey requests on Tk's main thread so current GUI values are read safely.
    try:
        while True:
            action = control_queue.get_nowait()
            if action == "start":
                request_start()
            elif action == "stop":
                request_stop()
            elif action == "exit":
                request_exit()
    except queue.Empty:
        pass

    try:
        while True:
            chunk = log_queue.get_nowait()
            log_widget.configure(state="normal")
            log_widget.insert("end", chunk)
            log_widget.see("end")
            log_widget.configure(state="disabled")
    except queue.Empty:
        pass

    if exit_requested:
        try:
            keyboard.unhook_all()
        except Exception:
            pass
        root.destroy()
        return

    if status_var is not None:
        if busy and running:
            status_var.set("Выполняется")
        elif busy:
            status_var.set("Останавливается…")
        else:
            status_var.set("Ожидание")

    root.after(100, drain_log_queue)


def on_close():
    request_exit()


def build_gui():
    global root, status_var, log_widget, settings_vars

    root = tk.Tk()
    root.title("PoE 2 — автоматизация сетки")
    root.geometry("720x690")
    root.minsize(620, 580)

    main = ttk.Frame(root, padding=12)
    main.pack(fill="both", expand=True)

    title = ttk.Label(main, text="Настройки обработки предметов", font=("Segoe UI", 13, "bold"))
    title.pack(anchor="w", pady=(0, 10))

    settings_frame = ttk.LabelFrame(main, text="Параметры", padding=10)
    settings_frame.pack(fill="x")

    settings_vars = {
        "target_file": tk.StringVar(value=TARGET_FILE),
        "columns": tk.StringVar(value=str(COLUMNS)),
        "rows": tk.StringVar(value=str(ROWS)),
        "move_right": tk.StringVar(value=str(MOVE_RIGHT_PIXELS)),
        "move_down": tk.StringVar(value=str(MOVE_DOWN_PIXELS)),
        "required_targets": tk.StringVar(value=str(REQUIRED_TARGETS)),
        "max_attempts": tk.StringVar(value=str(MAX_ATTEMPTS)),
    }

    def add_entry(row, label, key, width=16):
        ttk.Label(settings_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=5)
        entry = ttk.Entry(settings_frame, textvariable=settings_vars[key], width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        return entry

    ttk.Label(settings_frame, text="Файл свойств").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=5)
    ttk.Entry(settings_frame, textvariable=settings_vars["target_file"]).grid(
        row=0, column=1, sticky="ew", pady=5
    )
    ttk.Button(settings_frame, text="Обзор…", command=choose_target_file).grid(
        row=0, column=2, padx=(8, 0), pady=5
    )

    add_entry(1, "Столбцов", "columns")
    add_entry(2, "Строк", "rows")
    add_entry(3, "Смещение вправо (пикс.)", "move_right")
    add_entry(4, "Смещение вниз (пикс.)", "move_down")
    add_entry(5, "Сколько свойств требуется", "required_targets")
    add_entry(6, "Максимум попыток на предмет", "max_attempts")

    settings_frame.columnconfigure(1, weight=1)

    note = ttk.Label(
        main,
        text="Паузы и задержки оставлены фиксированными и в интерфейсе не настраиваются.",
        foreground="#666666"
    )
    note.pack(anchor="w", pady=(7, 10))

    controls = ttk.Frame(main)
    controls.pack(fill="x", pady=(0, 10))

    ttk.Button(controls, text="Старт (F6)", command=request_start).pack(side="left", padx=(0, 7))
    ttk.Button(controls, text="Стоп (F7)", command=request_stop).pack(side="left", padx=7)
    ttk.Button(controls, text="Выход (F10)", command=request_exit).pack(side="left", padx=7)

    status_var = tk.StringVar(value="Ожидание")
    ttk.Label(controls, textvariable=status_var).pack(side="right")

    hotkeys = ttk.LabelFrame(main, text="Глобальные горячие клавиши", padding=8)
    hotkeys.pack(fill="x", pady=(0, 10))
    ttk.Label(hotkeys, text="F6 — старт    F7 — стоп    F10 — выход").pack(anchor="w")
    ttk.Label(
        hotkeys,
        text="Работают, даже когда игра находится поверх этого окна.",
        foreground="#666666"
    ).pack(anchor="w", pady=(3, 0))

    log_frame = ttk.LabelFrame(main, text="Журнал", padding=8)
    log_frame.pack(fill="both", expand=True)
    log_widget = ScrolledText(log_frame, height=16, wrap="word", state="disabled", font=("Consolas", 9))
    log_widget.pack(fill="both", expand=True)

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.after(100, drain_log_queue)
    return root


def main():
    global root

    sys.stdout = QueueWriter()
    sys.stderr = QueueWriter()

    build_gui()

    log("PoE 2 — автоматизация сетки")
    log("F6 — старт, F7 — стоп, F10 — выход.")
    log("Выберите параметры, наведите курсор на первый предмет и нажмите Старт/F6.")
    log("Shift удерживается на протяжении обработки сетки.")
    log("Для работы глобальных клавиш программа должна оставаться запущенной.")

    try:
        keyboard.add_hotkey("f6", lambda: control_queue.put("start"))
        keyboard.add_hotkey("f7", lambda: control_queue.put("stop"))
        keyboard.add_hotkey("f10", lambda: control_queue.put("exit"))
    except Exception as exc:
        log(f"Не удалось зарегистрировать горячие клавиши: {exc}")

    root.mainloop()

    # Ensure worker stops and modifiers are released on GUI shutdown.
    stop()
    try:
        pydirectinput.keyUp("shift")
        pydirectinput.keyUp("ctrl")
        pydirectinput.keyUp("alt")
    except Exception:
        pass
    try:
        keyboard.unhook_all()
    except Exception:
        pass


if __name__ == "__main__":
    main()
