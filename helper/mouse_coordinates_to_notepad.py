from pathlib import Path
import time

import pyautogui
import keyboard

# Файл создаётся рядом с этим .py и дополняется при каждом нажатии F6.
OUTPUT_FILE = Path(__file__).resolve().with_name("mouse_coordinates.txt")

print(f"Координаты будут записываться в: {OUTPUT_FILE}")
print("F6 — записать текущие координаты мыши.")
print("F10 — завершить программу.")

def save_mouse_position():
    x, y = pyautogui.position()
    line = f"{x}, {y}\n"
    with OUTPUT_FILE.open("a", encoding="utf-8") as file:
        file.write(line)
    print(f"Записано: {x}, {y}")

keyboard.add_hotkey("F6", save_mouse_position)
keyboard.wait("F10")
