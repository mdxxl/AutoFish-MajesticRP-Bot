"""
MAJESTIC RP - ПОЛНЫЙ АВТОМАТИЧЕСКИЙ БОТ ДЛЯ РЫБАЛКИ
Цикл работы:
  1. [ЗАБРОС] — Детекция шкалы, попадание в зеленый сектор (Пробел).
  2. [ПОДСЕЧКА] — Ожидание поклевки по пузырькам у поплавка (Пробел).
  3. [ВЫВАЖИВАНИЕ] — Отслеживание движения камеры:
       - Камера влево -> зажимаем D
       - Камера вправо -> зажимаем A
       - Камера на месте -> отпускаем клавиши
  4. [УЛОВ] — Пока открыто окно улова, шкала заброса СТРОГО ОТКЛЮЧЕНА!
     Бот нажимает «Забрать себе» или «Отпустить (+1 EX)», ждет закрытия
     окна и только после этого снова включает прохождение шкалы.

Горячие клавиши:
  [F4] — Выбрать область нижнего меню снаряжения (авто-пауза при исчезновении)
  [F5] — Старт / Пауза
  [F6] — Полный выход
  [F7] — Выбрать область шкалы заброса мышкой
  [F8] — Выбрать область поплавка (индикатор поклевки) мышкой
  [F9] — Переключить режим рыбы (Забирать / Отпускать +1 EX)
  [F10] — Выбрать кнопки улова ("Забрать" / "Отпустить") мышкой
  [F11] — Показать / Скрыть визуальное окно отладки (чисто консоль)
  [F12] — Выбрать область камеры мышкой (рекомендуется бок экрана / берег / горизонт)
"""

import os
import sys
import time
import random
import ctypes
from ctypes import wintypes
import numpy as np
import cv2
import mss
import keyboard
import threading

# Путь к папке модулей и конфигураций
CORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core")
if CORE_DIR not in sys.path:
    sys.path.insert(0, CORE_DIR)

from select_roi import load_roi, select_roi
from select_indicator import load_bobber_roi, select_indicator_roi, detect_bubbles_in_crop
from select_fish_buttons import load_fish_action_config, select_fish_buttons, save_fish_action_config
from select_cam_roi import load_cam_roi, select_cam_roi, save_cam_roi
from select_menu_roi import load_menu_config, select_menu_roi, is_menu_present
from bot_bridge import get_bridge, BotBridge

# ==================== НАСТРОЙКИ СИСТЕМЫ ====================

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
SCREEN_W = user32.GetSystemMetrics(0)
SCREEN_H = user32.GetSystemMetrics(1)

SELECT_MENU_KEY = 'f4'
TOGGLE_KEY = 'f5'
EXIT_KEY = 'f6'
SELECT_BAR_KEY = 'f7'
SELECT_BOBBER_KEY = 'f8'
TOGGLE_MODE_KEY = 'f9'
SELECT_BUTTONS_KEY = 'f10'
TOGGLE_DEBUG_KEY = 'f11'
SELECT_CAM_KEY = 'f12'

# Настройки интерфейса
SHOW_DEBUG_WINDOW = False  # False — чисто консоль (быстрее и без всплывающих окон); True — показывать окно с полоской


# Состояния бота
STATE_CAST = "CAST"                 # Заброс удочки (шкала)
STATE_WAIT_BITE = "WAIT_BITE"       # Ожидание поклевки (поплавок)
STATE_REELING = "REELING"           # Вываживание рыбы (движение камеры A/D)
STATE_CATCH = "CATCH"               # Окно улова (выбор забрать/отпустить, шкала отключена)

# Загрузка координат
ROI_BAR = load_roi()
if not ROI_BAR:
    ROI_BAR = {"top": 1160, "left": 900, "width": 760, "height": 70}

ROI_BOBBER = load_bobber_roi()
if not ROI_BOBBER:
    ROI_BOBBER = {"top": 1115, "left": 1802, "width": 224, "height": 229}

FISH_CONFIG = load_fish_action_config()
if not FISH_CONFIG:
    FISH_CONFIG = {
        "mode": "take",
        "take_pos": [int(SCREEN_W * 0.45), int(SCREEN_H * 0.67)],
        "release_pos": [int(SCREEN_W * 0.55), int(SCREEN_H * 0.67)]
    }

# Настройки отслеживания движения рыбы / камеры в фазе вываживания
CAM_THRESH = 0.18           # Порог чувствительности сдвига dx (0.18 px / 100мс — четко и без ложных переключений)

# Область для отслеживания движения камеры (рекомендуется бок экрана: берег, скалы, горизонт)
CAM_ROI = load_cam_roi()
if not CAM_ROI:
    CAM_ROI = {
        "top": int(SCREEN_H * 0.15),
        "left": int(SCREEN_W * 0.04),
        "width": int(SCREEN_W * 0.22),
        "height": int(SCREEN_H * 0.25)
    }

# Область и эталонный фрагмент нижнего меню снаряжения для авто-паузы
ROI_MENU, MENU_TEMPLATE = load_menu_config()

# Область для проверки окна улова "ВЫ ПОЙМАЛИ РЫБУ" (центр экрана)
CENTER_CHECK_ROI = {
    "top": int(SCREEN_H * 0.10),
    "left": int(SCREEN_W * 0.30),
    "width": int(SCREEN_W * 0.40),
    "height": int(SCREEN_H * 0.50)
}

# Быстрый шаблон заголовка "ВЫ ПОЙМАЛИ РЫБУ"
TITLE_TEMPLATE_PATH = os.path.join(CORE_DIR, "fish_title.png")
TITLE_DOWN = None
if os.path.exists(TITLE_TEMPLATE_PATH):
    try:
        t_raw = cv2.imdecode(np.fromfile(TITLE_TEMPLATE_PATH, dtype=np.uint8), cv2.IMREAD_COLOR)
        if t_raw is not None:
            t_gray = cv2.cvtColor(t_raw, cv2.COLOR_BGR2GRAY)
            TITLE_DOWN = cv2.resize(t_gray, (t_gray.shape[1] // 2, t_gray.shape[0] // 2))
    except Exception:
        TITLE_DOWN = None

# ================= WIN32 DIRECTINPUT И МЫШЬ =================

ULONG_PTR = ctypes.c_ulonglong

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ('dx', wintypes.LONG),
        ('dy', wintypes.LONG),
        ('mouseData', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ULONG_PTR)
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk', wintypes.WORD),
        ('wScan', wintypes.WORD),
        ('dwFlags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ULONG_PTR)
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ('uMsg', wintypes.DWORD),
        ('wParamL', wintypes.WORD),
        ('wParamH', wintypes.WORD)
    ]

class INPUT_I(ctypes.Union):
    _fields_ = [
        ('mi', MOUSEINPUT),
        ('ki', KEYBDINPUT),
        ('hi', HARDWAREINPUT)
    ]

class INPUT(ctypes.Structure):
    _fields_ = [
        ('type', wintypes.DWORD),
        ('ii', INPUT_I)
    ]

SendInput = user32.SendInput
SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
SendInput.restype = wintypes.UINT

SPACE_SCAN = 0x39
VK_SPACE = 0x20

A_SCAN = 0x1E
VK_A = 0x41

D_SCAN = 0x20
VK_D = 0x44

def is_game_active():
    """
    Проверяет, развернута ли игра GTA5.exe (находится ли окно GTA5.exe в фокусе).
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value > 0:
            hProc = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
            if hProc:
                exe_buf = ctypes.create_unicode_buffer(512)
                sz = wintypes.DWORD(512)
                kernel32.QueryFullProcessImageNameW(hProc, 0, exe_buf, ctypes.byref(sz))
                kernel32.CloseHandle(hProc)
                exe_name = os.path.basename(exe_buf.value).lower()
                return exe_name == "gta5.exe"
    except Exception:
        pass

    return False

def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except:
        return False

def check_and_elevate():
    """Автоматический перезапуск от Администратора через UAC."""
    if not is_admin():
        print("[i] Запрос прав Администратора... Подтвердите в окне Windows.")
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}"'
        if len(sys.argv) > 1:
            params += " " + " ".join([f'"{a}"' for a in sys.argv[1:]])
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, params, os.path.dirname(script), 1
        )
        if ret > 32:
            sys.exit(0)

def key_down(vk, scan):
    try:
        inp = INPUT()
        inp.type = 1
        inp.ii.ki.wVk = vk
        inp.ii.ki.wScan = scan
        inp.ii.ki.dwFlags = 0x0008  # KEYEVENTF_SCANCODE
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    except Exception:
        pass
    try:
        user32.keybd_event(vk, scan, 0, 0)
    except Exception:
        pass

def key_up(vk, scan):
    try:
        inp = INPUT()
        inp.type = 1
        inp.ii.ki.wVk = vk
        inp.ii.ki.wScan = scan
        inp.ii.ki.dwFlags = 0x0008 | 0x0002  # KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    except Exception:
        pass
    try:
        user32.keybd_event(vk, scan, 2, 0)
    except Exception:
        pass

def press_space(hold_time=0.06):
    key_down(VK_SPACE, SPACE_SCAN)
    time.sleep(hold_time)
    key_up(VK_SPACE, SPACE_SCAN)

class SmoothKeyHolder:
    """
    Класс для непрерывного и стабильного ЗАЖАТИЯ клавиш (A/D) во время борьбы с рыбой.
    - Оптимизированный debounce (0.15 сек): быстрое переключение без дребезга.
    - Немедленный разворот (is_strong_reverse=True) при сильном подтвержденном движении камеры в обратную сторону.
    - При смене направления старая клавиша мгновенно гасится, а противоположная зажимается.
    - Клавиша зажимается и удерживается НЕПРЕРЫВНО на протяжении всего вываживания.
    """
    def __init__(self):
        self.current_key = None
        self.last_repeat_time = 0.0
        self.last_switch_time = 0.0
        self.last_motion_time = 0.0
        self.bridge = None

    def reset_timer(self, now):
        self.last_motion_time = now
        self.last_switch_time = now

    def update_direction(self, direction, now, is_strong_reverse=False):
        # direction: 'D', 'A', или None
        if direction is not None:
            self.last_motion_time = now
            if self.current_key != direction:
                # Если прошло >= 0.15с ИЛИ зафиксирован сильный разворот камеры в обратную сторону:
                allow_switch = (self.current_key is None) or (now - self.last_switch_time >= 0.15) or is_strong_reverse
                if allow_switch:
                    old_key = self.current_key
                    self.release_all()
                    self.current_key = direction
                    self.last_switch_time = now

                    # Включаем нужную клавишу с гарантированным отключением противоположной
                    if direction == 'D':
                        key_up(VK_A, A_SCAN)    # Жестко отпускаем A
                        key_down(VK_D, D_SCAN)  # Зажимаем D
                    elif direction == 'A':
                        key_up(VK_D, D_SCAN)    # Жестко отпускаем D
                        key_down(VK_A, A_SCAN)  # Зажимаем A

                    arrow = "ВЛЕВО -> [D]" if direction == 'D' else "ВПРАВО -> [A]"
                    if old_key is not None:
                        print(f"[{time.strftime('%H:%M:%S')}] [3. ВЫВАЖИВАНИЕ] Смена направления: [{old_key}] -> [{direction}] ({arrow})")
                    else:
                        print(f"[{time.strftime('%H:%M:%S')}] [3. ВЫВАЖИВАНИЕ] Захват движения: [{direction}] ({arrow})")

                    if self.bridge:
                        self.bridge.sig_log.emit("Reeling", f"Вываживание: [{direction}] ({arrow})", "info")

        # Если клавиша активна — непрерывно удерживаем ее (пульсация key_down каждые 30 мс)
        if self.current_key is not None:
            if now - self.last_repeat_time > 0.03:
                if self.current_key == 'D':
                    key_up(VK_A, A_SCAN)
                    key_down(VK_D, D_SCAN)
                elif self.current_key == 'A':
                    key_up(VK_D, D_SCAN)
                    key_down(VK_A, A_SCAN)
                self.last_repeat_time = now

    def release_all(self):
        """Гарантированно отпускает обе клавиши A и D."""
        try:
            key_up(VK_A, A_SCAN)
        except Exception:
            pass
        try:
            key_up(VK_D, D_SCAN)
        except Exception:
            pass
        self.current_key = None

key_holder = SmoothKeyHolder()


class MotionTracker:
    """
    Высокоточный оптический поток по выбранной зоне экрана (боковая зона / берег / горизонт).
    - Отслеживает смещение между последовательными кадрами (frame-to-frame) без буферных искажений и алиасинга.
    - Автоматически пополняет контрастные точки (Lucas-Kanade PyrLK, winSize=21, maxLevel=3).
    - Исключает краевые артефакты рамки (маска с отступом 8 px).
    - Резервная фазовая корреляция с порогом 0.02 (для однотонных текстур/неба).
    - Медианный сдвиг (np.median) полностью отсекает любые случайные выбросы.
    """
    def __init__(self, thresh=CAM_THRESH):
        self.thresh = thresh
        self.prev_gray = None
        self.last_t = 0.0
        self.smoothed_dx = 0.0
        self.candidate_dir = None
        self.candidate_count = 0
        self.last_flow_pts = []  # Список точек для отладочной визуализации [(x0, y0, x1, y1), ...]
        self.method_used = "LK"
        self.pts = None

    def reset(self):
        self.prev_gray = None
        self.last_t = 0.0
        self.smoothed_dx = 0.0
        self.candidate_dir = None
        self.candidate_count = 0
        self.last_flow_pts.clear()
        self.pts = None
        self.method_used = "LK"

    def update(self, gray_frame, now):
        if self.prev_gray is None:
            self.prev_gray = gray_frame
            self.last_t = now
            return self.smoothed_dx, None

        dt = now - self.last_t
        if dt < 0.015:
            return self.smoothed_dx, None

        h, w = gray_frame.shape
        self.last_flow_pts.clear()
        raw_dx = 0.0
        used_lk = False

        # Пополняем точки при их нехватке (с отступом от краев для исключения граничных артефактов)
        if self.pts is None or len(self.pts) < 12:
            mask = np.zeros((h, w), dtype=np.uint8)
            mask[8:-8, 8:-8] = 255
            fresh_pts = cv2.goodFeaturesToTrack(self.prev_gray, maxCorners=50, qualityLevel=0.01, minDistance=5, mask=mask)
            if fresh_pts is not None:
                if self.pts is None or len(self.pts) == 0:
                    self.pts = fresh_pts
                else:
                    self.pts = np.vstack([self.pts, fresh_pts])

        # 1. Оптический поток Lucas-Kanade
        if self.pts is not None and len(self.pts) >= 5:
            next_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                self.prev_gray, gray_frame, self.pts, None,
                winSize=(21, 21), maxLevel=3,
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03)
            )
            if next_pts is not None and status is not None:
                good = (status.flatten() == 1)
                # Оставляем только точки, не вышедшие за границы кадра
                p0 = self.pts[good].reshape(-1, 2)
                p1 = next_pts[good].reshape(-1, 2)
                in_bounds = (p1[:, 0] >= 4) & (p1[:, 0] < w - 4) & (p1[:, 1] >= 4) & (p1[:, 1] < h - 4)
                p0 = p0[in_bounds]
                p1 = p1[in_bounds]

                if len(p0) >= 4:
                    dx_arr = p1[:, 0] - p0[:, 0]
                    raw_dx = float(np.median(dx_arr))
                    used_lk = True
                    self.method_used = f"LK ({len(p0)} pts)"
                    for (x0, y0), (x1, y1) in zip(p0[:20], p1[:20]):
                        self.last_flow_pts.append((int(x0), int(y0), int(x1), int(y1)))
                    self.pts = p1.reshape(-1, 1, 2)
                else:
                    self.pts = None

        # 2. Если контрастных точек мало (гладкое небо / туман) — фазовая корреляция с окном Ханна
        if not used_lk:
            self.pts = None
            hann = cv2.createHanningWindow((w, h), cv2.CV_32F)
            f_prev_32 = self.prev_gray.astype(np.float32)
            f_curr_32 = gray_frame.astype(np.float32)
            shift, response = cv2.phaseCorrelate(f_prev_32, f_curr_32, hann)
            if response > 0.02:
                raw_dx = float(shift[0])
            else:
                raw_dx = 0.0
            self.method_used = f"PHASE (resp {response:.2f})"

        # Нормализуем сдвиг к стандартному интервалу 100 мс
        norm_dx = raw_dx * (0.10 / max(dt, 0.01))

        # Сглаживание EMA (50% новое, 50% старое)
        self.smoothed_dx = 0.50 * norm_dx + 0.50 * self.smoothed_dx

        self.prev_gray = gray_frame
        self.last_t = now

        instant_dir = None
        if self.smoothed_dx > self.thresh:
            instant_dir = 'D'  # Картинка сдвигается вправо (камера повернулась влево) -> зажимаем D
        elif self.smoothed_dx < -self.thresh:
            instant_dir = 'A'  # Картинка сдвигается влево (камера повернулась вправо) -> зажимаем A

        # Подтверждение направления: требуем 2 замера подряд в одном направлении
        if instant_dir is not None:
            if instant_dir == self.candidate_dir:
                self.candidate_count += 1
            else:
                self.candidate_dir = instant_dir
                self.candidate_count = 1

            if self.candidate_count >= 2:
                return self.smoothed_dx, instant_dir
        else:
            self.candidate_count = 0

        return self.smoothed_dx, None

motion_tracker = MotionTracker(thresh=CAM_THRESH)



def click_at(x, y):
    """Клик ЛКМ по координатам на экране."""
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.04)
    try:
        inp = INPUT()
        inp.type = 0
        inp.ii.mi.dwFlags = 0x0002  # MOUSEEVENTF_LEFTDOWN
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.05)
        inp.ii.mi.dwFlags = 0x0004  # MOUSEEVENTF_LEFTUP
        SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    except Exception:
        pass
    try:
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    except Exception:
        pass

# ================= ОБРАБОТКА КАДРОВ =================

def process_bar_frame(frame):
    b, g, r = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
    green_mask = (g > 140) & (r < 120) & (b < 120)
    green_ys, green_xs = np.where(green_mask)

    if len(green_xs) < 20:
        return None, None, None

    g_x_min, g_x_max = int(np.min(green_xs)), int(np.max(green_xs))
    g_y_min, g_y_max = int(np.min(green_ys)), int(np.max(green_ys))

    pad = 6
    bar_y1 = max(0, g_y_min - pad)
    bar_y2 = min(frame.shape[0], g_y_max + pad)
    bar_strip = frame[bar_y1:bar_y2, :]

    sb, sg, sr = bar_strip[:, :, 0], bar_strip[:, :, 1], bar_strip[:, :, 2]
    white_mask = (sr > 165) & (sb > 145) & (sg > 185)
    white_xs = np.where(white_mask)[1]

    slider_x = None
    if len(white_xs) >= 3:
        slider_x = int(np.median(white_xs))

    return (g_x_min, g_x_max), (g_y_min, g_y_max), slider_x

def check_fish_catch_window(sct):
    """
    Быстрая (2 мс) детекция окна 'ВЫ ПОЙМАЛИ РЫБУ'.
    """
    if TITLE_DOWN is None:
        return False
    
    check_img = np.array(sct.grab(CENTER_CHECK_ROI))
    gray = cv2.cvtColor(check_img, cv2.COLOR_BGRA2GRAY)
    gray_down = cv2.resize(gray, (gray.shape[1] // 2, gray.shape[0] // 2))
    
    res = cv2.matchTemplate(gray_down, TITLE_DOWN, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(res)
    return max_val > 0.80

# ================= ГЛАВНЫЙ ЦИКЛ =================

def run_bot(bridge=None, stop_event=None):
    global ROI_BAR, ROI_BOBBER, FISH_CONFIG, SHOW_DEBUG_WINDOW, CAM_ROI, ROI_MENU, MENU_TEMPLATE

    print("=" * 65)
    print("   MAJESTIC RP — ПОЛНЫЙ АВТОМАТИЧЕСКИЙ БОТ РЫБАЛКИ")
    print("=" * 65)
    print(f"Разрешение экрана: {SCREEN_W}x{SCREEN_H}")
    print(f"Режим улова: [{FISH_CONFIG['mode'].upper()}] (F9 для переключения)")
    print(f"Окно отладки: [{'ВКЛЮЧЕНО' if SHOW_DEBUG_WINDOW else 'СКРЫТО (чисто консоль)'}] (F11 для переключения)")
    menu_st = "ВКЛЮЧЕН" if (ROI_MENU and MENU_TEMPLATE is not None) else "НЕ НАСТРОЕН (F4 для выбора)"
    print(f"Контроль нижнего меню: [{menu_st}]")
    print("\nГорячие клавиши:")
    print(f"  [{SELECT_MENU_KEY.upper()}]  — Выбрать область нижнего меню (авто-пауза при исчезновении)")
    print(f"  [{TOGGLE_KEY.upper()}]  — Старт / Пауза")
    print(f"  [{SELECT_BAR_KEY.upper()}]  — Выбрать шкалу заброса мышкой")
    print(f"  [{SELECT_BOBBER_KEY.upper()}]  — Выбрать поплавок мышкой")
    print(f"  [{TOGGLE_MODE_KEY.upper()}]  — Переключить режим: Забирать / Отпускать")
    print(f"  [{SELECT_BUTTONS_KEY.upper()}] — Выбрать кнопки улова мышкой")
    print(f"  [{TOGGLE_DEBUG_KEY.upper()}] — Показать / Скрыть окно отладки (чисто консоль)")
    print(f"  [{SELECT_CAM_KEY.upper()}] — Выбрать область камеры мышкой (бок экрана / берег)")
    print(f"  [{EXIT_KEY.upper()}]  — Выход")
    print("\nСтатус: НА ПАУЗЕ (войдите в игру и нажмите " + TOGGLE_KEY.upper() + ")\n")

    caught_count = 0
    released_count = 0
    is_running = False
    bot_state = STATE_CAST
    state_timer = 0.0
    reeling_start_time = 0.0
    last_cam_check = 0.0
    last_hit_flash = 0.0
    last_inactive_log = 0.0
    last_menu_check = 0.0
    menu_missing_since = None
    menu_match_score = 1.0
    debug_window_created = False
    prev_game_active = None

    # Очередь запросов из GUI
    req_toggle_running = [False]
    req_toggle_mode = [False]

    if bridge:
        key_holder.bridge = bridge
        bridge.sig_request_toggle_running.connect(lambda: req_toggle_running.__setitem__(0, True))
        bridge.sig_request_toggle_mode.connect(lambda: req_toggle_mode.__setitem__(0, True))
        bridge.sig_fish_updated.emit(0, 0, FISH_CONFIG["mode"])
        bridge.sig_state_changed.emit(bot_state, is_running, is_game_active())
        bridge.sig_log.emit("Core", f"Клиент успешно подключен к окну Majestic RP ({SCREEN_W}x{SCREEN_H})", "info")
        bridge.sig_log.emit("Vision", "Калибровка зон (шкала, поплавок, камера): [OK]", "info")

    with mss.mss() as sct:
        while True:
            # Проверка сигнала завершения потока
            if (stop_event and stop_event.is_set()) or keyboard.is_pressed(EXIT_KEY):
                key_holder.release_all()
                print("Завершение работы бота...")
                if bridge:
                    bridge.sig_request_stop.emit()
                break

            now = time.time()

            # Управление горячими клавишами и запросами из GUI
            if keyboard.is_pressed(TOGGLE_KEY) or req_toggle_running[0]:
                req_toggle_running[0] = False
                is_running = not is_running
                status_msg = ">>> АКТИВЕН <<<" if is_running else "|| ПАУЗА ||"
                print(f"[{time.strftime('%H:%M:%S')}] Бот: {status_msg}")
                if not is_running:
                    key_holder.release_all()
                    motion_tracker.reset()
                if bridge:
                    bridge.sig_state_changed.emit(bot_state, is_running, is_game_active())
                    bridge.sig_log.emit("Status", f"Сессия: {status_msg}", "info")
                menu_missing_since = None
                time.sleep(0.3)

            if keyboard.is_pressed(SELECT_MENU_KEY):
                key_holder.release_all()
                new_roi, new_tmpl = select_menu_roi(delay=1)
                if new_roi and new_tmpl is not None:
                    ROI_MENU = new_roi
                    MENU_TEMPLATE = new_tmpl
                    menu_missing_since = None
                continue

            if keyboard.is_pressed(TOGGLE_MODE_KEY) or req_toggle_mode[0]:
                req_toggle_mode[0] = False
                FISH_CONFIG["mode"] = "release" if FISH_CONFIG["mode"] == "take" else "take"
                save_fish_action_config(FISH_CONFIG)
                mode_ru = "ЗАБИРАТЬ СЕБЕ" if FISH_CONFIG["mode"] == "take" else "ОТПУСКАТЬ (+1 EX)"
                print(f"[{time.strftime('%H:%M:%S')}] [F9] Режим улова изменен на: [{mode_ru}]")
                if bridge:
                    bridge.sig_fish_updated.emit(caught_count, released_count, FISH_CONFIG["mode"])
                    bridge.sig_log.emit("System", f"Режим улова переключен: [{mode_ru}]", "info")
                time.sleep(0.3)

            if keyboard.is_pressed(SELECT_BAR_KEY):
                key_holder.release_all()
                new_bar = select_roi(delay=1)
                if new_bar:
                    ROI_BAR = new_bar
                continue

            if keyboard.is_pressed(SELECT_BOBBER_KEY):
                key_holder.release_all()
                new_bobber = select_indicator_roi(delay=1)
                if new_bobber:
                    ROI_BOBBER = new_bobber
                continue

            if keyboard.is_pressed(SELECT_BUTTONS_KEY):
                key_holder.release_all()
                new_cfg = select_fish_buttons(delay=1)
                if new_cfg:
                    FISH_CONFIG = new_cfg
                continue

            if keyboard.is_pressed(TOGGLE_DEBUG_KEY):
                SHOW_DEBUG_WINDOW = not SHOW_DEBUG_WINDOW
                status_str = "ВКЛЮЧЕНО" if SHOW_DEBUG_WINDOW else "СКРЫТО (чисто консоль)"
                print(f"[{time.strftime('%H:%M:%S')}] [F11] Окно отладки: {status_str}")
                if not SHOW_DEBUG_WINDOW:
                    try:
                        cv2.destroyAllWindows()
                    except Exception:
                        pass
                    debug_window_created = False
                time.sleep(0.3)

            if keyboard.is_pressed(SELECT_CAM_KEY):
                key_holder.release_all()
                new_cam = select_cam_roi(delay=1)
                if new_cam:
                    CAM_ROI = new_cam
                    motion_tracker.reset()
                continue

            # -------------------------------------------------------------
            # ПРОВЕРКА ФОКУСА ОКНА ИГРЫ
            # -------------------------------------------------------------
            game_active = is_game_active()
            if prev_game_active is None or game_active != prev_game_active:
                prev_game_active = game_active
                if bridge:
                    bridge.sig_state_changed.emit(bot_state, is_running, game_active)
                    if not game_active:
                        bridge.sig_log.emit("Safety", "Окно GTA V не в фокусе (Alt-Tab). Ввод приостановлен.", "warn")
                    else:
                        bridge.sig_log.emit("Core", "Окно GTA V активно! Работа продолжается.", "info")

            # -------------------------------------------------------------
            # ЛОГИКА ЭТАПОВ РЫБАЛКИ
            # -------------------------------------------------------------
            if is_running:
                if not game_active:
                    key_holder.release_all()  # Если свернули игру — сразу глушим клавиши
                    if now - last_inactive_log > 3.0:
                        print(f"[{time.strftime('%H:%M:%S')}] [!] Игра свернута/не в фокусе. Бот ждет возврата в окно GTA...")
                        last_inactive_log = now
                    time.sleep(0.05)
                else:
                    # 1. ПЕРВЫМ ДЕЛОМ: ПРОВЕРЯЕМ, ОТКРЫТО ЛИ ОКНО ВЫБОРА РЫБЫ
                    is_catch_window = check_fish_catch_window(sct)

                    if is_catch_window:
                        key_holder.release_all()  # Немедленно отпускаем зажатую A/D
                        motion_tracker.reset()
                        bot_state = STATE_CATCH
                        if bridge:
                            bridge.sig_state_changed.emit(bot_state, is_running, game_active)

                        # Подгружаем актуальный конфиг
                        reloaded_cfg = load_fish_action_config()
                        if reloaded_cfg:
                            FISH_CONFIG = reloaded_cfg

                        # Выполняем действие с рыбой
                        mode = FISH_CONFIG.get("mode", "take")
                        if mode == "take":
                            tx, ty = FISH_CONFIG["take_pos"]
                            click_at(tx, ty)
                            caught_count += 1
                            print(f"[{time.strftime('%H:%M:%S')}] [4. УЛОВ] Блокировка шкалы. Клик: 'Забрать себе' ({tx}, {ty}) [Всего: {caught_count}]")
                            if bridge:
                                bridge.sig_fish_updated.emit(caught_count, released_count, mode)
                                bridge.sig_log.emit("Catch", f"Поймана рыба! Забрана себе в садок [Всего: {caught_count} шт.]", "catch")
                        else:
                            rx, ry = FISH_CONFIG["release_pos"]
                            click_at(rx, ry)
                            released_count += 1
                            print(f"[{time.strftime('%H:%M:%S')}] [4. УЛОВ] Блокировка шкалы. Клик: 'Отпустить (+1 EX)' ({rx}, {ry}) [Всего: {released_count}]")
                            if bridge:
                                bridge.sig_fish_updated.emit(caught_count, released_count, mode)
                                bridge.sig_log.emit("Catch", f"Поймана рыба! Отпущена (+1 EX) [Всего: {released_count} шт.]", "catch")

                        # Ждем, пока окно выбора рыбы исчезнет с экрана
                        wait_start = time.time()
                        while time.time() - wait_start < 2.0:
                            if not check_fish_catch_window(sct):
                                break
                            time.sleep(0.04)

                        post_catch_delay = round(random.uniform(2.0, 3.0), 2)
                        print(f"[{time.strftime('%H:%M:%S')}] [✓ ДЕЙСТВИЕ ПРИМЕНЕНО] Окно закрыто. Задержка {post_catch_delay:.2f} сек перед забросом...\n")

                        state_timer = time.time() + post_catch_delay
                        bot_state = STATE_CAST
                        if bridge:
                            bridge.sig_state_changed.emit(bot_state, is_running, game_active)
                        continue

                    # -------------------------------------------------------------
                    # 2. ПРОВЕРКА НАЛИЧИЯ НИЖНЕГО МЕНЮ СНАРЯЖЕНИЯ
                    # -------------------------------------------------------------
                    if ROI_MENU and MENU_TEMPLATE is not None:
                        if now - last_menu_check >= 0.25:
                            last_menu_check = now
                            menu_ok, score = is_menu_present(sct, ROI_MENU, MENU_TEMPLATE)
                            menu_match_score = score
                            if not menu_ok:
                                if menu_missing_since is None:
                                    menu_missing_since = now
                                elif now - menu_missing_since >= 1.0:
                                    is_running = False
                                    key_holder.release_all()
                                    motion_tracker.reset()
                                    menu_missing_since = None
                                    print(f"\n[{time.strftime('%H:%M:%S')}] [ВНИМАНИЕ] Нижнее меню снаряжения пропало с экрана (сходство: {score:.2f})!")
                                    print(f"[{time.strftime('%H:%M:%S')}] Бот автоматически переведен на || ПАУЗУ || (F5 для возобновления)\n")
                                    if bridge:
                                        bridge.sig_state_changed.emit(bot_state, False, game_active)
                                        bridge.sig_log.emit("HUD", f"Нижнее меню пропало! Авто-пауза (сходство: {score:.2f})", "warn")
                                    try:
                                        import winsound
                                        winsound.Beep(1000, 200)
                                        winsound.Beep(800, 300)
                                    except Exception:
                                        pass
                                    continue
                            else:
                                menu_missing_since = None

                    # -------------------------------------------------------------
                    # 3. ЭТАП 1: ЗАБРОС УДОЧКИ (ШКАЛА)
                    # -------------------------------------------------------------
                    if bot_state == STATE_CAST:
                        if now >= state_timer:
                            sct_img = sct.grab(ROI_BAR)
                            bar_frame = np.array(sct_img)
                            green_x, green_y, slider_x = process_bar_frame(bar_frame)

                            if green_x and slider_x is not None:
                                g_min, g_max = green_x
                                if g_min <= slider_x <= g_max:
                                    press_space()
                                    last_hit_flash = now
                                    print(f"[{time.strftime('%H:%M:%S')}] [1. ЗАБРОС] Попадание! Ползунок: {slider_x}, Зона: [{g_min}, {g_max}].")
                                    bot_state = STATE_WAIT_BITE
                                    state_timer = now + 1.8  # Пауза на полет поплавка в воду
                                    print(f"[{time.strftime('%H:%M:%S')}] [2. ПОПЛАВОК] Ожидание падения поплавка в воду...")
                                    if bridge:
                                        bridge.sig_state_changed.emit(bot_state, is_running, game_active)
                                        bridge.sig_log.emit("Vision", f"Попадание по шкале ({slider_x})! Ждём поклёвку...", "info")

                    # -------------------------------------------------------------
                    # 3. ЭТАП 2: ОЖИДАНИЕ ПУЗЫРЬКОВ (ПОДСЕЧКА)
                    # -------------------------------------------------------------
                    elif bot_state == STATE_WAIT_BITE:
                        if now > state_timer:
                            sct_bobber = sct.grab(ROI_BOBBER)
                            bobber_crop = np.array(sct_bobber)
                            is_bite, bubbles = detect_bubbles_in_crop(bobber_crop)

                            if is_bite:
                                press_space()  # Подсечка пробелом
                                last_hit_flash = now
                                print(f"[{time.strftime('%H:%M:%S')}] [2. ПОДСЕЧКА] Клев! Пузырьков: {bubbles}. Нажат ПРОБЕЛ!")
                                bot_state = STATE_REELING
                                motion_tracker.reset()
                                key_holder.reset_timer(now)
                                reeling_start_time = now
                                state_timer = now + 0.4
                                print(f"[{time.strftime('%H:%M:%S')}] [3. ВЫВАЖИВАНИЕ] Начало борьбы (камера влево -> D, вправо -> A)...")
                                if bridge:
                                    bridge.sig_state_changed.emit(bot_state, is_running, game_active)
                                    bridge.sig_log.emit("Success", f"Поклёвка! Пузырьков: {bubbles}. Подсечка [SPACE]!", "success")

                    # -------------------------------------------------------------
                    # 4. ЭТАП 3: ВЫВАЖИВАНИЕ (ТРЕКИНГ КАМЕРЫ A/D)
                    # -------------------------------------------------------------
                    elif bot_state == STATE_REELING:
                        if now > state_timer:
                            # Замер каждые 25 мс
                            if now - last_cam_check >= 0.025:
                                cam_frame = np.array(sct.grab(CAM_ROI))
                                h_cam, w_cam = cam_frame.shape[:2]
                                target_w = 240
                                target_h = max(60, int(240 * (h_cam / max(w_cam, 1))))
                                curr_cam_gray = cv2.resize(cv2.cvtColor(cam_frame, cv2.COLOR_BGRA2GRAY), (target_w, target_h))

                                smoothed_dx, detected_dir = motion_tracker.update(curr_cam_gray, now)

                                # Немедленный разворот при сильном подтвержденном движении в обратную сторону
                                is_strong_rev = False
                                if key_holder.current_key and detected_dir and detected_dir != key_holder.current_key:
                                    if abs(smoothed_dx) > 1.8 * CAM_THRESH:
                                        is_strong_rev = True

                                key_holder.update_direction(detected_dir, now, is_strong_reverse=is_strong_rev)
                                last_cam_check = now
                            else:
                                # Между замерами непрерывно поддерживаем зажатую клавишу
                                key_holder.update_direction(None, now)

                            # Защитный таймаут: только если полная тишина более 10 секунд (рыба сорвалась)
                            if (now - reeling_start_time > 3.0) and (now - key_holder.last_motion_time > 10.0):
                                key_holder.release_all()
                                motion_tracker.reset()
                                bot_state = STATE_CAST
                                print(f"[{time.strftime('%H:%M:%S')}] [3. ВЫВАЖИВАНИЕ] Рыба сорвалась (тишина 10 сек). Готовы к забросу...")
                                if bridge:
                                    bridge.sig_state_changed.emit(bot_state, is_running, game_active)
                                    bridge.sig_log.emit("Safety", "Рыба сорвалась (тишина 10 сек). Готовы к забросу.", "warn")

            # -------------------------------------------------------------
            # ОКНО ОТЛАДКИ (ЕСЛИ ВКЛЮЧЕНО)
            # -------------------------------------------------------------
            if SHOW_DEBUG_WINDOW:
                sct_img = sct.grab(ROI_BAR)
                frame = np.array(sct_img)
                bar_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                if bot_state == STATE_CAST:
                    green_x, green_y, slider_x = process_bar_frame(frame)
                    if green_x and green_y:
                        gx1, gx2 = green_x
                        gy1, gy2 = green_y
                        cv2.rectangle(bar_bgr, (gx1, gy1), (gx2, gy2), (0, 255, 0), 2)
                        if slider_x is not None:
                            is_in = (gx1 <= slider_x <= gx2)
                            cv2.line(bar_bgr, (slider_x, gy1 - 5), (slider_x, gy2 + 5), 
                                     (0, 255, 255) if is_in else (0, 0, 255), 2)

                panel_w = max(bar_bgr.shape[1], 760)
                panel_h = 120
                cam_panel = np.zeros((panel_h, panel_w, 3), dtype=np.uint8)
                cam_panel[:] = (30, 30, 30)

                try:
                    c_img = np.array(sct.grab(CAM_ROI))
                    c_bgr = cv2.cvtColor(c_img, cv2.COLOR_BGRA2BGR)
                    thumb_w = 160
                    thumb_h = 100
                    thumb = cv2.resize(c_bgr, (thumb_w, thumb_h))

                    if bot_state != STATE_REELING:
                        h_c, w_c = c_bgr.shape[:2]
                        pw = 240
                        ph = max(60, int(240 * (h_c / max(w_c, 1))))
                        c_gray = cv2.resize(cv2.cvtColor(c_bgr, cv2.COLOR_BGR2GRAY), (pw, ph))
                        motion_tracker.update(c_gray, now)

                    scale_x = thumb_w / 240.0
                    scale_y = thumb_h / 160.0
                    for (x0, y0, x1, y1) in motion_tracker.last_flow_pts:
                        tx0, ty0 = int(x0 * scale_x), int(y0 * scale_y)
                        tx1, ty1 = int(x1 * scale_x), int(y1 * scale_y)
                        cv2.circle(thumb, (tx0, ty0), 2, (0, 255, 0), -1)
                        if abs(x1 - x0) > 0.5:
                            cv2.arrowedLine(thumb, (tx0, ty0), (tx1, ty1), (0, 255, 255), 1, tipLength=0.3)

                    cam_panel[10:10+thumb_h, 10:10+thumb_w] = thumb
                    cv2.rectangle(cam_panel, (10, 10), (10+thumb_w, 10+thumb_h), (0, 200, 255), 1)
                except Exception:
                    pass

                dx_val = motion_tracker.smoothed_dx
                cv2.putText(cam_panel, f"CAM TRACKER: {motion_tracker.method_used}", (185, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
                cv2.putText(cam_panel, f"ZONE ROI: {CAM_ROI['width']}x{CAM_ROI['height']} at ({CAM_ROI['left']}, {CAM_ROI['top']}) [F12 to change]", 
                            (185, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)

                prefix = "" if bot_state == STATE_REELING else "[ТЕСТ] "
                if dx_val > CAM_THRESH:
                    dir_guide = f"{prefix}>>> ВПРАВО (Камера влево) -> [D] (DX: {dx_val:+.2f}) >>>"
                    dir_color = (0, 255, 0)
                elif dx_val < -CAM_THRESH:
                    dir_guide = f"{prefix}<<< ВЛЕВО (Камера вправо) -> [A] (DX: {dx_val:+.2f}) <<<"
                    dir_color = (0, 255, 255)
                else:
                    dir_guide = f"{prefix}--- КАМЕРА НА МЕСТЕ (DX: {dx_val:+.2f}) ---"
                    dir_color = (150, 150, 150)

                cv2.putText(cam_panel, dir_guide, (185, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.48, dir_color, 2)

                held_k = key_holder.current_key
                key_text = f"КЛАВИША: [{held_k}]" if held_k else "КЛАВИША: [-]"
                key_col = (0, 255, 255) if held_k else (120, 120, 120)
                cv2.putText(cam_panel, key_text, (185, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.45, key_col, 2)

                if ROI_MENU and MENU_TEMPLATE is not None:
                    m_col = (0, 255, 0) if menu_match_score >= 0.65 else (0, 0, 255)
                    m_txt = f"HUD: {'OK' if menu_match_score >= 0.65 else 'MISSING'} ({menu_match_score:.2f}) [F4]"
                else:
                    m_col = (130, 130, 130)
                    m_txt = "HUD: NOT SET [F4]"
                cv2.putText(cam_panel, m_txt, (400, 104), cv2.FONT_HERSHEY_SIMPLEX, 0.45, m_col, 2)

                if bar_bgr.shape[1] < panel_w:
                    padded_bar = np.zeros((bar_bgr.shape[0], panel_w, 3), dtype=np.uint8)
                    padded_bar[:, :bar_bgr.shape[1]] = bar_bgr
                    bar_bgr = padded_bar

                debug_img = np.vstack([bar_bgr, cam_panel])

                if not is_running:
                    status_color = (0, 0, 255)
                    st_name = "PAUSED (Press F5)"
                elif not game_active:
                    status_color = (0, 165, 255)
                    st_name = "WAITING GAME (ALT-TAB)"
                else:
                    status_color = (0, 255, 0)
                    st_name = "ACTIVE"
                cv2.putText(debug_img, f"BOT: {st_name}", (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, status_color, 2)

                if bot_state == STATE_CATCH:
                    stage_str = "4. УЛОВ [ШКАЛА ОТКЛЮЧЕНА]"
                    stage_color = (0, 140, 255)
                elif bot_state == STATE_CAST:
                    stage_str = "1. ШКАЛА ЗАБРОСА [АКТИВНА]"
                    stage_color = (0, 255, 0)
                elif bot_state == STATE_WAIT_BITE:
                    stage_str = "2. ЖДЕМ КЛЕВ (ПОПЛАВОК)"
                    stage_color = (255, 255, 255)
                else:
                    stage_str = "3. ВЫВАЖИВАНИЕ (A/D)"
                    stage_color = (255, 255, 0)

                cv2.putText(debug_img, stage_str, (160, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, stage_color, 2)

                mode_label = "TAKE" if FISH_CONFIG.get("mode") == "take" else "RELEASE"
                cv2.putText(debug_img, f"[{mode_label}]", (650, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 2)

                if now - last_hit_flash < 0.4:
                    cv2.putText(debug_img, ">>> SPACE HIT! <<<", (ROI_BAR["width"] // 2 - 80, ROI_BAR["height"] - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                win_title = "Fishing Bot Debug (F5: pause | F7: bar | F8: bobber | F9: mode | F10: buttons | F11: hide | F12: cam)"
                if not debug_window_created:
                    cv2.namedWindow(win_title, cv2.WINDOW_NORMAL)
                    cv2.moveWindow(win_title, 50, 50)
                    debug_window_created = True

                cv2.imshow(win_title, debug_img)

                if cv2.waitKey(1) & 0xFF == ord('q'):
                    key_holder.release_all()
                    break
            else:
                time.sleep(0.005)

    key_holder.release_all()
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass


def main():
    check_and_elevate()

    if "--no-gui" in sys.argv:
        run_bot(bridge=None)
    else:
        from PyQt6.QtWidgets import QApplication
        from overlay import FishingOverlay
        from bot_worker import BotWorkerThread
        from bot_bridge import get_bridge

        app = QApplication(sys.argv)
        overlay = FishingOverlay()
        overlay.show()

        bridge = get_bridge()
        worker = BotWorkerThread(run_bot)

        def on_about_to_quit():
            worker.stop()

        app.aboutToQuit.connect(on_about_to_quit)
        bridge.sig_request_stop.connect(app.quit)

        worker.start()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()

