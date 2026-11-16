import time

import pyautogui


time.sleep(2)
print("Размер экрана для перемещения мыши:", pyautogui.size())

screenshot = pyautogui.screenshot()
print("Размер скриншота:", screenshot.size)

print("Текущая позиция мыши:", pyautogui.position())

input("\nНажми Enter для выхода...")