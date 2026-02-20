import logging
import asyncio
import random
import aiosqlite
import time
import requests
import json
from datetime import datetime
from typing import Dict, Any, Union

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from aiocryptopay import AioCryptoPay

# ⚙️ КОНФИГУРАЦИЯ
BOT_TOKEN = "8295201485:AAGFxmaC584b75hJrTFAMukvXs7da3L7hAE"
CRYPTO_PAY_TOKEN = "514479:AAb64Swo8pexGV3iVkgI4MqdlYYsg22BhOZ"

# ❗ ВАЖНО: ID админов (числа).
ADMIN_IDS = [
    8119723042, 
    8448843727
]

MIN_BET = 0.1
MIN_DEPOSIT = 0.1
MIN_WITHDRAW = 1.0
BONUS_AMOUNT = 0.05
REFERRAL_REWARD = 0.1
REQUIRED_BIO_TEXT = "@Andcasino_bot_bot лучший бот для игр на $ с шансом 80% победы"

# --- ИМЯ БАЗЫ ---
DB_NAME = "andron_casino.db"

# Дефолтные настройки для мин
DEFAULT_MINES_CONFIG = {
    "1": 0.90, "3": 0.90, "5": 0.85, "8": 0.80,
    "10": 0.75, "15": 0.70, "20": 0.60, "24": 0.50
}

# Глобальные настройки (загружаются из БД)
GAME_CONFIG = {
    "dice_win": 1.8,       
    "dice_draw": 0.93,     
    "mines_config": DEFAULT_MINES_CONFIG.copy() 
}

# Словарь ключей для картинок
IMAGE_KEYS = {
    "start": "🏠 Главное меню (Приветствие)",
    "profile": "👤 Профиль",
    "wallet": "💳 Кошелек",
    "refs": "🤝 Рефералы",
    "bonus": "🎁 Бонус",
    "help": "ℹ️ Помощь",
    "rules": "📜 Правила",
    "games_menu": "🎮 Меню выбора игр",
    "game_mines": "💣 Игра: Мины (Заставка)",
    "game_dice": "🎲 Игра: Кубик/Дартс (Заставка)",
    "game_sport": "⚽ Игра: Спорт (Заставка)",
    "res_win": "🏆 Результат: Победа",
    "res_lose": "💀 Результат: Проигрыш",
    "res_draw": "⚖️ Результат: Ничья"
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
crypto = AioCryptoPay(token=CRYPTO_PAY_TOKEN)
dp = Dispatcher()

# --- ФУНКЦИИ ДЛЯ РАБОТЫ С CRYPTOBOT API ---
CRYPTO_API_URL = "https://pay.crypt.bot/api/"
CRYPTO_HEADERS = {
    "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN,
    "Content-Type": "application/json"
}

async def create_crypto_check(amount: float):
    """Создать чек (выплата) через CryptoBot API"""
    url = f"{CRYPTO_API_URL}createCheck"
    payload = {"asset": "USDT", "amount": str(amount)}
    try:
        response = requests.post(url, headers=CRYPTO_HEADERS, json=payload)
        res = response.json()
        if res.get("ok"):
            return {
                "success": True,
                "check_url": res["result"]["bot_check_url"],
                "check_id": res["result"].get("check_id")
            }
        else:
            return {"success": False, "error": str(res.get("error", "Unknown error"))}
    except Exception as e:
        return {"success": False, "error": str(e)}

# --- СОСТОЯНИЯ ---
class States(StatesGroup):
    waiting_for_captcha = State()
    waiting_for_bet = State()
    waiting_for_mines_count = State()
    waiting_for_turn = State()
    waiting_for_withdraw = State()
    waiting_for_deposit = State()
    admin_giving_balance = State()
    admin_manage_ban = State()
    admin_set_dice_win = State()
    admin_set_dice_draw = State()
    admin_set_mines_specific = State()
    admin_upload_photo = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, 
                username TEXT, 
                balance REAL DEFAULT 0.0,
                last_bonus INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_verified INTEGER DEFAULT 0,
                referrer_id INTEGER DEFAULT 0,
                referral_paid INTEGER DEFAULT 0,
                total_deposited REAL DEFAULT 0.0,
                total_withdrawn REAL DEFAULT 0.0,
                total_bets REAL DEFAULT 0.0,
                created_at INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT, 
                amount REAL,
                status TEXT DEFAULT 'pending', 
                invoice_id TEXT,
                check_id TEXT,
                created_at INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY,
                dice_win REAL DEFAULT 1.8,
                dice_draw REAL DEFAULT 0.93,
                mines_config TEXT
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS images (
                key_name TEXT PRIMARY KEY,
                file_id TEXT
            )
        """)

        async with db.execute("PRAGMA table_info(settings)") as cursor:
            columns = [col[1] for col in await cursor.fetchall()]
            if 'mines_config' not in columns:
                await db.execute("ALTER TABLE settings ADD COLUMN mines_config TEXT")

        cursor = await db.execute("SELECT COUNT(*) FROM settings")
        if (await cursor.fetchone())[0] == 0:
             await db.execute("INSERT INTO settings (id, dice_win, dice_draw, mines_config) VALUES (1, 1.8, 0.93, ?)", (json.dumps(DEFAULT_MINES_CONFIG),))
        else:
            cursor = await db.execute("SELECT mines_config FROM settings WHERE id = 1")
            row = await cursor.fetchone()
            if row and not row[0]:
                 await db.execute("UPDATE settings SET mines_config = ? WHERE id = 1", (json.dumps(DEFAULT_MINES_CONFIG),))
        
        await db.commit()

async def update_db_schema():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("PRAGMA table_info(users)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]
        required_columns = [
            ('total_bets', 'REAL DEFAULT 0.0'), ('games_played', 'INTEGER DEFAULT 0'),
            ('total_deposited', 'REAL DEFAULT 0.0'), ('total_withdrawn', 'REAL DEFAULT 0.0'),
            ('referral_paid', 'INTEGER DEFAULT 0'), ('referrer_id', 'INTEGER DEFAULT 0'),
            ('created_at', 'INTEGER DEFAULT 0')
        ]
        for column_name, column_type in required_columns:
            if column_name not in column_names:
                await db.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
        await db.commit()

async def load_settings():
    global GAME_CONFIG
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT dice_win, dice_draw, mines_config FROM settings WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            if row:
                GAME_CONFIG["dice_win"] = row[0]
                GAME_CONFIG["dice_draw"] = row[1]
                if row[2]:
                    try: GAME_CONFIG["mines_config"] = json.loads(row[2])
                    except: GAME_CONFIG["mines_config"] = DEFAULT_MINES_CONFIG.copy()
                else: GAME_CONFIG["mines_config"] = DEFAULT_MINES_CONFIG.copy()

async def save_setting(key, value):
    global GAME_CONFIG
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(f"UPDATE settings SET {key} = ? WHERE id = 1", (value,))
        await db.commit()
    GAME_CONFIG[key] = value

async def save_mines_config(new_config):
    global GAME_CONFIG
    json_str = json.dumps(new_config)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE settings SET mines_config = ? WHERE id = 1", (json_str,))
        await db.commit()
    GAME_CONFIG["mines_config"] = new_config

async def get_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            columns = [column[0] for column in cursor.description]
            row = await cursor.fetchone()
            if row:
                user_dict = {}
                for i, column in enumerate(columns):
                    user_dict[column] = row[i]
                return user_dict
            return None

async def update_total_bets(user_id, bet_amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET total_bets = total_bets + ? WHERE user_id = ?", (bet_amount, user_id))
        await db.commit()

async def is_user_banned(user_id):
    u = await get_user(user_id)
    return u and u.get('is_banned', 0) == 1

async def increment_games_played(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET games_played = games_played + 1 WHERE user_id = ?", (user_id,))
        await db.commit()

async def check_referral_reward(user_id):
    user = await get_user(user_id)
    if not user or user.get('referrer_id', 0) == 0 or user.get('referral_paid', 0) == 1: return False
    
    if user.get('games_played', 0) > 0:
        referrer_id = user.get('referrer_id', 0)
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_REWARD, referrer_id))
            await db.execute("UPDATE users SET referral_paid = 1 WHERE user_id = ?", (user_id,))
            await db.commit()
        try:
            referrer = await get_user(referrer_id)
            if referrer:
                await bot.send_message(referrer_id, f"🎉 **Реферальная награда!**\n\nВаш реферал {user.get('username')} сыграл в игры!\nВы получили: `{REFERRAL_REWARD}$`\n💰 Баланс: `{float(referrer.get('balance', 0)) + REFERRAL_REWARD:.2f}$`")
        except: pass
        return True
    return False

# --- ФУНКЦИИ КАРТИНОК ---
async def get_image_file_id(key):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT file_id FROM images WHERE key_name = ?", (key,))
        row = await cursor.fetchone()
        return row[0] if row else None

async def save_image_file_id(key, file_id):
    async with aiosqlite.connect(DB_NAME) as db:
        if file_id is None:
            await db.execute("DELETE FROM images WHERE key_name = ?", (key,))
        else:
            await db.execute("INSERT OR REPLACE INTO images (key_name, file_id) VALUES (?, ?)", (key, file_id))
        await db.commit()

async def send_or_edit_media(event: Union[types.Message, types.CallbackQuery], key: str, text: str, markup=None, parse_mode="Markdown"):
    """
    Универсальная функция:
    1. Если ключ картинки найден -> пытается отправить/заменить фото.
    2. Если ключа нет (или фото удалено) -> пытается отправить/отредактировать текст.
       Важно: если раньше было фото, а теперь текст, нужно удалить старое и прислать новое сообщение.
    """
    file_id = await get_image_file_id(key)
    chat_id = event.from_user.id if isinstance(event, types.CallbackQuery) else event.chat.id
    
    # 1. Сценарий с картинкой
    if file_id:
        try:
            if isinstance(event, types.CallbackQuery):
                # Пробуем удалить старое сообщение, чтобы прислать новое фото начисто,
                # либо используем EditMedia (сложнее). Проще удалить и прислать, 
                # т.к. InputMediaPhoto требует сложной структуры.
                # Но для плавности часто лучше EditMedia. 
                # В данном коде используется подход "удалить -> прислать" для фото, это надежнее.
                await event.message.delete()
            await bot.send_photo(chat_id, photo=file_id, caption=text, reply_markup=markup, parse_mode=parse_mode)
            return
        except Exception as e:
            logging.error(f"Ошибка отправки фото ({key}): {e}")
    
    # 2. Сценарий без картинки (только текст)
    try:
        if isinstance(event, types.CallbackQuery):
            try:
                # Если предыдущее сообщение было с фото, его нельзя редактировать в текст.
                # Нужно удалить и прислать новое.
                if event.message.photo:
                    await event.message.delete()
                    await bot.send_message(chat_id, text, reply_markup=markup, parse_mode=parse_mode)
                else:
                    # Если было текстовое, просто редактируем
                    await event.message.edit_text(text, reply_markup=markup, parse_mode=parse_mode)
            except TelegramBadRequest:
                # Если вдруг что-то пошло не так (например, сообщение слишком старое), удаляем и шлем новое
                try: await event.message.delete()
                except: pass
                await bot.send_message(chat_id, text, reply_markup=markup, parse_mode=parse_mode)
        else:
            await event.answer(text, reply_markup=markup, parse_mode=parse_mode)
    except Exception as e:
        logging.error(f"Ошибка отправки текста: {e}")

# --- ФУНКЦИИ ДЛЯ ТРАНЗАКЦИЙ ---
async def add_transaction(user_id, trans_type, amount, invoice_id=None, check_id=None, status='pending'):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO transactions (user_id, type, amount, status, invoice_id, check_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                         (user_id, trans_type, amount, status, invoice_id, check_id, int(time.time())))
        await db.commit()

async def update_transaction_status(invoice_id=None, check_id=None, status='completed'):
    async with aiosqlite.connect(DB_NAME) as db:
        if invoice_id: await db.execute("UPDATE transactions SET status = ? WHERE invoice_id = ?", (status, str(invoice_id)))
        elif check_id: await db.execute("UPDATE transactions SET status = ? WHERE check_id = ?", (status, str(check_id)))
        await db.commit()

async def get_transactions(limit=50, trans_type=None):
    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?"
        params = [limit]
        if trans_type:
            query = "SELECT * FROM transactions WHERE type = ? ORDER BY created_at DESC LIMIT ?"
            params = [trans_type, limit]
        cursor = await db.execute(query, params)
        return await cursor.fetchall()

# --- КЛАВИАТУРЫ ---
def main_menu_kb(user_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🎰 ИГРАТЬ", callback_data="menu_games")
    kb.button(text="👤 ПРОФИЛЬ", callback_data="menu_profile")
    kb.button(text="💳 КОШЕЛЕК", callback_data="menu_wallet")
    kb.button(text="🤝 РЕФЕРАЛЫ", callback_data="menu_refs")
    kb.button(text="🎁 БОНУС", callback_data="menu_bonus")
    kb.button(text="ℹ️ ПОМОЩЬ", callback_data="menu_help")
    kb.button(text="📜 ПРАВИЛА", callback_data="menu_rules")
    
    try:
        uid_int = int(user_id)
        if uid_int in ADMIN_IDS:
            kb.button(text="🔐 АДМИНКА", callback_data="admin_home")
            kb.adjust(1, 2, 2, 2, 1)
        else:
            kb.adjust(1, 2, 2, 2)
    except:
        kb.adjust(1, 2, 2, 2)
        
    return kb.as_markup()

def admin_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 ВЫДАТЬ БАЛАНС", callback_data="adm_give")
    kb.button(text="🔨 БАН / РАЗБАН", callback_data="adm_ban_menu")
    kb.button(text="📊 ПОПОЛНЕНИЯ", callback_data="adm_deposits")
    kb.button(text="📤 ВЫВОДЫ", callback_data="adm_withdraws")
    kb.button(text="📈 СТАТИСТИКА", callback_data="adm_stats")
    kb.button(text="⚙️ КОЭФФИЦИЕНТЫ", callback_data="adm_settings")
    kb.button(text="🖼 КАРТИНКИ", callback_data="adm_images")
    kb.button(text="🔙 НАЗАД", callback_data="start_over")
    kb.adjust(1, 2, 2, 2, 1)
    return kb.as_markup()

def admin_settings_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🎲 Dice Победа: x{GAME_CONFIG['dice_win']}", callback_data="set_dice_win")
    kb.button(text=f"⚖️ Dice Ничья: x{GAME_CONFIG['dice_draw']}", callback_data="set_dice_draw")
    kb.button(text="💣 Настройка Мин (детально)", callback_data="adm_set_mines_menu")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(1)
    return kb.as_markup()

def admin_mines_settings_kb():
    kb = InlineKeyboardBuilder()
    mines_options = sorted([int(k) for k in GAME_CONFIG["mines_config"].keys()])
    for count in mines_options:
        share = GAME_CONFIG["mines_config"].get(str(count), 0.9)
        kb.button(text=f"💣 {count}м ({int(share*100)}%)", callback_data=f"set_m_share_{count}")
    kb.button(text="🔙 Назад", callback_data="adm_settings")
    kb.adjust(2)
    return kb.as_markup()

def admin_images_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏠 Главное меню", callback_data="img_set_start")
    kb.button(text="👤 Профиль", callback_data="img_set_profile")
    kb.button(text="💳 Кошелек", callback_data="img_set_wallet")
    kb.button(text="🤝 Рефералы", callback_data="img_set_refs")
    kb.button(text="🎮 Меню игр", callback_data="img_set_games_menu")
    kb.button(text="ℹ️ Помощь/Правила", callback_data="img_sub_help")
    kb.button(text="🎲 Игры (Dice/Sport)", callback_data="img_set_game_dice")
    kb.button(text="💣 Мины (Игра)", callback_data="img_set_game_mines")
    kb.button(text="🏆 Победа/Проигрыш", callback_data="img_sub_res")
    kb.button(text="🔙 Назад", callback_data="admin_home")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()

# --- СТАРТ И ВЕРИФИКАЦИЯ ---
@dp.message(CommandStart())
@dp.callback_query(F.data == "start_over")
async def cmd_start(event: types.Message | types.CallbackQuery, state: FSMContext = None, command: CommandObject = None):
    if state: await state.clear()
    
    uid = event.from_user.id
    print(f"DEBUG: Пользователь зашел с ID: {uid}")
    if uid in ADMIN_IDS:
        print(f"DEBUG: ✅ Пользователь {uid} распознан как АДМИН")
    
    if await is_user_banned(uid): return
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT is_verified FROM users WHERE user_id = ?", (uid,))
        row = await cursor.fetchone()
        if not row:
            ref = int(command.args) if isinstance(event, types.Message) and command and command.args and command.args.isdigit() else 0
            await db.execute("INSERT INTO users (user_id, username, referrer_id, created_at) VALUES (?, ?, ?, ?)", 
                             (uid, event.from_user.first_name, ref, int(time.time())))
            await db.commit()
            is_verified = 0
        else: is_verified = row[0]

    if not is_verified:
        options = ["🍎", "🍌", "🍒", "🍉", "🍇", "🍓"]
        target = random.choice(options)
        random.shuffle(options)
        await state.update_data(captcha_target=target)
        kb = InlineKeyboardBuilder()
        for emoji in options: kb.button(text=emoji, callback_data=f"captcha_{emoji}")
        kb.adjust(3)
        await send_or_edit_media(event, "start", f"🤖 **ВЕРИФИКАЦИЯ**\n\nНажмите на: {target}", kb.as_markup())
        await state.set_state(States.waiting_for_captcha)
    else:
        text = f"👋 **Привет, {event.from_user.first_name}!**\n\n💎 **ANDRON CASINO** — лучшие игры на CryptoBot.\nВыбирай режим и начни выигрывать!"
        await send_or_edit_media(event, "start", text, main_menu_kb(uid))

@dp.callback_query(States.waiting_for_captcha, F.data.startswith("captcha_"))
async def process_captcha(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if c.data.split("_")[1] == data.get('captcha_target'):
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET is_verified = 1 WHERE user_id = ?", (c.from_user.id,))
            await db.commit()
        await state.clear()
        await c.answer("✅ Доступ открыт!")
        await cmd_start(c)
    else:
        await c.answer("❌ Неверно!", show_alert=True)
        await cmd_start(c, state)

# --- МЕНЮ (ПРОФИЛЬ, РЕФЫ И ТД) ---
@dp.callback_query(F.data == "menu_profile")
async def profile_cb(c: types.CallbackQuery):
    u = await get_user(c.from_user.id)
    if not u: return
    
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (c.from_user.id,))
        ref_count = (await cursor.fetchone())[0] or 0
    
    ref_info = ""
    if u.get('referrer_id') and u['referrer_id'] > 0:
        referrer = await get_user(u['referrer_id'])
        if referrer: ref_info = f"👤 Реферер: `{referrer.get('username','').replace('`','')}`\n"
    
    text = (
        f"👤 **ПРОФИЛЬ**\n\n"
        f"🆔 ID: `{u['user_id']}`\n"
        f"👤 Имя: `{u.get('username','').replace('`','')}`\n"
        f"💰 Баланс: `{float(u.get('balance', 0)):.2f}$`\n"
        f"🎮 Всего ставок: `{float(u.get('total_bets', 0)):.2f}$`\n"
        f"📥 Пополнено: `{float(u.get('total_deposited', 0)):.2f}$`\n"
        f"📤 Выведено: `{float(u.get('total_withdrawn', 0)):.2f}$`\n"
        f"🎮 Сыграно игр: {u.get('games_played', 0)}\n"
        f"{ref_info}"
        f"🤝 Рефералов: {ref_count}\n"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="start_over")
    await send_or_edit_media(c, "profile", text, kb.as_markup())

@dp.callback_query(F.data == "menu_refs")
async def refs_cb(c: types.CallbackQuery):
    u = await get_user(c.from_user.id)
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT username, games_played, referral_paid, balance FROM users WHERE referrer_id = ?", (c.from_user.id,))
        refs_raw = await cursor.fetchall()
    
    active_refs = sum(1 for r in refs_raw if r[1] > 0)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start={c.from_user.id}"
    
    text = (
        f"🤝 **РЕФЕРАЛЬНАЯ СИСТЕМА**\n\n"
        f"🔗 Ссылка:\n`{ref_link}`\n\n"
        f"💰 Награда: `{REFERRAL_REWARD}$` за активного реферала\n"
        f"💸 Заработано: `{active_refs * REFERRAL_REWARD:.2f}$`\n"
        f"👥 Рефералов: {len(refs_raw)} (Активных: {active_refs})\n"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="start_over")
    await send_or_edit_media(c, "refs", text, kb.as_markup())

@dp.callback_query(F.data == "menu_help")
async def help_cb(c: types.CallbackQuery):
    text = (
        "ℹ️ **ПОМОЩЬ И FAQ**\n\n"
        "🔹 **Как начать играть?**\n"
        "1. Пополните баланс в разделе «Кошелек».\n"
        "2. Перейдите в «Меню игр» и выберите режим.\n"
        "3. Сделайте ставку и выиграйте!\n\n"
        "🔹 **Пополнение и Вывод**\n"
        "Мы используем CryptoBot (USDT). Транзакции проходят автоматически. "
        "Если чек не активировался, попробуйте снова или напишите админу.\n\n"
        "🔹 **Проблемы?**\n"
        "Если нашли баг или есть вопросы по выплатам, нажмите кнопку ниже."
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍💻 Обратиться к Админу", url="https://t.me/Gemini_0")
    kb.button(text="🔙 Назад", callback_data="start_over")
    kb.adjust(1)
    await send_or_edit_media(c, "help", text, kb.as_markup())

@dp.callback_query(F.data == "menu_rules")
async def rules_cb(c: types.CallbackQuery):
    text = (
        "📜 **ПРАВИЛА ANDRON CASINO**\n\n"
        "💰 **ЛИМИТЫ:**\n"
        f"• Ставка: от `{MIN_BET}$`\n"
        f"• Пополнение: от `{MIN_DEPOSIT}$`\n"
        f"• Вывод: от `{MIN_WITHDRAW}$`\n\n"
        "🎮 **ИГРЫ:**\n"
        f"• Дартс/Кубик: Победа x{GAME_CONFIG.get('dice_win', 1.8)}, Ничья x{GAME_CONFIG.get('dice_draw', 0.93)}.\n"
        "• Мины: Выбирайте кол-во мин, чем больше мин, тем больше выигрыш.\n\n"
        "🎁 **БОНУС:**\n"
        "• Раз в 24 часа. Нужно иметь рекламу бота в БИО.\n\n"
        "🤝 **РЕФЕРАЛЫ:**\n"
        f"• `{REFERRAL_REWARD}$` за реферала, который сыграет в игры\n\n"
        "⚖️ **ОБЩИЕ ПРАВИЛА:**\n"
        "• Запрещен мультиаккаунтинг\n"
        "• Запрещено использование ботов\n"
        "• Администрация оставляет за собой право изменять правила"
    )
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data="start_over")
    await send_or_edit_media(c, "rules", text, kb.as_markup())

@dp.callback_query(F.data == "menu_bonus")
async def bonus_cb(c: types.CallbackQuery):
    u = await get_user(c.from_user.id)
    now = int(time.time())
    if now - u.get('last_bonus', 0) < 86400: return await c.answer("⏳ Только раз в сутки!", show_alert=True)
    
    try:
        chat = await bot.get_chat(c.from_user.id)
        if REQUIRED_BIO_TEXT.lower() not in (chat.bio or "").lower():
            return await c.message.answer(f"❌ **Установите в БИО:**\n`{REQUIRED_BIO_TEXT}`", parse_mode="Markdown")
        
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ?, last_bonus = ? WHERE user_id = ?", (BONUS_AMOUNT, now, c.from_user.id))
            await db.commit()
        
        text = f"✅ **Бонус +{BONUS_AMOUNT}$**"
        kb = InlineKeyboardBuilder()
        kb.button(text="🔙 Меню", callback_data="start_over")
        await send_or_edit_media(c, "bonus", text, kb.as_markup())
    except: await c.answer("❌ Ошибка доступа к профилю", show_alert=True)

# --- ИГРОВОЙ БЛОК ---
@dp.callback_query(F.data == "menu_games")
async def games_list(c: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    gs = [("🎯 Дартс", "darts"), ("🎲 Кубик", "dice"), ("⚽ Футбол", "football"), 
          ("🏀 Баскет", "basket"), ("🎳 Боулинг", "bowling"), ("💣 Мины", "mines")]
    for n, code in gs: kb.button(text=n, callback_data=f"play_{code}")
    kb.button(text="🔙 Назад", callback_data="start_over")
    kb.adjust(2)
    await send_or_edit_media(c, "games_menu", "🎰 **ВЫБЕРИТЕ ИГРУ**", kb.as_markup())

@dp.callback_query(F.data.startswith("play_"))
async def game_start(c: types.CallbackQuery, state: FSMContext):
    game = c.data.split("_")[1]
    await state.update_data(g=game)
    
    img_key = "game_mines" if game == "mines" else "game_sport" if game in ["football", "basket"] else "game_dice"
    
    text = f"🕹 Выбрано: **{game.upper()}**\nВведите сумму ставки:"
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Отмена", callback_data="start_over")
    
    await send_or_edit_media(c, img_key, text, kb.as_markup())
    await state.set_state(States.waiting_for_bet)

@dp.message(States.waiting_for_bet)
async def handle_bet(m: types.Message, state: FSMContext):
    try:
        bet = float(m.text.replace(',', '.'))
        u = await get_user(m.from_user.id)
        if bet < MIN_BET: return await m.answer(f"❌ Мин: {MIN_BET}$")
        if bet > float(u.get('balance', 0)): return await m.answer("❌ Недостаточно средств.")
        
        data = await state.get_data()
        
        if data['g'] == "mines":
            await state.update_data(bet=bet)
            kb = InlineKeyboardBuilder()
            for count in [1, 3, 5, 8, 10, 15, 20, 24]: kb.button(text=f"💣 {count}", callback_data=f"mines_set_{count}")
            kb.adjust(4)
            kb.button(text="❌ Отмена", callback_data="start_over")
            await send_or_edit_media(m, "game_mines", f"💣 **Mines**\nСтавка: `{bet}$`\nВыберите кол-во мин:", kb.as_markup())
            await state.set_state(States.waiting_for_mines_count)
            return
            
        emo = {"darts":"🎯", "dice":"🎲", "football":"⚽", "basket":"🏀", "bowling":"🎳"}[data['g']]
        await state.update_data(bet=bet, emo=emo)
        await m.answer(f"Отправьте эмодзи {emo} для броска!")
        await state.set_state(States.waiting_for_turn)
    except ValueError: await m.answer("❌ Введите число!")

# --- МИНЫ ---
@dp.callback_query(States.waiting_for_mines_count, F.data.startswith("mines_set_"))
async def start_mines_game(c: types.CallbackQuery, state: FSMContext):
    mines_count = int(c.data.split("_")[2])
    data = await state.get_data()
    bet = data['bet']
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (bet, c.from_user.id))
        await db.commit()
    await update_total_bets(c.from_user.id, bet)
    await increment_games_played(c.from_user.id)
    await check_referral_reward(c.from_user.id)
    
    f = ["M"] * mines_count + ["0"] * (25 - mines_count)
    random.shuffle(f)
    await state.update_data(field=f, mines_count=mines_count, opened=0, mult=1.0)
    
    text = f"💣 **MINES** ({mines_count} мин) | Ставка: `{bet}$`\nОткрывайте клетки!"
    await send_or_edit_media(c, "game_mines", text, get_mines_kb(f, 0))

def calculate_mines_coeff(opened, mines_count):
    total_cells = 25
    mult = 1.0
    for i in range(opened):
        safe_remaining = (total_cells - mines_count) - i
        total_remaining = total_cells - i
        if safe_remaining <= 0: return 0
        chance = safe_remaining / total_remaining
        mult *= (1 / chance)
    
    raw_profit = mult - 1.0
    share = GAME_CONFIG["mines_config"].get(str(mines_count), 0.9)
    return round(1.0 + raw_profit * share, 2)

def get_mines_kb(f, win, over=False):
    kb = InlineKeyboardBuilder()
    for i, cell in enumerate(f):
        if over:
            t = "💣" if cell=="M" else "💎"
            kb.button(text=t, callback_data="ignore")
        else:
            if cell == "O": kb.button(text="💎", callback_data="ignore")
            else: kb.button(text="🟦", callback_data=f"m_cl_{i}")
    kb.adjust(5)
    if not over and win > 0: kb.row(types.InlineKeyboardButton(text=f"💰 ЗАБРАТЬ {win:.2f}$", callback_data="m_cash"))
    elif over: kb.row(types.InlineKeyboardButton(text="🔙 МЕНЮ", callback_data="start_over"))
    return kb.as_markup()

@dp.callback_query(States.waiting_for_mines_count, F.data.startswith("m_cl_"))
async def mine_click(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = int(c.data.split("_")[2])
    f = data["field"].copy()
    
    if f[idx] == "M":
        await send_or_edit_media(c, "res_lose", f"💥 **ВЗРЫВ!**\nВы наткнулись на мину.", get_mines_kb(f, 0, True))
        await state.clear()
    else:
        f[idx] = "O"
        o = data["opened"] + 1
        m = calculate_mines_coeff(o, data["mines_count"])
        await state.update_data(field=f, opened=o, mult=m)
        
        try:
            text = f"💎 **MINES** | x{m}\nВыигрыш: `{data['bet']*m:.2f}$`"
            if c.message.photo:
                await c.message.edit_caption(caption=text, reply_markup=get_mines_kb(f, data['bet']*m), parse_mode="Markdown")
            else:
                await c.message.edit_text(text, reply_markup=get_mines_kb(f, data['bet']*m), parse_mode="Markdown")
        except: pass
    await c.answer()

@dp.callback_query(States.waiting_for_mines_count, F.data == "m_cash")
async def mine_cash(c: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    win = round(data["bet"] * data.get("mult", 1.0), 2)
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win, c.from_user.id))
        await db.commit()
    await send_or_edit_media(c, "res_win", f"🤑 **ВЫИГРЫШ ЗАБРАН!**\nСумма: `{win:.2f}$`", main_menu_kb(c.from_user.id))
    await state.clear()

# --- DICE / СПОРТ ---
@dp.message(States.waiting_for_turn, F.dice)
async def dice_logic(m: types.Message, state: FSMContext):
    data = await state.get_data()
    if m.dice.emoji != data['emo']: return
    
    bet = data['bet']
    await update_total_bets(m.from_user.id, bet)
    await increment_games_played(m.from_user.id)
    await check_referral_reward(m.from_user.id)
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (bet, m.from_user.id))
        await db.commit()
    
    b_dice = await m.answer_dice(emoji=data['emo'])
    await asyncio.sleep(4)
    
    if m.dice.value > b_dice.dice.value:
        mult = GAME_CONFIG.get("dice_win", 1.8)
        win = bet * mult
        res_key = "res_win"
        res_text = "🏆 ПОБЕДА"
    elif m.dice.value == b_dice.dice.value:
        mult = GAME_CONFIG.get("dice_draw", 0.93)
        win = bet * mult
        res_key = "res_draw"
        res_text = "🤝 НИЧЬЯ"
    else:
        win = 0
        res_key = "res_lose"
        res_text = "💀 ПРОИГРЫШ"
    
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (win, m.from_user.id))
        await db.commit()
    
    text = f"**{res_text}!**\nВы: {m.dice.value} | Бот: {b_dice.dice.value}\nБаланс: {'+' if win > 0 else ''}`{win:.2f}$`"
    
    fid = await get_image_file_id(res_key)
    kb = main_menu_kb(m.from_user.id)
    if fid:
        await m.answer_photo(photo=fid, caption=text, reply_markup=kb, parse_mode="Markdown")
    else:
        await m.answer(text, reply_markup=kb, parse_mode="Markdown")
    await state.clear()

# --- КОШЕЛЕК ---
@dp.callback_query(F.data == "menu_wallet")
async def wallet_view(c: types.CallbackQuery):
    u = await get_user(c.from_user.id)
    text = f"💳 **КОШЕЛЕК**\n\n💰 Баланс: `{float(u.get('balance', 0)):.2f}$`"
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ ПОПОЛНИТЬ", callback_data="deposit_auto")
    kb.button(text="📤 ВЫВЕСТИ", callback_data="withdraw_ask")
    kb.button(text="🔙 НАЗАД", callback_data="start_over")
    kb.adjust(2, 1)
    await send_or_edit_media(c, "wallet", text, kb.as_markup())

# --- ВЫВОД И ПОПОЛНЕНИЕ ---
@dp.callback_query(F.data == "withdraw_ask")
async def withdraw_ask_cb(c: types.CallbackQuery, state: FSMContext):
    u = await get_user(c.from_user.id)
    if float(u.get('balance', 0)) < MIN_WITHDRAW: return await c.answer(f"❌ Мин вывод: {MIN_WITHDRAW}$", show_alert=True)
    await c.message.answer("Введите сумму вывода:")
    await state.set_state(States.waiting_for_withdraw)

@dp.message(States.waiting_for_withdraw)
async def withdraw_handle(m: types.Message, state: FSMContext):
    try:
        amount = float(m.text.replace(',', '.'))
        u = await get_user(m.from_user.id)
        if amount > float(u.get('balance', 0)): return await m.answer("❌ Мало средств")
        
        check = await create_crypto_check(amount)
        if not check["success"]: return await m.answer(f"Ошибка: {check['error']}")
        
        await add_transaction(m.from_user.id, 'withdraw', amount, check_id=check.get("check_id"))
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance - ?, total_withdrawn = total_withdrawn + ? WHERE user_id = ?", (amount, amount, m.from_user.id))
            await db.commit()
        await m.answer(f"✅ Чек создан: {check['check_url']}")
        await state.clear()
    except: await m.answer("❌ Введите число")

@dp.callback_query(F.data == "deposit_auto")
async def dep_ask(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer(f"Введите сумму (мин {MIN_DEPOSIT}$):")
    await state.set_state(States.waiting_for_deposit)

@dp.message(States.waiting_for_deposit)
async def dep_create(m: types.Message, state: FSMContext):
    try:
        val = float(m.text.replace(',', '.'))
        inv = await crypto.create_invoice(asset='USDT', amount=val)
        await add_transaction(m.from_user.id, 'deposit', val, inv.invoice_id)
        kb = InlineKeyboardBuilder()
        kb.button(text="💳 ОПЛАТИТЬ", url=inv.bot_invoice_url)
        kb.button(text="🔄 ПРОВЕРИТЬ", callback_data=f"check_{inv.invoice_id}")
        kb.button(text="❌ ОТМЕНА", callback_data="start_over")
        kb.adjust(1)
        await m.answer(f"💎 Оплатите `{val}$`", reply_markup=kb.as_markup(), parse_mode="Markdown")
        await state.clear()
    except: await m.answer("Ошибка")

@dp.callback_query(F.data.startswith("check_"))
async def dep_check(c: types.CallbackQuery):
    iid = int(c.data.split("_")[1])
    invs = await crypto.get_invoices(invoice_ids=[iid])
    if invs and invs[0].status == 'paid':
        amt = float(invs[0].amount)
        await update_transaction_status(invoice_id=str(iid))
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ?, total_deposited = total_deposited + ? WHERE user_id = ?", (amt, amt, c.from_user.id))
            await db.commit()
        await c.message.answer("✅ Оплачено!")
        await cmd_start(c)
    else: await c.answer("⏳ Не оплачено", show_alert=True)

# --- АДМИНКА ---
@dp.callback_query(F.data == "admin_home")
async def adm_panel(c: types.CallbackQuery):
    try:
        # Принудительно приводим ID к int для надежности
        uid = int(c.from_user.id)
        if uid in ADMIN_IDS:
            # ИСПОЛЬЗУЕМ send_or_edit_media, чтобы корректно удалить фото (если оно есть в меню)
            # и отправить текстовое сообщение.
            await send_or_edit_media(c, "admin_home", "🔐 **АДМИН-ПАНЕЛЬ**", admin_menu_kb())
        else:
            await c.answer("⛔ Доступ запрещен", show_alert=True)
    except Exception as e:
        # Логируем реальную ошибку
        print(f"Error in adm_panel: {e}")
        await c.answer(f"⛔ Ошибка: {e}", show_alert=True)

@dp.callback_query(F.data == "adm_images")
async def adm_images_menu(c: types.CallbackQuery):
    if c.from_user.id in ADMIN_IDS:
        await c.message.edit_text("🖼 **Управление картинками**\nВыберите раздел для смены фото:", reply_markup=admin_images_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "img_sub_help")
async def img_sub_help(c: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="ℹ️ Помощь", callback_data="img_set_help")
    kb.button(text="📜 Правила", callback_data="img_set_rules")
    kb.button(text="🎁 Бонус", callback_data="img_set_bonus")
    kb.button(text="🔙 Назад", callback_data="adm_images")
    kb.adjust(1)
    await c.message.edit_text("Выберите подраздел:", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "img_sub_res")
async def img_sub_res(c: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🏆 Победа", callback_data="img_set_res_win")
    kb.button(text="💀 Проигрыш", callback_data="img_set_res_lose")
    kb.button(text="⚖️ Ничья", callback_data="img_set_res_draw")
    kb.button(text="🔙 Назад", callback_data="adm_images")
    kb.adjust(1)
    await c.message.edit_text("Выберите результат:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("img_set_"))
async def img_ask_photo(c: types.CallbackQuery, state: FSMContext):
    key = c.data.replace("img_set_", "")
    name = IMAGE_KEYS.get(key, key)
    
    current = "✅ Установлено" if await get_image_file_id(key) else "❌ Не установлено (текст)"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🗑 Удалить картинку", callback_data=f"img_del_{key}")
    kb.button(text="🔙 Отмена", callback_data="adm_images")
    
    await state.update_data(img_key=key)
    await c.message.edit_text(
        f"🖼 Редактирование: **{name}**\n\n"
        f"Текущий статус: {current}\n\n"
        f"📸 **Отправьте мне новое фото** для этого раздела.", 
        reply_markup=kb.as_markup(), parse_mode="Markdown"
    )
    await state.set_state(States.admin_upload_photo)

@dp.message(States.admin_upload_photo, F.photo)
async def img_save_photo(m: types.Message, state: FSMContext):
    data = await state.get_data()
    key = data.get("img_key")
    file_id = m.photo[-1].file_id
    
    await save_image_file_id(key, file_id)
    await m.answer(f"✅ Фото для **{IMAGE_KEYS.get(key, key)}** сохранено!", reply_markup=admin_images_kb())
    await state.clear()

@dp.callback_query(F.data.startswith("img_del_"))
async def img_delete_photo(c: types.CallbackQuery, state: FSMContext):
    key = c.data.replace("img_del_", "")
    await save_image_file_id(key, None)
    await c.answer("✅ Картинка удалена, будет использоваться текст.", show_alert=True)
    await adm_images_menu(c)
    await state.clear()

@dp.callback_query(F.data == "adm_deposits")
async def adm_deposits_cb(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return
    deposits = await get_transactions(trans_type='deposit', limit=10)
    text = "📥 **ПОПОЛНЕНИЯ**\n\n" + "\n".join([f"{d['amount']}$ (ID:{d['user_id']}) {d['status']}" for d in deposits])
    await c.message.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_withdraws")
async def adm_withdraws_cb(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return
    wd = await get_transactions(trans_type='withdraw', limit=10)
    text = "📤 **ВЫВОДЫ**\n\n" + "\n".join([f"{d['amount']}$ (ID:{d['user_id']}) {d['status']}" for d in wd])
    await c.message.edit_text(text, reply_markup=admin_menu_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_stats")
async def adm_stats_cb(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS: return
    async with aiosqlite.connect(DB_NAME) as db:
        users = (await (await db.execute("SELECT COUNT(*) FROM users")).fetchone())[0]
        bal = (await (await db.execute("SELECT SUM(balance) FROM users")).fetchone())[0] or 0
    await c.message.edit_text(f"📊 **СТАТИСТИКА**\nUsers: {users}\nBalances: {bal:.2f}$", reply_markup=admin_menu_kb(), parse_mode="Markdown")

@dp.callback_query(F.data == "adm_ban_menu")
async def adm_ban_st(c: types.CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS: return
    await c.message.answer("Введите ID пользователя:")
    await state.set_state(States.admin_manage_ban)

@dp.message(States.admin_manage_ban)
async def adm_ban_fin(m: types.Message, state: FSMContext):
    try:
        uid = int(m.text)
        u = await get_user(uid)
        if u:
            new = 1 if u['is_banned']==0 else 0
            async with aiosqlite.connect(DB_NAME) as db:
                await db.execute("UPDATE users SET is_banned = ? WHERE user_id = ?", (new, uid))
                await db.commit()
            await m.answer(f"Статус бана для {uid}: {new}")
        else: await m.answer("Юзер не найден")
    except: await m.answer("Ошибка")
    await state.clear()

@dp.callback_query(F.data == "adm_give")
async def adm_give_st(c: types.CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS: return
    await c.message.answer("Введите: ID сумма")
    await state.set_state(States.admin_giving_balance)

@dp.message(States.admin_giving_balance)
async def adm_give_fin(m: types.Message, state: FSMContext):
    try:
        uid, amt = map(float, m.text.split())
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amt, int(uid)))
            await db.commit()
        await m.answer("Выдано!")
    except: await m.answer("Ошибка формата")
    await state.clear()

async def main():
    await init_db()
    await update_db_schema()
    await load_settings()
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
