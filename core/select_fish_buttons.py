"""
Интерактивный выбор кнопок улова ("Забрать себе" / "Отпустить").
Позволяет пользователю в 2 клика указать координаты кнопок в окне улова
и выбрать режим: забирать рыбу себе или отпускать для прокачки опыта.

Координаты и режим сохраняются в 'fish_action_config.json'.
"""

import json
import os
import sys
import time
import cv2
import mss
import numpy as np

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fish_action_config.json")

def get_primary_monitor(sct):
    """Находит основной монитор."""
    for m in sct.monitors[1:]:
        if m.get("is_primary"):
            return m
    return sct.monitors[1]

def select_fish_buttons(delay=2):
    """
    Открывает интерактивное окно для выбора кнопок 'Забрать себе' и 'Отпустить'.
    """
    if delay > 0:
        print("\n" + "=" * 65)
        print("   ВЫБОР КНОПОК ДЕЙСТВИЯ С РЫБОЙ (ЗАБРАТЬ / ОТПУСТИТЬ)")
        print("=" * 65)
        print("Перейдите в игру (чтобы окно 'ВЫ ПОЙМАЛИ РЫБУ' было на экране).")
        for i in range(delay, 0, -1):
            print(f"Снимок экрана через: {i}...")
            time.sleep(1.0)
        print("СНИМОК СДЕЛАН! Открываем окно выбора...\n")

    with mss.mss() as sct:
        monitor = get_primary_monitor(sct)
        sct_img = sct.grab(monitor)
        screenshot = np.array(sct_img)

    original = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
    h_screen, w_screen = original.shape[:2]

    # Состояние выбора
    state = {
        "step": 1,  # 1: выбор "Забрать себе", 2: выбор "Отпустить", 3: подтверждение
        "take_pt": None,
        "release_pt": None,
        "mode": "take"  # "take" или "release"
    }

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            if state["step"] == 1:
                state["take_pt"] = (x, y)
                state["step"] = 2
                print(f"[1] Кнопка 'Забрать себе' выбрана: X={x}, Y={y}")
            elif state["step"] == 2:
                state["release_pt"] = (x, y)
                state["step"] = 3
                print(f"[2] Кнопка 'Отпустить' выбрана: X={x}, Y={y}")

    win_name = "Select Fish Buttons (Follow instructions on top banner)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win_name, monitor["left"], monitor["top"])
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(win_name, on_mouse)

    result_config = None

    while True:
        display = original.copy()

        # Отрисовка выбранных точек
        if state["take_pt"]:
            tx, ty = state["take_pt"]
            cv2.circle(display, (tx, ty), 12, (0, 255, 0), -1)
            cv2.circle(display, (tx, ty), 16, (255, 255, 255), 2)
            cv2.putText(display, "1. ЗАБРАТЬ СЕБЕ", (tx - 60, ty - 25), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 0), 2)

        if state["release_pt"]:
            rx, ry = state["release_pt"]
            cv2.circle(display, (rx, ry), 12, (0, 165, 255), -1)
            cv2.circle(display, (rx, ry), 16, (255, 255, 255), 2)
            cv2.putText(display, "2. ОТПУСТИТЬ (+1 EX)", (rx - 70, ry - 25), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 165, 255), 2)

        # Верхний баннер с инструкциями
        banner_h = 75
        banner = np.zeros((banner_h, w_screen, 3), dtype=np.uint8)
        banner[:] = (30, 30, 30)

        if state["step"] == 1:
            t1 = "ШАГ 1: Кликните ЛКМ по центру кнопки [ ЗАБРАТЬ СЕБЕ ]"
            t2 = "[ESC] — Отмена выбора"
            banner_color = (0, 255, 0)
        elif state["step"] == 2:
            t1 = "ШАГ 2: Кликните ЛКМ по центру кнопки [ ОТПУСТИТЬ ]"
            t2 = "[ESC] — Отмена выбора"
            banner_color = (0, 200, 255)
        else:
            mode_str = "ЗАБИРАТЬ СЕБЕ" if state["mode"] == "take" else "ОТПУСКАТЬ РЫБУ (+1 EX)"
            t1 = f"ШАГ 3: Выберите режим: [1] - Забирать | [2] - Отпускать. Сейчас: [{mode_str}]"
            t2 = "[ENTER] или [ПРОБЕЛ] — Сохранить выбор  |  [R] — Сбросить точки  |  [ESC] — Отмена"
            banner_color = (0, 255, 255)

        cv2.putText(banner, t1, (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, banner_color, 2)
        cv2.putText(banner, t2, (20, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.58, (200, 200, 200), 2)

        display[0:banner_h, 0:w_screen] = banner

        cv2.imshow(win_name, display)
        key = cv2.waitKey(20) & 0xFF

        if key in [27, ord('q'), ord('Q')]:
            print("[x] Выбор кнопок отменен.")
            break
        elif key == ord('1'):
            state["mode"] = "take"
            print("[i] Режим изменен на: ЗАБИРАТЬ СЕБЕ")
        elif key == ord('2'):
            state["mode"] = "release"
            print("[i] Режим изменен на: ОТПУСКАТЬ РЫБУ (+1 EX)")
        elif key in [ord('r'), ord('R')]:
            state["step"] = 1
            state["take_pt"] = None
            state["release_pt"] = None
            print("[i] Точки сброшены. Кликните по кнопке 'Забрать себе' заново.")
        elif key in [13, 32]:  # ENTER или SPACE
            if state["step"] == 3 and state["take_pt"] and state["release_pt"]:
                result_config = {
                    "mode": state["mode"],  # "take" или "release"
                    "take_pos": [int(state["take_pt"][0]), int(state["take_pt"][1])],
                    "release_pos": [int(state["release_pt"][0]), int(state["release_pt"][1])],
                    # Область для детекции заголовка окна "ВЫ ПОЙМАЛИ РЫБУ"
                    "check_area": {
                        "top": int(min(state["take_pt"][1], state["release_pt"][1]) - 550),
                        "left": int(min(state["take_pt"][0], state["release_pt"][0]) - 80),
                        "width": int(abs(state["release_pt"][0] - state["take_pt"][0]) + 160),
                        "height": 550
                    }
                }
                save_fish_action_config(result_config)
                print("\n" + "=" * 60)
                print(f"[✓] Настройки улова успешно сохранены в {CONFIG_FILE}:")
                print(f"    Режим: {result_config['mode'].upper()}")
                print(f"    Кнопка Забрать: {result_config['take_pos']}")
                print(f"    Кнопка Отпустить: {result_config['release_pos']}")
                print("=" * 60 + "\n")
                break
            else:
                print("[!] Сначала кликните по обеим кнопкам на экране!")

    cv2.destroyAllWindows()
    return result_config

def save_fish_action_config(cfg):
    """Сохраняет настройки действий с рыбой в JSON."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=4)

def load_fish_action_config():
    """Загружает настройки действий с рыбой."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "take_pos" in data and "release_pos" in data:
                    return data
        except Exception as e:
            print(f"[!] Ошибка чтения {CONFIG_FILE}: {e}")
    return None

if __name__ == "__main__":
    select_fish_buttons(delay=2)
