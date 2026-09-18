import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import time
import threading
import secrets
import os

# ================= تنظیمات ربات =================
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN environment variable is not set')
ADMIN_ID = 7105951313  # آیدی عددی شما (مالک)

CHANNEL_ID = -1004426473744  # آیدی چنل گزارشات واریز و برداشت
CHANNEL_LINK = "https://t.me/trustcasinomeowi" # لینک چنل شما برای پیام استارت

MY_MEW_CARD = "371095153433"  # شماره کارت میویی شما
MY_MEW_NAME = "Zimo°"  # نام اکانت شما

# عکس پروفایل ربات برای بازی (حتماً یک لینک مستقیم مثل اینگور یا آیدی عکس در تلگرام باشد)
BOT_PHOTO = "https://postimg.cc/bsFhLBzs"

# ================= تنظیمات گروه‌ها =================
# آیدی، نام و لینک گپ‌های خود را اینجا وارد کنید (میتوانید هر تعداد که خواستید اضافه کنید)
GROUPS_INFO = {
    -1004410278746: {"name": "گپ کازینو میویی", "link": "https://t.me/+EIMTMUbEeftmZDVi"},
    -1004361388414: {"name": "Gp chat meow", "link": "https://t.me/+sQyzswr0cddhOWVk"},
    -1003922581663: {"name": "گپ میویی", "link": "https://t.me/+EfaCLf6aNY05Y2U6"}
}
ALLOWED_GROUPS = list(GROUPS_INFO.keys())

bot = telebot.TeleBot(BOT_TOKEN)

# ================= تنظیمات دیتابیس =================
db_lock = threading.Lock()
conn = sqlite3.connect('bot_data.db', check_same_thread=False)

with db_lock:
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, balance INTEGER, card_number TEXT, card_name TEXT, username TEXT)''')
    
    # آپدیت هوشمند دیتابیس (جلوگیری از ارور تغییر ساختار جدول قدیمی)
    try:
        c.execute("SELECT group_id FROM stats LIMIT 1")
    except sqlite3.OperationalError:
        c.execute('DROP TABLE IF EXISTS stats')
        
    c.execute('''CREATE TABLE IF NOT EXISTS stats (group_id INTEGER PRIMARY KEY, games_count INTEGER, total_tax INTEGER)''')
    
    # ساخت دیتابیس مجزا برای هر گروه
    for gid in ALLOWED_GROUPS:
        c.execute("INSERT OR IGNORE INTO stats (group_id, games_count, total_tax) VALUES (?, 0, 0)", (gid,))
    conn.commit()

bot_settings = {'deposit_locked': False, 'group_game_locked': False, 'withdraw_locked': False, 'support_locked': False}
active_games = {}

# ================= توابع کمکی =================
def persian_to_english_num(text):
    if not text: return text
    persian_nums = '۰۱۲۳۴۵۶۷۸۹'
    english_nums = '0123456789'
    for p, e in zip(persian_nums, english_nums):
        text = text.replace(p, e)
    text = text.lower().replace('k', '000').replace('کی', '000')
    return text

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
            cursor.execute("INSERT INTO users (user_id, balance, card_number, card_name, username) VALUES (?, 0, 'ثبت نشده', 'ثبت نشده', ?)", (user_id, username))
            conn.commit()

def update_balance(user_id, amount):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))
        conn.commit()

def add_game_stat(tax_amount, group_id):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute("UPDATE stats SET games_count = games_count + 1, total_tax = total_tax + ? WHERE group_id = ?", (tax_amount, group_id))
        conn.commit()

def get_balance(user_id):
    user = get_user(user_id)
    return user[1] if user else 0

def update_db_field(message, field):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (message.text, message.from_user.id))
        conn.commit()
    bot.send_message(message.chat.id, "✅ با موفقیت ثبت شد.")

# ================= کیبوردها =================
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("👤 حساب کاربری"), KeyboardButton("💳 افزایش موجودی"))
    markup.add(KeyboardButton("💸 برداشت موجودی"), KeyboardButton("🎧 پشتیبانی"))
    markup.add(KeyboardButton("⚠️ قوانین و گروه ما"))
    if user_id == ADMIN_ID:
        markup.add(KeyboardButton("⚙️ پنل مدیریت"))
    return markup

def get_admin_panel_markup():
    mk = InlineKeyboardMarkup(row_width=2)
    st_dep = "🔓 قفل واریز" if bot_settings['deposit_locked'] else "🔒 بستن واریز"
    st_with = "🔓 قفل برداشت" if bot_settings['withdraw_locked'] else "🔒 بستن برداشت"
    st_game = "🔓 قفل بازی‌ها" if bot_settings['group_game_locked'] else "🔒 بستن بازی گپ"
    st_sup = "🔓 قفل پشتیبانی" if bot_settings['support_locked'] else "🔒 بستن پشتیبانی"
    
    mk.add(
        InlineKeyboardButton(st_dep, callback_data="admin_lock_dep"),
        InlineKeyboardButton(st_with, callback_data="admin_lock_with")
    )
    mk.add(
        InlineKeyboardButton(st_game, callback_data="admin_lock_game"),
        InlineKeyboardButton(st_sup, callback_data="admin_lock_sup")
    )
    mk.add(
        InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        InlineKeyboardButton("📊 اطلاعات گپ‌ها", callback_data="admin_gap_info")
    )
    return mk

# ================= قفل گروه و ورود خروج =================
@bot.message_handler(content_types=['new_chat_members'])
def check_group_membership(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            if message.chat.id not in ALLOWED_GROUPS:
                bot.send_message(message.chat.id, "⛔️ من مجاز به فعالیت در این گروه نیستم. خدانگهدار!")
                bot.leave_chat(message.chat.id)

# ================= دستورات اصلی PV =================
@bot.message_handler(commands=['start'], func=lambda m: m.chat.type == 'private')
def start_cmd(message):
    add_user(message.from_user.id, message.from_user.username)
    text = f"""🎉 <b>سلام دوست عزیز! به ربات سرگرمی و بازی میو خوش آمدی!</b> 🐾
    
با این ربات می‌تونی با سکه‌های میویی بازی کنی، شرط‌بندی کنی و موجودیت رو چند برابر کنی! 💰🎰

📢 چنل ما: {CHANNEL_LINK}

از دکمه‌های زیر برای کار با ربات استفاده کن 👇"""
    bot.send_message(message.chat.id, text, reply_markup=main_menu(message.from_user.id), parse_mode='HTML')

@bot.message_handler(commands=['help'], func=lambda m: m.chat.type == 'private')
def help_cmd(message):
    text = """ℹ️ <b>راهنمای ربات سرگرمی میو</b> 🐾

🤖 <b>این ربات چیست؟</b>
اینجا میتونی با مبالغ بالای 5 میلیون میو پوینت (معادل 5000 سکه ربات) بازی کنی و لذت ببری.
💱 <b>نرخ تبدیل:</b> هر 1000 سکه در این ربات = 1,000,000 میو پوینت.

🎮 <b>بازی‌ها:</b>
1️⃣ <b>شانسی:</b> سیستم کاملاً تصادفی یک برنده انتخاب میکنه.
2️⃣ <b>کازینو 🎰:</b> گردونه میچرخه و هرکی ترکیب بهتری بیاره برندست.
3️⃣ <b>تاس 🎲:</b> یک بازی دو نفره جذاب (زوج/فرد/بزرگتر/کوچکتر).

💬 <b>پشتیبانی اعداد:</b> ربات اعداد فارسی (۱۲۳) و پسوند k (مثل 6k به جای 6000) رو پشتیبانی میکنه!"""
    bot.send_message(message.chat.id, text, parse_mode='HTML')

# ================= دکمه های اصلی PV =================
@bot.message_handler(func=lambda m: m.chat.type == 'private', content_types=['text'])
def pv_buttons(message):
    user_id = message.from_user.id
    text = message.text
    add_user(user_id, message.from_user.username)

    if text == "👤 حساب کاربری":
        user = get_user(user_id)
        msg = f"""👤 <b>اطلاعات حساب کاربری شما:</b>

🆔 آیدی عددی: <code>{user[0]}</code>
💰 موجودی سکه: <code>{user[1]}</code>
💳 شماره کارت میویی: <code>{user[2]}</code>
👤 نام کارت میویی: <code>{user[3]}</code>"""
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("⚙️ تنظیم شماره کارت میویی", callback_data="set_card"),
               InlineKeyboardButton("📝 نام شماره کارت میویی", callback_data="set_card_name"))
        bot.send_message(message.chat.id, msg, reply_markup=mk, parse_mode='HTML')

    elif text == "💳 افزایش موجودی":
        if bot_settings['deposit_locked']:
            bot.send_message(user_id, "🔒 بخش افزایش موجودی موقتاً توسط مدیریت قفل شده است.")
            return
        msg = bot.send_message(user_id, "لطفاً مقداری که میخواهید شارژ کنید را وارد کنید (حداقل 6000 و حداکثر 1000000):")
        bot.register_next_step_handler(msg, process_deposit_amount)

    elif text == "💸 برداشت موجودی":
        if bot_settings['withdraw_locked']:
            bot.send_message(user_id, "🔒 بخش برداشت موجودی موقتاً توسط مدیریت قفل شده است.")
            return
        user = get_user(user_id)
        if user[2] == 'ثبت نشده' or user[3] == 'ثبت نشده':
            bot.send_message(user_id, "⚠️ ابتدا باید اطلاعات کارت و نام خود را از بخش «حساب کاربری» ثبت کنید.")
            return
        msg = bot.send_message(user_id, f"💰 موجودی فعلی شما: <code>{user[1]}</code> سکه\n\nلطفاً مقدار برداشتی خود را وارد کنید:", parse_mode='HTML')
        bot.register_next_step_handler(msg, process_withdraw_amount, user)

    elif text == "🎧 پشتیبانی":
        if bot_settings['support_locked']:
            bot.send_message(user_id, "🔒 بخش پشتیبانی موقتاً توسط مدیریت قفل شده است.")
            return
        msg = bot.send_message(user_id, "✍️ لطفاً پیام خود را برای مدیریت بنویسید و ارسال کنید:")
        bot.register_next_step_handler(msg, process_support)

    elif text == "⚠️ قوانین و گروه ما":
        mk = InlineKeyboardMarkup(row_width=1)
        for gid, info in GROUPS_INFO.items():
            mk.add(InlineKeyboardButton(f"🔗 ورود به {info['name']}", url=info['link']))
            
        bot.send_message(user_id, "این ربات در هیچ گروهی به جز گروه‌های تایید شده زیر فعالیت نمیکند.\nبرای ورود به گپ‌های ما روی دکمه‌های زیر کلیک کنید:", reply_markup=mk)

    elif text == "⚙️ پنل مدیریت" and user_id == ADMIN_ID:
        bot.send_message(user_id, "👨‍💻 به پنل مدیریت خوش آمدید:", reply_markup=get_admin_panel_markup())

# ================= توابع پردازش PV =================
def process_deposit_amount(message):
    if message.text in ["👤 حساب کاربری", "💳 افزایش موجودی", "💸 برداشت موجودی", "⚙️ پنل مدیریت"]: return
    try:
        amount_text = persian_to_english_num(message.text)
        amount = int(amount_text)
        if amount < 6000 or amount > 1000000:
            bot.send_message(message.chat.id, "❌ مبلغ باید بین 6,000 تا 1,000,000 باشد.")
            return
        
        mew_point = amount * 1000
        text = f"""محاسبه: شما برای دریافت {amount} سکه، باید <b>{mew_point}</b> میو پوینت واریز کنید.
        
💳 شماره کارت: <code>{MY_MEW_CARD}</code>
👤 نام اکانت: <code>{MY_MEW_NAME}</code>

⚠️ لطفاً پیام رسید واریز خود را که از ربات میو دریافت می‌کنید، روی همین پیام <b>فوروارد (Forward)</b> کنید.
(در واریز کردن دقت کافی داشته باشید در غیر این صورت مسئولیت کامل آن به عهده خودتان است)."""
        msg = bot.send_message(message.chat.id, text, parse_mode='HTML')
        bot.register_next_step_handler(msg, process_deposit_receipt, amount)
    except:
        bot.send_message(message.chat.id, "❌ لطفاً فقط عدد وارد کنید.")

def process_deposit_receipt(message, amount):
    if message.text in ["👤 حساب کاربری", "💳 افزایش موجودی"]: return
    bot.send_message(message.chat.id, "✅ رسید شما برای مدیریت ارسال شد. منتظر تایید باشید.")
    
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("✅ تایید", callback_data=f"dep_acc_{message.from_user.id}_{amount}"),
           InlineKeyboardButton("❌ لغو", callback_data=f"dep_rej_{message.from_user.id}"))
    bot.send_message(ADMIN_ID, f"آیا میخواهید ({amount}) سکه به کاربر <code>{message.from_user.id}</code> ارسال کنید؟", reply_markup=mk, parse_mode='HTML')

def process_withdraw_amount(message, user):
    try:
        amount_text = persian_to_english_num(message.text)
        amount = int(amount_text)
        if amount <= 0 or amount > user[1]:
            bot.send_message(message.chat.id, "❌ موجودی کافی نیست یا مبلغ نامعتبر است.")
            return
        
        text = f"""❓ آیا از برداشت خود با این اطلاعات اطمینان دارید؟

💰 مقدار برداشت: {amount} سکه
💳 شماره کارت: <code>{user[2]}</code>
👤 نام اکانت: <code>{user[3]}</code>

⚠️ اگر اطلاعات اشتباه زده باشید مسئولیت آن بر عهده خودتان است."""
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("✅ تایید", callback_data=f"with_acc_{amount}"),
               InlineKeyboardButton("❌ لغو", callback_data="with_rej"))
        bot.send_message(message.chat.id, text, reply_markup=mk, parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, "❌ لطفاً فقط عدد وارد کنید.")

def process_support(message):
    bot.send_message(message.chat.id, "✅ پیام شما با موفقیت برای مدیریت ارسال شد.")
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("ℹ️ اطلاعات فرستنده", callback_data=f"sup_info_{message.from_user.id}"),
           InlineKeyboardButton("👁 دیده شد", callback_data=f"sup_seen_{message.from_user.id}"),
           InlineKeyboardButton("💬 پاسخ", callback_data=f"sup_rep_{message.from_user.id}"))
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(ADMIN_ID, "پیام جدید پشتیبانی:", reply_markup=mk)

def send_admin_reply(message, target_id):
    bot.send_message(target_id, f"پیام از طرف مدیریت:\n\n{message.text}")
    bot.send_message(message.chat.id, "✅ پاسخ ارسال شد.")

def broadcast_message(message):
    with db_lock:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        
    count = 0
    for u in users:
        try:
            bot.send_message(u[0], f"📢 پیام همگانی:\n\n{message.text}")
            count += 1
        except: pass
    bot.send_message(message.chat.id, f"✅ پیام به {count} نفر ارسال شد.")

# ================= کال بک ها (دکمه های شیشه ای) =================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data == "set_card":
        msg = bot.send_message(call.message.chat.id, "لطفاً شماره کارت میویی خود را با دقت وارد کنید (مسئولیت اشتباه وارد کردن با شماست):")
        bot.register_next_step_handler(msg, lambda m: update_db_field(m, 'card_number'))
    elif data == "set_card_name":
        msg = bot.send_message(call.message.chat.id, "لطفاً نام اکانت میویی خود را وارد کنید:")
        bot.register_next_step_handler(msg, lambda m: update_db_field(m, 'card_name'))

    elif data.startswith("dep_acc_") and user_id == ADMIN_ID:
        _, _, target_id, amount = data.split('_')
        update_balance(target_id, int(amount))
        bot.edit_message_text("✅ تایید شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, f"✅ درخواست واریز شما تایید شد و {amount} سکه به حساب شما اضافه گردید.")
    elif data.startswith("dep_rej_") and user_id == ADMIN_ID:
        target_id = data.split('_')[2]
        bot.edit_message_text("❌ رد شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "❌ افزایش موجودی شما توسط مدیریت رد شد، لطفاً با پشتیبانی در ارتباط باشید.")

    elif data.startswith("with_acc_"):
        amount = int(data.split('_')[2])
        user = get_user(user_id)
        if user[1] < amount:
            bot.answer_callback_query(call.id, "موجودی شما تغییر کرده و کافی نیست!", show_alert=True)
            return
        update_balance(user_id, -amount)
        bot.edit_message_text("✅ درخواست شما برای مدیریت ارسال شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("✅ واریز کردم (تایید)", callback_data=f"ad_with_acc_{user_id}_{amount}"),
               InlineKeyboardButton("❌ لغو برداشت", callback_data=f"ad_with_rej_{user_id}_{amount}"))
        req_msg = f"درخواست برداشت:\nمبلغ: {amount}\nآیدی: <code>{user_id}</code>\nکارت: <code>{user[2]}</code>\nنام: <code>{user[3]}</code>"
        bot.send_message(ADMIN_ID, req_msg, reply_markup=mk, parse_mode='HTML')
        
    elif data == "with_rej":
        bot.edit_message_text("❌ درخواست برداشت موجودی با موفقیت لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data.startswith("ad_with_acc_") and user_id == ADMIN_ID:
        _, _, _, target_id, amount = data.split('_')
        target_id = int(target_id)
        user = get_user(target_id)
        bot.edit_message_text("✅ برداشت تایید و در کانال ثبت شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "✅ میو پوینت ها با موفقیت به حساب شما واریز شد.")
        
        ch_mk = InlineKeyboardMarkup()
        ch_mk.add(InlineKeyboardButton("🤖 ورود به ربات", url=f"https://t.me/{bot.get_me().username}"))
        import datetime
        date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        ch_msg = f"💸 <b>برداشت سکه با موفقیت انجام شد</b> 💸\n\n🆔 آیدی کاربر: <code>{target_id}</code>\n💳 شماره کارت: <code>{user[2]}</code>\n👤 نام اکانت: <code>{user[3]}</code>\n💰 مبلغ برداشت: {amount} سکه\n📅 تاریخ: {date_str}"
        bot.send_message(CHANNEL_ID, ch_msg, reply_markup=ch_mk, parse_mode='HTML')

    elif data.startswith("ad_with_rej_") and user_id == ADMIN_ID:
        _, _, _, target_id, amount = data.split('_')
        update_balance(target_id, int(amount))
        bot.edit_message_text("❌ برداشت لغو و پول برگشت داده شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        bot.send_message(target_id, "❌ درخواست برداشت شما توسط مدیریت لغو شد و موجودی به حساب شما بازگشت.")

    elif data.startswith("sup_info_") and user_id == ADMIN_ID:
        target_id = int(data.split('_')[2])
        user = get_user(target_id)
        msg = f"🆔 آیدی عددی: <code>{user[0]}</code>\n👤 یوزرنیم: @{user[4] or 'ندارد'}\n💳 نام اکانت: {user[3]}"
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("🔙 برگشت", callback_data=f"sup_back_{target_id}"))
        bot.edit_message_text(msg, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')
    elif data.startswith("sup_seen_") and user_id == ADMIN_ID:
        target_id = int(data.split('_')[2])
        bot.send_message(target_id, "👁 پیام شما توسط مدیریت دیده شد.")
        bot.answer_callback_query(call.id, "به کاربر اطلاع داده شد.")
    elif data.startswith("sup_rep_") and user_id == ADMIN_ID:
        target_id = int(data.split('_')[2])
        msg = bot.send_message(ADMIN_ID, "لطفاً پاسخ خود را بنویسید:")
        bot.register_next_step_handler(msg, lambda m: send_admin_reply(m, target_id))
    elif data.startswith("sup_back_") and user_id == ADMIN_ID:
        target_id = int(data.split('_')[2])
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("ℹ️ اطلاعات فرستنده", callback_data=f"sup_info_{target_id}"),
               InlineKeyboardButton("👁 دیده شد", callback_data=f"sup_seen_{target_id}"),
               InlineKeyboardButton("💬 پاسخ", callback_data=f"sup_rep_{target_id}"))
        bot.edit_message_text("پیام جدید پشتیبانی:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk)

    elif data == "admin_lock_dep" and user_id == ADMIN_ID:
        bot_settings['deposit_locked'] = not bot_settings['deposit_locked']
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())
    elif data == "admin_lock_game" and user_id == ADMIN_ID:
        bot_settings['group_game_locked'] = not bot_settings['group_game_locked']
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())
    elif data == "admin_lock_with" and user_id == ADMIN_ID:
        bot_settings['withdraw_locked'] = not bot_settings['withdraw_locked']
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())
    elif data == "admin_lock_sup" and user_id == ADMIN_ID:
        bot_settings['support_locked'] = not bot_settings['support_locked']
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())

    elif data == "admin_broadcast" and user_id == ADMIN_ID:
        msg = bot.send_message(ADMIN_ID, "پیام همگانی خود را بفرستید:")
        bot.register_next_step_handler(msg, broadcast_message)
        
    elif data == "admin_gap_info" and user_id == ADMIN_ID:
        mk = InlineKeyboardMarkup(row_width=1)
        for gid, info in GROUPS_INFO.items():
            mk.add(InlineKeyboardButton(f"📊 اطلاعات {info['name']}", callback_data=f"gstat_{gid}"))
        mk.add(InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back_panel"))
        bot.edit_message_text("لطفاً گروه مورد نظر را برای مشاهده آمار انتخاب کنید:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk)
        
    elif data.startswith("gstat_") and user_id == ADMIN_ID:
        gid = int(data.split('_')[1])
        with db_lock:
            cursor = conn.cursor()
            cursor.execute("SELECT games_count, total_tax FROM stats WHERE group_id=?", (gid,))
            stat = cursor.fetchone()
            if not stat: stat = (0, 0)
            
        info = GROUPS_INFO.get(gid, {"name": "نامشخص", "link": ""})
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton(f"🔄 ریست آمار {info['name']}", callback_data=f"rststat_{gid}"))
        mk.add(InlineKeyboardButton("🔙 بازگشت به لیست گپ‌ها", callback_data="admin_gap_info"))
        
        text = f"""📊 <b>اطلاعات {info['name']}:</b>
        
لینک: <a href='{info['link']}'>کلیک برای ورود</a>

🎮 تعداد کل بازی‌های انجام شده: <b>{stat[0]}</b>
💰 مجموع مالیات کسر شده (سکه): <b>{stat[1]}</b>"""
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')
    
    elif data.startswith("rststat_") and user_id == ADMIN_ID:
        gid = int(data.split('_')[1])
        with db_lock:
            cursor = conn.cursor()
            cursor.execute("UPDATE stats SET games_count=0, total_tax=0 WHERE group_id=?", (gid,))
            conn.commit()
        bot.answer_callback_query(call.id, "آمار این گروه با موفقیت صفر شد!", show_alert=True)
        
        info = GROUPS_INFO.get(gid, {"name": "نامشخص", "link": ""})
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton(f"🔄 ریست آمار {info['name']}", callback_data=f"rststat_{gid}"))
        mk.add(InlineKeyboardButton("🔙 بازگشت به لیست گپ‌ها", callback_data="admin_gap_info"))
        
        text = f"📊 <b>اطلاعات {info['name']}:</b>\n\nلینک: <a href='{info['link']}'>کلیک برای ورود</a>\n\n🎮 تعداد کل بازی‌های انجام شده: <b>0</b>\n💰 مجموع مالیات کسر شده (سکه): <b>0</b>"
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=mk, parse_mode='HTML')

    elif data == "admin_back_panel" and user_id == ADMIN_ID:
        bot.edit_message_text("👨‍💻 به پنل مدیریت خوش آمدید:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=get_admin_panel_markup())

    # --- هندلر بازی های گپ ---
    elif data.startswith("game_sel_"):
        if bot_settings['group_game_locked']:
            bot.answer_callback_query(call.id, "بازی ها بسته است!", show_alert=True)
            return
        g_type = data.split('_')[2]
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        active_games[game_id] = {'type': g_type, 'creator': user_id, 'step': 'amount'}
        bot.edit_message_caption(caption="💰 لطفاً رقم بازی را با <b>ریپلای (Reply)</b> روی همین پیام ارسال کنید.", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='HTML')

    elif data.startswith("g_players_"):
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id not in active_games or active_games[game_id]['creator'] != user_id: return
        count = int(data.split('_')[2])
        active_games[game_id]['max_players'] = count
        active_games[game_id]['players'] = {user_id: {'score': 0}}
        active_games[game_id]['step'] = 'lobby'
        update_game_lobby(call.message.chat.id, call.message.message_id, game_id)

    elif data == "join_game":
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id not in active_games or active_games[game_id]['step'] != 'lobby': return
        game = active_games[game_id]
        
        if get_balance(user_id) < game['amount']:
            bot.answer_callback_query(call.id, "❌ سکه کافی نداری!", show_alert=True)
            return
            
        if user_id in game['players']:
            bot.answer_callback_query(call.id, "شما از قبل در بازی هستید.")
            return

        game['players'][user_id] = {'score': 0}
        
        if len(game['players']) == game['max_players']:
            for p in game['players']:
                update_balance(p, -game['amount'])
            
            game['step'] = 'playing'
            if game['type'] == 'shansi':
                bot.edit_message_caption(caption="🎲 در حال انتخاب برنده به صورت شانسی...", chat_id=call.message.chat.id, message_id=call.message.message_id)
                process_winner_shansi(call.message.chat.id, call.message.message_id, game)
            else:
                extra = "🎰 حالا همه بازیکنان یک گردونه کازینو روی این پیام ریپلی کنند." if game['type'] == 'casino' else "🎲 حالا همه تاس بیندازند (روی پیام ریپلی کنید)."
                bot.edit_message_caption(caption=f"🔥 ظرفیت تکمیل شد!\n{extra}", chat_id=call.message.chat.id, message_id=call.message.message_id)
        else:
            update_game_lobby(call.message.chat.id, call.message.message_id, game_id)

    elif data == "cancel_game":
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id in active_games and active_games[game_id]['creator'] == user_id:
            del active_games[game_id]
            bot.edit_message_caption(caption="❌ بازی توسط برگزار کننده لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)

    elif data.startswith("dice_mode_"):
        game_id = f"{call.message.chat.id}_{call.message.message_id}"
        if game_id not in active_games or active_games[game_id]['creator'] != user_id: return
        mode = data.split('_')[2]
        active_games[game_id]['dice_mode'] = mode
        active_games[game_id]['max_players'] = 2
        active_games[game_id]['players'] = {user_id: {'score': 0}}
        active_games[game_id]['step'] = 'lobby'
        update_game_lobby(call.message.chat.id, call.message.message_id, game_id)

    elif call.data.startswith("g_trans_") or call.data.startswith("g_deduct_"):
        if call.data == "g_trans_rej":
            bot.edit_message_text("❌ عملیات لغو شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            return

        split_data = call.data.split('_')
        action = split_data[1] 
        target_id = int(split_data[2])
        amount = int(split_data[3])

        if action == "trans":
            if get_balance(call.from_user.id) >= amount:
                update_balance(call.from_user.id, -amount)
                update_balance(target_id, amount)
                bot.edit_message_text(f"✅ انتقال {amount} سکه با موفقیت انجام شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)
            else:
                bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
                
        elif action == "deduct":
            update_balance(target_id, -amount)
            bot.edit_message_text(f"✅ کسر {amount} سکه با موفقیت انجام شد.", chat_id=call.message.chat.id, message_id=call.message.message_id)

# ================= دستورات گروه (گپ) =================
@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'], content_types=['text'])
def group_handler(message):
    if message.chat.id not in ALLOWED_GROUPS: return 
    
    text = message.text
    user_id = message.from_user.id
    add_user(user_id, message.from_user.username)

    if text == "موجودی":
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton(f"{get_balance(user_id):,} سکه", callback_data="ignore"))
        bot.reply_to(message, "موجودی شما:", reply_markup=mk)

    elif text.startswith("انتقال "):
        if not message.reply_to_message: return
        target_id = message.reply_to_message.from_user.id
        if target_id == user_id or target_id == bot.get_me().id: return
        
        try:
            amount = int(persian_to_english_num(text.replace("انتقال ", "")))
            if get_balance(user_id) < amount or amount <= 0:
                bot.reply_to(message, "موجودی ناکافی یا مبلغ نامعتبر!")
                return
            mk = InlineKeyboardMarkup()
            mk.add(InlineKeyboardButton("✅ تایید", callback_data=f"g_trans_{target_id}_{amount}"),
                   InlineKeyboardButton("❌ لغو", callback_data="g_trans_rej"))
            bot.reply_to(message, f"آیا میخواهید {amount} سکه به کاربر منتقل کنید؟", reply_markup=mk)
        except: pass

    elif text.startswith("کسر ") and user_id == ADMIN_ID:
        if not message.reply_to_message: return
        target_id = message.reply_to_message.from_user.id
        try:
            amount = int(persian_to_english_num(text.replace("کسر ", "")))
            mk = InlineKeyboardMarkup()
            mk.add(InlineKeyboardButton("✅ تایید", callback_data=f"g_deduct_{target_id}_{amount}"),
                   InlineKeyboardButton("❌ لغو", callback_data="g_trans_rej"))
            bot.reply_to(message, f"آیا از کسر {amount} سکه اطمینان دارید؟", reply_markup=mk)
        except: pass

    elif text.startswith("/id") and user_id == ADMIN_ID:
        target_id = None
        if message.reply_to_message:
            target_id = message.reply_to_message.from_user.id
        else:
            try: target_id = int(text.split(' ')[1])
            except: pass
        if target_id:
            u = get_user(target_id)
            if u: bot.reply_to(message, f"موجودی: {u[1]}\nکارت: {u[2]}\nنام: {u[3]}")

    elif text == "بازی":
        if bot_settings['group_game_locked']:
            bot.reply_to(message, "🔒 بازی ها فعلا بسته هستند.")
            return
        msg = f"🎮 <b>بخش بازی‌ها</b>\n\nبرای شروع یکی از بازی‌های زیر را انتخاب کنید:"
        mk = InlineKeyboardMarkup()
        mk.add(InlineKeyboardButton("🎲 شانسی", callback_data="game_sel_shansi"),
               InlineKeyboardButton("🎰 کازینو", callback_data="game_sel_casino"),
               InlineKeyboardButton("🎲 تاس", callback_data="game_sel_dice"))
        bot.send_photo(message.chat.id, BOT_PHOTO, caption=msg, reply_to_message_id=message.message_id, reply_markup=mk, parse_mode='HTML')

    elif message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id:
        game_id = f"{message.chat.id}_{message.reply_to_message.message_id}"
        if game_id in active_games and active_games[game_id]['step'] == 'amount' and active_games[game_id]['creator'] == user_id:
            try:
                amt = int(persian_to_english_num(text))
                if amt < 6000 or amt > 1000000:
                    bot.reply_to(message, "این ربات برای بازی‌های بالا 5 میلیون میو (6000 سکه) طراحی شده است.")
                    return
                if get_balance(user_id) < amt:
                    bot.reply_to(message, "موجودی شما برای ایجاد این بازی کافی نیست!")
                    return
                
                active_games[game_id]['amount'] = amt
                
                mk = InlineKeyboardMarkup()
                if active_games[game_id]['type'] == 'dice':
                    mk.add(InlineKeyboardButton("🔹 زوج فرد", callback_data="dice_mode_zojfard"),
                           InlineKeyboardButton("🔸 فرد زوج", callback_data="dice_mode_fardzoj"))
                    mk.add(InlineKeyboardButton("📈 عدد بزرگتر", callback_data="dice_mode_high"),
                           InlineKeyboardButton("📉 عدد کوچکتر", callback_data="dice_mode_low"))
                    bot.edit_message_caption(caption="🎲 حالت بازی تاس را انتخاب کنید:", chat_id=message.chat.id, message_id=message.reply_to_message.message_id, reply_markup=mk)
                else:
                    mk.add(InlineKeyboardButton("👤 2 نفره", callback_data="g_players_2"),
                           InlineKeyboardButton("👥 3 نفره", callback_data="g_players_3"),
                           InlineKeyboardButton("👨‍👩‍👦 4 نفره", callback_data="g_players_4"))
                    bot.edit_message_caption(caption="👥 بازی چند نفره باشد؟", chat_id=message.chat.id, message_id=message.reply_to_message.message_id, reply_markup=mk)
                
                bot.delete_message(message.chat.id, message.message_id)
            except: pass

# ================= منطق بازی ها =================
def update_game_lobby(chat_id, msg_id, game_id):
    if game_id not in active_games: return
    game = active_games[game_id]
    
    g_type_name = {'shansi':'شانسی 🎲', 'casino':'کازینو 🎰', 'dice': 'تاس 🎲'}[game['type']]
    tax = int((game['amount'] * game['max_players']) * 0.10)
    prize = (game['amount'] * game['max_players']) - tax
    
    text = f"""🎮 <b>بازی {g_type_name}</b>

💸 <b>مبلغ ورود:</b> {game['amount']} سکه
🏆 <b>جایزه برنده:</b> {prize} سکه (با کسر 10٪ مالیات)
👥 <b>ظرفیت:</b> {len(game['players'])}/{game['max_players']}

<b>بازیکنان:</b>\n"""
    
    for i, pid in enumerate(game['players'].keys(), 1):
        u = get_user(pid)
        name = f"@{u[4]}" if u[4] else str(pid)
        role = " (برگزار کننده)" if i==1 else ""
        text += f"{i} _ {name}{role}\n"

    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("➕ پیوستن به بازی", callback_data="join_game"))
    mk.add(InlineKeyboardButton("❌ لغو بازی", callback_data="cancel_game"))
    
    bot.edit_message_caption(caption=text, chat_id=chat_id, message_id=msg_id, reply_markup=mk, parse_mode='HTML')

def process_winner_shansi(chat_id, msg_id, game):
    players = list(game['players'].keys())
    winner_id = secrets.choice(players)  
    finalize_game(chat_id, msg_id, game, winner_id)

@bot.message_handler(content_types=['dice'], func=lambda m: m.chat.type in ['group', 'supergroup'])
def handle_game_dice(message):
    if message.chat.id not in ALLOWED_GROUPS: return 

    if not message.reply_to_message: return
    game_id = f"{message.chat.id}_{message.reply_to_message.message_id}"
    if game_id not in active_games: return
    
    game = active_games[game_id]
    user_id = message.from_user.id
    
    if game['step'] != 'playing' or user_id not in game['players']: return
    if game['players'][user_id]['score'] != 0: return 

    if game['type'] == 'casino' and message.dice.emoji == '🎰':
        game['players'][user_id]['score'] = message.dice.value
    elif game['type'] == 'dice' and message.dice.emoji == '🎲':
        game['players'][user_id]['score'] = message.dice.value
    else:
        return

    all_rolled = all(p['score'] > 0 for p in game['players'].values())
    
    if all_rolled:
        time.sleep(3) 
        
        if game['type'] == 'casino':
            scores = [(pid, data['score']) for pid, data in game['players'].items()]
            scores.sort(key=lambda x: x[1], reverse=True)
            
            if scores[0][1] == scores[1][1]:
                refund_game(message.chat.id, message.reply_to_message.message_id, game)
            else:
                finalize_game(message.chat.id, message.reply_to_message.message_id, game, scores[0][0])
                
        elif game['type'] == 'dice':
            p1_id = list(game['players'].keys())[0] 
            p2_id = list(game['players'].keys())[1] 
            p1_score = game['players'][p1_id]['score']
            p2_score = game['players'][p2_id]['score']
            mode = game['dice_mode']
            
            winner_id = None
            if mode == 'zojfard':
                if p1_score % 2 == 0 and p2_score % 2 == 0: winner_id = p1_id 
                elif p1_score % 2 != 0 and p2_score % 2 != 0: winner_id = p2_id 
                else: winner_id = None 
            elif mode == 'fardzoj':
                if p1_score % 2 != 0 and p2_score % 2 != 0: winner_id = p1_id 
                elif p1_score % 2 == 0 and p2_score % 2 == 0: winner_id = p2_id 
                else: winner_id = None 
            elif mode == 'high':
                if p1_score > p2_score: winner_id = p1_id
                elif p2_score > p1_score: winner_id = p2_id
            elif mode == 'low':
                if p1_score < p2_score: winner_id = p1_id
                elif p2_score < p1_score: winner_id = p2_id
            
            if winner_id is None:
                refund_game(message.chat.id, message.reply_to_message.message_id, game)
            else:
                finalize_game(message.chat.id, message.reply_to_message.message_id, game, winner_id)

def refund_game(chat_id, msg_id, game):
    for pid in game['players'].keys():
        update_balance(pid, game['amount'])
    bot.edit_message_caption(caption="⚖️ <b>بازی مساوی شد!</b>\nمبلغ ورودی به حساب بازیکنان برگشت داده شد (بدون کسر مالیات).", chat_id=chat_id, message_id=msg_id, parse_mode='HTML')
    if f"{chat_id}_{msg_id}" in active_games: del active_games[f"{chat_id}_{msg_id}"]

def finalize_game(chat_id, msg_id, game, winner_id):
    tax = int((game['amount'] * game['max_players']) * 0.10)
    prize = (game['amount'] * game['max_players']) - tax
    
    update_balance(winner_id, prize)
    add_game_stat(tax, chat_id)
    
    text = "✅ <b>بازی با موفقیت به اتمام رسید!</b>\n\n"
    for pid in game['players'].keys():
        u = get_user(pid)
        name = f"@{u[4]}" if u[4] else str(pid)
        
        score_text = ""
        if game['type'] == 'casino':
            score_text = f" (امتیاز: {game['players'][pid]['score']})"
        elif game['type'] == 'dice':
            score_text = f" (تاس: {game['players'][pid]['score']})"

        if pid == winner_id:
            text += f"👑 برنده: {name}{score_text}\n"
        else:
            text += f"💀 بازنده: {name}{score_text}\n"
            
    text += f"\n💰 جایزه برنده: {prize} (10٪ مالیات کسر شد)"
    
    mk = InlineKeyboardMarkup()
    mk.add(InlineKeyboardButton("🏆 جایزه برنده", callback_data="ignore"), InlineKeyboardButton(f"{prize} 🪙", callback_data="ignore"))
    mk.add(InlineKeyboardButton("💰 موجودی برنده", callback_data="ignore"), InlineKeyboardButton(f"{get_balance(winner_id)}", callback_data="ignore"))
    
    for i, pid in enumerate([p for p in game['players'].keys() if p != winner_id], 1):
        mk.add(InlineKeyboardButton(f"📉 موجودی بازنده {i}", callback_data="ignore"), InlineKeyboardButton(f"{get_balance(pid)}", callback_data="ignore"))
        
    bot.edit_message_caption(caption=text, chat_id=chat_id, message_id=msg_id, reply_markup=mk, parse_mode='HTML')
    if f"{chat_id}_{msg_id}" in active_games: del active_games[f"{chat_id}_{msg_id}"]

# اجرای ربات
print("Bot is running...")
bot.infinity_polling()
