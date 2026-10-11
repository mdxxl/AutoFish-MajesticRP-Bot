"""
Интерактивный выбор области индикатора поклевки (поплавка) мышкой.
Позволяет пользователю зажать ЛКМ и протянуть рамку вокруг квадрата с поплавком.
Координаты автоматически сохраняются в 'bobber_config.json'.
"""

import json
import os
import sys
import time
import ctypes
import cv2
import mss
import numpy as np

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bobber_config.json")

def get_primary_monitor(sct):
    """Находит основной монитор."""
    for m in sct.monitors[1:]:
        if m.get("is_primary"):
            return m
    return sct.monitors[1]

def detect_bubbles_in_crop(crop):
    """
    Анализирует область индикатора на наличие пузырьков поклевки:
    Считает светлые пиксели над ватерлинией слева и справа от поплавка.
    """
    if crop.shape[0] < 20 or crop.shape[1] < 20:
        return False, 0

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    top_left = gray[int(0.12 * h):int(0.48 * h), int(0.10 * w):int(0.40 * w)]
    top_right = gray[int(0.12 * h):int(0.48 * h), int(0.60 * w):int(0.90 * w)]

    thresh = 75
    b_left = int(np.sum(top_left > thresh))
    b_right = int(np.sum(top_right > thresh))
    total_bubbles = b_left + b_right

    is_bite = total_bubbles > 30
    return is_bite, total_bubbles

def select_indicator_roi(delay=2):
    """
    Делает снимок экрана с таймером, открывает полноэкранное окно и дает
    пользователю возможность выделить квадрат поплавка мышкой.
    """
    if delay > 0:
        print("\n" + "=" * 65)
        print("   ВЫБОР ОБЛАСТИ ИНДИКАТОРА ПОКЛЕВКИ (ПОПЛАВКА) МЫШКОЙ")
        print("=" * 65)
        print("Перейдите в окно GTA V (чтобы индикатор поплавка был виден на экране).")
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

    drag_state = {
        "selecting": False,
        "x1": 0, "y1": 0,
        "x2": 0, "y2": 0,
        "has_selection": False
    }

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            drag_state["selecting"] = True
            drag_state["x1"] = x
            drag_state["y1"] = y
            drag_state["x2"] = x
            drag_state["y2"] = y
            drag_state["has_selection"] = False

        elif event == cv2.EVENT_MOUSEMOVE:
            if drag_state["selecting"]:
                drag_state["x2"] = x
                drag_state["y2"] = y
                drag_state["has_selection"] = True

        elif event == cv2.EVENT_LBUTTONUP:
            drag_state["selecting"] = False
            drag_state["x2"] = x
            drag_state["y2"] = y
            if abs(drag_state["x2"] - drag_state["x1"]) > 15 and abs(drag_state["y2"] - drag_state["y1"]) > 15:
                drag_state["has_selection"] = True

    win_name = "Select Bobber Indicator (Drag mouse, press ENTER to confirm, ESC to cancel)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win_name, monitor["left"], monitor["top"])
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(win_name, on_mouse)

    selected_roi = None

    while True:
        display = original.copy()

        if drag_state["selecting"] or drag_state["has_selection"]:
            rx1 = min(drag_state["x1"], drag_state["x2"])
            ry1 = min(drag_state["y1"], drag_state["y2"])
            rx2 = max(drag_state["x1"], drag_state["x2"])
            ry2 = max(drag_state["y1"], drag_state["y2"])

            rw = rx2 - rx1
            rh = ry2 - ry1

            # Затемнение фона вне рамки
            dark_mask = np.zeros_like(display)
            dark_mask[ry1:ry2, rx1:rx2] = 1
            display = np.where(dark_mask == 1, display, (display * 0.45).astype(np.uint8))

            # Рамка вокруг поплавка
            cv2.rectangle(display, (rx1, ry1), (rx2, ry2), (0, 255, 255), 2)

            crop = original[ry1:ry2, rx1:rx2]
            is_bite, bubbles_count = detect_bubbles_in_crop(crop)

            info_text = f"Индикатор: {rw}x{rh} px | Пузырьков: {bubbles_count}"
            if is_bite:
                info_text += " -> [ОБНАРУЖЕН КЛЕВ!]"
                text_color = (0, 255, 0)
            else:
                info_text += " -> [ОЖИДАНИЕ (поплавок в воде)]"
                text_color = (0, 255, 255)

            cv2.putText(display, info_text, (rx1, max(30, ry1 - 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, text_color, 2)

        # Верхний баннер с инструкцией
        banner_h = 70
        banner = np.zeros((banner_h, w_screen, 3), dtype=np.uint8)
        banner[:] = (30, 30, 30)

        t1 = "ИНСТРУКЦИЯ: Зажмите ЛКМ и выделите квадрат индикатора с поплавком."
        t2 = "[ENTER] или [ПРОБЕЛ] — Сохранить выбор   |   [ESC] или [Q] — Отмена   |   ЛКМ еще раз — перевыбрать"

        cv2.putText(banner, t1, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(banner, t2, (20, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 200), 2)

        display[0:banner_h, 0:w_screen] = banner

        cv2.imshow(win_name, display)
        key = cv2.waitKey(20) & 0xFF

        if key in [13, 32]:  # ENTER или SPACE
            if drag_state["has_selection"]:
                rx1 = min(drag_state["x1"], drag_state["x2"])
                ry1 = min(drag_state["y1"], drag_state["y2"])
                rx2 = max(drag_state["x1"], drag_state["x2"])
                ry2 = max(drag_state["y1"], drag_state["y2"])

                selected_roi = {
                    "top": int(monitor["top"] + ry1),
                    "left": int(monitor["left"] + rx1),
                    "width": int(rx2 - rx1),
                    "height": int(ry2 - ry1)
                }
                save_bobber_roi(selected_roi)
                print(f"[✓] Индикатор поплавка сохранен в {CONFIG_FILE}:")
                print(f"    top={selected_roi['top']}, left={selected_roi['left']}, "
                      f"width={selected_roi['width']}, height={selected_roi['height']}\n")
                break
            else:
                print("[!] Сначала выделите область индикатора мышкой!")

        elif key in [27, ord('q'), ord('Q')]:
            print("[x] Выбор индикатора отменен.")
            break

    cv2.destroyAllWindows()
    return selected_roi

def save_bobber_roi(roi):
    """Сохраняет координаты поплавка в JSON файл."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(roi, f, indent=4)

def load_bobber_roi():
    """Загружает сохраненные координаты поплавка из JSON файла."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if all(k in data for k in ("top", "left", "width", "height")):
                    return data
        except Exception as e:
            print(f"[!] Ошибка чтения {CONFIG_FILE}: {e}")
    return None

if __name__ == "__main__":
    select_indicator_roi(delay=2)
