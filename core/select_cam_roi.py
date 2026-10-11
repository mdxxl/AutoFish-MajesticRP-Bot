"""
Интерактивный выбор области для отслеживания движения камеры мышкой.
Позволяет пользователю зажать ЛКМ и протянуть рамку на статичном объекте
(берег, скалы, горизонт, пристань, набережная) сбоку экрана вдали от рыбы и брызг воды.
Координаты автоматически сохраняются в 'cam_roi_config.json'.
"""

import json
import os
import sys
import time
import ctypes
import cv2
import mss
import numpy as np

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cam_roi_config.json")

def get_primary_monitor(sct):
    """Находит основной монитор."""
    for m in sct.monitors[1:]:
        if m.get("is_primary"):
            return m
    return sct.monitors[1]

def select_cam_roi(delay=2):
    """
    Делает скриншот с задержкой, открывает полноэкранное окно и дает
    пользователю возможность выделить прямоугольник мышкой для трекинга камеры.
    Возвращает dict с top, left, width, height или None при отмене.
    """
    if delay > 0:
        print("\n" + "=" * 65)
        print("   ВЫБОР ОБЛАСТИ СЛЕЖЕНИЯ ЗА КАМЕРОЙ (БОК ЭКРАНА / БЕРЕГ / ГОРИЗОНТ)")
        print("=" * 65)
        print("Совет: Выделите область СБОКУ экрана (скалы, берег, фонарь, набережная).")
        print("ВАЖНО: Избегайте попадания в зону рыбы, персонажа и брызг воды!")
        for i in range(delay, 0, -1):
            print(f"Снимок экрана через: {i}...")
            time.sleep(1.0)
        print("СНИМОК СДЕЛАН! Открываем окно выбора...\n")

    with mss.mss() as sct:
        monitor = get_primary_monitor(sct)
        sct_img = sct.grab(monitor)
        screenshot = np.array(sct_img)

    # BGRA -> BGR
    original = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
    h_screen, w_screen = original.shape[:2]

    # Состояние мыши
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
            if abs(drag_state["x2"] - drag_state["x1"]) > 10 and abs(drag_state["y2"] - drag_state["y1"]) > 10:
                drag_state["has_selection"] = True

    win_name = "Select Camera Tracking Zone (Side of screen / Scenery) - Drag mouse, ENTER to save, ESC to cancel"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win_name, monitor["left"], monitor["top"])
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(win_name, on_mouse)

    selected_roi = None

    while True:
        display = original.copy()

        # Если есть выделение или пользователь тянет мышь:
        if drag_state["selecting"] or drag_state["has_selection"]:
            rx1 = min(drag_state["x1"], drag_state["x2"])
            ry1 = min(drag_state["y1"], drag_state["y2"])
            rx2 = max(drag_state["x1"], drag_state["x2"])
            ry2 = max(drag_state["y1"], drag_state["y2"])

            rw = rx2 - rx1
            rh = ry2 - ry1

            # Затемняем область снаружи рамки
            overlay = display.copy()
            cv2.rectangle(overlay, (0, 0), (w_screen, h_screen), (0, 0, 0), -1)
            # Возвращаем выбранную область без затемнения
            overlay[ry1:ry2, rx1:rx2] = original[ry1:ry2, rx1:rx2]
            display = cv2.addWeighted(display, 0.35, overlay, 0.65, 0)

            # Зеленая рамка вокруг выбранной зоны
            cv2.rectangle(display, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)

            # Размеры выделенной области
            info_text = f"{rw} x {rh} px"
            cv2.putText(display, info_text, (rx1 + 5, ry1 - 10 if ry1 > 30 else ry1 + 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        # Верхняя панель с подсказками
        banner_h = 75
        banner = np.zeros((banner_h, w_screen, 3), dtype=np.uint8)
        banner[:] = (20, 20, 20)

        t1 = "ЗОНА КАМЕРЫ: Выделите неподвижный объект СБОКУ (берег, скалы, горизонт, здания) без рыбы и брызг!"
        t2 = "[ENTER] / [ПРОБЕЛ] — Сохранить выбор  |  [ESC] / [Q] — Отмена  |  ЛКМ — перевыбрать"

        cv2.putText(banner, t1, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 220, 255), 2)
        cv2.putText(banner, t2, (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

        display[0:banner_h, 0:w_screen] = banner

        cv2.imshow(win_name, display)
        key = cv2.waitKey(20) & 0xFF

        # ENTER (13) или SPACE (32) — подтверждение выбора
        if key in [13, 32]:
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
                save_cam_roi(selected_roi)
                print(f"[✓] Зона слежения за камерой успешно выбрана и сохранена:")
                print(f"    top={selected_roi['top']}, left={selected_roi['left']}, "
                      f"width={selected_roi['width']}, height={selected_roi['height']}\n")
                break
            else:
                print("[!] Сначала выделите область сбоку экрана мышкой (зажмите ЛКМ и потяните)!")

        # ESC (27) или Q — отмена
        elif key in [27, ord('q'), ord('Q')]:
            print("[x] Выбор зоны слежения за камерой отменен.")
            break

    cv2.destroyAllWindows()
    return selected_roi

def save_cam_roi(roi):
    """Сохраняет ROI камеры в JSON файл."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(roi, f, indent=4)

def load_cam_roi():
    """Загружает сохраненный ROI камеры из JSON файла, если он существует."""
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
    select_cam_roi(delay=2)
