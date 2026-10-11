"""
Majestic RP Fishing Bot Launcher
Точка запуска рыболовного бота Majestic RP.
"""
import os
import sys

# Обеспечиваем корректные пути импорта
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

import main

if __name__ == "__main__":
    main.main()
