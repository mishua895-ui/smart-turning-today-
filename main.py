import telebot
import os
import psycopg2
from psycopg2 import sql
from datetime import datetime
import pytz

# --- ১. এনভায়রনমেন্ট ভ্যারিয়েবল ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
ADMIN_ID = os.environ.get('ADMIN_ID')

# --- ২. কনফিগারেশন ---
TASK_REWARD = 5.00
REFERRAL_BONUS = 2.00
MIN_WITHDRAWAL = 100.00
TIMEZONE = 'Asia/Dhaka'

# ✅ প্রয়োজনীয় চ্যানেলগুলোর তালিকা
REQUIRED_CHANNELS = ['@SmartEarnOfficial', '@SmartEarnUpdates']

# --- ৩. বট ইনিশিয়ালাইজ ---
bot = telebot.TeleBot(BOT_TOKEN)


# --- ৪. ডাটাবেস কানেকশন ---
def get_db_connection():
    try:
        if not DATABASE_URL:
            print("❌ DATABASE_URL missing")
            return None
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return None


# --- ৫. ইউজার চেক ফাংশন ---
def check_user(user_id, username=None, referrer_id=None):
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE user_id=%s", (user_id,))
        data = cur.fetchone()

        if data is None:
            cur.execute("INSERT INTO users (user_id, username) VALUES (%s, %s)", (user_id, username))
            conn.commit()

            # Referral Bonus
            if referrer_id:
                cur.execute("""
                    UPDATE users SET referral_count = referral_count + 1, earning_balance = earning_balance + %s 
                    WHERE user_id = %s
                """, (REFERRAL_BONUS, referrer_id))
                conn.commit()

            return {'new_user': True}
        else:
            return {'new_user': False}
    finally:
        conn.close()


# --- ৬. ইউজার ডেটা ফাংশন ---
def get_user_data(user_id):
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT earning_balance, referral_count FROM users WHERE user_id=%s", (user_id,))
        data = cur.fetchone()
        if data:
            return {'earning_balance': data[0], 'referral_count': data[1]}
        return None
    finally:
        conn.close()


# --- 🔍 চ্যানেল সাবস্ক্রিপশন চেক ---
def is_user_subscribed(user_id):
    not_joined = []
    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                not_joined.append(channel)
        except Exception as e:
            print(f"⚠️ Error checking {channel}: {e}")
            not_joined.append(channel)
    return not_joined


# --- 🧭 START COMMAND ---
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    referrer_id = None

    # রেফারেল চেক
    if len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = None
        except:
            referrer_id = None

    check_user(user_id, username, referrer_id)

    # 🔍 চ্যানেল চেক
    not_joined = is_user_subscribed(user_id)

    if not_joined:
        text = "🚫 দুঃখিত! আপনি নিচের চ্যানেলগুলোতে এখনো যোগ দেননি:\n\n"
        for ch in not_joined:
            text += f"➡️ {ch}\n"
        text += "\nসব চ্যানেলে জয়েন করার পর নিচের বোতামটি চাপুন 👇"

        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(telebot.types.KeyboardButton("✅ Check Again"))
        bot.send_message(user_id, text, reply_markup=markup)
        return

    # ✅ সব ঠিক থাকলে মেইন মেনু
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        telebot.types.KeyboardButton('💰 Earning'),
        telebot.types.KeyboardButton('💸 Withdraw'),
        telebot.types.KeyboardButton('👥 Referral'),
        telebot.types.KeyboardButton('📊 Balance')
    )
    bot.send_message(user_id, "🎉 স্বাগতম! আপনি এখন কাজ শুরু করতে পারেন।", reply_markup=markup)


# --- ✅ Check Again বাটন ---
@bot.message_handler(func=lambda m: m.text == "✅ Check Again")
def handle_check_again(message):
    user_id = message.from_user.id
    not_joined = is_user_subscribed(user_id)

    if not_joined:
        text = "🚫 আপনি এখনো সব চ্যানেলে যোগ দেননি:\n"
        for ch in not_joined:
            text += f"➡️ {ch}\n"
        bot.send_message(user_id, text)
    else:
        handle_start(message)


# --- 💰 Earning ---
@bot.message_handler(regexp='💰 Earning')
def handle_earning(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    if conn is None:
        return bot.send_message(user_id, "❌ ডাটাবেস ত্রুটি।")

    try:
        cur = conn.cursor()
        cur.execute("UPDATE users SET earning_balance = earning_balance + %s WHERE user_id = %s", (TASK_REWARD, user_id))
        conn.commit()

        user_data = get_user_data(user_id)
        balance = user_data['earning_balance']
        bot.send_message(user_id, f"✅ আপনি ₹{TASK_REWARD:.2f} আয় করেছেন!\n💰 মোট ব্যালেন্স: ₹{balance:.2f}")
    finally:
        conn.close()


# --- 📊 Balance ---
@bot.message_handler(regexp='📊 Balance')
def handle_balance(message):
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    if user_data:
        bot.send_message(user_id, f"📊 ব্যালেন্স: ₹{user_data['earning_balance']:.2f}\n👥 রেফারেল: {user_data['referral_count']}")
    else:
        bot.send_message(user_id, "❌ ডেটা পাওয়া যায়নি। /start দিন।")


# --- 👥 Referral ---
@bot.message_handler(regexp='👥 Referral')
def handle_referral(message):
    user_id = message.from_user.id
    referral_link = f"https://t.me/SmartEarnbdBot?start={user_id}"
    text = f"👥 আপনার রেফারেল লিংক:\n`{referral_link}`\n\nপ্রত্যেক রেফারে ₹{REFERRAL_BONUS} পাবেন।"
    bot.send_message(user_id, text, parse_mode="Markdown")


# --- 💸 Withdraw ---
@bot.message_handler(regexp='💸 Withdraw')
def handle_withdraw(message):
    bot.send_message(message.chat.id, "💳 Withdraw সিস্টেম আগের মতই কাজ করবে। (Bkash/Nagad/Rocket)")

# --- বট চালু করুন ---
if __name__ == '__main__':
    print("✅ Bot is running with Channel Check...")
    bot.polling(none_stop=True)
