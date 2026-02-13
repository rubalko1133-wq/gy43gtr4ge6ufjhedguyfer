import asyncio
import logging
import sqlite3
from datetime import datetime
from typing import Union

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode

# ================== НАСТРОЙКИ ==================
BOT_TOKEN = "8576803474:AAHM6zzi4s-Ey097oejl8lr9FwjUg3_F_Rg"  # Токен бота от @BotFather
CHANNEL_ID = -1003842969203  # ID канала (отрицательное число с -100)
ADMIN_IDS = [8287134813,1431520267]  # ID админов (через запятую)
# ================================================

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ================== РАБОТА С БАЗОЙ ДАННЫХ ==================
def init_db():
    """Создание таблиц в базе данных"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # Таблица забаненных пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            ban_date TEXT,
            reason TEXT
        )
    ''')
    
    # Таблица для хранения связи сообщений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS message_links (
            original_msg_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            forward_message_id INTEGER,
            channel_message_id INTEGER,
            msg_date TEXT,
            UNIQUE(forward_message_id, channel_message_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def is_user_banned(user_id: int) -> bool:
    """Проверка, забанен ли пользователь"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM banned_users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone() is not None
    conn.close()
    return result

def ban_user(user_id: int, reason: str = "Нарушение правил"):
    """Добавление пользователя в бан"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO banned_users (user_id, ban_date, reason) VALUES (?, ?, ?)',
        (user_id, datetime.now().isoformat(), reason)
    )
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    """Разбан пользователя"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM banned_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def save_message_link(user_id: int, forward_msg_id: int, channel_msg_id: int):
    """Сохранение связи между сообщениями"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO message_links (user_id, forward_message_id, channel_message_id, msg_date) VALUES (?, ?, ?, ?)',
        (user_id, forward_msg_id, channel_msg_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

def get_user_by_message(message_id: int, is_forward: bool = True) -> Union[int, None]:
    """Получение user_id по ID сообщения"""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    if is_forward:
        cursor.execute('SELECT user_id FROM message_links WHERE forward_message_id = ?', (message_id,))
    else:
        cursor.execute('SELECT user_id FROM message_links WHERE channel_message_id = ?', (message_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# ================== КЛАВИАТУРЫ ==================
def get_moderation_keyboard(user_id: int, forward_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для модерации"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"pub_{forward_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"rej_{forward_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🚫 Забанить", callback_data=f"ban_{forward_id}")
    )
    return builder.as_markup()

def get_reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для ответа анонимному пользователю"""
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="✍️ Ответить анонимно", 
        callback_data=f"reply_{user_id}"
    ))
    return builder.as_markup()

# ================== ОБРАБОТЧИКИ КОМАНД ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    user_id = message.from_user.id
    
    # Проверка на бан
    if is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы и не можете отправлять сообщения.")
        return
    
    welcome_text = """
👋 Привет! Я бот для анонимных сообщений в канал.

📝 Просто отправь мне текст, фото или видео, и оно уйдет на модерацию.
🔒 Твоя анонимность гарантирована - админ не увидит твои данные.
⚠️ Помни: ты несешь ответственность за отправленный контент.
    """
    await message.answer(welcome_text)

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    """Панель администратора"""
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ У вас нет прав администратора.")
        return
    
    admin_text = """
🔐 **Панель администратора**

Команды:
/ban [user_id] [причина] - забанить пользователя
/unban [user_id] - разбанить пользователя
/stats - статистика бота
    """
    await message.answer(admin_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика бота"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM banned_users')
    banned_count = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM message_links')
    messages_count = cursor.fetchone()[0]
    
    conn.close()
    
    stats_text = f"""
📊 **Статистика бота**
📝 Всего опубликовано: {messages_count}
🚫 Забанено пользователей: {banned_count}
    """
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(Command("ban"))
async def cmd_ban(message: types.Message):
    """Бан пользователя по ID"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer("❌ Использование: /ban [user_id] [причина]")
        return
    
    try:
        user_id = int(args[1])
        reason = args[2] if len(args) > 2 else "Нарушение правил"
        
        ban_user(user_id, reason)
        await message.answer(f"✅ Пользователь {user_id} забанен. Причина: {reason}")
    except ValueError:
        await message.answer("❌ Некорректный ID пользователя")

@dp.message(Command("unban"))
async def cmd_unban(message: types.Message):
    """Разбан пользователя"""
    if message.from_user.id not in ADMIN_IDS:
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Использование: /unban [user_id]")
        return
    
    try:
        user_id = int(args[1])
        unban_user(user_id)
        await message.answer(f"✅ Пользователь {user_id} разбанен")
    except ValueError:
        await message.answer("❌ Некорректный ID пользователя")

# ================== ОБРАБОТЧИК СООБЩЕНИЙ ОТ ПОЛЬЗОВАТЕЛЕЙ ==================
@dp.message(F.text | F.photo | F.video | F.voice | F.document)
async def handle_user_message(message: types.Message):
    """Обработка входящих сообщений от пользователей"""
    user_id = message.from_user.id
    
    # Проверка на бан
    if is_user_banned(user_id):
        await message.answer("⛔ Вы заблокированы. Вы не можете отправлять сообщения.")
        return
    
    # Сообщение для админов (копия с кнопками)
    admin_text = f"📨 **Новое сообщение от пользователя**\n"
    admin_text += f"🆔 User ID: `{user_id}`\n"
    admin_text += f"👤 Username: @{message.from_user.username or 'отсутствует'}\n"
    admin_text += f"📅 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
    
    # Пересылаем копию админам
    for admin_id in ADMIN_IDS:
        try:
            # Отправляем копию сообщения
            if message.text:
                msg = await bot.send_message(
                    admin_id, 
                    admin_text + f"📝 Текст:\n{message.text}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_moderation_keyboard(user_id, message.message_id)
                )
            elif message.photo:
                # Для фото отправляем подпись отдельно
                caption = message.caption or ""
                sent_msg = await bot.send_photo(
                    admin_id,
                    message.photo[-1].file_id,
                    caption=admin_text + f"📝 Подпись: {caption}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_moderation_keyboard(user_id, message.message_id)
                )
                msg = sent_msg
            elif message.video:
                sent_msg = await bot.send_video(
                    admin_id,
                    message.video.file_id,
                    caption=admin_text + f"📝 Подпись: {message.caption or ''}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_moderation_keyboard(user_id, message.message_id)
                )
                msg = sent_msg
            elif message.voice:
                sent_msg = await bot.send_voice(
                    admin_id,
                    message.voice.file_id,
                    caption=admin_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_moderation_keyboard(user_id, message.message_id)
                )
                msg = sent_msg
            else:
                # Другие типы файлов
                sent_msg = await bot.send_document(
                    admin_id,
                    message.document.file_id,
                    caption=admin_text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_moderation_keyboard(user_id, message.message_id)
                )
                msg = sent_msg
            
            # Сохраняем связь forward_id -> user_id
            save_message_link(user_id, msg.message_id, 0)  # channel_message_id пока 0
            
        except Exception as e:
            logger.error(f"Ошибка отправки админу {admin_id}: {e}")
    
    # Подтверждение пользователю
    await message.answer("✅ Ваше сообщение отправлено на модерацию. После проверки оно появится в канале.")

# ================== ОБРАБОТЧИК КНОПОК ==================
@dp.callback_query(lambda c: c.data.startswith(('pub_', 'rej_', 'ban_', 'reply_')))
async def process_callback(callback: CallbackQuery):
    """Обработка нажатий на кнопки"""
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ У вас нет прав администратора!", show_alert=True)
        return
    
    action, data = callback.data.split('_', 1)
    
    if action == 'pub':
        # Публикация в канал
        forward_id = int(data)
        
        # Получаем user_id по forward_id
        user_id = get_user_by_message(forward_id)
        if not user_id:
            await callback.answer("❌ Ошибка: пользователь не найден", show_alert=True)
            return
        
        # Получаем оригинальное сообщение
        try:
            # Пересылаем сообщение в канал
            forwarded = await bot.forward_message(
                chat_id=CHANNEL_ID,
                from_chat_id=callback.message.chat.id,
                message_id=callback.message.message_id
            )
            
            # Обновляем связь с ID сообщения в канале
            conn = sqlite3.connect('bot_database.db')
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE message_links SET channel_message_id = ? WHERE forward_message_id = ?',
                (forwarded.message_id, forward_id)
            )
            conn.commit()
            conn.close()
            
            # Отправляем уведомление пользователю
            try:
                await bot.send_message(
                    user_id,
                    "✅ Ваше сообщение было опубликовано в канале!"
                )
            except:
                pass  # Пользователь заблокировал бота
            
            # Обновляем сообщение у админа
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ **Опубликовано**",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("✅ Сообщение опубликовано!")
            
        except Exception as e:
            await callback.answer(f"❌ Ошибка публикации: {e}", show_alert=True)
    
    elif action == 'rej':
        # Отклонение сообщения
        forward_id = int(data)
        user_id = get_user_by_message(forward_id)
        
        if user_id:
            try:
                await bot.send_message(
                    user_id,
                    "❌ Ваше сообщение было отклонено модератором."
                )
            except:
                pass
        
        # Удаляем сообщение у админа или помечаем
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ **Отклонено**",
            parse_mode=ParseMode.MARKDOWN
        )
        await callback.answer("❌ Сообщение отклонено")
    
    elif action == 'ban':
        # Бан пользователя
        forward_id = int(data)
        user_id = get_user_by_message(forward_id)
        
        if user_id:
            ban_user(user_id, "Нарушение правил")
            try:
                await bot.send_message(
                    user_id,
                    "⛔ Вы забанены за нарушение правил."
                )
            except:
                pass
            
            # Помечаем сообщение
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.edit_text(
                callback.message.text + f"\n\n🚫 **Пользователь {user_id} забанен**",
                parse_mode=ParseMode.MARKDOWN
            )
            await callback.answer("🚫 Пользователь забанен")
    
    elif action == 'reply':
        # Ответ пользователю
        user_id = int(data)
        
        # Создаем временное состояние для ответа
        await callback.message.answer(
            f"✍️ Введите ответ для пользователя {user_id} (анонимно):"
        )
        
        # Сохраняем в памяти, что этот админ сейчас отвечает этому пользователю
        # В реальном проекте лучше использовать FSM, но для простоты так
        reply_context[callback.from_user.id] = user_id
        
        await callback.answer()

# Хранилище контекста ответов (в реальном проекте заменить на FSM)
reply_context = {}

@dp.message(lambda message: message.from_user.id in ADMIN_IDS and message.text and not message.text.startswith('/'))
async def handle_admin_reply(message: types.Message):
    """Обработка ответа админа пользователю"""
    admin_id = message.from_user.id
    
    if admin_id in reply_context:
        user_id = reply_context[admin_id]
        
        try:
            # Отправляем ответ пользователю
            await bot.send_message(
                user_id,
                f"📨 **Ответ администратора (анонимно):**\n\n{message.text}"
            )
            await message.answer(f"✅ Ответ отправлен пользователю {user_id}")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить ответ: {e}")
        
        # Очищаем контекст
        del reply_context[admin_id]

# ================== ЗАПУСК БОТА ==================
async def main():
    """Главная функция запуска бота"""
    # Инициализация БД
    init_db()
    
    logger.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())