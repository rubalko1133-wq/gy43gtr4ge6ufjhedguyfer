import logging
import sqlite3
import random
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
TOKEN = "8426732266:AAGAokm2pmq-FC9m0Laj3rlgFN328IsaFCw"
ADMIN_IDS = [8287134813, 1431520267]  # ID администраторов
GROUP_CHAT_ID = -1003737353498  # ID группы, куда пересылать сообщения

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

# Генерация случайного ника
def generate_random_nickname():
    adjectives = ['Смелый', 'Храбрый', 'Веселый', 'Умный', 'Быстрый', 'Тихий', 'Яркий']
    nouns = ['Кот', 'Пес', 'Лис', 'Волк', 'Медведь', 'Тигр', 'Дракон']
    number = random.randint(1, 999)
    return f"{random.choice(adjectives)}{random.choice(nouns)}{number}"

# Команда старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("""INSERT OR IGNORE INTO users 
                 (user_id, username, first_name, join_date, is_registered) 
                 VALUES (?, ?, ?, ?, ?)""",
              (user.id, user.username, user.first_name, datetime.now().isoformat(), 0))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "Я буду пересылать ваши сообщения в группу анонимно.\n"
        "Для начала работы зарегистрируйтесь: /register"
    )

# Команда регистрации
async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT is_registered FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result and result[0] == 1:
        await update.message.reply_text("✅ Вы уже зарегистрированы!")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton("🎲 Случайный ник", callback_data="random_nick")],
        [InlineKeyboardButton("✏️ Свой ник", callback_data="custom_nick")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "📝 Регистрация\nВыберите способ:",
        reply_markup=reply_markup
    )
    return REGISTER_NICKNAME

# Обработка выбора ника
async def register_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "random_nick":
        while True:
            nickname = generate_random_nickname()
            if is_nickname_unique(nickname):
                break
        
        user_id = query.from_user.id
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET nickname=?, is_registered=1 WHERE user_id=?", (nickname, user_id))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"✅ Регистрация завершена!\nВаш ник: *{nickname}*",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    elif query.data == "custom_nick":
        await query.edit_message_text(
            "✏️ Введите ник (3-20 символов, буквы/цифры/_):"
        )
        return REGISTER_NICKNAME

# Обработка ввода ника
async def register_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    nickname = update.message.text.strip()
    
    if not nickname.replace('_', '').isalnum() or len(nickname) < 3 or len(nickname) > 20:
        await update.message.reply_text("❌ Некорректный ник. Попробуйте снова:")
        return REGISTER_NICKNAME
    
    if not is_nickname_unique(nickname):
        await update.message.reply_text("❌ Ник занят. Выберите другой:")
        return REGISTER_NICKNAME
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET nickname=?, is_registered=1 WHERE user_id=?", (nickname, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Регистрация завершена! Ваш ник: *{nickname}*", parse_mode='Markdown')
    return ConversationHandler.END

# Отмена
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

# Команда помощи
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
📚 Команды:

/start - Начать
/register - Регистрация
/myprofile - Мой профиль
/changenick - Сменить ник
/help - Помощь

Просто напишите мне сообщение, и оно будет анонимно отправлено в группу!
    """
    await update.message.reply_text(text)

# Профиль
async def my_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT nickname, join_date, messages_count, is_banned FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or not result[0]:
        await update.message.reply_text("❌ Сначала зарегистрируйтесь: /register")
        return
    
    nickname, join_date, msg_count, is_banned = result
    text = f"""
👤 Профиль:
📝 Ник: {nickname}
📅 Регистрация: {join_date[:10]}
💬 Сообщений: {msg_count}
🚫 Статус: {'Забанен' if is_banned else 'Активен'}
    """
    await update.message.reply_text(text)

# Смена ника
async def change_nick_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT is_registered FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if not result or result[0] == 0:
        await update.message.reply_text("❌ Сначала зарегистрируйтесь: /register")
        return ConversationHandler.END
    
    await update.message.reply_text("✏️ Введите новый ник:")
    return REGISTER_NICKNAME

# Обработка смены ника
async def change_nickname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    new_nickname = update.message.text.strip()
    
    if not new_nickname.replace('_', '').isalnum() or len(new_nickname) < 3 or len(new_nickname) > 20:
        await update.message.reply_text("❌ Некорректный ник. Попробуйте снова:")
        return REGISTER_NICKNAME
    
    if not is_nickname_unique(new_nickname):
        await update.message.reply_text("❌ Ник занят. Выберите другой:")
        return REGISTER_NICKNAME
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET nickname=? WHERE user_id=?", (new_nickname, user_id))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ Ник изменен на *{new_nickname}*", parse_mode='Markdown')
    return ConversationHandler.END

# Обработка сообщений от пользователя (пересылка в группу)
async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # Проверяем, что это личное сообщение
    if update.effective_chat.type != 'private':
        return
    
    # Проверяем регистрацию
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    c.execute("SELECT is_registered, is_banned, nickname FROM users WHERE user_id=?", (user.id,))
    result = c.fetchone()
    
    if not result or result[0] == 0:
        conn.close()
        await update.message.reply_text(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /register для регистрации."
        )
        return
    elif result[1] == 1:
        conn.close()
        await update.message.reply_text("❌ Вы забанены и не можете отправлять сообщения.")
        return
    
    nickname = result[2]
    
    # Обновляем счетчик
    c.execute("UPDATE users SET messages_count = messages_count + 1 WHERE user_id=?", (user.id,))
    
    # Сохраняем сообщение
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
    
    if query.data.startswith("complain_"):
        message_id = int(query.data.split("_")[1])
        
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("SELECT nickname, message_text FROM messages WHERE message_id=?", (message_id,))
        msg_info = c.fetchone()
        
        if msg_info:
            reported_nick, msg_text = msg_info
            
            c.execute("""INSERT INTO complaints 
                         (message_id, message_text, complainer_id, reported_nick, reason, timestamp) 
                         VALUES (?, ?, ?, ?, ?, ?)""",
                      (message_id, msg_text, query.from_user.id, reported_nick, 
                       "Жалоба на сообщение", datetime.now().isoformat()))
            conn.commit()
            
            # Уведомление админам
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        admin_id,
                        f"⚠️ Жалоба на {reported_nick}\n"
                        f"Сообщение: {msg_text[:100]}..."
                    )
                except:
                    pass
            
            await query.edit_message_text(
                text=query.message.text + "\n\n✅ Жалоба отправлена",
                reply_markup=None
            )
        else:
            await query.edit_message_text(
                text=query.message.text + "\n\n❌ Сообщение не найдено",
                reply_markup=None
            )
        conn.close()

# Админ-панель
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Нет доступа")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("🚫 Баны", callback_data="admin_bans")],
        [InlineKeyboardButton("⚠️ Жалобы", callback_data="admin_complaints")],
    ]
    await update.message.reply_text("👑 Админ-панель", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if update.effective_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Нет доступа")
        return
    
    conn = sqlite3.connect('anon_bot.db')
    c = conn.cursor()
    
    if query.data == "admin_stats":
        c.execute("SELECT COUNT(*) FROM users")
        total = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_registered=1")
        reg = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users WHERE is_banned=1")
        banned = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM messages")
        msgs = c.fetchone()[0]
        
        text = f"📊 Статистика:\n👥 Всего: {total}\n✅ Зарегистрировано: {reg}\n🚫 Забанено: {banned}\n💬 Сообщений: {msgs}"
        await query.edit_message_text(text)
    
    elif query.data == "admin_bans":
        c.execute("SELECT nickname, user_id FROM users WHERE is_banned=1")
        banned = c.fetchall()
        if not banned:
            await query.edit_message_text("🚫 Нет забаненных")
        else:
            text = "🚫 Забаненные:\n" + "\n".join([f"• {n} (ID: {i})" for n, i in banned])
            await query.edit_message_text(text)
    
    elif query.data == "admin_complaints":
        c.execute("SELECT complaint_id, reported_nick, message_text FROM complaints WHERE status='pending'")
        comps = c.fetchall()
        if not comps:
            await query.edit_message_text("📭 Нет жалоб")
        else:
            text = "⚠️ Жалобы:\n" + "\n".join([f"#{id} на {n}: {t[:30]}..." for id, n, t in comps])
            await query.edit_message_text(text)
    
    conn.close()

# Бан/разбан
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    try:
        nickname = context.args[0]
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Нарушение"
        
        conn = sqlite3.connect('anon_bot.db')
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned=1, ban_reason=? WHERE nickname=?", (reason, nickname))
        affected = c.rowcount
        conn.commit()
        conn.close()
        
        if affected > 0:
            await update.message.reply_text(f"✅ {nickname} забанен")
        else:
            await update.message.reply_text("❌ Пользователь не найден")
    except:
        await update.message.reply_text("❌ Использование: /ban [ник] [причина]")

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
            await update.message.reply_text(f"✅ {nickname} разбанен")
        else:
            await update.message.reply_text("❌ Пользователь не найден")
    except:
        await update.message.reply_text("❌ Использование: /unban [ник]")

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация
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
    
    # Смена ника
    changenick_conv = ConversationHandler(
        entry_points=[CommandHandler("changenick", change_nick_start)],
        states={
            REGISTER_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_nickname)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("myprofile", my_profile))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    
    application.add_handler(register_conv)
    application.add_handler(changenick_conv)
    
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(complain_callback, pattern="^complain_"))
    
    # ВАЖНО: этот обработчик ловит сообщения в ЛС
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_user_message))
    
    print("✅ Бот-пересыльщик запущен!")
    print(f"📨 Сообщения из ЛС будут отправляться в группу {GROUP_CHAT_ID}")
    application.run_polling()

if __name__ == '__main__':
    main()
