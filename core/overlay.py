"""
Majestic RP Fishing Bot - Overlay UI
Сверхлёгкий оверлей поверх GTA V с поддержкой сквозного клика (WS_EX_TRANSPARENT)
и предотвращением перехвата фокуса ввода (WS_EX_NOACTIVATE).
Компактный размер под виджеты интерфейса Majestic RP.
"""
import os
import sys
import json
import time
import ctypes
from ctypes import wintypes
from typing import Optional

from PyQt6.QtCore import Qt, QPoint, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QTextBrowser, QPushButton, QFrame, QGraphicsDropShadowEffect
)

try:
    from bot_bridge import get_bridge
except ImportError:
    from core.bot_bridge import get_bridge

# ================= WIN32 API =================
user32 = ctypes.windll.user32
LONG_PTR = ctypes.c_int64

user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = LONG_PTR
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, LONG_PTR]
user32.SetWindowLongPtrW.restype = LONG_PTR

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "overlay_config.json")

DEFAULT_CONFIG = {
    "x": 2134,
    "y": 398,
    "width": 414,
    "height": 355,
    "click_through": True,
    "opacity": 0.98
}

def load_overlay_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_overlay_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
    except Exception:
        pass


class FishingOverlay(QWidget):
    def __init__(self):
        super().__init__()

        self.cfg = load_overlay_config()
        self.click_through = self.cfg.get("click_through", True)
        self.caught_count = 0
        self.released_count = 0
        self.is_running = False
        self.current_mode = "take"
        self.game_active = False

        # Перемещение окна мышью (когда режим кликов выключен)
        self.drag_position = QPoint()
        self.is_dragging = False

        self._init_window()
        self._init_ui()
        self._connect_signals()

        # Применяем координаты и размер
        self.move(self.cfg.get("x", 2134), self.cfg.get("y", 398))
        self.resize(self.cfg.get("width", 414), self.cfg.get("height", 355))

        # Настраиваем Win32 стили
        self.update_window_styles()

        # Локальный таймер для периодической проверки хоткея F3 (переключение режима кликов)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._check_hotkeys)
        self.hotkey_timer.start(100)

    def _init_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle("Majestic RP Fishing Overlay")

    def update_window_styles(self):
        """Применяет Win32 стили для click-through и non-activation."""
        try:
            hwnd = int(self.winId())
            cur_style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
            
            # Базовые стили: слоистое окно + никогда не перехватывает фокус ввода у GTA V
            new_style = cur_style | WS_EX_LAYERED | WS_EX_NOACTIVATE

            if self.click_through:
                # В сквозном режиме клики проходят прямо сквозь окно в игру
                new_style |= WS_EX_TRANSPARENT
            else:
                # В режиме перемещения окно можно перетаскивать мышкой
                new_style &= ~WS_EX_TRANSPARENT

            user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, new_style)
        except Exception as e:
            print(f"[Overlay] Ошибка применения стилей Win32: {e}")

    def toggle_click_through(self):
        """Переключает режим сквозных кликов (F3) и гарантированно сохраняет позицию."""
        self.click_through = not self.click_through
        self.cfg["click_through"] = self.click_through
        self.cfg["x"] = self.pos().x()
        self.cfg["y"] = self.pos().y()
        self.cfg["width"] = self.width()
        self.cfg["height"] = self.height()
        save_overlay_config(self.cfg)
        self.update_window_styles()
        self._update_mode_indicator()

        if self.click_through:
            self.append_log("System", f"Позиция сохранена ({self.pos().x()}, {self.pos().y()}). Сквозной режим: ВКЛ [F3]", "system")
        else:
            self.append_log("System", "Режим настройки: ВЫКЛ (переместите окно, затем нажмите F3 для фиксации)", "system")

    def _check_hotkeys(self):
        """Проверка нажатия F3 для переключения режима оверлея."""
        try:
            # 0x72 = VK_F3
            if user32.GetAsyncKeyState(0x72) & 0x0001:
                self.toggle_click_through()
        except Exception:
            pass

    def _init_ui(self):
        # Главный контейнер
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(4, 4, 4, 4)

        # Фоновый фрейм с тёмной темой и скруглением
        self.bg_frame = QFrame(self)
        self.bg_frame.setObjectName("bgFrame")
        self.bg_frame.setStyleSheet("""
            QFrame#bgFrame {
                background-color: #0d0e12;
                border: 1px solid #232532;
                border-radius: 12px;
            }
        """)

        # Тень для эффекта глубины
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 170))
        shadow.setOffset(0, 3)
        self.bg_frame.setGraphicsEffect(shadow)

        bg_layout = QVBoxLayout(self.bg_frame)
        bg_layout.setContentsMargins(12, 10, 12, 10)
        bg_layout.setSpacing(8)

        # -------------------------------------------------------------
        # 1. ШАПКА ОКНА (Заголовок и статус)
        # -------------------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        # Название по центру/слева
        self.title_label = QLabel("⚡ MajesticFish [ACTIVE]")
        self.title_label.setStyleSheet("""
            QLabel {
                color: #b0b4c3;
                font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                font-size: 11px;
                font-weight: 600;
            }
        """)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        # Бейдж статуса справа
        self.badge_status = QLabel("РАБОТАЕТ")
        self.badge_status.setStyleSheet("""
            QLabel {
                background-color: #0c281e;
                border: 1px solid #166534;
                color: #22c55e;
                font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                font-size: 10px;
                font-weight: bold;
                border-radius: 4px;
                padding: 2px 7px;
            }
        """)
        header_layout.addWidget(self.badge_status)

        bg_layout.addLayout(header_layout)

        # -------------------------------------------------------------
        # 2. ТРИ КАРТОЧКИ СТАТИСТИКИ (ПОЙМАНО / ОТПУЩЕНО / РЕЖИМ)
        # -------------------------------------------------------------
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(6)

        # Карточка 1: Поймано (В садок)
        card_caught, self.lbl_caught_val = self._create_metric_card(
            "ВЫЛОВЛЕНО", "0 шт.", "#ffffff"
        )
        # Карточка 2: Отпущено (+1 EX)
        card_released, self.lbl_released_val = self._create_metric_card(
            "ОТПУЩЕНО", "0 шт.", "#2ed573"
        )
        # Карточка 3: Текущий режим
        card_mode, self.lbl_mode_val = self._create_metric_card(
            "РЕЖИМ (F9)", "Забрать", "#ffffff"
        )

        cards_layout.addWidget(card_caught)
        cards_layout.addWidget(card_released)
        cards_layout.addWidget(card_mode)
        bg_layout.addLayout(cards_layout)

        # -------------------------------------------------------------
        # 3. ТЕРМИНАЛ ЛОГОВ (ЦВЕТНАЯ КОНСОЛЬ)
        # -------------------------------------------------------------
        self.log_console = QTextBrowser()
        self.log_console.setOpenExternalLinks(False)
        self.log_console.setStyleSheet("""
            QTextBrowser {
                background-color: #0a0b0e;
                border: 1px solid #1f202b;
                border-radius: 7px;
                color: #e2e8f0;
                font-family: 'Cascadia Code', 'Consolas', 'Courier New', monospace;
                font-size: 10px;
                line-height: 1.35;
                padding: 5px 7px;
            }
            QScrollBar:vertical {
                border: none;
                background: #0a0b0e;
                width: 5px;
                margin: 2px 0 2px 0;
            }
            QScrollBar::handle:vertical {
                background: #282a3a;
                min-height: 15px;
                border-radius: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        bg_layout.addWidget(self.log_console, stretch=1)

        # -------------------------------------------------------------
        # 5. НИЖНЯЯ ПАНЕЛЬ УПРАВЛЕНИЯ И ХОТКЕЕВ
        # -------------------------------------------------------------
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(8)

        # Кнопка Пауза / Старт
        self.btn_pause = QPushButton("⏸ Пауза (F5)")
        self.btn_pause.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pause.setStyleSheet("""
            QPushButton {
                background-color: #1a1b24;
                border: 1px solid #282a38;
                border-radius: 6px;
                color: #e2e8f0;
                font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                font-size: 10.5px;
                font-weight: 600;
                padding: 6px 10px;
            }
            QPushButton:hover {
                background-color: #242633;
                border-color: #3b3d52;
            }
            QPushButton:pressed {
                background-color: #14151c;
            }
        """)
        self.btn_pause.clicked.connect(self._on_pause_clicked)
        bottom_layout.addWidget(self.btn_pause, 1)

        # Бейдж хоткеев
        self.lbl_hotkeys = QLabel("🗲 F9: Режим | F3: Окно")
        self.lbl_hotkeys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hotkeys.setStyleSheet("""
            QLabel {
                background-color: #1a1b24;
                border: 1px solid #282a38;
                border-radius: 6px;
                color: #94a3b8;
                font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                font-size: 10.5px;
                font-weight: 500;
                padding: 6px 8px;
            }
        """)
        bottom_layout.addWidget(self.lbl_hotkeys, 1)

        bg_layout.addLayout(bottom_layout)

        # -------------------------------------------------------------
        # 6. СТРОКА СТАТУСА РЕЖИМА КЛИКОВ (СКВОЗНОЙ / ПЕРЕМЕЩЕНИЕ)
        # -------------------------------------------------------------
        self.lbl_mode_status = QLabel()
        self.lbl_mode_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_mode_status.setStyleSheet("""
            QLabel {
                color: #64748b;
                font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                font-size: 9.5px;
                padding-top: 1px;
            }
        """)
        bg_layout.addWidget(self.lbl_mode_status)
        self._update_mode_indicator()

        main_layout.addWidget(self.bg_frame)

    def _create_metric_card(self, title: str, val: str, val_color: str):
        card = QFrame()
        card.setObjectName("metricCard")
        card.setStyleSheet("""
            QFrame#metricCard {
                background-color: #17181f;
                border: 1px solid #232532;
                border-radius: 8px;
            }
            QFrame#metricCard QLabel {
                border: none;
                background: transparent;
            }
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(3)

        lbl_title = QLabel(title)
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title.setStyleSheet("""
            color: #7b8092;
            font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
            font-size: 9px;
            font-weight: 600;
            letter-spacing: 0.5px;
        """)
        layout.addWidget(lbl_title)

        lbl_val = QLabel(val)
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_val.setStyleSheet(f"""
            color: {val_color};
            font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
            font-size: 15px;
            font-weight: bold;
        """)
        layout.addWidget(lbl_val)

        return card, lbl_val

    def _update_mode_indicator(self):
        if self.click_through:
            self.lbl_mode_status.setText("🛡 Сквозной клик: ВКЛ (F3 - двигать окно)")
            self.lbl_mode_status.setStyleSheet("color: #22c55e; font-size: 9.5px; font-family: monospace;")
        else:
            self.lbl_mode_status.setText("✋ Настройка: ВЫКЛ (F3 - сохранить позицию)")
            self.lbl_mode_status.setStyleSheet("color: #f59e0b; font-size: 9.5px; font-family: monospace; font-weight: bold;")

    def _connect_signals(self):
        bridge = get_bridge()
        bridge.sig_log.connect(self.append_log)
        bridge.sig_state_changed.connect(self.on_state_changed)
        bridge.sig_fish_updated.connect(self.on_fish_updated)
        bridge.sig_progress_updated.connect(self.on_progress_updated)

    @pyqtSlot(str, str, str)
    def append_log(self, tag: str, message: str, level: str = "info"):
        t_str = time.strftime("%H:%M:%S")
        
        tag_colors = {
            "Core": "#f43f5e",
            "Vision": "#c084fc",
            "Success": "#22c55e",
            "Catch": "#06b6d4",
            "Safety": "#eab308",
            "Reeling": "#f97316",
            "HUD": "#38bdf8",
            "System": "#a855f7"
        }
        color = tag_colors.get(tag, "#38bdf8")

        html = f"""
        <div style="margin-bottom: 2px;">
            <span style="color: #64748b;">[{t_str}]</span>
            <span style="color: {color}; font-weight: bold;">[{tag}]</span>
            <span style="color: #e2e8f0;"> {message}</span>
        </div>
        """
        self.log_console.append(html)
        
        # Ограничиваем количество строк до 200
        doc = self.log_console.document()
        if doc.blockCount() > 200:
            cursor = self.log_console.textCursor()
            cursor.movePosition(cursor.MoveOperation.Start)
            cursor.select(cursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()

        # Автоскролл вниз
        self.log_console.verticalScrollBar().setValue(
            self.log_console.verticalScrollBar().maximum()
        )

    @pyqtSlot(str, bool, bool)
    def on_state_changed(self, state: str, is_running: bool, game_active: bool):
        self.is_running = is_running
        self.game_active = game_active

        # Обновляем кнопку
        if is_running:
            self.btn_pause.setText("⏸ Пауза (F5)")
        else:
            self.btn_pause.setText("▶ Старт (F5)")

        # Обновляем бейдж и заголовок
        if not is_running:
            self.badge_status.setText("ПАУЗА")
            self.badge_status.setStyleSheet("""
                QLabel {
                    background-color: #2e1c12;
                    border: 1px solid #78350f;
                    color: #f59e0b;
                    font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                    font-size: 10px;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 2px 7px;
                }
            """)
            self.title_label.setText("MajesticFish [PAUSED]")
        elif not game_active:
            self.badge_status.setText("ЖДЕТ GTA")
            self.badge_status.setStyleSheet("""
                QLabel {
                    background-color: #271d15;
                    border: 1px solid #b45309;
                    color: #fb923c;
                    font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                    font-size: 10px;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 2px 7px;
                }
            """)
            self.title_label.setText("MajesticFish [WAITING]")
        else:
            self.badge_status.setText("РАБОТАЕТ")
            self.badge_status.setStyleSheet("""
                QLabel {
                    background-color: #0c281e;
                    border: 1px solid #166534;
                    color: #22c55e;
                    font-family: 'Cascadia Code', 'Consolas', 'Segoe UI', monospace;
                    font-size: 10px;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 2px 7px;
                }
            """)
            self.title_label.setText("⚡ MajesticFish [ACTIVE]")

    @pyqtSlot(int, int, str)
    def on_fish_updated(self, caught: int, released: int, mode: str):
        self.caught_count = caught
        self.released_count = released
        self.current_mode = mode

        self.lbl_caught_val.setText(f"{caught} шт.")
        self.lbl_released_val.setText(f"{released} шт.")

        mode_ru = "Забрать" if mode == "take" else "Отпустить"
        self.lbl_mode_val.setText(mode_ru)

    @pyqtSlot(int, int)
    def on_progress_updated(self, current: int, max_cap: int):
        pass

    def _on_pause_clicked(self):
        bridge = get_bridge()
        bridge.sig_request_toggle_running.emit()

    # -------------------------------------------------------------
    # Перетаскивание окна мышкой (только когда click-through выключен)
    # -------------------------------------------------------------
    def mousePressEvent(self, event):
        if not self.click_through and event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if not self.click_through and self.is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            self.cfg["x"] = self.pos().x()
            self.cfg["y"] = self.pos().y()
            save_overlay_config(self.cfg)
            event.accept()

    def closeEvent(self, event):
        self.cfg["x"] = self.pos().x()
        self.cfg["y"] = self.pos().y()
        self.cfg["width"] = self.width()
        self.cfg["height"] = self.height()
        save_overlay_config(self.cfg)
        super().closeEvent(event)


def start_overlay():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    overlay = FishingOverlay()
    overlay.show()
    return app, overlay

if __name__ == "__main__":
    app, overlay = start_overlay()
    
    bridge = get_bridge()
    bridge.sig_log.emit("Core", "Клиент подключен к Majestic RP (2560x1440)", "info")
    bridge.sig_log.emit("Vision", "Калибровка зон (шкала, поплавок): [OK]", "info")
    bridge.sig_log.emit("Success", "Поклёвка! Подсечка [SPACE] (задержка 34ms)", "success")
    bridge.sig_log.emit("Catch", "Поймана: Форель радужная (3.8 кг)", "catch")
    bridge.sig_log.emit("Safety", "Анти-AFK: выполнено микродвижение камеры на 2°", "warn")
    bridge.sig_fish_updated.emit(15, 6, "take")
    bridge.sig_state_changed.emit("STATE_CAST", True, True)

    sys.exit(app.exec())
