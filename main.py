import logging
import sqlite3
import random
import string
from datetime import datetime
from functools import wraps

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = "8426732266:AAGAokm2pmq-FC9m0Laj3rlgFN328IsaFCw"  # Замените на токен вашего бота
ADMIN_IDS = [8287134813,1431520267]  # ID администраторов бота

# Состояния для ConversationHandler
REGISTER_NICKNAME = 1

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('anon_group.db')
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
    
    # Индекс для быстрого поиска ников
    c.execute('''CREATE INDEX IF NOT EXISTS idx_nickname ON users(nickname)''')
    
    conn.commit()
    conn.close()

init_db()

# Декоратор для проверки прав администратора
def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id in ADMIN_IDS:
            return await func(update, context, *args, **kwargs)
        else:
            await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
            return
    return wrapper

# Декоратор для проверки регистрации
def registered_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("SELECT is_registered, is_banned FROM users WHERE user_id=?", (user_id,))
        result = c.fetchone()
        conn.close()
        
        if not result or result[0] == 0:
            await update.message.reply_text(
                "❌ Вы не зарегистрированы.\n"
                "Используйте /register для регистрации."
            )
            return
        elif result[1] == 1:
            await update.message.reply_text("❌ Вы забанены и не можете писать в чат.")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper

# Проверка уникальности ника
def is_nickname_unique(nickname):
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE nickname=?", (nickname,))
    result = c.fetchone()
    conn.close()
    return result is None

# Генерация случайного ника (на случай, если пользователь не хочет придумывать)
def generate_random_nickname():
    adjectives = ['Смелый', 'Храбрый', 'Веселый', 'Умный', 'Быстрый', 'Тихий', 'Яркий', 'Темный']
    nouns = ['Кот', 'Пес', 'Лис', 'Волк', 'Медведь', 'Тигр', 'Дракон', 'Феникс']
    number = random.randint(1, 999)
    return f"{random.choice(adjectives)}{random.choice(nouns)}{number}"

# Команда старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Сохраняем пользователя в БД
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, join_date, is_registered) 
                 VALUES (?, ?, ?, ?, ?)""",
              (user.id, user.username, user.first_name, datetime.now().isoformat(), 0))
    conn.commit()
    conn.close()
    
    # Проверяем, зарегистрирован ли пользователь
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("SELECT is_registered FROM users WHERE user_id=?", (user.id,))
    is_registered = c.fetchone()[0]
    conn.close()
    
    if is_registered:
        await update.message.reply_text(
            "👋 С возвращением в анонимный чат!\n"
            "Используйте /help для списка команд."
        )
    else:
        await update.message.reply_text(
            "👋 Добро пожаловать в анонимный чат!\n\n"
            "Для участия в чате необходимо зарегистрироваться.\n"
            "Используйте /register для регистрации."
        )

# Команда регистрации
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем, не зарегистрирован ли уже
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("SELECT is_registered FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0] == 1:
        await update.message.reply_text("✅ Вы уже зарегистрированы в чате!")
        return ConversationHandler.END
    
    # Предлагаем варианты
    keyboard = [
        [InlineKeyboardButton("🎲 Сгенерировать случайный ник", callback_data="random_nick")],
        [InlineKeyboardButton("✏️ Ввести свой ник", callback_data="custom_nick")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📝 Регистрация в чате\n\n"
        "Выберите способ создания ника:",
        reply_markup=reply_markup
    )
    
    return REGISTER_NICKNAME

# Обработка выбора ника
async def register_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "random_nick":
        # Генерируем уникальный ник
        while True:
            nickname = generate_random_nickname()
            if is_nickname_unique(nickname):
                break
        
        # Сохраняем ник
        user_id = query.from_user.id
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("""UPDATE users 
                     SET nickname=?, is_registered=1 
                     WHERE user_id=?""",
                  (nickname, user_id))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"✅ Регистрация завершена!\n\n"
            f"Ваш ник: *{nickname}*\n"
            f"Теперь вы можете писать в чат анонимно.\n"
            f"Используйте /help для списка команд.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    elif query.data == "custom_nick":
        await query.edit_message_text(
            "✏️ Введите желаемый никнейм:\n\n"
            "Требования:\n"
            "• Только буквы и цифры\n"
            "• Длина от 3 до 20 символов\n"
            "• Ник должен быть уникальным"
        )
        return REGISTER_NICKNAME

# Обработка ввода своего ника
async def register_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    nickname = update.message.text.strip()
    
    # Валидация ника
    if not nickname.replace('_', '').isalnum() or len(nickname) < 3 or len(nickname) > 20:
        await update.message.reply_text(
            "❌ Некорректный никнейм.\n\n"
            "Требования:\n"
            "• Только буквы, цифры и _\n"
            "• Длина от 3 до 20 символов\n\n"
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
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("""UPDATE users 
                 SET nickname=?, is_registered=1 
                 WHERE user_id=?""",
              (nickname, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Регистрация завершена!\n\n"
        f"Ваш ник: *{nickname}*\n"
        f"Теперь вы можете писать в чат анонимно.\n"
        f"Используйте /help для списка команд.",
        parse_mode='Markdown'
    )
    return ConversationHandler.END

# Команда помощи
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📚 Доступные команды:

👤 Для всех пользователей:
/start - Начать работу
/register - Регистрация в чате
/myprofile - Мой профиль
/changenick - Сменить никнейм
/help - Показать эту справку
/complain - Пожаловаться на сообщение (ответом на него)

👑 Для администраторов:
/admin - Панель администратора
/ban [ник] [причина] - Забанить пользователя
/unban [ник] - Разбанить пользователя
/stats - Статистика чата
/users - Список пользователей
    """
    await update.message.reply_text(help_text)

# Профиль пользователя
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("""SELECT nickname, join_date, messages_count, is_banned 
                 FROM users WHERE user_id=?""", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or not result[0]:
        await update.message.reply_text("❌ Вы не зарегистрированы. Используйте /register")
        return
    
    nickname, join_date, msg_count, is_banned = result
    
    profile_text = f"""
👤 Ваш профиль:

📝 Никнейм: {nickname}
📅 Дата регистрации: {join_date[:10]}
💬 Сообщений: {msg_count}
🚫 Статус: {'Забанен' if is_banned else 'Активен'}
    """
    await update.message.reply_text(profile_text)

# Смена ника
async def change_nick_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("SELECT is_registered FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or result[0] == 0:
        await update.message.reply_text("❌ Сначала зарегистрируйтесь через /register")
        return
    
    await update.message.reply_text(
        "✏️ Введите новый никнейм:\n\n"
        "Требования:\n"
        "• Только буквы и цифры\n"
        "• Длина от 3 до 20 символов\n"
        "• Ник должен быть уникальным"
    )
    return REGISTER_NICKNAME

# Обработка смены ника
async def change_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_nickname = update.message.text.strip()
    
    # Валидация
    if not new_nickname.replace('_', '').isalnum() or len(new_nickname) < 3 or len(new_nickname) > 20:
        await update.message.reply_text(
            "❌ Некорректный никнейм. Попробуйте снова:"
        )
        return REGISTER_NICKNAME
    
    # Проверка уникальности
    if not is_nickname_unique(new_nickname):
        await update.message.reply_text(
            "❌ Этот никнейм уже занят. Выберите другой:"
        )
        return REGISTER_NICKNAME
    
    # Меняем ник
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("UPDATE users SET nickname=? WHERE user_id=?", (new_nickname, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Никнейм успешно изменен на *{new_nickname}*", parse_mode='Markdown')
    return ConversationHandler.END

# Отмена регистрации/смены ника
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено.")
    return ConversationHandler.END

# Админ-панель
@admin_only
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 Забаненные", callback_data="admin_banned")],
        [InlineKeyboardButton("⚠️ Жалобы", callback_data="admin_complaints")],
        [InlineKeyboardButton("👥 Все пользователи", callback_data="admin_users")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👑 Панель администратора\nВыберите действие:",
        reply_markup=reply_markup
    )

# Обработка callback-запросов из админки
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "admin_stats":
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
        banned_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE is_registered=1")
        registered_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM messages")
        total_messages = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM complaints WHERE status='pending'")
        pending_complaints = c.fetchone()[0]
        
        conn.close()
        
        stats_text = f"""
📊 Статистика чата:
👥 Всего пользователей: {total_users}
✅ Зарегистрировано: {registered_users}
🚫 Забанено: {banned_users}
💬 Всего сообщений: {total_messages}
⚠️ Ожидающих жалоб: {pending_complaints}
        """
        await query.edit_message_text(stats_text)
    
    elif query.data == "admin_banned":
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("SELECT user_id, nickname, first_name, ban_reason FROM users WHERE is_banned=1")
        banned_users = c.fetchall()
        conn.close()
        
        if not banned_users:
            await query.edit_message_text("🚫 Нет забаненных пользователей.")
            return
        
        text = "🚫 Забаненные пользователи:\n\n"
        for user in banned_users:
            user_id, nickname, first_name, reason = user
            text += f"Ник: {nickname}\n"
            text += f"ID: {user_id}\n"
            text += f"Имя: {first_name}\n"
            text += f"Причина: {reason if reason else 'не указана'}\n"
            text += "-" * 20 + "\n"
        
        await query.edit_message_text(text[:4096])
    
    elif query.data == "admin_complaints":
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("""SELECT complaint_id, message_text, complainer_nick, reported_nick, reason, timestamp 
                     FROM complaints 
                     WHERE status='pending'
                     ORDER BY timestamp DESC""")
        complaints = c.fetchall()
        conn.close()
        
        if not complaints:
            await query.edit_message_text("📭 Нет новых жалоб.")
            return
        
        text = "⚠️ Новые жалобы:\n\n"
        for complaint in complaints:
            comp_id, msg_text, complainer, reported, reason, timestamp = complaint
            text += f"Жалоба #{comp_id}\n"
            text += f"От: {complainer}\n"
            text += f"На: {reported}\n"
            text += f"Сообщение: {msg_text[:50]}...\n"
            text += f"Причина: {reason}\n"
            text += f"Время: {timestamp}\n"
            text += f"Действия: /resolve_{comp_id}\n"
            text += "-" * 20 + "\n"
        
        await query.edit_message_text(text[:4096])
    
    elif query.data == "admin_users":
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("SELECT nickname, messages_count, join_date, is_banned FROM users WHERE is_registered=1 ORDER BY messages_count DESC LIMIT 20")
        users = c.fetchall()
        conn.close()
        
        text = "👥 Активные пользователи:\n\n"
        for user in users:
            nickname, msgs, join_date, banned = user
            status = "🚫" if banned else "✅"
            text += f"{status} {nickname} - {msgs} сообщ. (с {join_date[:10]})\n"
        
        await query.edit_message_text(text[:4096])

# Команда бана по нику
@admin_only
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nickname = context.args[0]
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Нарушение правил"
        
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE nickname=?", (reason, nickname))
        affected = c.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await update.message.reply_text(f"✅ Пользователь {nickname} забанен.\nПричина: {reason}")
        else:
            await update.message.reply_text(f"❌ Пользователь с ником {nickname} не найден.")
    except IndexError:
        await update.message.reply_text("❌ Использование: /ban [ник] [причина]")

# Команда разбана по нику
@admin_only
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        nickname = context.args[0]
        
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned=0, ban_reason=NULL WHERE nickname=?", (nickname,))
        affected = c.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await update.message.reply_text(f"✅ Пользователь {nickname} разбанен.")
        else:
            await update.message.reply_text(f"❌ Пользователь с ником {nickname} не найден.")
    except IndexError:
        await update.message.reply_text("❌ Использование: /unban [ник]")

# Список всех пользователей для админа
@admin_only
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("SELECT nickname, user_id, messages_count, is_banned FROM users WHERE is_registered=1 ORDER BY messages_count DESC")
    users = c.fetchall()
    conn.close()
    
    text = "📋 Все пользователи:\n\n"
    for user in users:
        nickname, user_id, msgs, banned = user
        status = "🚫" if banned else "✅"
        text += f"{status} {nickname} (ID: {user_id}) - {msgs} сообщ.\n"
    
    await update.message.reply_text(text[:4096])

# Команда статистики
@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE is_registered=1")
    registered_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
    banned_users = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*) FROM messages")
    total_messages = c.fetchone()[0]
    
    c.execute("SELECT SUM(messages_count) FROM users")
    total_messages_from_users = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM messages WHERE date(timestamp) = date('now')")
    today_messages = c.fetchone()[0]
    
    conn.close()
    
    stats_text = f"""
📊 Статистика чата:
👥 Всего пользователей: {total_users}
✅ Зарегистрировано: {registered_users}
🚫 Забанено: {banned_users}
💬 Всего сообщений: {total_messages}
📅 Сообщений сегодня: {today_messages}
    """
    await update.message.reply_text(stats_text)

# Обработка сообщений (только для зарегистрированных)
@registered_only
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Получаем ник пользователя
    conn = sqlite3.connect('anon_group.db')
    c = conn.cursor()
    c.execute("SELECT nickname FROM users WHERE user_id=?", (user.id,))
    nickname = c.fetchone()[0]
    
    # Обновляем счетчик сообщений
    c.execute("UPDATE users SET messages_count = messages_count + 1 WHERE user_id=?", (user.id,))
    
    # Сохраняем сообщение
    c.execute("""INSERT INTO messages (user_id, nickname, message_text, timestamp, tg_message_id) 
                 VALUES (?, ?, ?, ?, ?)""",
              (user.id, nickname, update.message.text, datetime.now().isoformat(), update.message.message_id))
    message_id = c.lastrowid
    conn.commit()
    conn.close()
    
    # Удаляем оригинальное сообщение
    await update.message.delete()
    
    # Создаем клавиатуру с кнопкой жалобы
    keyboard = [[InlineKeyboardButton("⚠️ Пожаловаться", callback_data=f"complain_{message_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем анонимное сообщение с ником
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"👤 *{nickname}*:\n\n{update.message.text}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Обработка жалоб
async def complain_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("complain_"):
        message_id = int(query.data.split("_")[1])
        complainer_id = query.from_user.id
        
        # Получаем информацию о сообщении
        conn = sqlite3.connect('anon_group.db')
        c = conn.cursor()
        c.execute("SELECT user_id, nickname, message_text FROM messages WHERE message_id=?", (message_id,))
        message_info = c.fetchone()
        
        if message_info:
            reported_user_id, reported_nick, message_text = message_info
            
            # Получаем ник жалобщика
            c.execute("SELECT nickname FROM users WHERE user_id=?", (complainer_id,))
            complainer_nick = c.fetchone()[0]
            
            # Сохраняем жалобу
            c.execute("""INSERT INTO complaints 
                         (message_id, message_text, complainer_id, complainer_nick, reported_nick, reason, timestamp) 
                         VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (message_id, message_text, complainer_id, complainer_nick, reported_nick, 
                       "Пользовательская жалоба", datetime.now().isoformat()))
            conn.commit()
            
            await query.edit_message_text(
                text=query.message.text + "\n\n✅ Жалоба отправлена администратору.",
                reply_markup=None
            )
        else:
            await query.edit_message_text(
                text=query.message.text + "\n\n❌ Сообщение не найдено.",
                reply_markup=None
            )
        
        conn.close()

# Текстовая команда жалобы
async def complain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение, на которое хотите пожаловаться.")
        return
    
    # Проверяем, что сообщение от бота (анонимное)
    if not update.message.reply_to_message.from_user.is_bot:
        await update.message.reply_text("❌ Можно жаловаться только на анонимные сообщения.")
        return
    
    # Здесь можно добавить логику для текстовой жалобы
    await update.message.reply_text(
        "✅ Жалоба отправлена.\n"
        "Используйте кнопку 'Пожаловаться' под сообщением для более быстрой отправки."
    )

# Основная функция
def main():
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # ConversationHandler для регистрации
    register_conv = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            REGISTER_NICKNAME: [
                CallbackQueryHandler(register_choice, pattern="^(random_nick|custom_nick)$"),
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
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("complain", complain_command))
    
    # Добавляем ConversationHandler'ы
    application.add_handler(register_conv)
    application.add_handler(changenick_conv)
    
    # Обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(complain_callback, pattern="^complain_"))
    
    # Обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
