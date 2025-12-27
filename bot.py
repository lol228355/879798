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

# --- ТВОИ КОНФИГУРАЦИИ ---
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

# --- СОСТОЯНИЯ ДЛЯ АДМИНКИ ---
class AdminStates(StatesGroup):
    waiting_for_media = State()

# --- ФУНКЦИИ БД ---
def get_welcome_media():
    cursor.execute("SELECT value, type FROM settings WHERE key='welcome_media'")
    return cursor.fetchone()

def set_welcome_media(file_id, media_type):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value, type) VALUES ('welcome_media', ?, ?)", (file_id, media_type))
    conn.commit()

# --- ФУНКЦИЯ ПРОВЕРКИ ПОДПИСКИ ---
async def check_sub(user_id):
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # Статусы, которые считаются "подписанными"
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
            return True
        return False
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        # Если бот не админ в канале или ошибка доступа, лучше пустить юзера, чем блокировать навсегда
        return True 

# --- КЛАВИАТУРЫ ---

# 1. Клавиатура Подписки (Инлайн)
def get_sub_kb():
    kb = [
        [InlineKeyboardButton(text="👉 ПОДПИСАТЬСЯ НА КАНАЛ", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я ПОДПИСАЛСЯ", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# 2. Главная клавиатура (Меню)
def get_main_kb():
    kb = [
        [KeyboardButton(text="💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")],
        [KeyboardButton(text="🆘 ТЕХ. ПОДДЕРЖКА")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, input_field_placeholder="🔥 Выбери действие")

# 3. Клавиатура Админа
def get_admin_kb():
    kb = [
        [InlineKeyboardButton(text="🎬 Заменить Видео/Фото приветствия", callback_data="change_welcome")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ЛОГИКА ПРИВЕТСТВИЯ (ВЫНЕСЕНА В ОТДЕЛЬНУЮ ФУНКЦИЮ) ---
async def send_welcome_content(message: types.Message):
    media_data = get_welcome_media()
    
    caption_text = (
        "<b>🚀 ДОБРО ПОЖАЛОВАТЬ В КОМАНДУ!</b>\n\n"
        "🤑 <b>Ты в шаге от первого заработка.</b>\n"
        "Здесь мы делаем реальный кэш. Система настроена и готова к работе.\n\n"
        "👇 <b>ЖМИ КНОПКУ НИЖЕ, ЧТОБЫ ПОЛУЧИТЬ ДОСТУП!</b>"
    )

    if media_data:
        file_id, media_type = media_data
        try:
            if media_type == 'video':
                await message.answer_video(video=file_id, caption=caption_text, parse_mode="HTML", reply_markup=get_main_kb())
            elif media_type == 'photo':
                await message.answer_photo(photo=file_id, caption=caption_text, parse_mode="HTML", reply_markup=get_main_kb())
            else:
                 await message.answer(caption_text, parse_mode="HTML", reply_markup=get_main_kb())
        except Exception:
            await message.answer(caption_text, parse_mode="HTML", reply_markup=get_main_kb())
    else:
        await message.answer(caption_text, parse_mode="HTML", reply_markup=get_main_kb())

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    
    # ПРОВЕРКА ПОДПИСКИ
    if await check_sub(user_id):
        # Если подписан - показываем контент
        await send_welcome_content(message)
    else:
        # Если НЕ подписан - требуем подписку
        text = (
            "🔒 <b>ДОСТУП ОГРАНИЧЕН!</b>\n\n"
            "⚠️ Чтобы начать зарабатывать и получить доступ к боту, "
            "необходимо подписаться на наш закрытый канал.\n\n"
            "👇 <b>Подпишись и нажми кнопку проверки:</b>"
        )
        # Отправляем просто текст или фото-заглушку, если хочешь
        await message.answer(text, parse_mode="HTML", reply_markup=get_sub_kb())

@dp.callback_query(F.data == "check_subscription")
async def callback_check_sub(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete() # Удаляем сообщение с требованием подписки
        await send_welcome_content(callback.message)
    else:
        await callback.answer("❌ Вы еще не подписались! Сделайте это, чтобы продолжить.", show_alert=True)

# Кнопка "Ввести номер"
@dp.message(F.text == "💸 ПОДКЛЮЧИТЬ ВЫПЛАТЫ / ВВЕСТИ НОМЕР")
async def cmd_add_number(message: types.Message):
    # Повторная проверка подписки (на случай, если отписался)
    if not await check_sub(message.from_user.id):
        await message.answer("⛔️ Вы отписались от канала! Доступ закрыт.", reply_markup=get_sub_kb())
        return

    text = (
        "💎 <b>АКТИВАЦИЯ АККАУНТА</b>\n"
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬\n\n"
        "👤 <b>Добавление по номеру телефона:</b>\n"
        "<i>Для закрепления реквизитов и связи введите ваш номер.</i>\n\n"
        "👇 <b>СТРОГО В ФОРМАТЕ:</b>\n"
        "🇷🇺 РФ: <code>+79990000000</code>\n\n"
        "⚡️ <i>Отправь номер прямо сейчас и доступ откроется мгновенно!</i>"
    )
    await message.answer(text, parse_mode="HTML")

# Кнопка "Тех. Поддержка" (просто ссылка, но в виде красивого текста)
@dp.message(F.text == "🆘 ТЕХ. ПОДДЕРЖКА")
async def cmd_support(message: types.Message):
    text = (
        "👨‍💻 <b>СЛУЖБА ЗАБОТЫ</b>\n\n"
        "Возникли вопросы? Менеджер на связи 24/7.\n"
        f"👉 <a href='{SUPPORT_LINK}'>Написать в поддержку</a>"
    )
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

# --- АДМИНКА ---

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id in ADMIN_IDS: # Проверяем, есть ли ID в списке
        await message.answer("😎 <b>Админ-панель</b>\nЗагрузи крутое видео, чтобы поднять конверсию!", parse_mode="HTML", reply_markup=get_admin_kb())
    else:
        # Игнорируем или пишем отказ
        pass

@dp.callback_query(F.data == "change_welcome")
async def cb_change_welcome(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS: return
    
    await callback.message.answer("📤 <b>Кидай новое ВИДЕО или ФОТО</b>\nЖелательно с деньгами или тачками, чтобы цепляло! 🔥")
    await state.set_state(AdminStates.waiting_for_media)
    await callback.answer()

@dp.message(StateFilter(AdminStates.waiting_for_media))
async def process_media_upload(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return

    if message.video:
        file_id = message.video.file_id
        set_welcome_media(file_id, 'video')
        await message.answer("✅ <b>Видео сохранено!</b>", parse_mode="HTML")
    elif message.photo:
        file_id = message.photo[-1].file_id
        set_welcome_media(file_id, 'photo')
        await message.answer("✅ <b>Картинка сохранена!</b>", parse_mode="HTML")
    else:
        await message.answer("❌ Нужно прислать Видео или Фото.")
        return 

    await state.clear()

async def main():
    print("Бот запущен... 🚀")
    # Удаляем вебхук на всякий случай, если был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
