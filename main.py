import logging
import sqlite3
import random
import warnings
from datetime import datetime
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Подавляем предупреждение
warnings.filterwarnings(
    action="ignore",
    message=r".*CallbackQueryHandler",
    category=PTBUserWarning
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "8426732266:AAGAokm2pmq-FC9m0Laj3rlgFN328IsaFCw"
ADMIN_IDS = [8287134813, 1431520267]  # ID администраторов
GROUP_CHAT_ID = -1003737353498  # ID группы

# Состояния для ConversationHandler
REGISTER_NICKNAME = 1

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  nickname TEXT UNIQUE,
                  join_date TEXT,
                  is_banned INTEGER DEFAULT 0,
                  ban_reason TEXT,
                  is_registered INTEGER DEFAULT 0,
                  messages_count INTEGER DEFAULT 0)''')
    
    # Таблица сообщений
    c.execute('''CREATE TABLE IF NOT EXISTS messages
                 (message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  nickname TEXT,
                  message_text TEXT,
                  timestamp TEXT,
                  tg_message_id INTEGER)''')
    
    # Таблица жалоб
    c.execute('''CREATE TABLE IF NOT EXISTS complaints
                 (complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
                  message_id INTEGER,
                  message_text TEXT,
                  complainer_id INTEGER,
                  complainer_nick TEXT,
                  reported_nick TEXT,
                  reason TEXT,
                  timestamp TEXT,
                  status TEXT DEFAULT 'pending')''')
    
    conn.commit()
    conn.close()

init_db()

# Проверка уникальности ника
def is_nickname_unique(nickname):
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE nickname=?", (nickname,))
    result = c.fetchone()
    conn.close()
    return result is None

# Проверка, зарегистрирован ли пользователь
def is_user_registered(user_id):
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT is_registered, is_banned, nickname FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

# Получение информации о пользователе для админов
def get_user_info(user_id=None, nickname=None):
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    if user_id:
        c.execute("SELECT user_id, username, first_name, nickname, join_date, messages_count, is_banned, ban_reason FROM users WHERE user_id=?", (user_id,))
    elif nickname:
        c.execute("SELECT user_id, username, first_name, nickname, join_date, messages_count, is_banned, ban_reason FROM users WHERE nickname=?", (nickname,))
    else:
        conn.close()
        return None
    result = c.fetchone()
    conn.close()
    return result

# Генерация случайного ника
def generate_random_nickname():
    adjectives = ['Смелый', 'Храбрый', 'Веселый', 'Умный', 'Быстрый', 'Тихий', 'Яркий']
    nouns = ['Кот', 'Пес', 'Лис', 'Волк', 'Медведь', 'Тигр', 'Дракон']
    number = random.randint(1, 999)
    return f"{random.choice(adjectives)}{random.choice(nouns)}{number}"

# Команда старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Сохраняем пользователя в БД, если его еще нет
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, join_date, is_registered) 
                 VALUES (?, ?, ?, ?, ?)""",
              (user.id, user.username, user.first_name, datetime.now().isoformat(), 0))
    conn.commit()
    conn.close()
    
    # Проверяем, зарегистрирован ли пользователь
    result = is_user_registered(user.id)
    
    if result and result[0] == 1:
        # Показываем информацию о привязке аккаунта
        await update.message.reply_text(
            f"👋 С возвращением, *{result[2]}*!\n\n"
            f"🔐 *Ваш аккаунт привязан:*\n"
            f"• Telegram ID: `{user.id}`\n"
            f"• Username: @{user.username if user.username else 'не указан'}\n"
            f"• Имя: {user.first_name}\n"
            f"• Ник в чате: *{result[2]}*\n\n"
            f"📝 Просто напиши мне сообщение, и я отправлю его в группу анонимно.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "👋 Добро пожаловать в анонимный чат!\n\n"
            "🔐 *Для участия нужно привязать аккаунт:*\n"
            "• Выберите никнейм\n"
            "• Он будет привязан к вашему Telegram ID\n"
            "• Никнейм будет виден в группе\n\n"
            "Используй /register для регистрации.",
            parse_mode='Markdown'
        )

# Команда регистрации
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Проверяем, не зарегистрирован ли уже
    result = is_user_registered(user_id)
    
    if result and result[0] == 1:
        await update.message.reply_text(
            f"✅ Вы уже зарегистрированы!\n\n"
            f"🔐 *Привязка аккаунта:*\n"
            f"• Telegram ID: `{user_id}`\n"
            f"• Ваш ник: *{result[2]}*\n"
            f"• Статус: {'✅ Активен' if not result[1] else '🚫 Забанен'}\n\n"
            f"Хотите сменить ник? Используйте /changenick",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    # Показываем информацию о привязке перед регистрацией
    await update.message.reply_text(
        f"🔐 *Привязка аккаунта*\n\n"
        f"Ваш Telegram ID: `{user_id}`\n"
        f"Username: @{user.username if user.username else 'не указан'}\n"
        f"Имя: {user.first_name}\n\n"
        f"Этот ID будет навсегда привязан к выбранному нику.\n"
        f"С одного аккаунта нельзя зарегистрировать несколько ников.\n\n"
        f"Продолжаем регистрацию?",
        parse_mode='Markdown'
    )
    
    keyboard = [
        [InlineKeyboardButton("🎲 Случайный ник", callback_data="random_nick")],
        [InlineKeyboardButton("✏️ Свой ник", callback_data="custom_nick")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_reg")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📝 Выберите способ создания ника:",
        reply_markup=reply_markup
    )
    return REGISTER_NICKNAME

# Обработка выбора ника
async def register_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_reg":
        await query.edit_message_text("❌ Регистрация отменена.")
        return ConversationHandler.END
    
    if query.data == "random_nick":
        # Генерируем уникальный ник
        while True:
            nickname = generate_random_nickname()
            if is_nickname_unique(nickname):
                break
        
        # Сохраняем ник
        user = query.from_user
        user_id = user.id
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("""UPDATE users 
                     SET nickname=?, is_registered=1 
                     WHERE user_id=?""",
                  (nickname, user_id))
        conn.commit()
        conn.close()
        
        # Показываем подтверждение с информацией о привязке
        await query.edit_message_text(
            f"✅ *Регистрация завершена!*\n\n"
            f"🔐 *Аккаунт привязан:*\n"
            f"• Telegram ID: `{user_id}`\n"
            f"• Username: @{user.username if user.username else 'не указан'}\n"
            f"• Имя: {user.first_name}\n"
            f"• Ваш ник: *{nickname}*\n\n"
            f"📝 Теперь просто пишите мне сообщения, и я буду отправлять их в группу.\n"
            f"ℹ️ Для просмотра профиля используйте /myprofile",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    elif query.data == "custom_nick":
        await query.edit_message_text(
            "✏️ Введите желаемый никнейм:\n\n"
            "Требования:\n"
            "• Только буквы, цифры и _\n"
            "• Длина от 3 до 20 символов\n"
            "• Ник должен быть уникальным\n\n"
            "Этот ник будет привязан к вашему Telegram ID."
        )
        return REGISTER_NICKNAME

# Обработка ввода своего ника
async def register_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    nickname = update.message.text.strip()
    
    # Валидация
    if not nickname.replace('_', '').isalnum() or len(nickname) < 3 or len(nickname) > 20:
        await update.message.reply_text(
            "❌ Некорректный никнейм.\n"
            "Используйте только буквы, цифры и _. Длина от 3 до 20.\n"
            "Попробуйте снова:"
        )
        return REGISTER_NICKNAME
    
    # Проверка уникальности
    if not is_nickname_unique(nickname):
        await update.message.reply_text(
            "❌ Этот никнейм уже занят.\n"
            "Пожалуйста, выберите другой:"
        )
        return REGISTER_NICKNAME
    
    # Сохраняем ник
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("""UPDATE users 
                 SET nickname=?, is_registered=1 
                 WHERE user_id=?""",
              (nickname, user_id))
    conn.commit()
    conn.close()
    
    # Показываем подтверждение с информацией о привязке
    await update.message.reply_text(
        f"✅ *Регистрация завершена!*\n\n"
        f"🔐 *Аккаунт привязан:*\n"
        f"• Telegram ID: `{user_id}`\n"
        f"• Username: @{user.username if user.username else 'не указан'}\n"
        f"• Имя: {user.first_name}\n"
        f"• Ваш ник: *{nickname}*\n\n"
        f"📝 Теперь просто пишите мне сообщения, и я буду отправлять их в группу.\n"
        f"ℹ️ Для просмотра профиля используйте /myprofile",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Регистрация отменена.")
    return ConversationHandler.END

# Команда помощи
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📚 *Доступные команды:*

👤 *Для всех:*
/start - Начать работу
/register - Регистрация (привязка аккаунта)
/myprofile - Мой профиль (информация о привязке)
/changenick - Сменить ник
/help - Это меню

📝 *Как пользоваться:*
1. Зарегистрируйтесь через /register
2. Ваш Telegram ID привяжется к нику
3. Пишите сообщения - они уйдут в группу анонимно

👑 *Для админов:*
/admin - Панель управления
/ban [ник] [причина] - Забанить
/unban [ник] - Разбанить
/user [ник или ID] - Информация о пользователе
    """
    await update.message.reply_text(text, parse_mode='Markdown')

# Профиль
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    result = is_user_registered(user_id)
    
    if not result or result[0] == 0:
        await update.message.reply_text("❌ Вы не зарегистрированы. Используйте /register")
        return
    
    is_registered, is_banned, nickname = result
    
    # Получаем дополнительную информацию
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT join_date, messages_count FROM users WHERE user_id=?", (user_id,))
    join_date, msg_count = c.fetchone()
    conn.close()
    
    status = "✅ Активен" if not is_banned else f"🚫 Забанен"
    ban_status = f"\n🚫 Причина бана: {c.fetchone()[0]}" if is_banned else ""
    
    profile_text = f"""
👤 *Ваш профиль:*

🔐 *Привязка аккаунта:*
• Telegram ID: `{user_id}`
• Username: @{user.username if user.username else 'не указан'}
• Имя: {user.first_name}

📝 *Данные в чате:*
• Никнейм: *{nickname}*
• Дата регистрации: {join_date[:10]}
• Сообщений отправлено: {msg_count}
• Статус: {status}{ban_status}
    """
    await update.message.reply_text(profile_text, parse_mode='Markdown')

# Информация о пользователе для админов
async def user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    try:
        query = ' '.join(context.args)
        
        # Пытаемся найти по ID или нику
        user_info = None
        if query.isdigit():
            user_info = get_user_info(user_id=int(query))
        else:
            user_info = get_user_info(nickname=query)
        
        if not user_info:
            await update.message.reply_text(f"❌ Пользователь не найден: {query}")
            return
        
        user_id, username, first_name, nickname, join_date, msg_count, is_banned, ban_reason = user_info
        
        status = "🚫 Забанен" if is_banned else "✅ Активен"
        ban_info = f"\n• Причина бана: {ban_reason}" if is_banned and ban_reason else ""
        
        text = f"""
👤 *Информация о пользователе:*

🔐 *Аккаунт Telegram:*
• ID: `{user_id}`
• Username: @{username if username else 'не указан'}
• Имя: {first_name}

📝 *Данные в чате:*
• Никнейм: *{nickname}*
• Дата регистрации: {join_date[:10]}
• Сообщений: {msg_count}
• Статус: {status}{ban_info}
        """
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except IndexError:
        await update.message.reply_text("❌ Использование: /user [ник или ID]")

# Смена ника
async def change_nick_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    result = is_user_registered(user_id)
    
    if not result or result[0] == 0:
        await update.message.reply_text("❌ Сначала зарегистрируйтесь через /register")
        return ConversationHandler.END
    
    await update.message.reply_text(
        f"✏️ *Смена ника*\n\n"
        f"Текущий ник: *{result[2]}*\n"
        f"Telegram ID: `{user_id}` (останется привязанным)\n\n"
        f"Введите новый никнейм:",
        parse_mode='Markdown'
    )
    return REGISTER_NICKNAME

# Обработка смены ника
async def change_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    new_nickname = update.message.text.strip()
    
    # Валидация
    if not new_nickname.replace('_', '').isalnum() or len(new_nickname) < 3 or len(new_nickname) > 20:
        await update.message.reply_text(
            "❌ Некорректный никнейм. Попробуйте снова:"
        )
        return REGISTER_NICKNAME
    
    # Проверка уникальности (исключая текущего пользователя)
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE nickname=? AND user_id!=?", (new_nickname, user_id))
    if c.fetchone():
        await update.message.reply_text("❌ Этот никнейм уже занят. Выберите другой:")
        conn.close()
        return REGISTER_NICKNAME
    
    # Меняем ник
    c.execute("UPDATE users SET nickname=? WHERE user_id=?", (new_nickname, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ *Никнейм изменен!*\n\n"
        f"🔐 Привязка к Telegram ID `{user_id}` сохранена.\n"
        f"📝 Новый ник: *{new_nickname}*",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# Обработка сообщений от пользователя (пересылка в группу)
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем, что это личное сообщение
    if update.effective_chat.type != 'private':
        return
    
    # Проверяем регистрацию
    result = is_user_registered(user.id)
    
    if not result:
        # Пользователя нет в БД - создаем запись
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("""INSERT INTO users 
                     (user_id, username, first_name, join_date, is_registered) 
                     VALUES (?, ?, ?, ?, ?)""",
                  (user.id, user.username, user.first_name, datetime.now().isoformat(), 0))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /register для регистрации и привязки аккаунта."
        )
        return
    
    is_registered, is_banned, nickname = result
    
    if is_registered == 0:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /register для регистрации и привязки аккаунта."
        )
        return
    
    if is_banned == 1:
        await update.message.reply_text("❌ Вы забанены и не можете отправлять сообщения.")
        return
    
    # Обновляем счетчик сообщений
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET messages_count = messages_count + 1 WHERE user_id=?", (user.id,))
    
    # Сохраняем сообщение в историю
    c.execute("""INSERT INTO messages (user_id, nickname, message_text, timestamp) 
                 VALUES (?, ?, ?, ?)""",
              (user.id, nickname, update.message.text, datetime.now().isoformat()))
    message_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Создаем клавиатуру для жалоб
    keyboard = [[InlineKeyboardButton("⚠️ Пожаловаться", callback_data=f"complain_{message_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение в группу
    try:
        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=f"👤 *{nickname}*:\n\n{update.message.text}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        await update.message.reply_text("✅ Сообщение отправлено в группу!")
    except Exception as e:
        logger.error(f"Ошибка отправки в группу: {e}")
        await update.message.reply_text("❌ Ошибка при отправке. Попробуйте позже.")

# Обработка жалоб
async def complain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not query.data.startswith("complain_"):
        return
    
    message_id = int(query.data.split("_")[1])
    complainer_id = query.from_user.id
    
    # Получаем информацию о сообщении, на которое жалуются
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id, nickname, message_text FROM messages WHERE message_id=?", (message_id,))
    msg_info = c.fetchone()
    
    if not msg_info:
        await query.edit_message_text(
            text=query.message.text + "\n\n❌ Сообщение не найдено",
            reply_markup=None
        )
        conn.close()
        return
    
    reported_user_id, reported_nick, msg_text = msg_info
    
    # Получаем ник жалобщика
    c.execute("SELECT nickname FROM users WHERE user_id=?", (complainer_id,))
    complainer = c.fetchone()
    complainer_nick = complainer[0] if complainer else "Неизвестно"
    
    # Сохраняем жалобу
    c.execute("""INSERT INTO complaints 
                 (message_id, message_text, complainer_id, complainer_nick, reported_nick, reason, timestamp) 
                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (message_id, msg_text, complainer_id, complainer_nick, reported_nick, 
               "Пользовательская жалоба", datetime.now().isoformat()))
    conn.commit()
    
    # Уведомление админам
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"⚠️ *Новая жалоба!*\n\n"
                f"👤 *От:* {complainer_nick}\n"
                f"👤 *На:* {reported_nick}\n"
                f"💬 *Сообщение:* {msg_text[:100]}...",
                parse_mode='Markdown'
            )
        except:
            pass
    
    await query.edit_message_text(
        text=query.message.text + "\n\n✅ Жалоба отправлена администраторам",
        reply_markup=None
    )
    
    conn.close()

# Админ-панель
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ У вас нет прав администратора.")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 Забаненные", callback_data="admin_bans")],
        [InlineKeyboardButton("⚠️ Жалобы", callback_data="admin_complaints")],
        [InlineKeyboardButton("👥 Все пользователи", callback_data="admin_users")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👑 *Панель администратора*\n\nВыберите действие:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ У вас нет прав администратора.")
        return
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    
    if query.data == "admin_stats":
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_registered=1")
        registered = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
        banned = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM messages")
        messages = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM complaints WHERE status='pending'")
        complaints = c.fetchone()[0]
        
        text = f"""
📊 *Статистика:*

👥 Всего пользователей: {total}
✅ Зарегистрировано: {registered}
🚫 Забанено: {banned}
💬 Сообщений: {messages}
⚠️ Жалоб ожидает: {complaints}
        """
        await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == "admin_bans":
        c.execute("SELECT nickname, user_id, ban_reason FROM users WHERE is_banned=1")
        banned = c.fetchall()
        
        if not banned:
            await query.edit_message_text("🚫 *Нет забаненных пользователей*", parse_mode='Markdown')
        else:
            text = "🚫 *Забаненные пользователи:*\n\n"
            for nick, uid, reason in banned:
                text += f"• *{nick}* (ID: `{uid}`)\n  Причина: {reason or 'не указана'}\n\n"
            await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == "admin_complaints":
        c.execute("""SELECT complaint_id, reported_nick, message_text, timestamp 
                     FROM complaints WHERE status='pending' ORDER BY timestamp DESC LIMIT 10""")
        complaints = c.fetchall()
        
        if not complaints:
            await query.edit_message_text("📭 *Нет новых жалоб*", parse_mode='Markdown')
        else:
            text = "⚠️ *Последние жалобы:*\n\n"
            for cid, nick, msg, ts in complaints:
                text += f"• Жалоба #{cid}\n  На: *{nick}*\n  Сообщение: {msg[:50]}...\n  Время: {ts[:16]}\n\n"
            await query.edit_message_text(text, parse_mode='Markdown')
    
    elif query.data == "admin_users":
        c.execute("SELECT nickname, user_id, messages_count, is_banned FROM users WHERE is_registered=1 ORDER BY messages_count DESC LIMIT 20")
        users = c.fetchall()
        
        text = "👥 *Активные пользователи:*\n\n"
        for nick, uid, msgs, banned in users:
            status = "🚫" if banned else "✅"
            text += f"{status} *{nick}* (ID: `{uid}`) — {msgs} сообщ.\n"
        
        await query.edit_message_text(text, parse_mode='Markdown')
    
    conn.close()

# Бан пользователя
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    try:
        nickname = context.args[0]
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Нарушение правил"
        
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE nickname=?", (reason, nickname))
        affected = c.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await update.message.reply_text(f"✅ Пользователь *{nickname}* забанен.\nПричина: {reason}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Пользователь с ником *{nickname}* не найден.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("❌ Использование: /ban [ник] [причина]")

# Разбан пользователя
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    try:
        nickname = context.args[0]
        
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE nickname=?", (nickname,))
        affected = c.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await update.message.reply_text(f"✅ Пользователь *{nickname}* разбанен.", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Пользователь с ником *{nickname}* не найден.", parse_mode='Markdown')
    except IndexError:
        await update.message.reply_text("❌ Использование: /unban [ник]")

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    
    # ConversationHandler для регистрации
    register_conv = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            REGISTER_NICKNAME: [
                CallbackQueryHandler(register_choice, pattern="^(random_nick|custom_nick|cancel_reg)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, register_nickname)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # ConversationHandler для смены ника
    changenick_conv = ConversationHandler(
        entry_points=[CommandHandler("changenick", change_nick_start)],
        states={
            REGISTER_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_nickname)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myprofile", my_profile))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("user", user_info))
    
    application.add_handler(register_conv)
    application.add_handler(changenick_conv)
    
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(complain_callback, pattern="^complain_"))
    
    # Обработчик личных сообщений (пересылка в группу)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, 
        handle_user_message
    ))
    
    print("✅ Бот-пересыльщик запущен!")
    print(f"📨 Сообщения из ЛС будут отправляться в группу с ID: {GROUP_CHAT_ID}")
    print(f"👑 Администраторы: {ADMIN_IDS}")
    print("🔐 Привязка аккаунта: включена (Telegram ID <-> Ник)")
    
    application.run_polling()

if __name__ == '__main__':
    main()
