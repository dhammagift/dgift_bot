# Standard Library
import json
import os
import asyncio
import logging
import re
import sys
import urllib.parse
import hashlib

# Telegram Core
from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    MenuButtonWebApp,
    WebAppInfo,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultsButton
)

# Telegram Extensions
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    TypeHandler,
    filters,
    CallbackContext,
)

from watcher import create_watcher_post_init
import geolocal
import dpdmini


# === Сообщения ===
WELCOME_MESSAGES = {
    "en": (
        "✨ Welcome to Dhamma Gift Bot!\n\n"
        "❓ <b>How to use:</b>\n\n"
        "💬 <b>Call me in any chat or group:</b>\n"
        "⌨️ Type @dgift_bot or @dhammagift_bot and start typing a word to search or sutta reference (e.g. <code>sn12.2</code>)\n\n"
        "💡 Suggestions will appear for Pali words and sutta references\n\n"
        "🤓 You can use Velthuis transliteration for diacritics: <code>.t .d .n ~n aa ii uu</code> → <code>ṭ ḍ ṇ ñ ā ī ū</code>\n\n"
        "💬 <b>In this private chat:</b>\n"
        "Simply send me a word or reference (e.g. <code>saariputta</code> or <code>mn10</code>)\n\n\n"
        "Following commands available:\n"
        "/start - this message\n"
        "/extra - Mini App links\n"
        "/uposatha - Uposatha days for the next 30 days (<code>/uposatha Colombo</code> for a city; inline: <code>@dgift_bot uposatha</code>)\n"
        "/help - Dhamma.gift help will be here\n\n"
        "Change Bots language 👇 Изменить язык \n"
    ),
    "ru": (
        "Добро пожаловать в Dhamma Gift Bot!\n\n"
        "🔍 <b>Как использовать:</b>\n\n"
        "💬 <b>Вы можете вызвать меня в любом чате или группе:</b>\n"
        "⌨️ Напишите @dgift_bot или @dhammagift_bot и начните печатать слово или номер сутты (например, <code>sn12.2</code>)\n"
        "💡 Я предложу варианты палийских слов и ссылок на сутты\n\n"
        "🤓 Также Вы можете использовать транслитерацию Velthuis для диакритики: <code>.t .d .n ~n aa ii uu</code> → <code>ṭ ḍ ṇ ñ ā ī ū</code>\n\n"
        "💬 <b>В этом личном чате:</b>\n"
        "Просто отправьте мне слово или номер сутты (например, <code>saariputta</code> или <code>mn10</code>)\n\n\n"
        "Доступны следующие команды:\n"
        "/start - это сообщение\n"
        "/extra - ссылки на Mini Apps\n"
        "/uposatha - дни Упосатхи на 30 дней (<code>/uposatha Москва</code> — для города; в инлайне: <code>@dgift_bot упосатха</code>)\n"
        "/help - здесь будет документация Dhamma.gift\n\n"
        "Изменить язык Бота 👇 Change Language\n"
    )
}

EXTRA_MESSAGES = {
    "ru": (
        "Мини Приложения на Русском. Вы можете закрепить это сообщение для быстрого доступа:\n\n"
        "🔎 Поиск\n"
        "http://t.me/dgift_bot/find\n"
        "📖 Чтение\n"
        "http://t.me/dgift_bot/read\n"
        "🌐 Словарь\n"
        "http://t.me/dgift_bot/dict\n\n"
    ),
    "en": (
        "Mini Applications in English. You may want to pin this message for quick access:\n\n"
        "🔎 Search\n"
        "http://t.me/dhammagift_bot/find\n"
        "📖 Read\n"
        "http://t.me/dhammagift_bot/read\n"
        "🌐 Dictionary\n"
        "http://t.me/dhammagift_bot/dict\n\n"
    )
}

# === Загрузка конфига ===
config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
with open(config_path, "r") as f:
    config = json.load(f)

bot_name = config.get("NAME", "default_bot")
TOKEN = config.get("TOKEN", "")
ADMIN_IDS = {int(x) for x in config.get("ADMIN_ID", []) if str(x).lstrip("-").isdigit()}

# === Логирование ===
class TelegramTokenFilter(logging.Formatter):
    @staticmethod
    def _mask_token(text: str) -> str:
        return re.sub(r'(https?://api\.telegram\.org)/bot[^/]+/', r'\1/botTOKEN/', text, flags=re.IGNORECASE)

    def format(self, record):
        original = super().format(record)
        return self._mask_token(original)

file_handler = logging.FileHandler(f"{bot_name}.log")
stream_handler = logging.StreamHandler()
formatter = TelegramTokenFilter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger(__name__)

# === Хранилище ===
USER_DATA_FILE = f"user_data_{bot_name}.json"
DEFAULT_LANG = "en"

def load_user_data() -> dict:
    if not os.path.exists(USER_DATA_FILE): return {}
    try:
        with open(USER_DATA_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e:
        logger.error(f"Error loading user_data: {e}")
        return {}

def save_user_data(user_id: int, key: str, value: str):
    try:
        data = load_user_data()
        user_id_str = str(user_id)
        if user_id_str not in data: data[user_id_str] = {}
        data[user_id_str][key] = value
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e: logger.error(f"Error saving user_data: {e}")

def get_user_lang(user_id: int) -> str:
    return load_user_data().get(str(user_id), {}).get("lang", DEFAULT_LANG)

def get_user_share_lang(user_id: int) -> str:
    data = load_user_data()
    return data.get(str(user_id), {}).get("share_lang", get_user_lang(user_id) or DEFAULT_LANG)

# === Обработка текста ===
def uniCoder(text):
    if not text: return text
    replacements = [("aa", "ā"), ("ii", "ī"), ("uu", "ū"), ('"n', "ṅ"), ("~n", "ñ"), (".t", "ṭ"), (".d", "ḍ"), (".n", "ṇ"), (".m", "ṃ"), (".l", "ḷ"), (".h", "ḥ")]
    for pattern, repl in replacements: text = text.replace(pattern, repl)
    return text

def normalize(text: str) -> str:
    if not text: return text
    if not hasattr(normalize, "cache"): normalize.cache = {}
    if text in normalize.cache: return normalize.cache[text]
    
    text_lower = text.lower()
    replacements = [("aa", "a"), ("ii", "i"), ("uu", "u"), ('"n', "n"), ("~n", "n"), (".t", "t"), (".d", "d"), (".n", "n"), (".m", "m"), (".l", "l"), (".h", "h")]
    for pattern, repl in replacements: text_lower = text_lower.replace(pattern, repl)
    
    result = (text_lower.replace("ṁ", "m").replace("ṃ", "m").replace("ṭ", "t").replace("ḍ", "d").replace("ṇ", "n").replace("ṅ", "n").replace("ñ", "n").replace("ā", "a").replace("ī", "i").replace("ū", "u").replace(".", " "))
    normalize.cache[text] = result
    return result

def get_link_query(text: str) -> str:
    """
    Логика сокращения ссылки:
    1. Если в первом блоке есть цифра или это исключение (bu-pm и т.д.):
       - Проверяем второй блок: если в нем есть цифры (номер сутты или диапазон),
         склеиваем первый и второй блок через точку (sn56 11 -> sn56.11).
       - Если во втором блоке нет цифр (просто текст), берем только первый блок (mn10 metta -> mn10).
    2. В остальных случаях возвращаем текст как есть.
    """
    if not text: return text
    parts = text.split()
    if len(parts) <= 1: return text
    
    first_block = parts[0]
    exceptions = {"bu-pm", "bi-pm", "pm", "bupm", "bipm"}
    
    has_digit = any(char.isdigit() for char in first_block)
    is_exception = first_block.lower() in exceptions
    
    if has_digit or is_exception:
        # Проверяем наличие второго блока и наличие цифр в нем (напр. "11", "1-10", "5a")
        if len(parts) > 1 and any(char.isdigit() for char in parts[1]):
            # Очищаем первый блок от возможной точки в конце и соединяем со вторым
            return f"{first_block.rstrip('.')}.{parts[1]}"
        
        # Если второй блок — это просто текст, возвращаем только первый блок
        return first_block
        
    return text


def autocomplete(prefix: str, max_results: int = 29) -> list[str]:
    try:
        if not hasattr(autocomplete, "word_data"): autocomplete.word_data = load_words()
        normalized_dict = autocomplete.word_data.get("normalized_dict", {})
        prefix_n = normalize(prefix)
        starts_with = [w for n, words in normalized_dict.items() if n.startswith(prefix_n) for w in words]
        contains = [w for n, words in normalized_dict.items() if prefix_n in n and not n.startswith(prefix_n) for w in words]
        suggestions = (sorted(list(set(starts_with)), key=lambda x: normalize(x)) + sorted(list(set(contains)), key=lambda x: normalize(x)))[:max_results]
        return suggestions
    except Exception as e:
        logger.error(f"Autocomplete error: {e}")
        return []

def load_words():
    try:
        path = os.path.join("assets", "sutta_words.txt")
        if not os.path.exists(path): return {"original_words": [], "normalized_dict": {}}
        with open(path, "r", encoding="utf-8") as f:
            words = [line.strip() for line in f if line.strip()]
            normalized_dict = {}
            for word in words:
                norm = normalize(word)
                normalized_dict.setdefault(norm, []).append(word)
            return {"original_words": words, "normalized_dict": normalized_dict}
    except Exception as e:
        logger.error(f"Dict load error: {e}")
        return {"original_words": [], "normalized_dict": {}}


# === Кэш для длинных запросов ===
QUERY_CACHE = {}

def get_query_id(text: str) -> str:
    if not text:
        return ""
    # Short text goes into callback_data as is (survives bot restarts); callback_data is limited to 64 bytes,
    # "inline_toggle_lang:ru:" takes 22. Longer text: stable 10-char hash (kept in memory only).
    if len(text.encode('utf-8')) <= 40:
        return text
    query_id = hashlib.md5(text.encode('utf-8')).hexdigest()[:10]
    QUERY_CACHE[query_id] = text
    
    # Предотвращаем бесконечное разрастание кэша
    if len(QUERY_CACHE) > 5000:
        # Удаляем старые записи
        for k in list(QUERY_CACHE.keys())[:1000]:
            del QUERY_CACHE[k]
            
    return query_id


# === Site links (clean paths: dhamma.gift/<word>, dict.dhamma.gift/<word>) ===
def site_url(q: str, lang: str) -> str:
    return f"https://dhamma.gift/{urllib.parse.quote(q)}{'?lang=ru' if lang == 'ru' else ''}"

def dict_url_for(q: str, lang: str) -> str:
    # ?silent: open the dictionary straight away, without flashing the home page
    return f"https://dict.dhamma.gift/{'ru/' if lang == 'ru' else ''}{urllib.parse.quote(q)}?silent"

# === Клавиатуры и Форматирование ===
def create_keyboard(original_query: str, lang: str = "en", is_inline: bool = False) -> InlineKeyboardMarkup:
    link_q = get_link_query(original_query)
    search_url = site_url(link_q, lang)
    dict_url = dict_url_for(link_q, lang)

    label_dict = "📘 Словарь" if lang == "ru" else "📘 Dictionary"
    label_site = f"{'Читать на' if lang == 'ru' else 'Read at'} 🔎 Dhamma.gift {'Ru' if lang == 'ru' else 'En'}"
    toggle_label = "Язык Ru/En" if lang == "ru" else "Lang En/Ru"

    callback_prefix = "inline_" if is_inline else ""
    
    # Получаем короткий ID вместо длинного текста
    query_id = get_query_id(original_query)
    
    keyboard = [
        [
            InlineKeyboardButton(text=toggle_label, callback_data=f"{callback_prefix}toggle_lang:{lang}:{query_id}"),
            InlineKeyboardButton(text=label_dict, url=dict_url),
        ],
        [InlineKeyboardButton(text=label_site, url=search_url)]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_message_with_links(display_text: str, link_query: str, lang: str = "en", meaning: str = "") -> str:
    # `meaning`: the short DPD meaning (HTML, see dpdmini.py), shown under the word when the word is in the mini dictionary
    if meaning:
        display_text = f"{display_text}\n\n{meaning}"
    search_url = site_url(link_query, lang)
    dict_url = dict_url_for(link_query, lang)
    label_dict = "📘 Словарь" if lang == "ru" else "📘 Dictionary"
    return f"\n{display_text}\n\n🔎 <a href='{search_url}'>Dhamma.gift</a> | <a href='{dict_url}'>{label_dict}</a>"

# === Обработчики ===
async def set_menu_button(update: Update, lang: str):
    user_id = update.effective_user.id
    button_text = "DG ru" if lang == "ru" else "DG en"
    button_url = f"https://dhamma.gift/?{'lang=ru&' if lang == 'ru' else ''}source=pwa"
    try:
        await update.get_bot().set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonWebApp(text=button_text, web_app=WebAppInfo(url=button_url)))
    except: pass

async def start(update: Update, context: CallbackContext):
    user_lang = get_user_lang(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("Русский" if user_lang == 'en' else "English", callback_data=f"lang_set:{user_lang}")]]
    await update.message.reply_text(WELCOME_MESSAGES[user_lang], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML", disable_web_page_preview=True)
    await set_menu_button(update, user_lang)

async def handle_language_selection(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    new_lang = 'ru' if query.data.split(':')[1] == 'en' else 'en'
    save_user_data(query.from_user.id, 'lang', new_lang)
    save_user_data(query.from_user.id, 'share_lang', new_lang)
    keyboard = [[InlineKeyboardButton("Русский" if new_lang == 'en' else "English", callback_data=f"lang_set:{new_lang}")]]
    await query.edit_message_text(text=WELCOME_MESSAGES[new_lang], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    await set_menu_button(update, new_lang)

def language_keyboard(lang: str):
    # the current language is marked with a check; a tap sets exactly that language (not a toggle)
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(("✓ " if lang == "en" else "") + "English", callback_data="setlang:en"),
        InlineKeyboardButton(("✓ " if lang == "ru" else "") + "Русский", callback_data="setlang:ru"),
    ]])

LANGUAGE_TEXT = {"en": "Interface language:", "ru": "Язык интерфейса:"}

async def language_command(update: Update, context: CallbackContext):
    lang = get_user_lang(update.effective_user.id)
    await update.effective_message.reply_text(LANGUAGE_TEXT[lang], reply_markup=language_keyboard(lang))

async def handle_setlang(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    new_lang = query.data.split(':')[1]
    if new_lang not in ("en", "ru"):
        return
    save_user_data(query.from_user.id, 'lang', new_lang)
    save_user_data(query.from_user.id, 'share_lang', new_lang)
    try:
        await query.edit_message_text(text=LANGUAGE_TEXT[new_lang], reply_markup=language_keyboard(new_lang))
    except Exception:
        pass  # "message is not modified": the same language was tapped again
    await set_menu_button(update, new_lang)

async def extra_command(update: Update, context: CallbackContext):
    lang = get_user_lang(update.effective_user.id)
    keyboard = [[InlineKeyboardButton("English" if lang == "ru" else "Русский", callback_data=f"extra_toggle:{lang}")]]
    await update.message.reply_text(EXTRA_MESSAGES[lang], reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def handle_extra_toggle(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    new_lang = 'en' if query.data.split(':')[1] == 'ru' else 'ru'
    save_user_data(query.from_user.id, 'lang', new_lang)
    keyboard = [[InlineKeyboardButton("English" if new_lang == "ru" else "Русский", callback_data=f"extra_toggle:{new_lang}")]]
    await query.edit_message_text(text=EXTRA_MESSAGES[new_lang], reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

# === Uposatha schedule as plain text (engine: dg-node-prod uposatha-core.js via upo.js) ===
UPO_WORDS = {"uposatha", "упосатха", "упосатхи", "упосатху"}
UPO_DEFAULT_TZ = "Asia/Kolkata"  # Bodh Gaya; without a city the day runs 18:00 to 18:00
UPO_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upo_cache.json")
GEO_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo_cache.json")
GEO_CACHE_VERSION = 3  # bump it when the labels change: the cache lives on disk and has no expiry
# Which geocoder answers: "online" is the Open-Meteo API, "offline" the 34k cities kept in geo/ (instant,
# no network, tolerates typos, but holds ~90 MB). Switched with /geo, remembered in geo_mode.txt; the file
# wins over the GEO_MODE environment variable.
GEO_MODE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geo_mode.txt")

def geo_mode() -> str:
    try:
        with open(GEO_MODE_FILE, encoding="utf-8") as f:
            mode = f.read().strip().lower()
        if mode in ("online", "offline"):
            return mode
    except OSError:
        pass
    return "offline" if os.environ.get("GEO_MODE", "").strip().lower() == "offline" else "online"

def set_geo_mode(mode: str):
    with open(GEO_MODE_FILE, "w", encoding="utf-8") as f:
        f.write(mode + "\n")
    if mode == "online":
        geolocal.unload()  # the point of the switch: the cities go back to the OS

def _cache_read(path: str) -> dict:
    """Both caches outlive a restart: the first query for a city after a deploy should not wait again."""
    try:
        with open(path, encoding="utf-8") as f:
            return {tuple(k): v for k, v in json.load(f)}
    except Exception:
        return {}

def _cache_write(path: str, cache: dict, keep: int):
    try:
        if len(cache) > keep:
            for k in sorted(cache, key=lambda k: cache[k][0] if isinstance(cache[k], list) and cache[k] and isinstance(cache[k][0], (int, float)) else 0)[:len(cache) - keep]:
                cache.pop(k, None)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([[list(k), v] for k, v in cache.items()], f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.error(f"cache write failed for {path}: {e}")

_upo_cache = _cache_read(UPO_CACHE_FILE)
_geo_cache = _cache_read(GEO_CACHE_FILE)

def _fetch_json(url: str):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "dgift-bot"})
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)

async def geocode(name: str, lang: str) -> list:
    """City candidates {label, lat, lon, tz}. Offline: the local GeoNames dump (instant, no network, typos
    tolerated — see geolocal.py). Online: the Open-Meteo API. So far the API is what a missing local answer
    falls back to either way."""
    import asyncio
    key = (name.lower(), lang, GEO_CACHE_VERSION)
    if key in _geo_cache:
        return _geo_cache[key]
    found = geolocal.search(name, lang) if geo_mode() == "offline" else []
    if not found:
        found = await _geocode_request(name, _geo_lang(name, lang))
        if not found:
            # The wrong guess for the language of the name finds nothing at all ("алматы" asked for in English
            # is an empty answer, not a bad one): one retry in the other language covers mixed input.
            found = await _geocode_request(name, "en" if _geo_lang(name, lang) == "ru" else "ru")
    _geo_cache[key] = found
    _cache_write(GEO_CACHE_FILE, _geo_cache, 500)
    return found

def _geo_lang(name: str, lang: str) -> str:
    """Open-Meteo searches the names of the language it is asked for, so a Cyrillic city must be asked for
    in Russian: «алматы» with language=en returns nothing while language=ru returns Алматы."""
    return "ru" if re.search(r"[А-Яа-яЁёІіЇїЄєҐґ]", name) else lang

async def _geocode_request(name: str, lang: str) -> list:
    import asyncio
    url = "https://geocoding-api.open-meteo.com/v1/search?count=3&format=json&language=%s&name=%s" % (lang, urllib.parse.quote(name))
    try:
        data = await asyncio.to_thread(_fetch_json, url)
    except Exception as e:
        logger.error(f"geocode failed: {e}")
        return []
    return [{"label": ", ".join(dict.fromkeys(x for x in (g.get("name"), g.get("admin1"), g.get("country")) if x)),  # drops repeats like "Алматы, Алматы"
             "id": g.get("id"), "lat": g["latitude"], "lon": g["longitude"], "tz": g.get("timezone", "UTC")}
            for g in data.get("results", [])]

async def uposatha_text(lang: str, place: dict = None) -> str:
    import asyncio, time
    # The schedule is cached for an hour, and the key carries the mtimes of what produces it — the script and the engine
    # it requires (_upo_mtime): editing either (a new layout, another column, a new rule for the key days) must not keep
    # serving the text it produced before the edit. That is why "не поменялось": the cache outlived the change.
    key = (lang, place["label"] if place else None, _upo_mtime())
    hit = _upo_cache.get(key)
    if hit and time.time() - hit[0] < 3600:
        return hit[1]
    args = [lang, place["tz"] if place else UPO_DEFAULT_TZ, "30"]
    if place:
        args += [str(place["lat"]), str(place["lon"]), place["label"]]
    proc = await asyncio.create_subprocess_exec(
        "node", UPO_JS, *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    text = out.decode().strip()
    if text:
        _upo_cache[key] = (time.time(), text)
        _cache_write(UPO_CACHE_FILE, _upo_cache, 200)
    return text

UPO_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upo.js")
# The engine upo.js requires (the same file the site and the apps use): it decides the days, so its mtime belongs in the
# cache key as much as the script's — an edit there left the old schedule served for the rest of the hour.
UPO_CORE = "/var/www/dg-node-prod/public/overrides/js/uposatha-core.js"

def _upo_mtime() -> float:
    stamps = []
    for f in (UPO_JS, UPO_CORE):
        try:
            stamps.append(os.path.getmtime(f))
        except OSError:
            pass
    return max(stamps) if stamps else 0

async def _uposatha_prewarm():
    # Offline mode reads the 34k cities once, here, so that the first query does not pay for the load.
    if geo_mode() == "offline":
        await asyncio.to_thread(geolocal.load)
    for lang in ("ru", "en"):
        try:
            await uposatha_text(lang)
        except Exception as e:
            logger.error(f"uposatha prewarm failed: {e}")

async def geo_command(update: Update, context: CallbackContext):
    """Admin only: which geocoder answers. /geo offline — the 34k cities from geo/ in RAM; /geo online — the
    Open-Meteo API, and the city names go back to the OS."""
    if update.effective_user.id not in ADMIN_IDS:
        return
    arg = context.args[0].strip().lower() if context.args else ""
    if arg in ("online", "api", "онлайн"):
        set_geo_mode("online")
    elif arg in ("offline", "local", "офлайн"):
        set_geo_mode("offline")
        await asyncio.to_thread(geolocal.load)
    elif arg:
        await update.message.reply_text("Использование: /geo online | /geo offline")
        return
    try:
        with open("/proc/self/status") as f:
            rss = int(next(l.split()[1] for l in f if l.startswith("VmRSS"))) // 1024
    except Exception:
        rss = 0
    await update.message.reply_text(
        f"Геокодер: {'офлайн (локальные города)' if geo_mode() == 'offline' else 'онлайн (Open-Meteo)'}\n"
        f"Города в памяти: {'да' if geolocal.loaded() else 'нет'} · RSS {rss} МБ")

_place_labels = {}  # "lat,lon" -> label, so the language button can rebuild the header
_place_ids = {}  # "lat,lon" -> Open-Meteo id, to name the same city in the other language
_inline_seq = {}    # user_id -> number of the latest inline query, so a superseded keystroke can stop

def _inline_touch(user_id: int) -> int:
    seq = _inline_seq.get(user_id, 0) + 1
    _inline_seq[user_id] = seq
    return seq

def _inline_stale(user_id: int, seq: int) -> bool:
    return _inline_seq.get(user_id) != seq

def upo_keyboard(lang: str, place: dict = None) -> InlineKeyboardMarkup:
    """Ru/En switch (callback_data, <=64 bytes, carries the place) and the calendar link: the link lives on a button, not in the text."""
    where = "-"
    if place:
        where = f"{round(place['lat'], 2)},{round(place['lon'], 2)},{place['tz']}"
        _place_labels[where.rsplit(",", 1)[0]] = place["label"]
        if place.get("id"):
            _place_ids[where.rsplit(",", 1)[0]] = place["id"]
    label = "Язык Ru/En" if lang == "ru" else "Lang En/Ru"
    new_lang = "en" if lang == "ru" else "ru"
    cal_label = "📅 Календарь упосатх" if lang == "ru" else "📅 Uposatha calendar"
    cal_url = "https://dhamma.gift/uposatha-calendar" + ("?lang=ru" if lang == "ru" else "")
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"upo:{new_lang}:{where}"),
        InlineKeyboardButton(cal_label, url=cal_url),
    ]])

async def upo_toggle(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    _, lang, where = query.data.split(":", 2)
    place = None
    if where != "-":
        lat, lon, tz = where.split(",", 2)
        place = {"lat": float(lat), "lon": float(lon), "tz": tz, "label": _place_labels.get(f"{lat},{lon}", tz)}
    if place and _place_ids.get(where.rsplit(",", 1)[0]):
        # The saved label is in the language it was found in: ask Open-Meteo for the same place by id in the new one.
        try:
            g = await asyncio.to_thread(_fetch_json, "https://geocoding-api.open-meteo.com/v1/get?id=%s&language=%s" % (_place_ids[where.rsplit(",", 1)[0]], lang))
            place["label"] = ", ".join(dict.fromkeys(x for x in (g.get("name"), g.get("admin1"), g.get("country")) if x))
        except Exception as e:
            logger.error(f"place relabel failed: {e}")
    text = await uposatha_text(lang, place)
    await query.edit_message_text(text=text, reply_markup=upo_keyboard(lang, place), parse_mode="HTML", disable_web_page_preview=True)

def saved_place(user_id: int):
    """The city the inline query falls back to (it is not used by the command: "/uposatha" without an argument
    is the common list, not somebody's last city)."""
    raw = load_user_data().get(str(user_id), {}).get("city")
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None

RESET_WORDS = ("reset", "-", "сброс")

async def uposatha_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    lang = get_user_share_lang(user_id)
    ru = lang == "ru"
    name = " ".join(context.args).strip()
    # "/uposatha" without an argument keeps showing the city saved earlier (the same one the inline falls back
    # to); "/uposatha <city>" saves a new one, and the reset is spelled out — "/uposatha reset", not a dash
    # nobody reads as a command.
    place = None
    if name.lower() in RESET_WORDS:
        save_user_data(user_id, "city", "")
        note = ("Сохранённый город сброшен · показываю Бодхгаю" if ru
                else "Saved city cleared · showing Bodh Gaya")
    elif name:
        found = await geocode(name, lang)
        if not found:
            await update.message.reply_text("Город не найден 🤷" if ru else "City not found 🤷")
            return
        place = found[0]
        save_user_data(user_id, "city", json.dumps(place, ensure_ascii=False))
        note = (f"{place['label']} — сохранённый город · /uposatha reset — сбросить" if ru
                else f"{place['label']} — saved city · /uposatha reset to clear it")
    else:
        place = saved_place(user_id)
        note = ((f"{place['label']} — сохранённый город · /uposatha reset — сбросить" if ru
                 else f"{place['label']} — saved city · /uposatha reset to clear it") if place
                else ("/uposatha &lt;город&gt; — расписание для города" if ru
                      else "/uposatha &lt;city&gt; — the schedule for a city"))
    text = await uposatha_text(lang, place)
    await update.message.reply_text((text or "—") + "\n\n" + note, reply_markup=upo_keyboard(lang, place), parse_mode="HTML", disable_web_page_preview=True)

async def inline_query(update: Update, context: CallbackContext):
    query_text = update.inline_query.query.strip()
    logger.info(f"inline query from {update.inline_query.from_user.id}: {query_text!r}")
    user_id = update.inline_query.from_user.id
    
    # Получаем настройки языка
    interface_lang = get_user_lang(user_id)
    share_lang = get_user_share_lang(user_id)
    
    # 1. Сначала преобразуем ввод (pa.ticca -> paṭicca)
    display_text = uniCoder(query_text)
    
    # 2. Генерируем "чистый" запрос для ссылки (mn2 sabbasava -> mn2)
    link_q = get_link_query(display_text)
    
    # Формируем текст кнопки WebApp
    action_text = "Открыть Dhamma.gift Ru" if share_lang == "ru" else "Open Dhamma.gift En"
    btn_text = f"🔎 {action_text}: {link_q}" if query_text else f"🔎 {action_text}"
    
    # Формируем URL для WebApp
    final_url = site_url(link_q if query_text else "", share_lang)
    
    hot_button = InlineQueryResultsButton(text=btn_text, web_app=WebAppInfo(url=final_url))
    results = []

    # Uposatha: empty query, or "uposatha [city]" (the Pali word keeps working below as a normal search)
    word, _, city = query_text.partition(" ")
    if not query_text or word.lower() in UPO_WORDS:
        ru = share_lang == "ru"
        city = " ".join(city.split())  # "chiang  mai " -> "chiang mai"
        # An inline query arrives on every keystroke. Give each one a number, and let a superseded one stop
        # before the (slow) schedule is computed and before it answers: the last keystroke is the one the
        # person is waiting for.
        seq = _inline_touch(user_id)
        # No city typed: the inline falls back to the city the person saved with "/uposatha <city>", or Bodh Gaya.
        places = await geocode(city, share_lang) if city else [saved_place(user_id)]
        if _inline_stale(user_id, seq):
            return
        if city and not places:
            results.append(InlineQueryResultArticle(
                id="uposatha_nocity",
                title=f"Город не найден: «{city}»" if ru else f"City not found: “{city}”",
                description=("Проверьте написание, например «упосатха Чиангмай»" if ru else "Check the spelling, e.g. «uposatha Chiang Mai»"),
                input_message_content=InputTextMessageContent(
                    (f"🌗 Город «{city}» не найден. Проверьте написание, например: «упосатха Чиангмай»." if ru
                     else f"🌗 City “{city}” not found. Check the spelling, e.g. «uposatha Chiang Mai».")),
            ))
        else:
            # All the candidates at once: one node run each, and they cost the same wall time together as one
            texts = await asyncio.gather(*[uposatha_text(share_lang, p) for p in places])
            if _inline_stale(user_id, seq):
                return
            for i, (place, upo) in enumerate(zip(places, texts)):
                if not upo:
                    continue
                where = f" — {place['label']}" if place else ""
                results.append(InlineQueryResultArticle(
                    id=f"uposatha_{i}",
                    # no emoji in the title: Telegram would draw it again as the item's thumbnail (two moons)
                    title=("Дни Упосатхи на 30 дней" if ru else "Uposatha days, next 30 days") + where,
                    description=(("Бодхгая, 18:00→18:00 · свой город: «упосатха Алматы»" if ru else "Bodh Gaya, 18:00 to 18:00 · your city: «uposatha Almaty»")
                                 if not place else ("Отправить расписание в чат" if ru else "Send the schedule to the chat")),
                    input_message_content=InputTextMessageContent(upo, parse_mode="HTML", disable_web_page_preview=True),
                    reply_markup=upo_keyboard(share_lang, place),
                ))

    if query_text:
        suggestions = autocomplete(query_text)
        
        # === Результат 1: То, что ввел пользователь ===
        results.append(InlineQueryResultArticle(
            id="user_input",
            title=f"✏️ Send: {display_text}" if interface_lang == "en" else f"✏️ Отправить: {display_text}",
            input_message_content=InputTextMessageContent(
                # В сообщение вставляем полный текст, но ссылки формируем на основе короткого link_q
                format_message_with_links(display_text, link_q, lang=share_lang, meaning=dpdmini.meaning(display_text, share_lang)), 
                parse_mode="HTML", 
                disable_web_page_preview=True
            ),
            # ВАЖНО: Сюда передаем display_text (полный), чтобы кнопка "Язык" запомнила полное название.
            # Внутри create_keyboard сама вызовет get_link_query для URL-кнопок.
            reply_markup=create_keyboard(display_text, lang=share_lang, is_inline=True)
        ))
        
        # === Результат 2+: Подсказки из словаря ===
        for idx, word in enumerate(suggestions):
            word_link_q = get_link_query(word)
            word_meaning = dpdmini.meaning(word, share_lang)
            results.append(InlineQueryResultArticle(
                id=f"dict_{idx}", 
                title=word,
                description=re.sub(r"<[^>]+>", "", word_meaning).replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").split("\n")[0].split(" — ", 1)[-1][:100] or None,  # the headword is the title already
                input_message_content=InputTextMessageContent(
                    format_message_with_links(word, word_link_q, lang=share_lang, meaning=word_meaning), 
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                ),
                # Здесь тоже передаем полное слово 'word'
                reply_markup=create_keyboard(word, lang=share_lang, is_inline=True)
            ))
    
    await update.inline_query.answer(results, button=hot_button, cache_time=0, is_personal=True)

async def handle_message(update: Update, context: CallbackContext):
    if not update.message or not update.message.text: return
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if update.message.via_bot and update.message.via_bot.username in ["dgift_bot", "dhammagift_bot"]: return
    if re.search(r'http[s]?://', text):
        await update.message.reply_text("Пожалуйста, пришлите текст без URL." if get_user_lang(user_id) == "ru" else "Please send text without URLs.")
        return

    share_lang = get_user_share_lang(user_id)
    display_text = uniCoder(text)
    link_q = get_link_query(text)
    
    await update.message.reply_text(
        format_message_with_links(display_text, link_q, lang=share_lang, meaning=dpdmini.meaning(display_text, share_lang)), 
        reply_markup=create_keyboard(text, lang=share_lang), 
        parse_mode="HTML", 
        disable_web_page_preview=True
    )

async def toggle_language(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    parts = query.data.split(':')
    is_inline = parts[0] == 'inline_toggle_lang'
    new_lang = 'ru' if parts[1] == 'en' else 'en'
    
    # Получаем ID из callback_data
    query_id = ':'.join(parts[2:])
    
    # Достаем оригинальный текст из кэша. Если произошел перезапуск бота (кэш пуст), 
    # используем сам query_id в качестве фоллбека.
    original_text = QUERY_CACHE.get(query_id, query_id)
    
    save_user_data(query.from_user.id, 'share_lang', new_lang)
    save_user_data(query.from_user.id, 'lang', new_lang)
    
    display_text = uniCoder(original_text)
    link_q = get_link_query(original_text)
    
    await query.edit_message_text(
        text=format_message_with_links(display_text, link_q, lang=new_lang, meaning=dpdmini.meaning(display_text, new_lang)), 
        reply_markup=create_keyboard(original_text, lang=new_lang, is_inline=is_inline), 
        parse_mode="HTML", 
        disable_web_page_preview=True
    )

def main():
    os.makedirs("assets", exist_ok=True)

    watcher_init = create_watcher_post_init(config)

    async def post_init(app):
        # Command menu, so everyone sees that the Uposatha mode exists
        from telegram import BotCommand
        for lang_code, cmds in (
            (None, [("start", "Start"), ("language", "Language"), ("extra", "Mini Apps"), ("uposatha", "Uposatha days, next 30 days")]),
            ("ru", [("start", "Начать"), ("language", "Язык"), ("extra", "Мини-приложения"), ("uposatha", "Дни Упосатхи на 30 дней")]),
        ):
            try:
                await app.bot.set_my_commands([BotCommand(c, d) for c, d in cmds], language_code=lang_code)
            except Exception as e:
                logger.error(f"set_my_commands failed: {e}")
        await watcher_init(app)
        # The list the empty inline query and /uposatha show, in both languages, computed now: nobody should
        # pay for the astronomy in the first second after a deploy.
        asyncio.create_task(_uposatha_prewarm())

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    async def log_update(update: Update, context: CallbackContext):  # debug: which update types reach the bot
        kinds = [k for k in ("message", "inline_query", "chosen_inline_result", "callback_query") if getattr(update, k, None)]
        if kinds != ["inline_query"]:
            logger.info(f"update kinds: {kinds}")
        if update.callback_query:
            logger.info(f"callback_query data={update.callback_query.data!r} inline={bool(update.callback_query.inline_message_id)}")
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("extra", extra_command))
    app.add_handler(CommandHandler("uposatha", uposatha_command))
    app.add_handler(CommandHandler("geo", geo_command))
    app.add_handler(CallbackQueryHandler(handle_language_selection, pattern="^lang_set:"))
    app.add_handler(CallbackQueryHandler(handle_setlang, pattern=r"^setlang:"))
    app.add_handler(CallbackQueryHandler(handle_extra_toggle, pattern=r"^extra_toggle:"))
    app.add_handler(CallbackQueryHandler(upo_toggle, pattern=r"^upo:"))
    app.add_handler(CallbackQueryHandler(toggle_language, pattern=r"^(inline_)?toggle_lang:"))
    app.add_handler(InlineQueryHandler(inline_query))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(allowed_updates=Update.ALL_TYPES)  # explicit: callback_query must never be filtered out

if __name__ == "__main__":
    main()

