import re
import asyncio
from telethon import TelegramClient, events

# ==================== НАСТРОЙКИ ====================
API_ID = 1234567  # Замени на свой api_id
API_HASH = 'your_api_hash_here'  # Замени на свой api_hash
PHONE_NUMBER = '+7XXXXXXXXXX'  # Твой номер телефона

# Паттерн для номера телефона (только номер, без другого текста)
PHONE_PATTERN = re.compile(r'^(\+7|7|8)?\d{10}$')

# Список ID чатов для мониторинга (будет заполнен через избранное)
MONITORED_CHATS = []

# ==================== КЛИЕНТ ====================
client = TelegramClient('session_name', API_ID, API_HASH)

# ==================== ФУНКЦИИ ====================
async def ask_chat_ids():
    """Запрашивает ID чатов через избранное"""
    async with client:
        me = await client.get_me()
        saved = await client.get_messages('me', limit=10)
        
        # Отправляем инструкцию в избранное
        await client.send_message('me', 
            "📌 Отправь мне ID чатов для мониторинга (каждый с новой строки).\n"
            "Чтобы получить ID чата, перешли любое сообщение из него боту @userinfobot\n"
            "Готово? Отправь 'готово'."
        )
        
        @client.on(events.NewMessage(from_users=me.id, chats='me'))
        async def handler(event):
            if event.message.text.lower() == 'готово':
                await event.reply("✅ Настройка завершена. Начинаю мониторинг.")
                event.client.remove_event_handler(handler)
                return
            
            # Парсим ID чатов
            lines = event.message.text.split('\n')
            for line in lines:
                line = line.strip()
                if line.isdigit() or (line.startswith('-') and line[1:].isdigit()):
                    MONITORED_CHATS.append(int(line))
                    await event.reply(f"✅ Чат {line} добавлен.")
        
        await client.run_until_disconnected()

async def monitor_chats():
    """Мониторинг чатов и реакция на номера"""
    @client.on(events.NewMessage(chats=MONITORED_CHATS))
    async def handler(event):
        message_text = event.message.text.strip()
        
        # Проверяем, что сообщение содержит только номер телефона
        if PHONE_PATTERN.match(message_text):
            # Отправляем "вз" в тот же чат
            await client.send_message(event.chat_id, "вз")
            
            # Уведомляем в избранное
            chat = await event.get_chat()
            chat_title = chat.title if hasattr(chat, 'title') else chat.first_name
            await client.send_message(
                'me',
                f"📢 Отправлено 'вз' в чат: {chat_title}\n"
                f"📞 По номеру: {message_text}\n"
                f"🕒 Время: {event.message.date}"
            )
    
    async with client:
        await client.send_message('me', "👁️ Мониторинг чатов запущен.")
        await client.run_until_disconnected()

# ==================== ЗАПУСК ====================
async def main():
    print("🔑 Авторизация в Telegram...")
    await client.start(phone=PHONE_NUMBER)
    
    # Запрашиваем ID чатов
    await ask_chat_ids()
    
    # Запускаем мониторинг
    if MONITORED_CHATS:
        await monitor_chats()
    else:
        print("❌ Не указаны чаты для мониторинга.")

if __name__ == '__main__':
    asyncio.run(main())
