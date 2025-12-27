import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8220500651:AAHKBf-AZ3UT7kH1oOrEEl-NwDWSE4DYoWw"
# ID админов (добавь свой, если его тут нет)
ADMIN_IDS = [7323981601, 8383446699] 
# Канал для обязательной подписки
CHANNEL_LINK = "https://t.me/+4K_4dildrI82ODY6"
CHANNEL_ID = -1003532318157
# Ссылка на поддержку
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

# --- СОСТОЯНИЯ (FSM) ---
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
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        # Если бот не админ в канале, лучше пустить, чем заблокировать всех
        return True 

# --- КЛАВИАТУРЫ ---

# 1. Клавиатура Подписки (ОП)
def get_sub_kb():
    kb = [
        [InlineKeyboardButton(text="👉 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я ПОДПИСАЛСЯ", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# 2. Главное меню
def get_main_kb():
    kb = [
        [KeyboardButton(text="💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")],
        [KeyboardButton(text="🆘 ТЕХ. ПОДДЕРЖКА")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb, 
        resize_keyboard=True, 
        input_field_placeholder="💎 Выберите действие..."
    )

# 3. Админ-панель
def get_admin_kb():
    kb = [
        [InlineKeyboardButton(text="🎬 Заменить Видео/Фото приветствия", callback_data="change_welcome")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_admin")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ТЕКСТЫ ---
def get_welcome_caption():
    return (
        "<b>👋 ДОБРО ПОЖАЛОВАТЬ!</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "🚀 <b>Система готова к работе.</b>\n"
        "Ты попал в команду, где делаются реальные деньги. "
        "Весь функционал настроен и ждет твоих действий.\n\n"
        "💸 <b>Твой статус:</b> <code>АКТИВЕН</code>\n"
        "📉 <b>Доступ:</b> <code>РАЗРЕШЕН</code>\n\n"
        "👇 <b>Жми кнопку ниже, чтобы начать:</b>"
    )

# --- ФУНКЦИЯ ОТПРАВКИ ПРИВЕТСТВИЯ ---
async def send_welcome_content(message: types.Message):
    media_data = get_welcome_media()
    caption_text = get_welcome_caption()
    
    try:
        if media_data:
            file_id, media_type = media_data
            if media_type == 'video':
                await message.answer_video(video=file_id, caption=caption_text, parse_mode="HTML", reply_markup=get_main_kb())
            elif media_type == 'photo':
                await message.answer_photo(photo=file_id, caption=caption_text, parse_mode="HTML", reply_markup=get_main_kb())
            else:
                await message.answer(caption_text, parse_mode="HTML", reply_markup=get_main_kb())
        else:
            await message.answer(caption_text, parse_mode="HTML", reply_markup=get_main_kb())
    except Exception:
        # Если медиа удалено или ошибка, шлем текст
        await message.answer(caption_text, parse_mode="HTML", reply_markup=get_main_kb())

# --- АДМИН ПАНЕЛЬ ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return 
    await message.answer("<b>⚙️ ПАНЕЛЬ АДМИНИСТРАТОРА</b>", parse_mode="HTML", reply_markup=get_admin_kb())

@dp.callback_query(F.data == "change_welcome")
async def admin_change_media_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        return
    await callback.message.edit_text(
        "<b>📤 ОТПРАВЬТЕ НОВОЕ МЕДИА</b>\n\nПришлите фото или видео в этот чат.", 
        parse_mode="HTML"
    )
    await state.set_state(AdminStates.waiting_for_media)

@dp.message(AdminStates.waiting_for_media, F.content_type.in_({'photo', 'video'}))
async def admin_save_media(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    file_id = None
    media_type = None

    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = 'photo'
    elif message.video:
        file_id = message.video.file_id
        media_type = 'video'

    if file_id:
        set_welcome_media(file_id, media_type)
        await message.answer(f"✅ <b>Медиа обновлено!</b> Тип: {media_type}", parse_mode="HTML", reply_markup=get_main_kb())
        await state.clear()
    else:
        await message.answer("❌ Ошибка. Попробуйте снова.")

@dp.callback_query(F.data == "close_admin")
async def close_admin_panel(callback: types.CallbackQuery):
    await callback.message.delete()

# --- ХЕНДЛЕРЫ ПОЛЬЗОВАТЕЛЯ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    # 1. ПРОВЕРКА ПОДПИСКИ
    if await check_sub(user_id):
        await send_welcome_content(message)
    else:
        # Если не подписан
        text = (
            "🔒 <b>ДОСТУП ОГРАНИЧЕН!</b>\n\n"
            "⚠️ Чтобы начать зарабатывать и получить доступ к боту, "
            "необходимо подписаться на наш закрытый канал.\n\n"
            "👇 <b>Подпишись и нажми кнопку проверки:</b>"
        )
        await message.answer(text, parse_mode="HTML", reply_markup=get_sub_kb())

@dp.callback_query(F.data == "check_subscription")
async def callback_check_sub(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await send_welcome_content(callback.message)
    else:
        await callback.answer("❌ Вы еще не подписались!", show_alert=True)

# Кнопка "Ввести номер"
@dp.message(F.text == "💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")
async def cmd_add_number(message: types.Message):
    # Повторная проверка, чтобы не обходили меню
    if not await check_sub(message.from_user.id):
        await message.answer("⛔️ Вы отписались от канала! Доступ закрыт.", reply_markup=get_sub_kb())
        return

    text = (
        "<b>👤 Добавление по номеру телефона</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Для привязки реквизитов и получения выплат, введите ваш номер.\n\n"
        "<b>Введите номера в форматах:</b>\n"
        "🇷🇺 Россия: <code>+7XXXXXXXXXX</code>\n\n"
        "<i>❗️ Вводите номер внимательно, без пробелов.</i>"
    )
    await message.answer(text, parse_mode="HTML")

# Кнопка "Тех. Поддержка"
@dp.message(F.text == "🆘 ТЕХ. ПОДДЕРЖКА")
async def cmd_support(message: types.Message):
    text = (
        "<b>🛡 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "Возникли вопросы или проблемы с выплатой?\n"
        "Наш менеджер на связи <b>24/7</b>.\n\n"
        f"👨‍💻 <b>Связь:</b> <a href='{SUPPORT_LINK}'>НАПИСАТЬ МЕНЕДЖЕРУ</a>"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

# Обработка ввода номера (визуальная часть)
@dp.message(F.text.regexp(r'^\+?[0-9]{10,15}$'))
async def process_number_input(message: types.Message):
    if not await check_sub(message.from_user.id):
        return

    await message.answer(
        "✅ <b>ЗАЯВКА ПРИНЯТА</b>\n\n"
        f"Номер <code>{message.text}</code> добавлен в очередь.\n"
        "Ожидайте зачисления средств.",
        parse_mode="HTML"
    )

# --- ЗАПУСК ---
async def main():
    print("🤖 Бот запущен (ОП включена)...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
