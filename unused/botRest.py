import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Путь к файлу, который нужно отслеживать
FILE_TO_WATCH = "/var/www/telegram_bot/bot.py"

# Команда для запуска бота
BOT_COMMAND = ["python3", FILE_TO_WATCH]

class BotRestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = subprocess.Popen(BOT_COMMAND)  # Запускаем бота при старте

    def on_modified(self, event):
        if event.src_path == FILE_TO_WATCH:
            print(f"Файл {FILE_TO_WATCH} изменен. Перезапуск бота...")
            self.process.terminate()  # Останавливаем текущий процесс
            self.process = subprocess.Popen(BOT_COMMAND)  # Перезапускаем бота

if __name__ == "__main__":
    event_handler = BotRestartHandler()
    observer = Observer()
    observer.schedule(event_handler, path="/var/www/telegram_bot", recursive=False)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
