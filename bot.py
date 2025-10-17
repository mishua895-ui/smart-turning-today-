import telebot
import os
import psycopg2
from psycopg2 import sql
from datetime import datetime, timedelta
import pytz

# --- ১. এনভায়রনমেন্ট ভ্যারিয়েবল লোড ---
# আপনার সব গোপন ডেটা এনভায়রনমেন্ট ভ্যারিয়েবল থেকে নেওয়া হবে।
# Render-এ সঠিক মানগুলো সেট করা আছে কিনা, তা নিশ্চিত করুন।

# টেলিগ্রাম বট টোকেন
BOT_TOKEN = os.environ.get('BOT_TOKEN')
# ডাটাবেস সংযোগ URL (সংশোধিত: &channel_binding=require বাদ দেওয়া হয়েছে)
DATABASE_URL = os.environ.get('DATABASE_URL')
# অ্যাডমিন ইউজার আইডি
ADMIN_ID = os.environ.get('ADMIN_ID')

# কনফিগারেশন
TASK_REWARD = 5.00  # প্রতি টাস্কের জন্য প্রাপ্ত টাকা
REFERRAL_BONUS = 2.00  # প্রতি রেফারেলে প্রাপ্ত টাকা
MIN_WITHDRAWAL = 100.00  # সর্বনিম্ন উইথড্র অ্যামাউন্ট
TIMEZONE = 'Asia/Dhaka'  # সময় অঞ্চল (আপনার দেশের সময় অনুযায়ী)

# --- ২. বট ইনিশিয়ালাইজেশন ---
bot = telebot.TeleBot(BOT_TOKEN)

# --- ৩. ডাটাবেস সংযোগ ফাংশন ---
def get_db_connection():
    conn = None
    try:
        if not DATABASE_URL:
            print("❌ ERROR: DATABASE_URL is not set.")
            return None
            
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.Error as e:
        # Render-এর লগে সংযোগ ব্যর্থতার কারণ দেখাবে।
        print(f"❌ Database connection error: {e}")
        return None
    except Exception as e:
        print(f"❌ An unexpected database error occurred: {e}")
        return None

# --- ৪. ইউজার ডেটা ফাংশন ---
def check_user(user_id, username=None, referrer_id=None):
    conn = get_db_connection()
    if conn is None:
        return None  # সংযোগ ব্যর্থ হলে None রিটার্ন করুন
    
    try:
        cur = conn.cursor()
        
        # ইউজার ডেটা খুঁজে বের করুন
        cur.execute("SELECT user_id, earning_balance, referral_count FROM users WHERE user_id = %s", (user_id,))
        user_data = cur.fetchone()

        if user_data is None:
            # যদি ইউজার না থাকে, তবে নতুন ইউজার তৈরি করুন
            cur.execute("""
                INSERT INTO users (user_id, username)
                VALUES (%s, %s)
            """, (user_id, username))
            conn.commit()
            
            # রেফারেল বোনাস যোগ করুন (যদি referrer_id থাকে)
            if referrer_id:
                cur.execute(sql.SQL("""
                    UPDATE users SET referral_count = referral_count + 1, earning_balance = earning_balance + %s WHERE user_id = %s;
                """), (REFERRAL_BONUS, referrer_id))
                conn.commit()
                print(f"✅ Referral bonus ({REFERRAL_BONUS} BDT) added to referrer ({referrer_id})")
                
            return {'new_user': True}
        
        # ইউজার থাকলে তার ডেটা রিটার্ন করুন
        return {
            'user_id': user_data[0],
            'earning_balance': user_data[1],
            'referral_count': user_data[2],
            'new_user': False
        }

    except psycopg2.Error as e:
        print(f"❌ Database operation error (check_user): {e}")
        return None
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_user_data(user_id):
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, earning_balance, referral_count, is_admin FROM users WHERE user_id = %s", (user_id,))
        data = cur.fetchone()
        
        if data:
            return {
                'user_id': data[0],
                'earning_balance': data[1],
                'referral_count': data[2],
                'is_admin': data[3]
            }
        return None
        
    except psycopg2.Error as e:
        print(f"❌ Database operation error (get_user_data): {e}")
        return None
    finally:
        if conn:
            conn.close()

# --- ৫. টাস্ক এবং ব্যালেন্স ফাংশন ---
def get_daily_task_count(user_id):
    conn = get_db_connection()
    if conn is None:
        return 0
        
    try:
        cur = conn.cursor()
        today = datetime.now(pytz.timezone(TIMEZONE)).date()
        
        cur.execute("SELECT task_count FROM user_tasks WHERE user_id = %s AND task_date = %s", (user_id, today))
        data = cur.fetchone()
        
        return data[0] if data else 0
        
    except psycopg2.Error as e:
        print(f"❌ Database operation error (get_daily_task_count): {e}")
        return 0
    finally:
        if conn:
            conn.close()

def add_earning(user_id):
    conn = get_db_connection()
    if conn is None:
        return False
        
    try:
        cur = conn.cursor()
        today = datetime.now(pytz.timezone(TIMEZONE)).date()
        
        # 1. টাস্ক কাউন্ট আপডেট
        cur.execute("""
            INSERT INTO user_tasks (user_id, task_date, task_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, task_date)
            DO UPDATE SET task_count = user_tasks.task_count + 1;
        """, (user_id, today))
        
        # 2. আর্নিং ব্যালেন্স আপডেট
        cur.execute(sql.SQL("""
            UPDATE users SET earning_balance = earning_balance + %s WHERE user_id = %s;
        """), (TASK_REWARD, user_id))
        
        conn.commit()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database operation error (add_earning): {e}")
        return False
    finally:
        if conn:
            conn.close()

# --- ৬. বট কমান্ড এবং হ্যান্ডলার ---

# স্টার্ট কমান্ড
@bot.message_handler(commands=['start'])
def handle_start(message):
    try:
        user_id = message.from_user.id
        username = message.from_user.username
        referrer_id = None
        
        # রেফারেল আইডি বের করুন (যদি থাকে)
        if len(message.text.split()) > 1:
            try:
                referrer_id = int(message.text.split()[1])
                if referrer_id == user_id: # নিজকে রেফার করা যাবে না
                    referrer_id = None
            except ValueError:
                referrer_id = None

        user_info = check_user(user_id, username, referrer_id)
        
        if user_info and user_info.get('new_user'):
            welcome_text = "স্বাগতম! আপনি আমাদের আর্নিং বটের একজন নতুন সদস্য।\n\nআপনি রেফারেল লিংক ব্যবহার করে থাকলে, আপনার রেফারকারীকে ₹{} বোনাস দেওয়া হয়েছে।".format(REFERRAL_BONUS)
        else:
            welcome_text = "স্বাগতম! আপনি মেনু থেকে আপনার কাজ শুরু করতে পারেন।"

        # মেইন মেনু তৈরি
        markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        btn1 = telebot.types.KeyboardButton('💰 Earning')
        btn2 = telebot.types.KeyboardButton('💸 Withdraw')
        btn3 = telebot.types.KeyboardButton('👥 Referral')
        btn4 = telebot.types.KeyboardButton('📊 Balance')
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(user_id, welcome_text, reply_markup=markup)
        
    except Exception as e:
        print(f"❌ Error in handle_start: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")


# আর্নিং বাটন
@bot.message_handler(regexp='💰 Earning')
def handle_earning(message):
    try:
        user_id = message.from_user.id
        # টাস্ক লজিক এখানে যুক্ত হবে
        
        # সহজ টাস্ক: প্রতি ক্লিকে টাকা যোগ
        if add_earning(user_id):
            balance = get_user_data(user_id)['earning_balance']
            response = f"✅ সফল! আপনি ₹{TASK_REWARD:.2f} টাকা উপার্জন করেছেন।\n\nআপনার বর্তমান ব্যালেন্স: ₹{balance:.2f}"
        else:
            response = "❌ দুঃখিত! টাস্ক যোগ করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।"
            
        bot.send_message(user_id, response)
        
    except Exception as e:
        print(f"❌ Error in handle_earning: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")


# ব্যালেন্স বাটন
@bot.message_handler(regexp='📊 Balance')
def handle_balance(message):
    try:
        user_id = message.from_user.id
        user_data = get_user_data(user_id)
        
        if user_data:
            balance = user_data['earning_balance']
            referrals = user_data['referral_count']
            
            response = f"📊 আপনার বর্তমান ব্যালেন্স: **₹{balance:.2f}**\n\n👥 আপনার রেফারেল সংখ্যা: **{referrals}** জন"
            bot.send_message(user_id, response, parse_mode='Markdown')
        else:
            bot.send_message(user_id, "❌ আপনার তথ্য খুঁজে পাওয়া যায়নি। /start কমান্ড দিন।")
            
    except Exception as e:
        print(f"❌ Error in handle_balance: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")


# রেফারেল বাটন
@bot.message_handler(regexp='👥 Referral')
def handle_referral(message):
    try:
        user_id = message.from_user.id
        referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
        
        response = f"👥 আপনার রেফারেল লিংক:\n`{referral_link}`\n\nএই লিংক ব্যবহার করে কেউ জয়েন করলে আপনি ₹{REFERRAL_BONUS:.2f} টাকা বোনাস পাবেন।"
        
        bot.send_message(user_id, response, parse_mode='Markdown')
        
    except Exception as e:
        print(f"❌ Error in handle_referral: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")

# উইথড্র বাটন
@bot.message_handler(regexp='💸 Withdraw')
def handle_withdraw(message):
    try:
        user_id = message.from_user.id
        user_data = get_user_data(user_id)
        
        if user_data is None:
            return bot.send_message(user_id, "❌ আপনার তথ্য খুঁজে পাওয়া যায়নি। /start কমান্ড দিন।")
            
        balance = user_data['earning_balance']
        
        if balance < MIN_WITHDRAWAL:
            response = f"❌ দুঃখিত! উইথড্র করার জন্য আপনার কমপক্ষে ₹{MIN_WITHDRAWAL:.2f} ব্যালেন্স থাকতে হবে। আপনার বর্তমান ব্যালেন্স: ₹{balance:.2f}"
            return bot.send_message(user_id, response)
            
        # উইথড্র করার অ্যামাউন্ট জানতে চান
        msg = bot.send_message(user_id, "💸 আপনি কত টাকা উইথড্র করতে চান? (সর্বনিম্ন ₹{}):".format(MIN_WITHDRAWAL))
        bot.register_next_step_handler(msg, handle_withdraw_amount)
        
    except Exception as e:
        print(f"❌ Error in handle_withdraw: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")

def handle_withdraw_amount(message):
    try:
        user_id = message.from_user.id
        amount = message.text
        
        try:
            amount = float(amount)
        except ValueError:
            msg = bot.send_message(user_id, "❌ অবৈধ অ্যামাউন্ট। দয়া করে শুধু সংখ্যা লিখুন। আবার চেষ্টা করুন:")
            return bot.register_next_step_handler(msg, handle_withdraw_amount)

        user_data = get_user_data(user_id)
        balance = user_data['earning_balance']

        if amount < MIN_WITHDRAWAL:
            msg = bot.send_message(user_id, f"❌ সর্বনিম্ন উইথড্র অ্যামাউন্ট ₹{MIN_WITHDRAWAL:.2f}। আবার চেষ্টা করুন:")
            return bot.register_next_step_handler(msg, handle_withdraw_amount)
            
        if amount > balance:
            msg = bot.send_message(user_id, f"❌ আপনার ব্যালেন্সে যথেষ্ট টাকা নেই। বর্তমান ব্যালেন্স: ₹{balance:.2f}। আবার চেষ্টা করুন:")
            return bot.register_next_step_handler(msg, handle_withdraw_amount)
            
        # পেমেন্ট মেথড জানতে চান
        msg = bot.send_message(user_id, "🏦 আপনি কোন পেমেন্ট মেথডের মাধ্যমে উইথড্র করতে চান? (যেমন: বিকাশ, নগদ, রকেট):")
        bot.register_next_step_handler(msg, handle_withdraw_info, amount)
        
    except Exception as e:
        print(f"❌ Error in handle_withdraw_amount: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")

def handle_withdraw_info(message, amount):
    try:
        user_id = message.from_user.id
        method = message.text
        
        # পেমেন্ট তথ্য (যেমন: নম্বর) জানতে চান
        msg = bot.send_message(user_id, f"📱 আপনার {method} নম্বর বা অ্যাকাউন্ট আইডি লিখুন:")
        bot.register_next_step_handler(msg, handle_withdraw_finalize, amount, method)
        
    except Exception as e:
        print(f"❌ Error in handle_withdraw_info: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")

def handle_withdraw_finalize(message, amount, method):
    try:
        user_id = message.from_user.id
        info = message.text  # পেমেন্ট নম্বর/আইডি
        
        # উইথড্র রিকোয়েস্ট তৈরি এবং ব্যালেন্স আপডেট
        if create_withdrawal_request(user_id, amount, method, info):
            bot.send_message(user_id, "✅ আপনার উইথড্র রিকোয়েস্ট সফলভাবে জমা দেওয়া হয়েছে। ২৪ ঘন্টার মধ্যে পেমেন্ট পেয়ে যাবেন।")
            
            # অ্যাডমিনকে নোটিফিকেশন পাঠান
            admin_message = f"🔔 **নতুন উইথড্র রিকোয়েস্ট**\n\nইউজার ID: `{user_id}`\nইউজার: @{message.from_user.username}\nঅ্যামাউন্ট: ₹{amount:.2f}\nমেথড: {method}\nপেমেন্ট তথ্য: {info}"
            bot.send_message(ADMIN_ID, admin_message, parse_mode='Markdown')
        else:
            bot.send_message(user_id, "❌ দুঃখিত! উইথড্র রিকোয়েস্ট জমা দিতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")
            
    except Exception as e:
        print(f"❌ Error in handle_withdraw_finalize: {e}")
        bot.send_message(message.chat.id, "দুঃখিত! একটি অপ্রত্যাশিত ত্রুটি হয়েছে।")

def create_withdrawal_request(user_id, amount, method, info):
    conn = get_db_connection()
    if conn is None:
        return False
        
    try:
        cur = conn.cursor()
        
        # 1. ব্যালেন্স থেকে টাকা কমানো
        cur.execute(sql.SQL("""
            UPDATE users SET earning_balance = earning_balance - %s WHERE user_id = %s;
        """), (amount, user_id))
        
        # 2. রিকোয়েস্ট টেবিল এন্ট্রি
        cur.execute("""
            INSERT INTO withdrawal_requests (user_id, method, amount, payment_info)
            VALUES (%s, %s, %s, %s);
        """, (user_id, method, amount, info))
        
        conn.commit()
        return True
        
    except psycopg2.Error as e:
        print(f"❌ Database operation error (create_withdrawal_request): {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


# --- ৭. বট লুপ ---
if __name__ == '__main__':
    print("✅ Bot is polling...")
    try:
        bot.polling(none_stop=True)
    except Exception as e:
        print(f"❌ Bot polling failed: {e}")

# --- End of bot.py ---
