import psycopg2
import os
from psycopg2 import sql

# DATABASE_URL এনভায়রনমেন্ট ভ্যারিয়েবল থেকে নেওয়া হবে
DATABASE_URL = os.environ.get('DATABASE_URL')

def setup_database():
    conn = None
    try:
        if not DATABASE_URL:
            print("❌ ERROR: DATABASE_URL environment variable is not set.")
            return

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 1. users টেবিল তৈরি
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

        # 2. withdrawal_requests টেবিল তৈরি
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                request_id BIGSERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                method TEXT NOT NULL,
                amount DECIMAL(10, 2) NOT NULL,
                request_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            );
        """)

        # 3. user_tasks টেবিল তৈরি
        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id BIGINT REFERENCES users(user_id),
                task_date DATE NOT NULL,
                task_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, task_date)
            );
        """)

        # অ্যাডমিন ইউজার যোগ/আপডেট করুন
        ADMIN_ID = 8145444675 # আপনার অ্যাডমিন আইডি
        cur.execute(sql.SQL("""
            INSERT INTO users (user_id, is_admin) VALUES (%s, TRUE)
            ON CONFLICT (user_id) DO UPDATE SET is_admin = TRUE;
        """), (ADMIN_ID,))

        conn.commit()
        print("✅ Database setup complete: Tables and Admin user ensured.")

    except psycopg2.Error as e:
        print(f"❌ Database connection or setup error: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred during DB setup: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    setup_database()
