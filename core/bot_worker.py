"""
Bot Worker Thread - Поток для независимой работы логики бота параллельно с Qt GUI.
"""
import sys
import threading
from PyQt6.QtCore import QThread, pyqtSlot

from bot_bridge import get_bridge

class BotWorkerThread(QThread):
    def __init__(self, bot_runner_func):
        super().__init__()
        self.bot_runner_func = bot_runner_func
        self.bridge = get_bridge()
        self._stop_event = threading.Event()

    def run(self):
        try:
            self.bot_runner_func(bridge=self.bridge, stop_event=self._stop_event)
        except Exception as e:
            self.bridge.sig_log.emit("System", f"Ошибка в потоке бота: {e}", "warn")

    def stop(self):
        self._stop_event.set()
        self.wait(2000)
