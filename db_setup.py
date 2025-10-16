import psycopg2
import os
from psycopg2 import sql
import psycopg2
import os
from psycopg2 import sql

# DB URL কে সরাসরি এনভায়রনমেন্ট ভ্যারিয়েবল থেকে নেওয়া হবে
# কোডের এই অংশে হার্ডকোডেড বা ডিফল্ট কোনো URL রাখবেন না
DATABASE_URL = os.environ.get('DATABASE_URL') 

# এই অংশটি সংযোগ ব্যর্থতা হ্যান্ডেল করবে
if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable is not set. Check Render settings.")
    # আমরা এই ক্ষেত্রে কোড ফেইল না করিয়ে শুধুমাত্র একটি মেসেজ দেখাচ্ছি।

def setup_database():
    conn = None
    try:
        # DB URL না থাকলে সংযোগ প্রচেষ্টা ব্যর্থ হবে, যা আমরা চাই।
        if not DATABASE_URL:
             raise Exception("DATABASE_URL environment variable is not set.")
             
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # ... বাকি টেবিল তৈরির কোড ...

# হোস্টিংয়ে Environment Variable থেকে URL নেওয়ার জন্য
if 'DATABASE_URL' in os.environ:
    DATABASE_URL = os.environ['DATABASE_URL']

def setup_database():
    conn = None
    try:
        # ডাটাবেসের সাথে সংযোগ স্থাপন
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 1. users টেবিল তৈরি (ইউজার ব্যালেন্স, রেফারের জন্য)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                earning_balance DECIMAL(10, 2) DEFAULT 0.00,
                referral_count INTEGER DEFAULT 0,
                is_admin BOOLEAN DEFAULT FALSE,
                is_banned BOOLEAN DEFAULT FALSE,
                last_task_time TIMESTAMP WITHOUT TIME ZONE,
                registration_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 2. withdrawal_requests টেবিল তৈরি (উইথড্র ডেটা সংরক্ষণের জন্য)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                amount DECIMAL(10, 2) NOT NULL,
                method TEXT NOT NULL,
                wallet_info TEXT NOT NULL,
                request_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Pending'
            );
        """)
        
        # 3. user_tasks টেবিল (ইউজার কতবার টাস্ক করেছে তা সংরক্ষণের জন্য)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id BIGINT REFERENCES users(user_id),
                task_date DATE NOT NULL,
                task_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, task_date)
            );
        """)
        
        # 4. অ্যাডমিন ইউজার তৈরি বা নিশ্চিত করা
        # আপনার অ্যাডমিন আইডি (8145444675) অবশ্যই এখানে থাকতে হবে
        ADMIN_ID = 8145444675 # <- আপনার টেলিগ্রাম ইউজার আইডি
        cur.execute(sql.SQL("""
            INSERT INTO users (user_id, is_admin) VALUES (%s, TRUE)
            ON CONFLICT (user_id) DO UPDATE SET is_admin = TRUE;
        """), (ADMIN_ID,))

        conn.commit()
        print("Database setup complete: Tables and Admin user ensured.")

    except Exception as e:
        print(f"Database setup error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    setup_database()
