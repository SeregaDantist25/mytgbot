# -*- coding: utf-8 -*-
"""
Точка входа бота.

Содержит только:
- импорты
- конфигурацию (из config.py)
- инициализацию бота
- регистрацию обработчиков

Вся бизнес-логика вынесена в пакеты handlers/, services/, utils/.
"""

import os
import logging
import time
import threading

import telebot
from telebot import custom_filters

import bot_context
from config import Config, setup_logging

# --- Конфигурация ---
config = Config()
config.validate()

# --- Логирование ---
setup_logging(log_level=config.LOG_LEVEL, log_file=config.LOG_FILE)
logger = logging.getLogger(__name__)

# --- Бот ---
bot = telebot.TeleBot(config.BOT_TOKEN)
bot.add_custom_filter(custom_filters.StateFilter(bot))

# --- Заполняем общий контекст ---
bot_context.bot = bot
bot_context.ADMIN_IDS = config.ADMIN_IDS
bot_context.ENGINEER_CODE = config.ENGINEER_CODE

# --- Пути к файлам (для обратной совместимости) ---
TEMPLATES_DIR = config.TEMPLATES_DIR
DATA_DIR = config.DATA_DIR
CHECKLISTS_FILE = os.path.join(DATA_DIR, "checklists.json")
COUNTERS_FILE = os.path.join(DATA_DIR, "counters.json")
SHIPS_FILE = os.path.join(DATA_DIR, "ships.json")
COMPANIES_FILE = os.path.join(DATA_DIR, "companies.json")
COUNTERS_DB = os.path.join(DATA_DIR, "counters.db")
CHAT_STATE_FILE = os.path.join(DATA_DIR, "chat_state.json")

# ============================================================
#  ИМПОРТ ГОСТ ЧЕКЕРА И АЛИСЫ
# ============================================================

try:
    from gost_checker import GOSTChecker
    bot_context.gost_checker = GOSTChecker()
    logger.info(f"ГОСТ чекер загружен. Доступно ГОСТов: {len(bot_context.gost_checker.get_all_gosts())}")
except Exception as e:
    logger.warning(f"Ошибка при загрузке ГОСТ чекера: {e}")
    bot_context.gost_checker = None

# Пытаемся загрузить Алису (ai_router)
try:
    from ai.ai_router import router as alisa_router
    bot_context.alisa_router = alisa_router
    logger.info("Алиса (YandexGPT) загружена успешно!")
except ImportError as e:
    logger.warning(f"Модуль ai_router не найден: {e}")
except Exception as e:
    logger.warning(f"Ошибка при загрузке Алисы: {e}")

# Пытаемся загрузить создателя актов через Алису
try:
    from ai.alisa_act_creator import act_creator as alisa_act_creator
    bot_context.alisa_act_creator = alisa_act_creator
    logger.info("Создатель актов через Алису загружен!")
except ImportError as e:
    logger.warning(f"Модуль alisa_act_creator не найден: {e}")
except Exception as e:
    logger.warning(f"Ошибка при загрузке создателя актов: {e}")

# --- База данных насосов ---
from services.extra import pump_db
bot_context.pump_db = pump_db

# --- Новые модули для документооборота ---
try:
    import document_manager
    from handlers import repair_handlers
    bot_context.DOCUMENT_MANAGER_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Модули документооборота не загружены: {e}")
    bot_context.DOCUMENT_MANAGER_AVAILABLE = False

# ============================================================
#  РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ
# ============================================================

from handlers.registry import register_all_handlers

REGISTERED_HANDLER_GROUPS = register_all_handlers(
    bot,
    document_manager_available=bot_context.DOCUMENT_MANAGER_AVAILABLE,
)
logger.info("Зарегистрированы группы обработчиков: %s", REGISTERED_HANDLER_GROUPS)

# ============================================================
#  ЗАПУСК С ПОВТОРНЫМИ ПОПЫТКАМИ
# ============================================================

from services.catalog_service import load_ships
from models import init_models, sync_ships_from_json
import document_commands


def start_scan_timer():
    """Запускает периодическое сканирование папки repair_docs (раз в 12 часов)."""
    def _run():
        while True:
            time.sleep(12 * 60 * 60)  # 12 часов
            try:
                import scanner
                messages = scanner.scan_repair_docs()
                for m in messages:
                    logger.info(f"[SCAN] {m}")
                from handlers.message_handlers import notify_contracts_for_approval
                notify_contracts_for_approval()
            except Exception as e:
                logger.warning(f"[SCAN] Ошибка: {e}")
    t = threading.Thread(target=_run, daemon=True)
    t.start()


def start_bot_with_retry():
    """Запуск бота с повторными попытками подключения."""
    max_retries = 5
    retry_delay = 10

    for attempt in range(max_retries):
        try:
            logger.info(f"Попытка подключения {attempt + 1}/{max_retries}...")
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
            break
        except Exception as e:
            logger.warning(f"Ошибка: {e}")
            if attempt < max_retries - 1:
                logger.info(f"Повтор через {retry_delay} секунд...")
                time.sleep(retry_delay)
                retry_delay += 5
            else:
                logger.error("Не удалось подключиться после всех попыток")
                raise


if __name__ == '__main__':
    logger.info("Бот-ассистент запущен!")
    logger.info("Типы оборудования в базе: насосы (центробежные, шестерёнчатые, поршневые), двигатели")
    logger.info("Доступные функции: ДА, АВР, проверка зазоров, дефекты, нормативы, чек-лист")

    if bot_context.alisa_router and bot_context.alisa_router.is_configured():
        logger.info("Алиса (YandexGPT) активна — все запросы проходят через неё!")
    else:
        logger.warning("Алиса НЕ загружена — работаю в локальном режиме")

    if bot_context.alisa_act_creator and bot_context.alisa_act_creator.is_configured():
        logger.info("Создатель актов через Алису загружен!")
    else:
        logger.warning("Создатель актов через Алису НЕ загружен")

    if bot_context.gost_checker:
        gosts = bot_context.gost_checker.get_all_gosts()
        logger.info(f"Загружено ГОСТов: {len(gosts)}")
        if gosts:
            sections = {}
            for gost_id, data in gosts.items():
                section = data.get("section", "Общие")
                sections[section] = sections.get(section, 0) + 1
            logger.info(f"Разделы ГОСТов: {sections}")
    else:
        logger.warning("ГОСТ чекер не загружен")

    # Инициализация ORM и синхронизация судов
    init_models()
    ships_data = load_ships()
    if ships_data:
        sync_ships_from_json(ships_data)

    # Автозагрузка ремонтной ведомости «Славянская», если её ещё нет в БД
    if bot_context.DOCUMENT_MANAGER_AVAILABLE:
        try:
            import document_manager as dm
            slavyanskaya_src = os.path.join(
                "repair_docs", "_processed", "Ремведомость_Славянская осн..xlsx"
            )
            ok, msg = dm.ensure_repair_list_loaded("Славянская", slavyanskaya_src)
            if ok:
                logger.info(f"[AUTO] {msg}")
            else:
                logger.info(f"[AUTO] {msg}")
        except Exception as e:
            logger.warning(f"[AUTO] Ошибка автозагрузки ведомости: {e}")

    # Автоимпорт готовых актов дефектации из папки acts/
    if bot_context.DOCUMENT_MANAGER_AVAILABLE:
        try:
            import act_importer
            for m in act_importer.import_acts():
                logger.info(f"[ACTS] {m}")
        except Exception as e:
            logger.warning(f"[ACTS] Ошибка автоимпорта актов: {e}")

    # Регистрация команд управления документами
    from services.extra import handle_document_approve, handle_document_archive, handle_document_delete
    document_commands.register_document_commands(
        bot, bot_context.ADMIN_IDS,
        handle_document_approve,
        lambda document_id, user_id: handle_document_archive(
            document_id, user_id, bot_context.ADMIN_IDS
        ),
        lambda document_id, user_id: handle_document_delete(
            document_id, user_id, bot_context.ADMIN_IDS
        ),
    )

    # Регистрация команд управления заявками на ремонт
    import order_commands
    order_commands.register_order_commands(bot, bot_context.ADMIN_IDS)

    # Периодическое сканирование папки repair_docs
    start_scan_timer()

    # Запуск с повторными попытками
    start_bot_with_retry()
