# === Smart Earn Bot ===
import telebot, os, psycopg2, pytz
from psycopg2 import sql
from datetime import datetime

BOT_TOKEN = os.environ.get('BOT_TOKEN')
DATABASE_URL = os.environ.get('DATABASE_URL')
ADMIN_ID = os.environ.get('ADMIN_ID')

TASK_REWARD = 5.00
REFERRAL_BONUS = 2.00
MIN_WITHDRAWAL = 100.00
TIMEZONE = 'Asia/Dhaka'

bot = telebot.TeleBot(BOT_TOKEN)

def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"DB Error: {e}")
        return None

def check_channel_membership(user_id):
    REQUIRED_CHANNELS = ['@SmartEarnOfficial', '@SmartEarnUpdates']
    for channel in REQUIRED_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username

    if not check_channel_membership(user_id):
        text = "📢 অনুগ্রহ করে নিচের চ্যানেলগুলোতে জয়েন করুন:\n\n"
        text += "👉 @SmartEarnOfficial\n👉 @SmartEarnUpdates\n\n✅ জয়েন করার পর আবার /start দিন।"
        bot.send_message(user_id, text)
        return
    
    markup = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('💰 Earning', '💸 Withdraw', '👥 Referral', '📊 Balance')
    bot.send_message(user_id, f"স্বাগতম @{username or 'User'}! 🎉\n\nআপনার কাজ শুরু করতে মেনু ব্যবহার করুন।", reply_markup=markup)

@bot.message_handler(regexp='📊 Balance')
def handle_balance(message):
    bot.send_message(message.chat.id, "📊 আপনার বর্তমান ব্যালেন্স ফিচার শিগগিরই চালু হবে!")

if __name__ == '__main__':
    print("✅ Bot is polling...")
    bot.polling(none_stop=True)
