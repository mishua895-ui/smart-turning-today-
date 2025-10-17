import telebot
import psycopg2
import os
from datetime import datetime, timedelta
import pytz
from psycopg2 import sql

# --- কনফিগারেশন ---
# টোকেন ও ডাটাবেস ইউআরএল এনভায়রনমেন্ট ভ্যারিয়েবল থেকে নেওয়া হবে
# Render-এ এগুলো অবশ্যই সেট করা থাকতে হবে।
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
# টাস্ক কনফিগারেশন
TASK_REWARD = 5.00  # প্রতি টাস্কে ৫.০০ টাকা
DAILY_TASK_LIMIT = 5 # প্রতিদিন ৫টি টাস্কের বেশি করা যাবে না
REFERRAL_BONUS = 10.00 # প্রতি রেফারেলের জন্য ১০.০০ টাকা
MIN_WITHDRAWAL = 100.00 # সর্বনিম্ন উইথড্র অ্যামাউন্ট
TIMEZONE = 'Asia/Dhaka' # বাংলাদেশের সময় অঞ্চল
ADMIN_ID = 8145444675 # আপনার টেলিগ্রাম ইউজার আইডি
bot = telebot.TeleBot(BOT_TOKEN)
   """ডাটাবেসের সাথে সংযোগ স্থাপন করে"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None
 check_user(user_id, username=None, referrer_id=None):
    """ইউজার ডাটাবেসে আছে কিনা চেক করে, না থাকলে নতুন ইউজার তৈরি করে।"""
    conn = get_db_connection()
    if conn is None: return

    cur = conn.cursor()
    try:
        # ইউজার আছে কিনা চেক
        cur.execute("SELECT user_id, earning_balance, referral_count FROM users WHERE user_id = %s", (user_id,))
        user_data = cur.fetchone()

        if user_data is None:
            # নতুন ইউজার তৈরি
            cur.execute("""
                INSERT INTO users (user_id, username) 
                VALUES (%s, %s)
            """, (user_id, username))
            conn.commit()
            
            # রেফারেল বোনাস যোগ
            if referrer_id:
                cur.execute("""
                    UPDATE users SET referral_count = referral_count + 1, earning_balance = earning_balance + %s WHERE user_id = %s
                """, (REFERRAL_BONUS, referrer_id))
                conn.commit()
                print(f"Referral bonus {REFERRAL_BONUS} added to referrer {referrer_id}")

            return {'new_user': True}
        
        # ইউজার ডাটা আপডেট (যদি ইউজারনেম পরিবর্তন হয়)
        cur.execute("UPDATE users SET username = %s WHERE user_id = %s", (username, user_id))
        conn.commit()

        return {'new_user': False, 'balance': user_data[1], 'referrals': user_data[2]}

    except Exception as e:
        print(f"Database operation error (check_user): {e}")
    finally:
        cur.close()
        conn.close()

def get_user_data(user_id):
    """ইউজারের ব্যালেন্স এবং রেফারেল সংখ্যা আনে"""
    conn = get_db_connection()
    if conn is None: return None
    cur = conn.cursor()
    try:
        cur.execute("SELECT earning_balance, referral_count, is_admin FROM users WHERE user_id = %s", (user_id,))
        data = cur.fetchone()
        if data:
            return {'balance': data[0], 'referrals': data[1], 'is_admin': data[2]}
        return None
    finally:
        cur.close()
        conn.close()

def add_earning(user_id, amount, task_info=None):
    """ইউজারের ব্যালেন্সে অর্থ যোগ করে"""
    conn = get_db_connection()
    if conn is None: return False
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users SET earning_balance = earning_balance + %s, last_task_time = NOW() 
            WHERE user_id = %s RETURNING earning_balance
        """, (amount, user_id))
        conn.commit()
        new_balance = cur.fetchone()[0]
        return new_balance
    except Exception as e:
        print(f"Database operation error (add_earning): {e}")
        return False
    finally:
        cur.close()
        conn.close()

def get_daily_task_count(user_id, date):
    """নির্দিষ্ট দিনে ইউজারের টাস্ক সংখ্যা আনে"""
    conn = get_db_connection()
    if conn is None: return DAILY_TASK_LIMIT + 1 # সংযোগ না পেলে টাস্ক limit এর বেশি দেখাবে
    cur = conn.cursor()
    try:
        cur.execute("SELECT task_count FROM user_tasks WHERE user_id = %s AND task_date = %s", (user_id, date))
        result = cur.fetchone()
        return result[0] if result else 0
    finally:
        cur.close()
        conn.close()

def update_daily_task_count(user_id, date):
    """নির্দিষ্ট দিনে ইউজারের টাস্ক সংখ্যা বাড়ায়"""
    conn = get_db_connection()
    if conn is None: return
    cur = conn.cursor()
    try:
        # যদি আজকের এন্ট্রি না থাকে তবে নতুন এন্ট্রি তৈরি করবে, অন্যথায় আপডেট করবে
        cur.execute("""
            INSERT INTO user_tasks (user_id, task_date, task_count) 
            VALUES (%s, %s, 1)
            ON CONFLICT (user_id, task_date) 
            DO UPDATE SET task_count = user_tasks.task_count + 1
        """, (user_id, date))
        conn.commit()
    finally:
        cur.close()
        conn.close()

def create_withdrawal_request(user_id, amount, method, wallet_info):
    """উইথড্র রিকোয়েস্ট তৈরি করে এবং ব্যালেন্স থেকে টাকা কমায়"""
    conn = get_db_connection()
    if conn is None: return False
    cur = conn.cursor()
    try:
        # ব্যালেন্স চেক
        cur.execute("SELECT earning_balance FROM users WHERE user_id = %s FOR UPDATE", (user_id,))
        current_balance = cur.fetchone()[0]

        if current_balance < amount:
            return "Insufficient balance"
        
        # ব্যালেন্স থেকে টাকা কমানো
        cur.execute("UPDATE users SET earning_balance = earning_balance - %s WHERE user_id = %s", (amount, user_id))

        # রিকোয়েস্ট তৈরি
        cur.execute("""
            INSERT INTO withdrawal_requests (user_id, amount, method, wallet_info) 
            VALUES (%s, %s, %s, %s)
        """, (user_id, amount, method, wallet_info))

        conn.commit()
        return "Success"
    except Exception as e:
        print(f"Database operation error (withdrawal): {e}")
        conn.rollback()
        return "Error"
    finally:
        cur.close()
        conn.close()


# --- টেলিগ্রাম হ্যান্ডলার ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """/start কমান্ড হ্যান্ডেল করে এবং ইউজারকে ডাটাবেসে যোগ করে।"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    # রেফারেল আইডি এক্সট্র্যাক্ট করা
    referrer_id = None
    if message.text.startswith('/start '):
        try:
            referrer_id = int(message.text.split()[1])
        except (ValueError, IndexError):
            pass

    # নিজের রেফারেল লিঙ্ক থেকে জয়েন করলে ব্লক
    if referrer_id == user_id:
        referrer_id = None

    result = check_user(user_id, username, referrer_id)
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Earning", "💸 Withdraw")
    markup.add("🔗 Refer & Earn", "📊 Balance")
    
    if result and result.get('new_user'):
        welcome_message = "স্বাগতম! আপনি আমাদের আর্নিং বটের একজন নতুন সদস্য।\n\nকাজ শুরু করতে নিচের বাটনগুলো ব্যবহার করুন।"
    else:
        welcome_message = "স্বাগতম! আপনার বট এখন রেডি। কাজ শুরু করতে নিচের বাটনগুলো ব্যবহার করুন।"

    bot.send_message(user_id, welcome_message, reply_markup=markup)


@bot.message_handler(func=lambda message: message.text == "💰 Earning")
def handle_earning(message):
    """'Earning' বাটন হ্যান্ডেল করে টাস্ক দেয়।"""
    user_id = message.from_user.id
    dhaka_tz = pytz.timezone(TIMEZONE)
    today = datetime.now(dhaka_tz).date()

    # দৈনিক টাস্ক লিমিট চেক
    task_count = get_daily_task_count(user_id, today)
    
    if task_count >= DAILY_TASK_LIMIT:
        bot.send_message(user_id, f"দুঃখিত, আপনার আজকের **{DAILY_TASK_LIMIT} টি টাস্কের লিমিট** পূর্ণ হয়েছে। আগামীকাল আবার চেষ্টা করুন।")
        return

    # টাস্ক কমপ্লিট করার বাটন
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(telebot.types.InlineKeyboardButton("✅ টাস্ক সম্পূর্ণ করুন এবং টাকা নিন", callback_data=f"complete_task_{user_id}_{today}"))
    
    task_message = f"আজকের কাজ:\n\n👉 **এই চ্যানেলটিতে জয়েন করুন:** [Your Telegram Channel Link]\n\nটাস্কটি সম্পূর্ণ করে নিচের বাটনে ক্লিক করুন। (আজকের টাস্ক: {task_count}/{DAILY_TASK_LIMIT})"

    bot.send_message(user_id, task_message, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('complete_task_'))
def callback_complete_task(call):
    """টাস্ক কমপ্লিট বাটন ক্লিক হ্যান্ডেল করে।"""
    user_id = call.from_user.id
    
    # নিশ্চিত করুন যে কলব্যাক ডেটাটি সঠিক ইউজারের জন্য
    parts = call.data.split('_')
    if len(parts) != 3: # complete_task_user_id_YYYY-MM-DD
        bot.answer_callback_query(call.id, "❌ Invalid task data.")
        return

    dhaka_tz = pytz.timezone(TIMEZONE)
    today = datetime.now(dhaka_tz).date()
    
    # ডেটাবেস থেকে আজকের টাস্ক সংখ্যা চেক
    task_count = get_daily_task_count(user_id, today)

    if task_count >= DAILY_TASK_LIMIT:
        bot.answer_callback_query(call.id, f"❌ আজকের টাস্ক লিমিট পূর্ণ হয়েছে: {DAILY_TASK_LIMIT}টি।")
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🚫 **টাস্ক কমপ্লিট করা সম্ভব নয়।**\nআপনার আজকের টাস্ক লিমিট ({DAILY_TASK_LIMIT}টি) পূর্ণ হয়েছে।",
            parse_mode="Markdown"
        )
        return

    # --- টাস্ক সফল ---
    update_daily_task_count(user_id, today)
    new_balance = add_earning(user_id, TASK_REWARD)
    
    if new_balance is not False:
        # মেসেজ আপডেট করা
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🎉 **টাস্ক সফলভাবে সম্পন্ন হয়েছে!**\n\nটাস্কের জন্য আপনার অ্যাকাউন্টে **{TASK_REWARD:.2f} টাকা** যোগ করা হয়েছে।\n\nআজকের সম্পন্ন হওয়া টাস্ক: **{task_count + 1}/{DAILY_TASK_LIMIT}**",
            parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, f"✅ সফল! {TASK_REWARD:.2f} টাকা যোগ হয়েছে।")
    else:
        bot.answer_callback_query(call.id, "❌ একটি ত্রুটি হয়েছে। পরে আবার চেষ্টা করুন।")


@bot.message_handler(func=lambda message: message.text == "📊 Balance")
def handle_balance(message):
    """ব্যালেন্স দেখায়।"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    if user_data:
        balance = user_data['balance']
        referrals = user_data['referrals']
        
        balance_message = f"**👤 আপনার অ্যাকাউন্ট ব্যালেন্স:**\n\n"
        balance_message += f"💰 মোট ব্যালেন্স: **{balance:.2f} টাকা**\n"
        balance_message += f"🔗 মোট রেফারেল: **{referrals} জন**"
        
        bot.send_message(user_id, balance_message, parse_mode="Markdown")
    else:
        bot.send_message(user_id, "দুঃখিত, আপনার ডেটা পাওয়া যায়নি। /start কমান্ড দিয়ে আবার শুরু করুন।")


@bot.message_handler(func=lambda message: message.text == "🔗 Refer & Earn")
def handle_referral(message):
    """রেফারেল লিঙ্ক প্রদান করে।"""
    user_id = message.from_user.id
    referral_link = f"https://t.me/{bot.get_me().username}?start={user_id}"
    
    referral_message = f"**রেফার করুন এবং উপার্জন করুন!**\n\n"
    referral_message += f"আপনার রেফারেল লিঙ্ক:\n`{referral_link}`\n\n"
    referral_message += f"আপনি যাকে রেফার করবেন, সে জয়েন করলে আপনি **{REFERRAL_BONUS:.2f} টাকা** বোনাস পাবেন!"
    
    bot.send_message(user_id, referral_message, parse_mode="Markdown")


@bot.message_handler(func=lambda message: message.text == "💸 Withdraw")
def handle_withdraw_start(message):
    """উইথড্র প্রক্রিয়া শুরু করে।"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data:
        bot.send_message(user_id, "দুঃখিত, আপনার ডেটা পাওয়া যায়নি। /start কমান্ড দিয়ে আবার শুরু করুন।")
        return

    balance = user_data['balance']
    
    if balance < MIN_WITHDRAWAL:
        bot.send_message(user_id, f"❌ **উইথড্র করতে ব্যর্থ।**\n\nআপনার বর্তমান ব্যালেন্স: **{balance:.2f} টাকা**।\nসর্বনিম্ন উইথড্র অ্যামাউন্ট হলো: **{MIN_WITHDRAWAL:.2f} টাকা**।")
        return

    # পেমেন্ট মেথড বাটন
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add("Bkash", "Nagad", "Rocket")
    
    msg = bot.send_message(user_id, f"আপনার ব্যালেন্স: **{balance:.2f} টাকা**। আপনি উইথড্র করতে পারবেন।\n\nঅনুগ্রহ করে, আপনার **পেমেন্ট মেথড** নির্বাচন করুন:", reply_markup=markup, parse_mode="Markdown")
    
    # পরবর্তী স্টেপ সেট
    bot.register_next_step_handler(msg, handle_withdraw_amount)

def handle_withdraw_amount(message):
    """উইথড্র অ্যামাউন্ট এবং পেমেন্ট মেথড হ্যান্ডেল করে।"""
    user_id = message.from_user.id
    method = message.text
    
    if method not in ["Bkash", "Nagad", "Rocket"]:
        # যদি ইউজার কোনো মেথড সিলেক্ট না করে অন্য মেসেজ দেয়
        bot.send_message(user_id, "❌ ভুল পেমেন্ট মেথড। উইথড্র করার জন্য আবার '💸 Withdraw' বাটনে ক্লিক করুন।")
        return

    user_data = get_user_data(user_id)
    balance = user_data['balance']

    msg = bot.send_message(user_id, f"আপনি **{method}** নির্বাচন করেছেন।\n\nকত টাকা উইথড্র করতে চান? (সর্বনিম্ন {MIN_WITHDRAWAL:.2f} টাকা)\n\nআপনার ব্যালেন্স: **{balance:.2f} টাকা**।", parse_mode="Markdown")
    
    # পরবর্তী স্টেপ সেট: উইথড্র অ্যামাউন্ট
    bot.register_next_step_handler(msg, handle_withdraw_wallet_info, method)

def handle_withdraw_wallet_info(message, method):
    """উইথড্র অ্যামাউন্ট নিশ্চিত করে এবং ওয়ালেট/অ্যাকাউন্ট নম্বর চায়।"""
    user_id = message.from_user.id
    amount_text = message.text
    
    try:
        amount = float(amount_text)
        if amount < MIN_WITHDRAWAL:
            bot.send_message(user_id, f"❌ উইথড্র অ্যামাউন্ট অবশ্যই সর্বনিম্ন **{MIN_WITHDRAWAL:.2f} টাকা** হতে হবে। আবার চেষ্টা করুন।")
            return
    except ValueError:
        bot.send_message(user_id, "❌ ইনভ্যালিড অ্যামাউন্ট। শুধুমাত্র সংখ্যা লিখুন। আবার চেষ্টা করুন।")
        return
    
    # ব্যালেন্স পুনরায় চেক
    user_data = get_user_data(user_id)
    balance = user_data['balance']
    
    if amount > balance:
        bot.send_message(user_id, f"❌ আপনার অ্যাকাউন্টে **{amount:.2f} টাকা** নেই। আপনার ব্যালেন্স: **{balance:.2f} টাকা**।")
        return

    msg = bot.send_message(user_id, f"আপনি **{amount:.2f} টাকা** উইথড্র করতে চান।\n\nএখন আপনার **{method} অ্যাকাউন্ট নম্বরটি** দিন:", parse_mode="Markdown")
    
    # পরবর্তী স্টেপ সেট: ওয়ালেট ইনফো
    bot.register_next_step_handler(msg, handle_withdraw_finalize, method, amount)

def handle_withdraw_finalize(message, method, amount):
    """উইথড্র রিকোয়েস্ট চূড়ান্ত করে ডাটাবেসে সেভ করে।"""
    user_id = message.from_user.id
    wallet_info = message.text.strip()
    
    # ডিফল্ট মেনু ফেরত আনা
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💰 Earning", "💸 Withdraw")
    markup.add("🔗 Refer & Earn", "📊 Balance")
    
    result = create_withdrawal_request(user_id, amount, method, wallet_info)
    
    if result == "Success":
        success_message = f"✅ **উইথড্র রিকোয়েস্ট সফল!**\n\n"
        success_message += f"অ্যামাউন্ট: **{amount:.2f} টাকা**\n"
        success_message += f"মেথড: **{method}**\n"
        success_message += f"অ্যাকাউন্ট: **{wallet_info}**\n\n"
        success_message += "আপনার রিকোয়েস্টটি পেন্ডিং রয়েছে। অ্যাডমিন শীঘ্রই এটি প্রসেস করবেন।"
        bot.send_message(user_id, success_message, reply_markup=markup, parse_mode="Markdown")
        
        # অ্যাডমিনকে নোটিফিকেশন
        bot.send_message(ADMIN_ID, f"🔔 **নতুন উইথড্র রিকোয়েস্ট!**\n\nUser ID: {user_id}\nUsername: @{message.from_user.username or 'N/A'}\nAmount: {amount:.2f} টাকা\nMethod: {method}\nWallet: {wallet_info}\n\nপ্রসেস করতে পারেন।", parse_mode="Markdown")
        
    elif result == "Insufficient balance":
        bot.send_message(user_id, "❌ দুঃখিত, আপনার ব্যালেন্স অপর্যাপ্ত।", reply_markup=markup)
    else:
        bot.send_message(user_id, "❌ দুঃখিত, উইথড্র রিকোয়েস্ট করার সময় একটি ত্রুটি হয়েছে।", reply_markup=markup)

# --- অ্যাডমিন কমান্ড (ADMIN COMMANDS) ---

@bot.message_handler(commands=['admin'])
def handle_admin_start(message):
    """অ্যাডমিন প্যানেল দেখায়"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data or not user_data.get('is_admin'):
        bot.send_message(user_id, "🚫 আপনার এই কমান্ডটি ব্যবহার করার অনুমতি নেই।")
        return
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("📝 Pending Withdrawals", "📊 All Users Data")
    
    bot.send_message(user_id, "🛠️ **অ্যাডমিন প্যানেল**", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📝 Pending Withdrawals")
def handle_pending_withdrawals(message):
    """পেন্ডিং উইথড্র রিকোয়েস্ট দেখায়"""
    user_id = message.from_user.id
    user_data = get_user_data(user_id)
    
    if not user_data or not user_data.get('is_admin'): return

    conn = get_db_connection()
    if conn is None: return bot.send_message(user_id, "❌ DB Connection Error.")
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT w.id, w.user_id, u.username, w.amount, w.method, w.wallet_info, w.request_date
            FROM withdrawal_requests w
            JOIN users u ON w.user_id = u.user_id
            WHERE w.status = 'Pending'
            ORDER BY w.request_date ASC
        """)
        requests = cur.fetchall()
        
        if not requests:
            bot.send_message(user_id, "🎉 বর্তমানে কোনো পেন্ডিং উইথড্র রিকোয়েস্ট নেই।")
            return
            
        for req in requests:
            req_id, req_user_id, username, amount, method, wallet, date = req
            
            # প্রসেস করার জন্য ইনলাইন বাটন
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(
                telebot.types.InlineKeyboardButton("✅ Paid", callback_data=f"set_paid_{req_id}_{req_user_id}"),
                telebot.types.InlineKeyboardButton("❌ Rejected", callback_data=f"set_rejected_{req_id}_{req_user_id}")
            )
            
            req_msg = f"**🆔 R-ID: {req_id}** (User: {req_user_id})\n"
            req_msg += f"👤 Username: @{username or 'N/A'}\n"
            req_msg += f"💰 Amount: **{amount:.2f} টাকা**\n"
            req_msg += f"💳 Method: {method} ({wallet})\n"
            req_msg += f"⏰ Date: {date.strftime('%Y-%m-%d %H:%M')}"
            
            bot.send_message(user_id, req_msg, reply_markup=markup, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(user_id, f"❌ Error fetching requests: {e}")
    finally:
        cur.close()
        conn.close()

@bot.callback_query_handler(func=lambda call: call.data.startswith('set_'))
def callback_set_withdrawal_status(call):
    """উইথড্র রিকোয়েস্ট স্ট্যাটাস সেট করে।"""
    admin_id = call.from_user.id
    user_data = get_user_data(admin_id)
    if not user_data or not user_data.get('is_admin'):
        bot.answer_callback_query(call.id, "🚫 আপনার অনুমতি নেই।")
        return
        
    parts = call.data.split('_')
    action = parts[1] # paid বা rejected
    req_id = int(parts[2])
    req_user_id = int(parts[3])
    
    new_status = 'Paid' if action == 'paid' else 'Rejected'
    
    conn = get_db_connection()
    if conn is None: 
        bot.answer_callback_query(call.id, "❌ DB Connection Error.")
        return
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE withdrawal_requests SET status = %s WHERE id = %s RETURNING amount, user_id
        """, (new_status, req_id))
        result = cur.fetchone()
        
        if result:
            amount, user_id_ret = result
            conn.commit()
            
            # ইউজারকে নোটিফিকেশন
            if new_status == 'Paid':
                msg_to_user = f"✅ **উইথড্র সফল!**\n\nআপনার **{amount:.2f} টাকা** সফলভাবে পেমেন্ট করা হয়েছে। ধন্যবাদ!"
            else:
                # Reject হলে ব্যালেন্স ফেরত দেওয়া
                cur.execute("UPDATE users SET earning_balance = earning_balance + %s WHERE user_id = %s", (amount, req_user_id))
                conn.commit()
                msg_to_user = f"❌ **উইথড্র বাতিল।**\n\nদুঃখিত, আপনার **{amount:.2f} টাকার** উইথড্র রিকোয়েস্টটি বাতিল করা হয়েছে। টাকা আপনার অ্যাকাউন্টে ফেরত দেওয়া হয়েছে।"

            bot.send_message(req_user_id, msg_to_user, parse_mode="Markdown")
            
            # অ্যাডমিন মেসেজ আপডেট
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"{call.message.text}\n\n**-- স্ট্যাটাস আপডেট: {new_status} --**",
                parse_mode="Markdown"
            )
            bot.answer_callback_query(call.id, f"✅ Request {req_id} set to {new_status}.")
        else:
            bot.answer_callback_query(call.id, "❌ Request ID not found.")

    except Exception as e:
        conn.rollback()
        bot.answer_callback_query(call.id, f"❌ Error updating status: {e}")
    finally:
        cur.close()
        conn.close()

# --- বট চালু ---
if __name__ == '__main__':
    # ডাটাবেস টেবিল তৈরি নিশ্চিত করতে এটি রান করা প্রয়োজন (হোস্টিংয়ে)
    # Pydroid 3-এ এটি ব্যর্থ হবে, কিন্তু হোস্টিংয়ে ঠিক কাজ করবে
    from db_setup import setup_database
    setup_database() 
    
    print("Bot is polling...")
    bot.infinity_polling()
