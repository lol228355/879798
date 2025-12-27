import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus

# --- КОНФИГУРАЦИЯ (ТВОИ ДАННЫЕ) ---
TOKEN = "8220500651:AAHKBf-AZ3UT7kH1oOrEEl-NwDWSE4DYoWw"
ADMIN_IDS = [7323981601, 8383446699] 
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"
CHANNEL_ID = -1003532318157
SUPPORT_LINK = "https://t.me/ik_126"

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect('bot_data.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, type TEXT)''')
conn.commit()

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# --- СОСТОЯНИЯ ---
class AdminStates(StatesGroup):
    waiting_for_media = State()

# --- ФУНКЦИИ БД ---
def get_welcome_media():
    cursor.execute("SELECT value, type FROM settings WHERE key='welcome_media'")
    return cursor.fetchone()

def set_welcome_media(file_id, media_type):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value, type) VALUES ('welcome_media', ?, ?)", (file_id, media_type))
    conn.commit()

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception:
        return True # Если ошибка доступа к каналу, пускаем юзера

# --- КЛАВИАТУРЫ ---

def get_sub_kb():
    kb = [
        [InlineKeyboardButton(text="👉 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я ПОДПИСАЛСЯ", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_main_kb():
    kb = [
        [KeyboardButton(text="💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")],
        [KeyboardButton(text="🆘 ТЕХ. ПОДДЕРЖКА")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_kb():
    kb = [
        [InlineKeyboardButton(text="🎬 Заменить Видео/Фото приветствия", callback_data="change_welcome")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ЛОГИКА ОТПРАВКИ КОНТЕНТА ---
async def send_welcome_content(message: types.Message):
    media_data = get_welcome_media()
    text = (
        "<b>🚀 ДОБРО ПОЖАЛОВАТЬ В КОМАНДУ!</b>\n\n"
        "🤑 <b>Ты в шаге от первого заработка.</b>\n"
        "Здесь мы делаем реальный кэш. Система готова.\n\n"
        "👇 <b>ЖМИ КНОПКУ НИЖЕ ДЛЯ ДОСТУПА!</b>"
    )
    
    if media_data:
        file_id, m_type = media_data
        try:
            if m_type == 'video':
                await bot.send_video(message.chat.id, video=file_id, caption=text, parse_mode="HTML", reply_markup=get_main_kb())
            else:
                await bot.send_photo(message.chat.id, photo=file_id, caption=text, parse_mode="HTML", reply_markup=get_main_kb())
            return
        except: pass
    await bot.send_message(message.chat.id, text, parse_mode="HTML", reply_markup=get_main_kb())

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if await check_sub(message.from_user.id):
        await send_welcome_content(message)
    else:
        await message.answer(
            "🔒 <b>ДОСТУП ОГРАНИЧЕН!</b>\n\n"
            "⚠️ Подпишись на наш канал, чтобы активировать бота и начать зарабатывать.",
            parse_mode="HTML", reply_markup=get_sub_kb()
        )

@dp.callback_query(F.data == "check_subscription")
async def callback_check_sub(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await send_welcome_content(callback.message)
    else:
        await callback.answer("❌ Подписка не найдена!", show_alert=True)

@dp.message(F.text == "💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")
async def cmd_add_number(message: types.Message):
    if not await check_sub(message.from_user.id):
        await message.answer("⛔️ Сначала подпишись на канал!", reply_markup=get_sub_kb())
        return

    text = (
        "💎 <b>АКТИВАЦИЯ АККАУНТА</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "👤 <b>Добавление по номеру телефона:</b>\n"
        "Введите номер для закрепления реквизитов.\n\n"
        "👇 <b>ФОРМАТ:</b>\n"
        "🇷🇺 Россия: <code>+7XXXXXXXXXX</code>\n\n"
        "⚡️ <i>Отправь номер и начни получать выплаты!</i>"
    )
    await message.answer(text, parse_mode="HTML")

@dp.message(F.text == "🆘 ТЕХ. ПОДДЕРЖКА")
async def cmd_support(message: types.Message):
    text = (
        "👨‍💻 <b>СЛУЖБА ЗАБОТЫ</b>\n\n"
        "Есть вопросы по выплатам? Пиши менеджеру:\n"
        f"👉 <a href='{SUPPORT_LINK}'>СВЯЗАТЬСЯ С ПОДДЕРЖКОЙ</a>"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

# --- АДМИНКА ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("😎 <b>Админ-панель</b>\nТут можно сменить видео/фото приветствия.", parse_mode="HTML", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "change_welcome")
async def cb_change_welcome(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id in ADMIN_IDS:
        await callback.message.answer("📤 <b>Отправь новое ВИДЕО или ФОТО:</b>")
        await state.set_state(AdminStates.waiting_for_media)
        await callback.answer()

@dp.message(StateFilter(AdminStates.waiting_for_media))
async def process_media_upload(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return

    if message.video:
        set_welcome_media(message.video.file_id, 'video')
        await message.answer("✅ Видео успешно установлено!")
    elif message.photo:
        set_welcome_media(message.photo[-1].file_id, 'photo')
        await message.answer("✅ Фото успешно установлено!")
    else:
        await message.answer("❌ Это не видео и не фото.")
        return
    await state.clear()

async def main():
    print("🚀 БОТ ЗАПУЩЕН И ГОТОВ К ВЫПЛАТАМ")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
