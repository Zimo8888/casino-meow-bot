import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import threading
import secrets
import io  # اضافه شده برای ساخت فایل متنی در حافظه
import os
import shutil

# ================= تنظیمات ربات =================
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN environment variable is not set.')

# آیدی‌های عددی مالکین ربات
ADMINS = [7105951313, 5103546561]  

CHANNEL_ID = -1004426473744  # آیدی چنل گزارشات واریز و برداشت
CHANNEL_LINK = "https://t.me/casimomeowi" # لینک چنل شما 

MEW_CARDS = {
    "1": {"card": "371095153433", "name": "Zimo°"},
    "2": {"card": "756110198335", "name": " 𝑺𝒊𝒏𝒂"}
}

BOT_PHOTO = "https://postimg.cc/bsFhLBzs"

# ================= تنظیمات گروه‌ها =================
GROUPS_INFO = {
    -1004410278746: {"name": "گپ کازینو میویی", "link": "https://t.me/+EIMTMUbEeftmZDVi"},
    -1004361388414: {"name": "Gp chat meow", "link": "https://t.me/+sQyzswr0cddhOWVk"},
    -1003922581663: {"name": "گپ میویی", "link": "https://t.me/+EfaCLf6aNY05Y2U6"}
}
ALLOWED_GROUPS = list(GROUPS_INFO.keys())

bot = telebot.TeleBot(BOT_TOKEN)

# ================= تنظیمات دیتابیس =================
db_lock = threading.Lock()
DB_PATH = os.getenv('DB_PATH', '/data/bot_data.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# اگر دیتابیس قدیمی در فایل‌سیستم موقت وجود داشته باشد و Volume خالی باشد،
# برای جلوگیری از از دست رفتن اطلاعات آن را یک‌بار به Volume منتقل می‌کنیم.
if DB_PATH != 'bot_data.db' and os.path.exists('bot_data.db') and not os.path.exists(DB_PATH):
    shutil.copy2('bot_data.db', DB_PATH)

conn = sqlite3.connect(DB_PATH, check_same_thread=False)

with db_lock:
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, balance INTEGER, card_number TEXT, card_name TEXT, username TEXT)''')
    try: c.execute("ALTER TABLE users ADD COLUMN mined_coins INTEGER DEFAULT 0")
    except: pass
    try: c.execute("SELECT group_id FROM stats LIMIT 1")
    except sqlite3.OperationalError: c.execute('DROP TABLE IF EXISTS stats')
        
    c.execute('''CREATE TABLE IF NOT EXISTS stats (group_id INTEGER PRIMARY KEY, games_count INTEGER, total_tax INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mines (user_id INTEGER, mine_time REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, link TEXT, reward INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_tasks (user_id INTEGER, task_id INTEGER)''')
    
    for gid in ALLOWED_GROUPS:
        c.execute("INSERT OR IGNORE INTO stats (group_id, games_count, total_tax) VALUES (?, 0, 0)", (gid,))
    conn.commit()

bot_settings = {
    'deposit_locked': False, 'group_game_locked': False, 'withdraw_locked': False, 'support_locked': False,
    'ma_locked': False, 'ma_mine_locked': False, 'ma_acc_locked': False, 'ma_with_locked': False, 'ma_tasks_locked': False,
    'active_card_id': "1"
}
active_games = {}

# ================= توابع کمکی =================
def persian_to_english_num(text):
    if not text: return text
    persian_nums = '۰۱۲۳۴۵۶۷۸۹'
    english_nums = '0123456789'
    for p, e in zip(persian_nums, english_nums): text = text.replace(p, e)
    return text.lower().replace('k', '000').replace('کی', '000')

def mask_data(data):
    s = str(data)
    if len(s) <= 4: return s
    return s[:2] + "****" + s[-2:]

def get_user(user_id):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        return cursor.fetchone()

def add_user(user_id, username):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO users (user_id, balance, card_number, card_name, username, mined_coins) VALUES (?, 0, 'ثبت نشده', 'ثبت نشده', ?, 0)", (user_id, username))
            conn.commit()

def update_balance(user_id, amount, is_mined=False):
    col = "mined_coins" if is_mined else "balance"
    with db_lock:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {col} = {col} + ? WHERE user_id=?", (amount, user_id))
        conn.commit()

def add_game_stat(tax_amount, group_id):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute("UPDATE stats SET games_count = games_count + 1, total_tax = total_tax + ? WHERE group_id = ?", (tax_amount, group_id))
        conn.commit()

def get_balance(user_id, is_mined=False):
    user = get_user(user_id)
    return (user[5] if is_mined else user[1]) if user else 0

# ================= کیبوردها =================
def main_menu(user_id):
    mk = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    mk.add(KeyboardButton("📱 استخراج میوپوینت"))
    mk.add(KeyboardButton("👤 حساب کاربری"), KeyboardButton("💳 افزایش موجودی"))
    mk.add(KeyboardButton("💸 برداشت موجودی"), KeyboardButton("🎧 پشتیبانی"))
    mk.add(KeyboardButton("⚠️ قوانین و گروه ما"))
    if user_id in ADMINS:
        mk.add(KeyboardButton("⚙️ پنل مدیریت"))
    return mk

def cancel_markup():
    mk = ReplyKeyboardMarkup(resize_keyboard=True)
    mk.add(KeyboardButton("🔙 بازگشت"))
    return mk

def check_cancel(message):
    if message.text == "🔙 بازگشت" or message.text == "/start":
        bot.send_message(message.chat.id, "❌ عملیات لغو شد.", reply_markup=main_menu(message.from_user.id))
        return True
    return False

def miniapp_menu(user_id):
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("⛏ ماین کوین", callback_data="ma_mine"))
    mk.add(InlineKeyboardButton("👤 حساب کاربری", callback_data="ma_account"),
           InlineKeyboardButton("💸 برداشت کوین", callback_data="ma_withdraw"))
    mk.add(InlineKeyboardButton("📋 تسک‌ها و زیرمجموعه", callback_data="ma_tasks"),
           InlineKeyboardButton("🔄 انتقال کوین", callback_data="ma_transfer_coin"))
    if user_id in ADMINS: mk.add(InlineKeyboardButton("➕ افزودن تسک (مدیر)", callback_data="ma_add_task"))
    return mk

def get_admin_panel_markup():
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("🔓 واریز" if bot_settings['deposit_locked'] else "🔒 واریز", callback_data="alock_deposit"),
           InlineKeyboardButton("🔓 برداشت" if bot_settings['withdraw_locked'] else "🔒 برداشت", callback_data="alock_withdraw"))
    mk.add(InlineKeyboardButton("🔓 بازی گپ" if bot_settings['group_game_locked'] else "🔒 بازی گپ", callback_data="alock_group_game"),
           InlineKeyboardButton("🔓 پشتیبانی" if bot_settings['support_locked'] else "🔒 پشتیبانی", callback_data="alock_support"))
    mk.add(InlineKeyboardButton("-----------------", callback_data="ignore"))
    mk.add(InlineKeyboardButton("🔓 مینی اپ" if bot_settings['ma_locked'] else "🔒 مینی اپ", callback_data="alock_ma"),
           InlineKeyboardButton("🔓 ماین" if bot_settings['ma_mine_locked'] else "🔒 ماین", callback_data="alock_ma_mine"))
    mk.add(InlineKeyboardButton("🔓 حساب MA" if bot_settings['ma_acc_locked'] else "🔒 حساب MA", callback_data="alock_ma_acc"),
           InlineKeyboardButton("🔓 برداشت MA" if bot_settings['ma_with_locked'] else "🔒 برداشت MA", callback_data="alock_ma_with"))
    mk.add(InlineKeyboardButton("🔓 تسک MA" if bot_settings['ma_tasks_locked'] else "🔒 تسک MA", callback_data="alock_ma_tasks"))
    mk.add(InlineKeyboardButton("-----------------", callback_data="ignore"))
    mk.add(InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"), InlineKeyboardButton("📊 آمار گپ‌ها", callback_data="admin_gap_info"))
    mk.add(InlineKeyboardButton("🎁 کوین همگانی", callback_data="admin_global_coin"), InlineKeyboardButton("🔎 استعلام کاربر", callback_data="admin_check_user"))
    mk.add(InlineKeyboardButton("➖ کسر کوین", callback_data="admin_deduct_coin"), InlineKeyboardButton("➖ کسر سکه", callback_data="admin_deduct_bal"))
    mk.add(InlineKeyboardButton("👥 کاربران ربات", callback_data="admin_users_list"), InlineKeyboardButton("💳 کارت‌های واریز", callback_data="admin_cards"))
    return mk

def get_admin_cards_markup():
    mk = InlineKeyboardMarkup(row_width=2)
    act = bot_settings['active_card_id']
    mk.add(InlineKeyboardButton(f"✅ کارت ۱" if act == "1" else "کارت ۱", callback_data="acard_1"),
           InlineKeyboardButton(f"✅ کارت ۲" if act == "2" else "کارت ۲", callback_data="acard_2"))
    mk.add(InlineKeyboardButton("🔙 بازگشت به پنل", callback_data="admin_back_panel"))
    return mk

# ================= دستورات اصلی PV =================
@bot.message_handler(commands=['start'], func=lambda m: m.chat.type == 'private')
def start_cmd(message):
    user_id = message.from_user.id
    
    is_new = False
    with db_lock:
        if not conn.cursor().execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone():
            is_new = True
            
    if is_new:
        add_user(user_id, message.from_user.username)
        if len(message.text.split()) > 1:
            ref_data = message.text.split()[1]
            if ref_data.startswith("ref_"):
                try:
                    referrer_id = int(ref_data.split("_")[1])
                    if referrer_id != user_id:
                        update_balance(referrer_id, 50, is_mined=True)
                        uname = f"@{message.from_user.username}" if message.from_user.username else str(user_id)
                        bot.send_message(referrer_id, f"🎉 کاربر {uname} با لینک اختصاصی شما وارد ربات شد!\n🎁 50 کوین ماین شده به شما هدیه داده شد.")
                except: pass
    else:
        add_user(user_id, message.from_user.username)

    text = f"🎉 <b>سلام دوست عزیز! به ربات کازینو میویی خوش آمدی!</b>\n\n📢 چنل ما: {CHANNEL_LINK}"
    bot.send_message(message.chat.id, text, reply_markup=main_menu(message.from_user.id), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.chat.type == 'private', content_types=['text'])
def pv_buttons(message):
    user_id = message.from_user.id
    text = message.text
    add_user(user_id, message.from_user.username)

    if text == "📱 استخراج میوپوینت":
        if bot_settings['ma_locked'] and user_id not in ADMINS: return bot.send_message(user_id, "🔒 موقتاً قفل است.")
        msg = f"🪙 <b>استخراج میوپوینت</b> 🪙\n\n✨ به بخش استخراج خوش آمدید!"
        bot.send_message(user_id, msg, reply_markup=miniapp_menu(user_id), parse_mode='HTML')

    elif text == "👤 حساب کاربری":
        user = get_user(user_id)
        msg = f"👤 <b>پروفایل شما:</b>\n\n🆔 آیدی: <code>{user[0]}</code>\n💰 سکه کازینو: <code>{user[1]}</code>\n💎 کوین ماین شده: <code>{user[5]}</code>\n💳 کارت: <code>{user[2]}</code>\n👤 نام اکانت: <code>{user[3]}</code>"
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("⚙️ تنظیم شماره کارت", callback_data="set_card"), InlineKeyboardButton("📝 تنظیم نام اکانت", callback_data="set_card_name"))
        bot.send_message(message.chat.id, msg, reply_markup=mk, parse_mode='HTML')

    elif text == "💳 افزایش موجودی":
        if bot_settings['deposit_locked']: return bot.send_message(user_id, "🔒 موقتاً قفل است.")
        msg = bot.send_message(user_id, "مقدار شارژ (بین 6000 تا 1000000):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_deposit_amount)

    elif text == "💸 برداشت موجودی":
        if bot_settings['withdraw_locked']: return bot.send_message(user_id, "🔒 موقتاً قفل است.")
        user = get_user(user_id)
        if user[2] == 'ثبت نشده' or user[3] == 'ثبت نشده': return bot.send_message(user_id, "⚠️ اول اطلاعات کارت رو ثبت کن.")
        msg = bot.send_message(user_id, f"💰 سکه کازینو: <code>{user[1]}</code>\nمقدار برداشت رو بنویس:", parse_mode='HTML', reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_withdraw_amount, user)

    elif text == "🎧 پشتیبانی":
        if bot_settings['support_locked']: return bot.send_message(user_id, "🔒 موقتاً قفل است.")
        msg = bot.send_message(user_id, "✍️ پیامت رو بنویس:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_support)

    elif text == "⚠️ قوانین و گروه ما":
        mk = InlineKeyboardMarkup(row_width=1)
        for gid, info in GROUPS_INFO.items(): mk.add(InlineKeyboardButton(f"🔗 {info['name']}", url=info['link']))
        bot.send_message(user_id, "برای ورود به گپ‌های ما کلیک کن:", reply_markup=mk)

    elif text == "⚙️ پنل مدیریت" and user_id in ADMINS:
        bot.send_message(user_id, "👨‍💻 پنل مدیریت:", reply_markup=get_admin_panel_markup())

# ================= پردازش واریز/برداشت =================
def process_deposit_amount(message):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        if amt < 6000 or amt > 1000000: raise ValueError
        c_info = MEW_CARDS[bot_settings['active_card_id']]
        text = f"برای دریافت {amt} سکه، <b>{amt*1000}</b> میو پوینت واریز کن.\n💳 <code>{c_info['card']}</code>\n👤 <code>{c_info['name']}</code>\nرسید رو فوروارد کن:"
        msg = bot.send_message(message.chat.id, text, parse_mode='HTML', reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_deposit_receipt, amt)
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد بین 6000 تا 1,000,000 وارد کن (یا بازگشت را بزن):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_deposit_amount)

def process_deposit_receipt(message, amount):
    if check_cancel(message): return
    bot.send_message(message.chat.id, "✅ رسید ارسال شد.", reply_markup=main_menu(message.from_user.id))
    mk = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ تایید", callback_data=f"dep_acc_{message.from_user.id}_{amount}"), InlineKeyboardButton("❌ لغو", callback_data=f"dep_rej_{message.from_user.id}"))
    for admin in ADMINS:
        try:
            bot.forward_message(admin, message.chat.id, message.message_id)
            bot.send_message(admin, f"تایید {amount} سکه به <code>{message.from_user.id}</code>؟", reply_markup=mk, parse_mode='HTML')
        except: pass

def process_withdraw_amount(message, user):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        if amt <= 0 or amt > user[1]: raise ValueError
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ تایید", callback_data=f"with_acc_{amt}"), InlineKeyboardButton("❌ لغو", callback_data="with_rej"))
        bot.send_message(message.chat.id, f"برداشت {amt} سکه\n💳 <code>{user[2]}</code>\n👤 <code>{user[3]}</code>", reply_markup=mk, parse_mode='HTML')
        bot.send_message(message.chat.id, "برای بازگشت به منو از کیبورد استفاده کنید.", reply_markup=main_menu(message.from_user.id))
    except:
        msg = bot.send_message(message.chat.id, "❌ موجودی کافی نیست یا عدد اشتباه است. دوباره وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_withdraw_amount, user)

def process_support(message):
    if check_cancel(message): return
    bot.send_message(message.chat.id, "✅ پیام ارسال شد.", reply_markup=main_menu(message.from_user.id))
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("ℹ️ فرستنده", callback_data=f"sup_info_{message.from_user.id}"),
           InlineKeyboardButton("👁 دیده شد", callback_data=f"sup_seen_{message.from_user.id}"),
           InlineKeyboardButton("💬 پاسخ", callback_data=f"sup_rep_{message.from_user.id}"))
    for admin in ADMINS:
        try:
            bot.forward_message(admin, message.chat.id, message.message_id)
            bot.send_message(admin, "پیام جدید پشتیبانی:", reply_markup=mk)
        except: pass

def send_admin_reply(message, target_id):
    if check_cancel(message): return
    bot.send_message(target_id, f"پاسخ مدیریت:\n\n{message.text}")
    bot.send_message(message.chat.id, "✅ پاسخ ارسال شد.", reply_markup=main_menu(message.from_user.id))

# ================= ابزارهای ادمین =================
def broadcast_message(message):
    if check_cancel(message): return
    with db_lock: users = conn.cursor().execute("SELECT user_id FROM users").fetchall()
    count = sum(1 for u in users if (lambda: bot.send_message(u[0], f"📢 پیام همگانی:\n\n{message.text}") or True)())
    bot.send_message(message.chat.id, f"✅ به {count} نفر ارسال شد.", reply_markup=main_menu(message.from_user.id))

def process_admin_global_coin(message):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        with db_lock:
            c = conn.cursor()
            c.execute("UPDATE users SET mined_coins = mined_coins + ?", (amt,))
            users = c.execute("SELECT user_id FROM users").fetchall()
            conn.commit()
        for u in users:
            try: bot.send_message(u[0], f"🎁 هدیه: {amt} کوین ماین‌شده اضافه شد!")
            except: pass
        bot.send_message(message.chat.id, "✅ انجام شد.", reply_markup=main_menu(message.from_user.id))
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد اشتباه است. مجدد تلاش کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_global_coin)

def process_admin_check_user(message):
    if check_cancel(message): return
    try:
        uid = int(persian_to_english_num(message.text))
        user = get_user(uid)
        if user: bot.send_message(message.chat.id, f"👤 کاربر: <code>{uid}</code>\n💰 سکه کازینو: {user[1]}\n💎 کوین ماین شده: {user[5]}", parse_mode='HTML', reply_markup=main_menu(message.from_user.id))
        else: raise ValueError
    except:
        msg = bot.send_message(message.chat.id, "❌ کاربر یافت نشد یا عدد اشتباه است. دوباره وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_check_user)

def process_admin_deduct_1(message):
    if check_cancel(message): return
    try:
        uid = int(persian_to_english_num(message.text))
        if not get_user(uid): raise ValueError
        msg = bot.send_message(message.chat.id, "مقدار کسر کوین ماین‌شده را بنویس:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_admin_deduct_2(m, uid))
    except:
        msg = bot.send_message(message.chat.id, "❌ آیدی نامعتبر. دوباره وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_deduct_1)

def process_admin_deduct_2(message, uid):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        update_balance(uid, -amt, is_mined=True)
        bot.send_message(message.chat.id, f"✅ مقدار {amt} کوین کسر شد.", reply_markup=main_menu(message.from_user.id))
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد نامعتبر. دوباره وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_admin_deduct_2(m, uid))

def process_admin_deduct_bal_1(message):
    if check_cancel(message): return
    try:
        uid = int(persian_to_english_num(message.text))
        if not get_user(uid): raise ValueError
        msg = bot.send_message(message.chat.id, "مقدار کسر سکه کازینو را بنویس:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_admin_deduct_bal_2(m, uid))
    except:
        msg = bot.send_message(message.chat.id, "❌ آیدی نامعتبر. دوباره وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_deduct_bal_1)

def process_admin_deduct_bal_2(message, uid):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        update_balance(uid, -amt, is_mined=False)
        bot.send_message(message.chat.id, f"✅ مقدار {amt} سکه کسر شد.", reply_markup=main_menu(message.from_user.id))
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد نامعتبر. دوباره وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_admin_deduct_bal_2(m, uid))

def process_set_card(message, field):
    if check_cancel(message): return
    with db_lock:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (message.text, message.from_user.id))
        conn.commit()
    bot.send_message(message.chat.id, "✅ با موفقیت ثبت شد.", reply_markup=main_menu(message.from_user.id))

# ================= کال بک ها =================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data.startswith("alock_") and user_id in ADMINS:
        key = data.replace("alock_", "") + "_locked"
        if key in bot_settings: bot_settings[key] = not bot_settings[key]
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())

    elif data == "admin_broadcast" and user_id in ADMINS:
        msg = bot.send_message(user_id, "پیام همگانی خود را بفرستید:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, broadcast_message)
    elif data == "admin_global_coin" and user_id in ADMINS:
        msg = bot.send_message(user_id, "تعداد کوین برای واریز همگانی را بنویس:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_global_coin)
    elif data == "admin_check_user" and user_id in ADMINS:
        msg = bot.send_message(user_id, "آیدی عددی کاربر را وارد کن:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_check_user)
    elif data == "admin_deduct_coin" and user_id in ADMINS:
        msg = bot.send_message(user_id, "آیدی کاربری که میخوای ازش کوین کسر بشه رو بده:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_deduct_1)
    elif data == "admin_deduct_bal" and user_id in ADMINS:
        msg = bot.send_message(user_id, "آیدی کاربری که میخوای ازش سکه کازینو کسر بشه رو بده:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_admin_deduct_bal_1)
    
    # خروجی گرفتن لیست کاربران به صورت فایل txt
    elif data == "admin_users_list" and user_id in ADMINS:
        bot.answer_callback_query(call.id, "در حال استخراج لیست، لطفاً صبر کنید...")
        with db_lock:
            users = conn.cursor().execute("SELECT user_id, username, card_name, balance, mined_coins FROM users").fetchall()
        
        count = len(users)
        file_content = f"لیست کل کاربران ربات (تعداد: {count} نفر)\n"
        file_content += "-" * 50 + "\n"
        for u in users:
            uname = f"@{u[1]}" if u[1] else "ندارد"
            file_content += f"ID: {u[0]} | Name: {u[2]} | Username: {uname} | Casino: {u[3]} | Mined: {u[4]}\n"
            
        file_data = io.BytesIO(file_content.encode('utf-8'))
        file_data.name = "users_list.txt"
        
        bot.send_document(call.message.chat.id, file_data, caption=f"👥 فایل لیست تمام {count} کاربر ربات")

    elif data == "admin_cards" and user_id in ADMINS:
        bot.edit_message_text("کارت فعال را انتخاب کنید:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_cards_markup())
    elif data.startswith("acard_") and user_id in ADMINS:
        bot_settings['active_card_id'] = data.split('_')[1]
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_cards_markup())
    elif data == "admin_back_panel" and user_id in ADMINS:
        bot.edit_message_text("👨‍💻 پنل مدیریت:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())

    # --- هندلر بازگشت مینی اپ (ویرایش پیام) ---
    elif data == "ma_back":
        msg = f"🪙 <b>استخراج میوپوینت</b> 🪙\n\n✨ به بخش استخراج خوش آمدید!"
        bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=miniapp_menu(user_id), parse_mode='HTML')

    elif data == "ma_mine":
        if bot_settings['ma_mine_locked'] and user_id not in ADMINS: return bot.answer_callback_query(call.id, "بخش ماین قفل است.", show_alert=True)
        now = time.time()
        with db_lock:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(mine_time) FROM mines WHERE user_id=?", (user_id,))
            last = cursor.fetchone()[0] or 0
            cursor.execute("SELECT COUNT(*) FROM mines WHERE user_id=? AND mine_time > ?", (user_id, now - 86400))
            day_count = cursor.fetchone()[0]
            
        if day_count >= 5: return bot.answer_callback_query(call.id, "❌ سقف استخراج روزانه شما (500 کوین) پر شده است. فردا امتحان کنید.", show_alert=True)
        if now - last < 10800:
            rem = int((10800 - (now - last)) / 60)
            return bot.answer_callback_query(call.id, f"⏳ {rem//60} ساعت و {rem%60} دقیقه تا استخراج بعدی...", show_alert=True)
            
        with db_lock:
            conn.cursor().execute("INSERT INTO mines (user_id, mine_time) VALUES (?, ?)", (user_id, now))
            conn.commit()
        update_balance(user_id, 100, is_mined=True)
        bot.answer_callback_query(call.id, "🎉 100 کوین با موفقیت استخراج شد!", show_alert=True)

    elif data == "ma_account":
        if bot_settings['ma_acc_locked'] and user_id not in ADMINS: return bot.answer_callback_query(call.id, "این بخش قفل است.", show_alert=True)
        user = get_user(user_id)
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 بازگشت", callback_data="ma_back"))
        bot.edit_message_text(f"👤 پروفایل <b>{user[4]}</b>\n\n🆔 آیدی: <code>{user[0]}</code>\n💰 سکه کازینو: <code>{user[1]}</code>\n💎 کوین ماین شده: <code>{user[5]}</code>", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')

    elif data == "ma_withdraw":
        if bot_settings['ma_with_locked'] and user_id not in ADMINS: return bot.answer_callback_query(call.id, "قفل است.", show_alert=True)
        user = get_user(user_id)
        if user[5] < 1000: return bot.answer_callback_query(call.id, "❌ حداقل برداشت کوین 1000 است.", show_alert=True)
        bot.answer_callback_query(call.id)
        msg = bot.send_message(user_id, f"💎 کوین: <code>{user[5]}</code>\nچه مقدار میخواهید برداشت کنید؟", parse_mode='HTML', reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_ma_withdraw_1)

    elif data == "ma_transfer_coin":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(user_id, "🆔 آیدی عددی کاربری که می‌خواهی به او کوین انتقال دهی را بنویس:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_ma_transfer_1)

    elif data == "ma_tasks":
        if bot_settings['ma_tasks_locked'] and user_id not in ADMINS: return bot.answer_callback_query(call.id, "قفل است.", show_alert=True)
        with db_lock:
            cursor = conn.cursor()
            tasks = cursor.execute("SELECT * FROM tasks").fetchall()
            completed = [t[0] for t in cursor.execute("SELECT task_id FROM user_tasks WHERE user_id=?", (user_id,)).fetchall()]
        
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton("🎁 دعوت دوستان (50 کوین پاداش)", callback_data="ma_invite_friends"))
        
        for t in tasks:
            if t[0] in completed: continue 
            mk.row(InlineKeyboardButton("🔗 عضویت در کانال", url=t[2]), InlineKeyboardButton(f"🎁 دریافت {t[3]} کوین", callback_data=f"chk_task_{t[0]}"))
            if user_id in ADMINS: mk.row(InlineKeyboardButton("❌ حذف تسک بالا", callback_data=f"del_task_{t[0]}"))
            
        mk.add(InlineKeyboardButton("🔙 بازگشت", callback_data="ma_back"))
        bot.edit_message_text("📋 <b>بخش تسک‌ها و زیرمجموعه‌گیری</b>\n\nبرای دریافت کوین رایگان، در کانال‌های زیر عضو شوید یا دوستان خود را دعوت کنید:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')

    elif data == "ma_invite_friends":
        bot_username = bot.get_me().username
        promo_text = f"""🎰 <b>ربات کازینو میویی</b> 🎰

با این ربات می‌تونید بازی‌های جذاب کازینو و تاس با مبالغ بالای 5 میلیون میو انجام بدید، بدون اینکه لیمیت بشید! 🤑🔥
همچنین با بخش مینی‌اپ می‌تونید کوین رایگان استخراج کنید و برداشت بزنید.

👇 همین الان از طریق لینک اختصاصی من وارد شو و جایزه بگیر:
https://t.me/{bot_username}?start=ref_{user_id}

<i>(این پیام را برای دوستان خود بفرستید. به ازای هر ورود ۵۰ کوین دریافت می‌کنید)</i>"""
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 بازگشت", callback_data="ma_tasks"))
        bot.edit_message_text(promo_text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')

    elif data.startswith("chk_task_"):
        tid = int(data.split('_')[2])
        with db_lock: task = conn.cursor().execute("SELECT chat_id, reward FROM tasks WHERE id=?", (tid,)).fetchone()
        if not task: return bot.answer_callback_query(call.id, "منقضی شده.", show_alert=True)
        try:
            status = bot.get_chat_member(task[0], user_id).status
            if status in ['member', 'administrator', 'creator']:
                with db_lock:
                    c = conn.cursor()
                    if c.execute("SELECT * FROM user_tasks WHERE user_id=? AND task_id=?", (user_id, tid)).fetchone(): return bot.answer_callback_query(call.id, "گرفته‌اید!", show_alert=True)
                    c.execute("INSERT INTO user_tasks (user_id, task_id) VALUES (?, ?)", (user_id, tid))
                    conn.commit()
                update_balance(user_id, task[1], is_mined=True)
                call.data = "ma_tasks"
                callback_handler(call)
                bot.answer_callback_query(call.id, "✅ پاداش با موفقیت دریافت شد!", show_alert=True)
            else: bot.answer_callback_query(call.id, "❌ ابتدا بپیوندید.", show_alert=True)
        except: bot.answer_callback_query(call.id, "❌ ربات در کانال ادمین نیست.", show_alert=True)

    elif data.startswith("del_task_") and user_id in ADMINS:
        tid = int(data.split('_')[2])
        with db_lock:
            conn.cursor().execute("DELETE FROM tasks WHERE id=?", (tid,))
            conn.commit()
        call.data = "ma_tasks"
        callback_handler(call)
        bot.answer_callback_query(call.id, "❌ تسک حذف شد.", show_alert=True)

    elif data == "ma_add_task" and user_id in ADMINS:
        msg = bot.send_message(user_id, "لینک دعوت چنل (مثلا https://t.me/mychannel):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_add_task_1)

    elif data in ["set_card", "set_card_name"]:
        f = 'card_number' if data == "set_card" else 'card_name'
        msg = bot.send_message(call.message.chat.id, "لطفاً اطلاعات را با دقت وارد کنید:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_set_card(m, f))

    elif data.startswith("dep_acc_") and user_id in ADMINS:
        _, _, target_id, amount = data.split('_')
        update_balance(target_id, int(amount))
        bot.edit_message_text("✅ تایید شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, f"✅ {amount} سکه به حساب شما اضافه گردید.")
    elif data.startswith("dep_rej_") and user_id in ADMINS:
        bot.edit_message_text("❌ رد شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(data.split('_')[2], "❌ واریز رد شد. با پشتیبانی در تماس باشید.")

    elif data.startswith("with_acc_"):
        amount = int(data.split('_')[2])
        user = get_user(user_id)
        if user[1] < amount: return bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
        update_balance(user_id, -amount)
        bot.edit_message_text("✅ درخواست برای مدیریت ارسال شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ واریز کردم", callback_data=f"ad_with_acc_{user_id}_{amount}"), InlineKeyboardButton("❌ لغو", callback_data=f"ad_with_rej_{user_id}_{amount}"))
        for admin in ADMINS:
            try: bot.send_message(admin, f"برداشت سکه کازینو:\nمبلغ: {amount}\nآیدی: <code>{user_id}</code>\nکارت: <code>{user[2]}</code>\nنام: <code>{user[3]}</code>", reply_markup=mk, parse_mode='HTML')
            except: pass
        
    elif data in ["with_rej", "ma_with_rej"]:
        bot.edit_message_text("❌ لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data.startswith("ad_with_acc_") and user_id in ADMINS:
        parts = data.split('_')
        target_id, amount = int(parts[3]), int(parts[4])
        user = get_user(target_id)
        bot.edit_message_text("✅ برداشت تایید شد و در کانال گزارش شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "✅ سکه‌ها با موفقیت به کارت شما واریز شد.")
        try:
            ch_mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🤖 ورود به ربات", url=f"https://t.me/{bot.get_me().username}"))
            ch_msg = f"💸 <b>برداشت موفق سکه کازینو</b> 💸\n\n🆔 آیدی: <code>{mask_data(target_id)}</code>\n👤 نام: <code>{user[3]}</code>\n💳 کارت: <code>{mask_data(user[2])}</code>\n💰 مبلغ: {amount} سکه"
            bot.send_message(CHANNEL_ID, ch_msg, reply_markup=ch_mk, parse_mode='HTML')
        except: pass

    elif data.startswith("ad_with_rej_") and user_id in ADMINS:
        parts = data.split('_')
        target_id, amount = int(parts[3]), int(parts[4])
        update_balance(target_id, amount) 
        bot.edit_message_text("❌ لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "❌ برداشت لغو و سکه‌ها برگشت داده شد.")

    elif data.startswith("ad_mawith_acc_") and user_id in ADMINS:
        parts = data.split('_')
        target_id, amount = int(parts[3]), int(parts[4])
        user = get_user(target_id)
        bot.edit_message_text("✅ برداشت کوین تایید و در کانال گزارش شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "✅ مبلغ معادل کوین‌ها به کارت شما واریز شد.")
        try:
            ch_mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🤖 ورود به ربات", url=f"https://t.me/{bot.get_me().username}"))
            ch_msg = f"💎 <b>برداشت موفق کوین ماین شده</b> 💎\n\n🆔 آیدی: <code>{mask_data(target_id)}</code>\n👤 نام: <code>{user[3]}</code>\n💳 کارت: <code>{mask_data(user[2])}</code>\n💰 مبلغ: {amount} کوین"
            bot.send_message(CHANNEL_ID, ch_msg, reply_markup=ch_mk, parse_mode='HTML')
        except: pass

    elif data.startswith("ad_mawith_rej_") and user_id in ADMINS:
        parts = data.split('_')
        target_id, amount = int(parts[3]), int(parts[4])
        update_balance(target_id, amount, is_mined=True)
        bot.edit_message_text("❌ لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "❌ برداشت لغو و کوین ها برگشت داده شد.")

    elif data.startswith("sup_info_") and user_id in ADMINS:
        uid = int(data.split('_')[2])
        u = get_user(uid)
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 برگشت", callback_data=f"sup_back_{uid}"))
        bot.edit_message_text(f"🆔 آیدی: <code>{u[0]}</code>\n👤 @{u[4]}", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')
        
    elif data.startswith("sup_back_") and user_id in ADMINS:
        uid = int(data.split('_')[2])
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("ℹ️ فرستنده", callback_data=f"sup_info_{uid}"),
               InlineKeyboardButton("👁 دیده شد", callback_data=f"sup_seen_{uid}"),
               InlineKeyboardButton("💬 پاسخ", callback_data=f"sup_rep_{uid}"))
        bot.edit_message_text("پیام جدید پشتیبانی:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk)

    elif data.startswith("sup_seen_") and user_id in ADMINS:
        uid = int(data.split('_')[2])
        try: bot.send_message(uid, "👁 پیام شما توسط مدیریت دیده شد.")
        except: pass
        bot.answer_callback_query(call.id, "به کاربر اطلاع داده شد.")

    elif data.startswith("sup_rep_") and user_id in ADMINS:
        msg = bot.send_message(user_id, "پاسخ را بنویس:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, int(data.split('_')[2])))

    elif data == "admin_gap_info" and user_id in ADMINS:
        mk = InlineKeyboardMarkup(row_width=1)
        for gid, info in GROUPS_INFO.items(): mk.add(InlineKeyboardButton(f"📊 {info['name']}", callback_data=f"gstat_{gid}"))
        bot.edit_message_text("گروه را انتخاب کن:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk)
        
    elif data.startswith("gstat_") and user_id in ADMINS:
        gid = int(data.split('_')[1])
        with db_lock: stat = conn.cursor().execute("SELECT games_count, total_tax FROM stats WHERE group_id=?", (gid,)).fetchone() or (0, 0)
        bot.edit_message_text(f"📊 بازی‌ها: {stat[0]}\n💰 مالیات: {stat[1]}", chat_id=call.message.chat.id, message_id=call.message.message_id)

    # ------------------ دکمه های شیشه ای انتقال/کسر گروه ------------------
    elif data.startswith("g_trans_") or data.startswith("g_deduct_"):
        if data == "g_trans_rej":
            return bot.edit_message_text("❌ عملیات لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        
        parts = data.split('_')
        action = parts[1]
        target_id = int(parts[2])
        amount = int(parts[3])
        
        target_user = get_user(target_id)
        target_name = f"@{target_user[4]}" if target_user and target_user[4] else str(target_id)

        if action == "trans":
            if get_balance(call.from_user.id) >= amount:
                update_balance(call.from_user.id, -amount)
                update_balance(target_id, amount)
                bot.edit_message_text(f"✅ انتقال {amount} سکه به {target_name} با موفقیت انجام شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
                
        elif action == "deduct":
            if call.from_user.id in ADMINS:
                update_balance(target_id, -amount)
                bot.edit_message_text(f"✅ کسر {amount} سکه از {target_name} با موفقیت انجام شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)

    # ------------------ هندلر بازی‌ها ------------------
    elif data.startswith("game_sel_"):
        parts = data.split('_')
        if user_id != int(parts[3]): return bot.answer_callback_query(call.id, "❌ این منو برای شما نیست!", show_alert=True)
        active_games[f"{call.message.chat.id}_{call.message.message_id}"] = {'type': parts[2], 'creator': user_id, 'step': 'amount'}
        bot.edit_message_caption(caption="💰 رقم بازی را <b>ریپلای</b> کن.", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='HTML')

    elif data.startswith("g_players_"):
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id not in active_games or active_games[game_id]['creator'] != user_id: return
        active_games[game_id]['max_players'] = int(data.split('_')[2])
        active_games[game_id]['players'] = {user_id: {'score': 0}}
        active_games[game_id]['step'] = 'lobby'
        update_game_lobby(call.message.chat.id, call.message.message_id, game_id)

    elif data == "join_game":
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id not in active_games or active_games[game_id]['step'] != 'lobby': return
        game = active_games[game_id]
        if get_balance(user_id) < game['amount']: return bot.answer_callback_query(call.id, "❌ سکه کافی نداری!", show_alert=True)
        if user_id in game['players']: return bot.answer_callback_query(call.id, "شما در بازی هستید.")
        game['players'][user_id] = {'score': 0}
        
        if len(game['players']) == game['max_players']:
            for p in game['players']: update_balance(p, -game['amount'])
            game['step'] = 'playing'
            if game['type'] == 'shansi':
                bot.edit_message_caption(caption="🎲 انتخاب برنده...", chat_id=call.message.chat.id, message_id=call.message.message_id)
                process_winner_shansi(call.message.chat.id, call.message.message_id, game)
            else:
                bot.edit_message_caption(caption=f"🔥 تکمیل شد!\n{'🎰 گردونه کازینو' if game['type'] == 'casino' else '🎲 تاس'} ریپلی کنید.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        else: update_game_lobby(call.message.chat.id, call.message.message_id, game_id)

    elif data == "cancel_game":
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id in active_games and active_games[game_id]['creator'] == user_id:
            del active_games[game_id]
            bot.edit_message_caption(caption="❌ لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data.startswith("dice_mode_"):
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id not in active_games or active_games[game_id]['creator'] != user_id: return
        active_games[game_id]['dice_mode'] = data.split('_')[2]
        active_games[game_id]['max_players'] = 2
        active_games[game_id]['players'] = {user_id: {'score': 0}}
        active_games[game_id]['step'] = 'lobby'
        update_game_lobby(call.message.chat.id, call.message.message_id, game_id)

# ================= پروسس‌های انتقال کوین ، تسک و مینی اپ =================
def process_ma_transfer_1(message):
    if check_cancel(message): return
    try:
        target_id = int(persian_to_english_num(message.text))
        if target_id == message.from_user.id: raise ValueError
        if not get_user(target_id): return bot.send_message(message.chat.id, "❌ کاربری با این آیدی یافت نشد.", reply_markup=main_menu(message.from_user.id))
        msg = bot.send_message(message.chat.id, "💰 چه مقدار کوین می‌خواهی انتقال دهی؟", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_ma_transfer_2(m, target_id))
    except:
        msg = bot.send_message(message.chat.id, "❌ آیدی نامعتبر است. مجدد بفرست (یا بازگشت):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_ma_transfer_1)

def process_ma_transfer_2(message, target_id):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        sender_id = message.from_user.id
        if amt <= 0 or get_balance(sender_id, is_mined=True) < amt:
            return bot.send_message(message.chat.id, "❌ موجودی کوین شما کافی نیست.", reply_markup=main_menu(sender_id))
        
        update_balance(sender_id, -amt, is_mined=True)
        update_balance(target_id, amt, is_mined=True)
        bot.send_message(sender_id, f"✅ انتقال {amt} کوین به کاربر <code>{target_id}</code> با موفقیت انجام شد.", reply_markup=main_menu(sender_id), parse_mode='HTML')
        try: bot.send_message(target_id, f"🎁 شما مقدار {amt} کوین از آیدی <code>{sender_id}</code> دریافت کردید!", parse_mode='HTML')
        except: pass
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد نامعتبر. مجدد بفرست (یا بازگشت):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_ma_transfer_2(m, target_id))

def process_add_task_1(message):
    if check_cancel(message): return
    link = message.text
    msg = bot.send_message(message.chat.id, "حالا آیدی چنل رو با @ بنویس (مثلا @meowichan):", reply_markup=cancel_markup())
    bot.register_next_step_handler(msg, lambda m: process_add_task_2(m, link))

def process_add_task_2(message, link):
    if check_cancel(message): return
    cid = message.text
    try:
        if bot.get_chat_member(cid, bot.get_me().id).status not in ['administrator', 'creator']:
            msg = bot.send_message(message.chat.id, "❌ ربات در کانال ادمین نیست! اول ادمین کن و دوباره آیدی بفرست:", reply_markup=cancel_markup())
            return bot.register_next_step_handler(msg, lambda m: process_add_task_2(m, link))
        msg = bot.send_message(message.chat.id, "پاداش تسک (کوین) چقدر باشد؟", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_add_task_3(m, link, cid))
    except:
        msg = bot.send_message(message.chat.id, "❌ چنل یافت نشد. ایدی دقیق با @ بفرست:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_add_task_2(m, link))

def process_add_task_3(message, link, cid):
    if check_cancel(message): return
    try:
        rew = int(persian_to_english_num(message.text))
        with db_lock:
            conn.cursor().execute("INSERT INTO tasks (chat_id, link, reward) VALUES (?, ?, ?)", (cid, link, rew))
            conn.commit()
        bot.send_message(message.chat.id, "✅ تسک اضافه شد.", reply_markup=main_menu(message.from_user.id))
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد نامعتبر. دوباره عدد بفرست:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_add_task_3(m, link, cid))

def process_ma_withdraw_1(message):
    if check_cancel(message): return
    try:
        amt = int(persian_to_english_num(message.text))
        user = get_user(message.from_user.id)
        if amt < 1000 or amt > user[5]: raise ValueError
        msg = bot.send_message(message.chat.id, "💳 شماره کارت میویی خود را با دقت وارد کنید:", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, lambda m: process_ma_withdraw_2(m, amt))
    except:
        msg = bot.send_message(message.chat.id, "❌ عدد اشتباه یا موجودی ناکافی. دوباره وارد کن (یا بازگشت):", reply_markup=cancel_markup())
        bot.register_next_step_handler(msg, process_ma_withdraw_1)

def process_ma_withdraw_2(message, amt):
    if check_cancel(message): return
    card = persian_to_english_num(message.text)
    msg = bot.send_message(message.chat.id, "👤 حالا نام مالک کارت را بنویسید:", reply_markup=cancel_markup())
    bot.register_next_step_handler(msg, lambda m: process_ma_withdraw_3(m, amt, card))

def process_ma_withdraw_3(message, amt, card):
    if check_cancel(message): return
    name = message.text
    mk = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ برداشت", callback_data=f"ma_with_cfm_{amt}_{card}_{name}"), InlineKeyboardButton("❌ لغو", callback_data="ma_with_rej"))
    bot.send_message(message.chat.id, f"برداشت {amt} کوین\nکارت: <code>{card}</code>\nنام: {name}\n\n⚠️ دقت فرمایید.", reply_markup=mk, parse_mode='HTML')
    bot.send_message(message.chat.id, "بازگشت به منو:", reply_markup=main_menu(message.from_user.id))

# ================= دستورات گروه =================
@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'], content_types=['text'])
def group_handler(message):
    if message.chat.id not in ALLOWED_GROUPS: return 
    text, user_id = message.text, message.from_user.id
    add_user(user_id, message.from_user.username)

    if text == "موجودی":
        bot.reply_to(message, "موجودی شما:", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(f"{get_balance(user_id):,} سکه", callback_data="ignore")))
    
    elif text.startswith("انتقال "):
        parts = text.split()
        if len(parts) >= 2:
            try: amt = int(persian_to_english_num(parts[1]))
            except: pass
            else:
                target_id = None
                target_name = "کاربر"
                if message.reply_to_message:
                    target_id = message.reply_to_message.from_user.id
                    target_name = message.reply_to_message.from_user.first_name
                elif len(parts) >= 3:
                    tid_str = parts[2].replace("@", "")
                    with db_lock:
                        c = conn.cursor()
                        if tid_str.isdigit(): c.execute("SELECT user_id, username, card_name FROM users WHERE user_id=?", (int(tid_str),))
                        else: c.execute("SELECT user_id, username, card_name FROM users WHERE username=?", (tid_str,))
                        res = c.fetchone()
                    if res:
                        target_id = res[0]
                        target_name = res[2] if res[2] != 'ثبت نشده' else (f"@{res[1]}" if res[1] else str(res[0]))
                    else:
                        return bot.reply_to(message, "❌ کاربر در دیتابیس یافت نشد.")

                if target_id:
                    if target_id == user_id or target_id == bot.get_me().id:
                        return bot.reply_to(message, "❌ به خودتون یا ربات نمیتونید انتقال بدید.")
                    if get_balance(user_id) >= amt > 0:
                        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ تایید", callback_data=f"g_trans_{target_id}_{amt}"), InlineKeyboardButton("❌ لغو", callback_data="g_trans_rej"))
                        bot.reply_to(message, f"انتقال {amt} سکه به {target_name}؟", reply_markup=mk)
                    else:
                        bot.reply_to(message, "❌ موجودی کافی نیست یا مبلغ نامعتبر است.")
    
    elif text.startswith("کسر ") and user_id in ADMINS:
        parts = text.split()
        if len(parts) >= 2:
            try: amt = int(persian_to_english_num(parts[1]))
            except: pass
            else:
                target_id = None
                target_name = "کاربر"
                if message.reply_to_message:
                    target_id = message.reply_to_message.from_user.id
                    target_name = message.reply_to_message.from_user.first_name
                elif len(parts) >= 3:
                    tid_str = parts[2].replace("@", "")
                    with db_lock:
                        c = conn.cursor()
                        if tid_str.isdigit(): c.execute("SELECT user_id, username, card_name FROM users WHERE user_id=?", (int(tid_str),))
                        else: c.execute("SELECT user_id, username, card_name FROM users WHERE username=?", (tid_str,))
                        res = c.fetchone()
                    if res:
                        target_id = res[0]
                        target_name = res[2] if res[2] != 'ثبت نشده' else (f"@{res[1]}" if res[1] else str(res[0]))
                    else:
                        return bot.reply_to(message, "❌ کاربر در دیتابیس یافت نشد.")

                if target_id:
                    if target_id == user_id or target_id == bot.get_me().id:
                        return bot.reply_to(message, "❌ از خودتون یا ربات نمیتونید کسر کنید.")
                    mk = InlineKeyboardMarkup().add(InlineKeyboardButton("✅ تایید", callback_data=f"g_deduct_{target_id}_{amt}"), InlineKeyboardButton("❌ لغو", callback_data="g_trans_rej"))
                    bot.reply_to(message, f"کسر {amt} سکه از {target_name}؟", reply_markup=mk)

    elif text.startswith("/id") and user_id in ADMINS:
        parts = text.split()
        target_id = None
        if message.reply_to_message: target_id = message.reply_to_message.from_user.id
        elif len(parts) > 1:
            try: target_id = int(persian_to_english_num(parts[1]))
            except: pass
        if target_id:
            user = get_user(target_id)
            if user: bot.reply_to(message, f"👤 کاربر: <code>{target_id}</code>\n💰 سکه کازینو: {user[1]}\n💎 کوین ماین شده: {user[5]}", parse_mode='HTML')
            else: bot.reply_to(message, "❌ کاربر یافت نشد.")

    elif text == "بازی":
        if bot_settings['group_game_locked']: return bot.reply_to(message, "🔒 بازی ها بسته هستند.")
        msg = f"🎮 <b>بخش بازی‌ها</b>\n\nبرای شروع انتخاب کنید:"
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("🎲 شانسی", callback_data=f"game_sel_shansi_{user_id}"), InlineKeyboardButton("🎰 کازینو", callback_data=f"game_sel_casino_{user_id}"), InlineKeyboardButton("🎲 تاس", callback_data=f"game_sel_dice_{user_id}"))
        bot.send_photo(message.chat.id, BOT_PHOTO, caption=msg, reply_to_message_id=message.message_id, reply_markup=mk, parse_mode='HTML')
    
    elif message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id:
        game_id = f"{message.chat.id}_{message.reply_to_message.message_id}"
        if game_id in active_games and active_games[game_id]['step'] == 'amount' and active_games[game_id]['creator'] == user_id:
            try:
                amt = int(persian_to_english_num(text))
                if amt < 6000: return bot.reply_to(message, "این ربات برای بازی های بالای 5 میلیون میو طراحی شده (برای بازی کردن رقم بالای 6k وارد کنید)")
                if get_balance(user_id) < amt: return bot.reply_to(message, "موجودی کافی نیست!")
                active_games[game_id]['amount'] = amt
                mk = InlineKeyboardMarkup()
                if active_games[game_id]['type'] == 'dice':
                    mk.add(InlineKeyboardButton("🔹 زوج فرد", callback_data="dice_mode_zojfard"), InlineKeyboardButton("🔸 فرد زوج", callback_data="dice_mode_fardzoj"))
                    mk.add(InlineKeyboardButton("📈 عدد بزرگتر", callback_data="dice_mode_high"), InlineKeyboardButton("📉 عدد کوچکتر", callback_data="dice_mode_low"))
                    bot.edit_message_caption(caption="🎲 حالت تاس:", chat_id=message.chat.id, message_id=message.reply_to_message.message_id, reply_markup=mk)
                else:
                    mk.add(InlineKeyboardButton("👤 2 نفره", callback_data="g_players_2"), InlineKeyboardButton("👥 3 نفره", callback_data="g_players_3"), InlineKeyboardButton("👨‍👩‍👦 4 نفره", callback_data="g_players_4"))
                    bot.edit_message_caption(caption="👥 تعداد بازیکن؟", chat_id=message.chat.id, message_id=message.reply_to_message.message_id, reply_markup=mk)
                bot.delete_message(message.chat.id, message.message_id)
            except: pass

def update_game_lobby(chat_id, msg_id, game_id):
    if game_id not in active_games: return
    game = active_games[game_id]
    tax = int((game['amount'] * game['max_players']) * 0.10)
    text = f"🎮 <b>بازی</b>\n💸 ورود: {game['amount']}\n🏆 جایزه: {(game['amount']*game['max_players'])-tax}\n👥 {len(game['players'])}/{game['max_players']}\n\n"
    for i, pid in enumerate(game['players'].keys(), 1): text += f"{i} _ @{get_user(pid)[4]}\n"
    bot.edit_message_caption(caption=text, chat_id=chat_id, message_id=msg_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("➕ پیوستن", callback_data="join_game"), InlineKeyboardButton("❌ لغو", callback_data="cancel_game")), parse_mode='HTML')

def process_winner_shansi(chat_id, msg_id, game): finalize_game(chat_id, msg_id, game, secrets.choice(list(game['players'].keys())))

@bot.message_handler(content_types=['dice'], func=lambda m: m.chat.type in ['group', 'supergroup'])
def handle_game_dice(message):
    if not message.reply_to_message: return
    game_id = f"{message.chat.id}_{message.reply_to_message.message_id}"
    if game_id not in active_games: return
    game, user_id = active_games[game_id], message.from_user.id
    if game['step'] != 'playing' or user_id not in game['players'] or game['players'][user_id]['score'] != 0: return 
    if game['type'] == 'casino' and message.dice.emoji == '🎰': game['players'][user_id]['score'] = message.dice.value
    elif game['type'] == 'dice' and message.dice.emoji == '🎲': game['players'][user_id]['score'] = message.dice.value
    else: return

    if all(p['score'] > 0 for p in game['players'].values()):
        time.sleep(3) 
        if game['type'] == 'casino':
            scores = sorted(game['players'].items(), key=lambda x: x[1]['score'], reverse=True)
            if scores[0][1]['score'] == scores[1][1]['score']: refund_game(message.chat.id, message.reply_to_message.message_id, game)
            else: finalize_game(message.chat.id, message.reply_to_message.message_id, game, scores[0][0])
        elif game['type'] == 'dice':
            p1, p2 = list(game['players'].keys())[:2]
            s1, s2 = game['players'][p1]['score'], game['players'][p2]['score']
            wid = None
            if game['dice_mode'] == 'zojfard': wid = p1 if s1%2==0 and s2%2==0 else (p2 if s1%2!=0 and s2%2!=0 else None)
            elif game['dice_mode'] == 'fardzoj': wid = p1 if s1%2!=0 and s2%2!=0 else (p2 if s1%2==0 and s2%2==0 else None)
            elif game['dice_mode'] == 'high': wid = p1 if s1>s2 else (p2 if s2>s1 else None)
            elif game['dice_mode'] == 'low': wid = p1 if s1<s2 else (p2 if s2<s1 else None)
            refund_game(message.chat.id, message.reply_to_message.message_id, game) if wid is None else finalize_game(message.chat.id, message.reply_to_message.message_id, game, wid)

def refund_game(chat_id, msg_id, game):
    for pid in game['players']: update_balance(pid, game['amount'])
    bot.edit_message_caption(caption="⚖️ <b>مساوی شد!</b> سکه‌ها برگشت داده شد.", chat_id=chat_id, message_id=msg_id, parse_mode='HTML')
    if f"{chat_id}_{msg_id}" in active_games: del active_games[f"{chat_id}_{msg_id}"]

def finalize_game(chat_id, msg_id, game, winner_id):
    tax = int((game['amount'] * game['max_players']) * 0.10)
    prize = (game['amount'] * game['max_players']) - tax
    update_balance(winner_id, prize)
    add_game_stat(tax, chat_id)
    
    text = "✅ <b>بازی با موفقیت به اتمام رسید!</b>\n\n"
    for pid in game['players']:
        score = f" ({game['players'][pid]['score']})" if game['type'] in ['casino', 'dice'] else ""
        text += f"{'👑 برنده' if pid == winner_id else '💀 بازنده'}: @{get_user(pid)[4]}{score}\n"
    
    text += f"\n💰 جایزه: {prize} (10٪ مالیات کسر شد)"
    
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("🏆 جایزه برنده", callback_data="ignore"), InlineKeyboardButton(f"{prize} 🪙", callback_data="ignore"))
    mk.add(InlineKeyboardButton("💰 موجودی برنده", callback_data="ignore"), InlineKeyboardButton(f"{get_balance(winner_id)}", callback_data="ignore"))
    
    for i, pid in enumerate([p for p in game['players'].keys() if p != winner_id], 1):
        mk.add(InlineKeyboardButton(f"📉 موجودی بازنده {i}", callback_data="ignore"), InlineKeyboardButton(f"{get_balance(pid)}", callback_data="ignore"))

    bot.edit_message_caption(caption=text, chat_id=chat_id, message_id=msg_id, reply_markup=mk, parse_mode='HTML')
    if f"{chat_id}_{msg_id}" in active_games: del active_games[f"{chat_id}_{msg_id}"]

print("Bot is running...")
bot.infinity_polling()
