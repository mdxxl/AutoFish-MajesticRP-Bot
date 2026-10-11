"""
Bot Bridge - Потокобезопасная связь между движком бота и интерфейсом оверлея PyQt6.
"""
from PyQt6.QtCore import QObject, pyqtSignal

class BotBridge(QObject):
    """
    Сигналы для передачи событий из рабочего потока бота в GUI оверлея.
    """
    # Лог-сообщение: tag, message, level
    sig_log = pyqtSignal(str, str, str)
    
    # Изменение состояния бота: state, is_running, game_active
    sig_state_changed = pyqtSignal(str, bool, bool)
    
    # Обновление статистики улова: caught_count, released_count, mode
    sig_fish_updated = pyqtSignal(int, int, str)
    
    # Обновление прогресса садка: current, max_capacity
    sig_progress_updated = pyqtSignal(int, int)
    
    # Телеметрия действия
    sig_telemetry = pyqtSignal(str)
    
    # Запросы от интерфейса к движку бота
    sig_request_toggle_running = pyqtSignal()
    sig_request_toggle_mode = pyqtSignal()
    sig_request_stop = pyqtSignal()

# Глобальный экземпляр моста
bridge: BotBridge | None = None

def get_bridge() -> BotBridge:
    global bridge
    if bridge is None:
        bridge = BotBridge()
    return bridge
