import asyncio
import os
import logging
from telegram.ext import Application

logger = logging.getLogger(__name__)

async def _watch_directory(app: Application, watch_dir: str, admin_ids: list):
    """Фоновая задача: отслеживает изменения в папке и отправляет файлы админам."""
    logger.info(f"🚀 Запуск _watch_directory с папкой {watch_dir}")
    seen_files = {}

    if os.path.exists(watch_dir):
        for file_name in os.listdir(watch_dir):
            file_path = os.path.join(watch_dir, file_name)
            if os.path.isfile(file_path):
                seen_files[file_name] = os.path.getmtime(file_path)
        logger.info(f"📁 Наблюдение за папкой начато. Существующих файлов: {len(seen_files)}")
    else:
        logger.warning(f"⚠️ Директория {watch_dir} пока не существует. Жду...")

    while True:
        await asyncio.sleep(5)
        if not os.path.exists(watch_dir):
            logger.warning(f"⚠️ Папка {watch_dir} исчезла, ждём восстановления...")
            continue

        current_files = os.listdir(watch_dir)

        for file_name in current_files:
            if (file_name.endswith((".swp", ".swo", ".swx")) or
                file_name.endswith("~") or
                file_name.startswith(".")):
                continue

            file_path = os.path.join(watch_dir, file_name)
            if os.path.isfile(file_path):
                try:
                    current_mtime = os.path.getmtime(file_path)
                except Exception as e:
                    logger.error(f"Ошибка получения mtime для {file_name}: {e}")
                    continue

                is_new = file_name not in seen_files
                is_modified = not is_new and current_mtime > seen_files[file_name]

                if is_new or is_modified:
                    action_text = "New file" if is_new else "Updated file"
                    logger.info(f"📄 Обнаружен {action_text}: {file_name} (mtime={current_mtime})")

                    for admin_id in admin_ids:
                        try:
                            with open(file_path, 'rb') as f:
                                await app.bot.send_document(
                                    chat_id=admin_id,
                                    document=f,
                                    caption=f"📄 {action_text} in lbl: {file_name}"
                                )
                            logger.info(f"✅ Успешно отправлен {file_name} админу ")
                        except Exception as e:
                            logger.error(f"❌ Ошибка при отправке файла {file_name} админу: {e}")

                    seen_files[file_name] = current_mtime
                    logger.info(f"🔄 Обновлён кеш для {file_name}")

def create_watcher_post_init(config: dict):
    """
    Возвращает функцию post_init для запуска наблюдателя.
    """
    watch_dir = config.get("WATCH_DIR", "/var/www/html/assets/texts/lbl/")
    raw_admin_ids = config.get("ADMIN_ID", [])

    if isinstance(raw_admin_ids, int):
        admin_ids = [raw_admin_ids]
    elif isinstance(raw_admin_ids, list):
        admin_ids = raw_admin_ids
    else:
        admin_ids = []

    if not admin_ids:
        logger.warning("⚠️ Наблюдатель не включён: ADMIN_ID не задан в конфиге.")
        async def noop(app: Application):
            logger.info("⏭️ Наблюдатель отключён (noop)")
        return noop

    logger.info("🔧 Создана функция post_init для наблюдателя")
    logger.info(f"📂 Папка наблюдения: {watch_dir}")
    logger.info(f"👥 Список админов: {admin_ids}")

    async def post_init(app: Application):
        logger.info("✅ Запуск наблюдателя за папкой...")
        asyncio.create_task(_watch_directory(app, watch_dir, admin_ids))
        logger.info("✅ Задача наблюдателя создана (запущена в фоне)")

    return post_init
