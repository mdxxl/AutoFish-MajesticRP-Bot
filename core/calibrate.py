"""
Утилита калибровки области захвата (ROI) для бота рыбалки.
Позволяет визуально настроить ползунками координаты захвата или
автоматически обнаружить полоску мини-игры на экране.

Управление в окне:
  [A] — Автопоиск полоски на экране (когда мини-игра активна)
  [S] — Вывести готовые координаты в консоль
  [Q] или [ESC] — Выход
"""

import ctypes
import cv2
import mss
import numpy as np

user32 = ctypes.windll.user32
SCREEN_W = user32.GetSystemMetrics(0)
SCREEN_H = user32.GetSystemMetrics(1)

# Начальные значения
if SCREEN_W >= 2560 and SCREEN_H >= 1440:
    init_top = 1270
    init_left = 890
    init_w = 780
    init_h = 160
elif SCREEN_W >= 1920 and SCREEN_H >= 1080:
    init_top = 940
    init_left = 670
    init_w = 580
    init_h = 130
else:
    init_top = int(SCREEN_H * 0.86)
    init_left = int(SCREEN_W * 0.33)
    init_w = int(SCREEN_W * 0.34)
    init_h = int(SCREEN_H * 0.12)

WIN_NAME = "Fishing Calibration (A: Auto-Find | S: Print | Q: Exit)"

def nothing(x):
    pass

cv2.namedWindow(WIN_NAME, cv2.WINDOW_NORMAL)
cv2.resizeWindow(WIN_NAME, 800, 300)

cv2.createTrackbar("Top (Y)", WIN_NAME, init_top, SCREEN_H - 20, nothing)
cv2.createTrackbar("Left (X)", WIN_NAME, init_left, SCREEN_W - 50, nothing)
cv2.createTrackbar("Width", WIN_NAME, init_w, SCREEN_W, nothing)
cv2.createTrackbar("Height", WIN_NAME, init_h, 400, nothing)

print("=" * 60)
print("      УТИЛИТА КАЛИБРОВКИ ОБЛАСТИ РЫБАЛКИ")
print("=" * 60)
print(f"Разрешение экрана: {SCREEN_W}x{SCREEN_H}")
print("Горячие клавиши:")
print("  [A] — Автопоиск шкалы (нажмите, когда полоска в игре на экране)")
print("  [S] — Напечатать текущий блок ROI для main.py")
print("  [Q] — Закрыть калибровку\n")

with mss.mss() as sct:
    while True:
        top = cv2.getTrackbarPos("Top (Y)", WIN_NAME)
        left = cv2.getTrackbarPos("Left (X)", WIN_NAME)
        w = max(50, cv2.getTrackbarPos("Width", WIN_NAME))
        h = max(20, cv2.getTrackbarPos("Height", WIN_NAME))

        # Защита от выхода за экран
        w = min(w, SCREEN_W - left)
        h = min(h, SCREEN_H - top)

        roi = {"top": top, "left": left, "width": w, "height": h}
        img = np.array(sct.grab(roi))
        view = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        # Проверка детекции
        b, g, r = img[:, :, 0], img[:, :, 1], img[:, :, 2]
        green_mask = (g > 150) & (r < 115) & (b < 115)
        green_ys, green_xs = np.where(green_mask)

        status_str = "Status: Searching for green zone..."
        status_color = (0, 165, 255)

        if len(green_xs) >= 35:
            gx1, gx2 = int(np.min(green_xs)), int(np.max(green_xs))
            gy1, gy2 = int(np.min(green_ys)), int(np.max(green_ys))
            
            # Рамка полосы
            cv2.rectangle(view, (0, max(0, gy1 - 6)), (w, min(h, gy2 + 6)), (80, 80, 80), 1)
            # Зеленый сектор
            cv2.rectangle(view, (gx1, gy1), (gx2, gy2), (0, 255, 0), 2)
            
            # Поиск ползунка в полосе
            bar_y1 = max(0, gy1 - 6)
            bar_y2 = min(h, gy2 + 6)
            bar_strip = img[bar_y1:bar_y2, :]
            sb, sg, sr = bar_strip[:, :, 0], bar_strip[:, :, 1], bar_strip[:, :, 2]
            white_mask = (sr > 215) & (sg > 215) & (sb > 215)
            white_xs = np.where(white_mask)[1]
            
            if len(white_xs) >= 5:
                sx = int(np.median(white_xs))
                cv2.line(view, (sx, max(0, gy1 - 10)), (sx, min(h, gy2 + 10)), (0, 0, 255), 2)
                status_str = f"LOCKED! Zone: [{gx1}, {gx2}], Slider: {sx}"
                status_color = (0, 255, 0)
            else:
                status_str = f"Green zone found at Y={gy1}..{gy2}, waiting for slider..."
                status_color = (0, 255, 255)

        cv2.putText(view, status_str, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, status_color, 2)
        cv2.imshow(WIN_NAME, view)

        key = cv2.waitKey(20) & 0xFF
        if key in [ord('q'), 27]:
            break
        elif key == ord('s'):
            print("\n" + "-" * 40)
            print("Скопируйте в main.py:")
            print("ROI = {")
            print(f'    "top": {top},')
            print(f'    "left": {left},')
            print(f'    "width": {w},')
            print(f'    "height": {h}')
            print("}")
            print("-" * 40 + "\n")
        elif key == ord('a'):
            # Автопоиск в нижней части экрана (нижние 40%)
            search_top = int(SCREEN_H * 0.6)
            search_roi = {
                "top": search_top,
                "left": 0,
                "width": SCREEN_W,
                "height": SCREEN_H - search_top
            }
            big_frame = np.array(sct.grab(search_roi))
            bb, bg, br = big_frame[:, :, 0], big_frame[:, :, 1], big_frame[:, :, 2]
            gm = (bg > 150) & (br < 115) & (bb < 115)
            g_ys, g_xs = np.where(gm)
            if len(g_xs) >= 35:
                found_screen_y = search_top + int(np.min(g_ys))
                found_screen_x = int(np.min(g_xs))
                print(f"[АВТОПОИСК] Шкала найдена! Y ~ {found_screen_y}, X ~ {found_screen_x}")
                
                # Центрируем ROI вокруг найденной шкалы
                new_top = max(0, found_screen_y - 60)
                new_h = 150
                # Шкала обычно шириной ~720px (2K) или ~540px (1080p)
                bar_est_w = 780 if SCREEN_W >= 2560 else 580
                new_left = max(0, (SCREEN_W - bar_est_w) // 2)
                
                cv2.setTrackbarPos("Top (Y)", WIN_NAME, new_top)
                cv2.setTrackbarPos("Left (X)", WIN_NAME, new_left)
                cv2.setTrackbarPos("Width", WIN_NAME, bar_est_w)
                cv2.setTrackbarPos("Height", WIN_NAME, new_h)
            else:
                print("[АВТОПОИСК] Зеленая шкала не обнаружена. Запустите мини-игру в GTA и нажмите [A] снова.")

cv2.destroyAllWindows()
