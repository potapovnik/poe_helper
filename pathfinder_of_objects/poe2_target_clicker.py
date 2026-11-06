# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import easyocr
import mss
import numpy as np
import pydirectinput


# ============================= НАСТРОЙКИ =============================

# Область поиска рассчитывается от разрешения экрана.
# Пропорции соответствуют центральному игровому полю на присланном скриншоте.
# Если нужно искать по всему экрану: SEARCH_REGION_MODE = "full"
SEARCH_REGION_MODE = "center"

# Ручная область поиска (используется, если SEARCH_REGION_MODE = "manual")
# Формат: (x, y, width, height)
MANUAL_SEARCH_REGION = (570, 0, 515, 930)

SEARCH_ATTEMPTS = 8
SEARCH_INTERVAL = 1.0
MAX_CLICK_ATTEMPTS = 2
VERIFY_TIMEOUT = 8.0
VERIFY_INTERVAL = 0.4
AFTER_CLICK_DELAY = 0.5

# Порог проверки появления окна по эталонному изображению.
TEMPLATE_THRESHOLD = 0.72

# Уверенность OCR; для небольших надписей допустимо умеренное значение.
OCR_CONFIDENCE = 0.18

# Увеличение изображения перед OCR помогает читать небольшие подписи.
OCR_SCALE = 1.7

# Названия целей. Сравнение слов строгое: «разборки» не подходит к «перековки».
TARGETS = {
    "Тайник": {
        "ocr_name": "Тайник",
        "template": "templates/stash_open.jpg",
    },
    "Верстак для перековки": {
        "ocr_name": "Верстак для перековки",
        "template": "templates/workbench_open.jpg",
        "verify": True,
    },
    "Дориани": {
        "ocr_name": "Дориани",
        "template": "templates/doriani_open.jpg",
        "verify": True,
    },
}

# ====================================================================

ROOT = Path(__file__).resolve().parent
pydirectinput.PAUSE = 0.08
pydirectinput.FAILSAFE = True

print("Инициализация EasyOCR...")
reader = easyocr.Reader(["ru", "en"], gpu=False)


def get_monitor():
    with mss.MSS() as sct:
        mon = sct.monitors[1]
        return {
            "left": mon["left"],
            "top": mon["top"],
            "width": mon["width"],
            "height": mon["height"],
        }


def get_search_region():
    mon = get_monitor()
    if SEARCH_REGION_MODE == "full":
        return (mon["left"], mon["top"], mon["width"], mon["height"])

    if SEARCH_REGION_MODE == "manual":
        x, y, w, h = MANUAL_SEARCH_REGION
        return (x, y, w, h)

    # Центральная область: пропорционально разрешению, а не фиксированные пиксели.
    x = mon["left"] + int(mon["width"] * 0.345)
    y = mon["top"]
    w = int(mon["width"] * 0.312)
    h = mon["height"]
    return (x, y, w, h)


def capture(region=None):
    with mss.MSS() as sct:
        if region is None:
            r = get_monitor()
            left, top, width, height = r["left"], r["top"], r["width"], r["height"]
        else:
            left, top, width, height = region

        shot = np.array(sct.grab({
            "left": left, "top": top, "width": width, "height": height
        }))
        return cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR), left, top


def words(text):
    return re.findall(r"[а-яёa-z0-9]+", text.lower().replace("ё", "е"))


def strict_text_match(expected_text, detected_text):
    """
    Разрешает только небольшие OCR-ошибки внутри каждого слова.
    Количество и порядок слов должны совпадать.
    Это исключает подмену «перековки» на «разборки».
    """
    expected = words(expected_text)
    detected = words(detected_text)

    if len(expected) != len(detected):
        return False

    for index, (a, b) in enumerate(zip(expected, detected)):
        ratio = SequenceMatcher(None, a, b).ratio()
        # Для коротких служебных слов требуем точного совпадения.
        threshold = 1.0 if len(a) <= 3 else 0.84
        if ratio < threshold:
            return False

    return True


def find_target(target_name):
    expected = TARGETS[target_name]["ocr_name"]
    region = get_search_region()
    image, offset_x, offset_y = capture(region)

    enlarged = cv2.resize(
        image, None, fx=OCR_SCALE, fy=OCR_SCALE,
        interpolation=cv2.INTER_CUBIC
    )

    results = reader.readtext(
        enlarged,
        detail=1,
        paragraph=False,
        decoder="greedy",
        text_threshold=0.45,
        low_text=0.25,
        link_threshold=0.35,
    )

    matches = []
    ocr_debug = []
    for bbox, detected_text, confidence in results:
        ocr_debug.append((str(detected_text), float(confidence)))
        if confidence < OCR_CONFIDENCE:
            continue
        if not strict_text_match(expected, detected_text):
            continue

        xs = [point[0] for point in bbox]
        ys = [point[1] for point in bbox]

        # Координаты OCR возвращаются для увеличенного изображения.
        center_x = int((min(xs) + max(xs)) / (2 * OCR_SCALE)) + offset_x
        center_y = int((min(ys) + max(ys)) / (2 * OCR_SCALE)) + offset_y
        matches.append((float(confidence), center_x, center_y, detected_text))

    if not matches:
        # Диагностика: показывает распознанные надписи, чтобы можно было
        # понять, мешает ли область поиска, качество текста или фильтр совпадения.
        if ocr_debug:
            preview = sorted(ocr_debug, key=lambda item: item[1], reverse=True)[:12]
            print("[OCR] Распознано:", "; ".join(
                f"{text!r} ({confidence:.2f})" for text, confidence in preview
            ))
        else:
            print("[OCR] В выбранной области текст не распознан.")
        return None

    matches.sort(key=lambda item: item[0], reverse=True)
    confidence, x, y, detected = matches[0]
    return x, y, confidence, detected


def wait_for_target(target_name):
    for attempt in range(1, SEARCH_ATTEMPTS + 1):
        result = find_target(target_name)
        if result:
            x, y, confidence, detected = result
            print(f"[НАЙДЕНО] {detected!r} x={x}, y={y}, OCR={confidence:.2f}")
            return x, y

        print(f"[ПОИСК] {target_name!r}: не найдено ({attempt}/{SEARCH_ATTEMPTS})")
        if attempt < SEARCH_ATTEMPTS:
            time.sleep(SEARCH_INTERVAL)

    return None


def load_template(target_name):
    path = ROOT / TARGETS[target_name]["template"]
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(f"Не удалось загрузить эталон: {path}")
    return template


def get_template_score(screen_gray, template):
    best = -1.0
    # Проверяем несколько масштабов, чтобы компенсировать небольшую разницу UI scale.
    for scale in (0.75, 0.85, 0.95, 1.0, 1.05, 1.15, 1.25):
        w = int(template.shape[1] * scale)
        h = int(template.shape[0] * scale)
        if w < 10 or h < 10 or w > screen_gray.shape[1] or h > screen_gray.shape[0]:
            continue
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(result)
        best = max(best, float(score))
    return best


def interaction_successful(target_name):
    screen, _, _ = capture()
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    template = load_template(target_name)
    score = get_template_score(gray, template)
    print(f"[ПРОВЕРКА] {target_name}: совпадение окна {score:.3f}")
    return score >= TEMPLATE_THRESHOLD


def wait_for_interaction(target_name):
    deadline = time.time() + VERIFY_TIMEOUT
    while time.time() < deadline:
        if interaction_successful(target_name):
            return True
        time.sleep(VERIFY_INTERVAL)
    return False


def move_to_target(target_name):
    if target_name not in TARGETS:
        raise ValueError(f"Неизвестная цель: {target_name}")

    print(f"\\n=== Ищу: {target_name} ===")

    for click_attempt in range(1, MAX_CLICK_ATTEMPTS + 1):
        print(f"[ПОПЫТКА] {click_attempt}/{MAX_CLICK_ATTEMPTS}")
        position = wait_for_target(target_name)

        if position is None:
            print(f"[ОШИБКА] Не найдено название «{target_name}».")
            return False

        x, y = position
        print(f"[КЛИК] По центру надписи: ({x}, {y})")
        pydirectinput.click(x, y)
        time.sleep(AFTER_CLICK_DELAY)

        if not TARGETS[target_name].get("verify", True):
            print(f"[КЛИК ВЫПОЛНЕН] «{target_name}» добавлен как цель без проверки окна.")
            return True

        if wait_for_interaction(target_name):
            print(f"[УСПЕХ] Окно «{target_name}» открыто.")
            return True

        print("[ПРЕДУПРЕЖДЕНИЕ] Окно не обнаружено.")
        if click_attempt < MAX_CLICK_ATTEMPTS:
            print("[ПОВТОР] Повторный поиск и клик.")

    print(f"[НЕУДАЧА] Не удалось открыть «{target_name}».")
    return False


if __name__ == "__main__":
    print("\\n1 — Тайник")
    print("2 — Верстак для перековки")
    print("3 — Дориани")
    print("q — Выход")
    print(f"Режим области поиска: {SEARCH_REGION_MODE}")
    print(f"Область на текущем экране: {get_search_region()}")
    print("OCR decoder: greedy (без beamsearch overflow)")

    while True:
        try:
            cmd = input("\\nВыбери цель: ").strip()
            if cmd.lower() in ("q", "й", "exit", "выход"):
                break
            if cmd == "1":
                move_to_target("Тайник")
            elif cmd == "2":
                move_to_target("Верстак для перековки")
            elif cmd == "3":
                move_to_target("Дориани")
            elif cmd in TARGETS:
                move_to_target(cmd)
            else:
                print("Неизвестная команда.")
        except KeyboardInterrupt:
            print("\\nОстановлено.")
            break
        except Exception as exc:
            print(f"[ОШИБКА] {type(exc).__name__}: {exc}")

    print("Программа завершена.")
