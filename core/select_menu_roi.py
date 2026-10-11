"""
Интерактивный выбор области нижнего меню снаряжения рыбалки для авто-отключения (паузы).
Позволяет пользователю выделить мышкой любую иконку или фрагмент нижней панели снаряжения
(например, иконку удочки, катушки или силуэт персонажа).
Координаты сохраняются в 'menu_roi_config.json', а эталонный снимок — в 'menu_template.png'.
Если эта панель исчезает с экрана (закончилась наживка, сломалась удочка, персонаж отошел),
бот автоматически переходит в режим паузы (F5).
"""

import json
import os
import sys
import time
import cv2
import mss
import numpy as np

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu_roi_config.json")
TEMPLATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu_template.png")


def get_primary_monitor(sct):
    """Находит основной монитор."""
    for m in sct.monitors[1:]:
        if m.get("is_primary"):
            return m
    return sct.monitors[1]


def save_menu_config(roi, crop_img):
    """Сохраняет ROI в JSON и эталонный фрагмент в PNG (с поддержкой кириллических путей)."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(roi, f, indent=4)

    if crop_img is not None and crop_img.size > 0:
        is_success, buf = cv2.imencode(".png", crop_img)
        if is_success:
            buf.tofile(TEMPLATE_FILE)


def load_menu_config():
    """
    Загружает сохраненный ROI и эталонный шаблон меню из папки core/.
    Возвращает кортеж (roi: dict, template_bgr: np.ndarray) или (None, None).
    """
    roi = None
    template = None

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if all(k in data for k in ("top", "left", "width", "height")):
                    roi = data
        except Exception as e:
            print(f"[!] Ошибка чтения {CONFIG_FILE}: {e}")

    if os.path.exists(TEMPLATE_FILE):
        try:
            template = cv2.imdecode(np.fromfile(TEMPLATE_FILE, dtype=np.uint8), cv2.IMREAD_COLOR)
        except Exception as e:
            print(f"[!] Ошибка чтения {TEMPLATE_FILE}: {e}")

    return roi, template


def is_menu_present(sct, roi, template, threshold=0.65, pad=8):
    """
    Проверяет, присутствует ли эталонное меню на экране в заданной области.
    Использует cv2.TM_CCOEFF_NORMED с небольшим отступом pad для компенсации микросдвигов.
    
    Возвращает (is_present: bool, match_score: float).
    """
    if roi is None or template is None:
        return True, 1.0

    try:
        grab_roi = {
            "top": max(0, int(roi["top"] - pad)),
            "left": max(0, int(roi["left"] - pad)),
            "width": int(roi["width"] + pad * 2),
            "height": int(roi["height"] + pad * 2)
        }

        sct_img = sct.grab(grab_roi)
        curr = np.array(sct_img)
        curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGRA2GRAY)

        if len(template.shape) == 3:
            tmpl_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        else:
            tmpl_gray = template

        if curr_gray.shape[0] < tmpl_gray.shape[0] or curr_gray.shape[1] < tmpl_gray.shape[1]:
            return False, 0.0

        res = cv2.matchTemplate(curr_gray, tmpl_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)

        return (max_val >= threshold), float(max_val)
    except Exception:
        return True, 1.0


def select_menu_roi(delay=2):
    """
    Делает снимок экрана, открывает интерактивное окно выбора и дает пользователю
    возможность выделить фрагмент нижней панели снаряжения мышкой.
    
    Сохраняет координаты в menu_roi_config.json и эталон в menu_template.png.
    Возвращает (roi, template).
    """
    if delay > 0:
        print("\n" + "=" * 65)
        print("   ВЫБОР ОБЛАСТИ НИЖНЕГО МЕНЮ (СНАРЯЖЕНИЯ) ДЛЯ АВТО-ПАУЗЫ")
        print("=" * 65)
        print("Совет: Выделите одну или несколько иконок снаряжения (например:")
        print("       иконку удочки, катушки или силуэт персонажа).")
        print("Когда эти иконки пропадут (рыбалка завершится), бот сам встанет на паузу (F5).")
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

    win_name = "Select Bottom Menu (Drag mouse, press ENTER to confirm, ESC to cancel)"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.moveWindow(win_name, monitor["left"], monitor["top"])
    cv2.setWindowProperty(win_name, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.setMouseCallback(win_name, on_mouse)

    selected_roi = None
    selected_crop = None

    while True:
        display = original.copy()

        if drag_state["selecting"] or drag_state["has_selection"]:
            x1 = min(drag_state["x1"], drag_state["x2"])
            y1 = min(drag_state["y1"], drag_state["y2"])
            x2 = max(drag_state["x1"], drag_state["x2"])
            y2 = max(drag_state["y1"], drag_state["y2"])

            # Затемнение фона
            mask = np.zeros_like(display)
            mask[y1:y2, x1:x2] = display[y1:y2, x1:x2]
            dimmed = cv2.addWeighted(display, 0.35, mask, 0.65, 0)
            dimmed[y1:y2, x1:x2] = display[y1:y2, x1:x2]
            display = dimmed

            # Рамка выбора
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 128), 2)
            cv2.putText(display, f"{x2 - x1}x{y2 - y1} px", (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 128), 2)

        # Информационная плашка сверху
        banner_h = 75
        banner = np.zeros((banner_h, w_screen, 3), dtype=np.uint8)
        banner[:] = (20, 20, 20)

        t1 = "КОНТРОЛЬ МЕНЮ: Выделите область нижнего меню/снаряжения (иконку удочки, катушки или силуэт)"
        t2 = "[ENTER] / [ПРОБЕЛ] — Сохранить выбор  |  [ESC] / [Q] — Отмена  |  ЛКМ — перевыбрать"

        cv2.putText(banner, t1, (20, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 255, 180), 2)
        cv2.putText(banner, t2, (20, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 2)

        display[0:banner_h, 0:w_screen] = banner

        cv2.imshow(win_name, display)
        key = cv2.waitKey(20) & 0xFF

        # ENTER (13) или SPACE (32) — подтверждение
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
                selected_crop = original[ry1:ry2, rx1:rx2].copy()

                save_menu_config(selected_roi, selected_crop)
                print(f"[✓] Область нижнего меню успешно выбрана и сохранена:")
                print(f"    top={selected_roi['top']}, left={selected_roi['left']}, "
                      f"width={selected_roi['width']}, height={selected_roi['height']}")
                print(f"    Эталон сохранен в: {TEMPLATE_FILE}\n")
                break
            else:
                print("[!] Сначала выделите область меню снаряжения мышкой (зажмите ЛКМ и потяните)!")

        # ESC (27) или Q — отмена
        elif key in [27, ord('q'), ord('Q')]:
            print("[x] Выбор области нижнего меню отменен.")
            break

    cv2.destroyAllWindows()
    return selected_roi, selected_crop


if __name__ == "__main__":
    select_menu_roi(delay=2)
