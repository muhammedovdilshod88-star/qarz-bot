import aiosqlite
from datetime import datetime
from config import DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                phone TEXT,
                is_active INTEGER DEFAULT 1,
                subscription_until TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Migratsiya: subscription_until ustunini tekshirib qo'shish
        try:
            await db.execute("ALTER TABLE shops ADD COLUMN subscription_until TIMESTAMP")
        except Exception:
            pass # Allaqachon mavjud bo'lsa o'tkazib yuboradi

        # Mavjud do'konlarga 30 kunlik muddat berish (agar bo'sh bo'lsa)
        await db.execute("""
            UPDATE shops 
            SET subscription_until = datetime('now', '+30 days') 
            WHERE subscription_until IS NULL
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                telegram_id INTEGER NOT NULL,
                name TEXT,
                role TEXT DEFAULT 'staff', -- 'owner' yoki 'staff'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(shop_id) REFERENCES shops(id),
                UNIQUE(shop_id, telegram_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                telegram_id INTEGER,
                full_name TEXT NOT NULL,
                phone TEXT,
                balance REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(shop_id) REFERENCES shops(id),
                UNIQUE(shop_id, telegram_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL, -- 'debt' (qarz) yoki 'payment' (to'lov)
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(shop_id) REFERENCES shops(id),
                FOREIGN KEY(customer_id) REFERENCES customers(id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS shop_staff_invites (
                token TEXT PRIMARY KEY,
                shop_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_used INTEGER DEFAULT 0,
                FOREIGN KEY(shop_id) REFERENCES shops(id)
            )
        """)
        
        # Mavjud do'kon egalarini shop_admins ga ko'chirish (migratsiya)
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, admin_id, name FROM shops") as cursor:
            existing_shops = await cursor.fetchall()
            for s in existing_shops:
                await db.execute("""
                    INSERT OR IGNORE INTO shop_admins (shop_id, telegram_id, name, role)
                    VALUES (?, ?, ?, 'owner')
                """, (s['id'], s['admin_id'], "Do'kon egasi"))
                
        await db.commit()

# ==================== SHOPS & ADMINS (DO'KONLAR VA SHERIKLAR) ====================

async def create_shop(name: str, admin_id: int, phone: str = None, days: int = 30) -> int:
    """Yangi do'kon ochish (default: 30 kunlik sinov muddati bilan)"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO shops (name, admin_id, phone, is_active, subscription_until) VALUES (?, ?, ?, 1, datetime('now', ?))",
            (name, admin_id, phone, f"+{days} days")
        )
        shop_id = cursor.lastrowid
        await db.execute(
            "INSERT OR IGNORE INTO shop_admins (shop_id, telegram_id, name, role) VALUES (?, ?, 'Do''kon egasi', 'owner')",
            (shop_id, admin_id)
        )
        await db.commit()
        return shop_id

async def check_shop_subscription(shop_id: int):
    """Do'kon obunasi holati va qolgan kunlarni qaytaradi"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT 
                is_active,
                subscription_until,
                CAST(JULIANDAY(subscription_until) - JULIANDAY('now') AS INTEGER) as days_left
            FROM shops 
            WHERE id = ?
        """, (shop_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, 0, None
                
            days_left = row['days_left'] if row['days_left'] is not None else 0
            is_valid = bool(row['is_active']) and (days_left >= 0)
            return is_valid, max(0, days_left), row['subscription_until']

async def extend_shop_subscription(shop_id: int, days: int = 30):
    """Do'kon obunasini uzaytirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE shops 
            SET subscription_until = datetime(
                CASE 
                    WHEN subscription_until > datetime('now') THEN subscription_until 
                    ELSE datetime('now') 
                END, 
                ?
            ), is_active = 1
            WHERE id = ?
        """, (f"+{days} days", shop_id))
        await db.commit()

import secrets

async def create_staff_invite(shop_id: int) -> str:
    """Sherik uchun bir martalik taklif tokeni yaratish"""
    token = secrets.token_hex(6)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO shop_staff_invites (token, shop_id, is_used) VALUES (?, ?, 0)",
            (token, shop_id)
        )
        await db.commit()
    return token

async def use_staff_invite(token: str, telegram_id: int, full_name: str):
    """Sherik taklif tokenini bosganda uni adminga aylantirish"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_staff_invites WHERE token = ? AND is_used = 0", (token,)) as cursor:
            invite = await cursor.fetchone()
            if not invite:
                return None, "Yaroqsiz yoki allaqachon ishlatilgan taklif havolasi!"
                
        shop_id = invite['shop_id']
        
        # 2 ta sherik limitini tekshirish
        async with db.execute("SELECT COUNT(*) as cnt FROM shop_admins WHERE shop_id = ? AND role = 'staff'", (shop_id,)) as cursor2:
            row = await cursor2.fetchone()
            if row['cnt'] >= 2:
                return None, "Ushbu do'konga allaqachon maksimal (2 ta) sherik biriktirilgan!"
                
        # Sherik sifatida qo'shish
        await db.execute(
            "INSERT OR REPLACE INTO shop_admins (shop_id, telegram_id, name, role) VALUES (?, ?, ?, 'staff')",
            (shop_id, telegram_id, full_name)
        )
        await db.execute("UPDATE shop_staff_invites SET is_used = 1 WHERE token = ?", (token,))
        await db.commit()
        
        async with db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)) as cursor3:
            shop = await cursor3.fetchone()
            return shop, "Muvaffaqiyatli qo'shildi!"

async def get_shop_by_admin(admin_id: int):
    """Foydalanuvchi do'kon egasi yoki qo'shilgan sherik bo'lsa do'konni qaytaradi"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT s.*, sa.role as admin_role, sa.name as staff_name
            FROM shops s
            JOIN shop_admins sa ON s.id = sa.shop_id
            WHERE sa.telegram_id = ? AND s.is_active = 1
            LIMIT 1
        """, (admin_id,)) as cursor:
            return await cursor.fetchone()

async def list_shop_admins(shop_id: int):
    """Do'kondagi barcha adminlar (ega + sheriklar) ro'yxati"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shop_admins WHERE shop_id = ? ORDER BY id ASC", (shop_id,)) as cursor:
            return await cursor.fetchall()

async def add_shop_staff(shop_id: int, telegram_id: int, name: str) -> bool:
    """Sherik qo'shish (maksimal 2 ta qo'shimcha sherik)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Nechta sherik borligini tekshiramiz
        async with db.execute("SELECT COUNT(*) as cnt FROM shop_admins WHERE shop_id = ? AND role = 'staff'", (shop_id,)) as cursor:
            row = await cursor.fetchone()
            if row['cnt'] >= 2:
                return False  # Limit: maksimal 2 ta sherik
                
        await db.execute(
            "INSERT OR REPLACE INTO shop_admins (shop_id, telegram_id, name, role) VALUES (?, ?, ?, 'staff')",
            (shop_id, telegram_id, name)
        )
        await db.commit()
        return True

async def delete_shop_staff(shop_admin_id: int, shop_id: int):
    """Sherikni o'chirish (faqat staff o'chiriladi, owner o'chirilmaydi)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM shop_admins WHERE id = ? AND shop_id = ? AND role = 'staff'", (shop_admin_id, shop_id))
        await db.commit()

async def get_shop_by_id(shop_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)) as cursor:
            return await cursor.fetchone()

async def update_shop_name(shop_id: int, new_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE shops SET name = ? WHERE id = ?", (new_name, shop_id))
        await db.commit()

async def list_all_shops():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM shops ORDER BY id DESC") as cursor:
            return await cursor.fetchall()

async def toggle_shop_status(shop_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE shops SET is_active = 1 - is_active WHERE id = ?", (shop_id,))
        await db.commit()

async def delete_shop(shop_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM transactions WHERE shop_id = ?", (shop_id,))
        await db.execute("DELETE FROM customers WHERE shop_id = ?", (shop_id,))
        await db.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
        await db.commit()

# ==================== CUSTOMERS (MIJOZLAR) ====================

async def add_manual_customer(shop_id: int, full_name: str, phone: str = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO customers (shop_id, full_name, phone, balance) VALUES (?, ?, ?, 0.0)",
            (shop_id, full_name, phone)
        )
        await db.commit()
        return cursor.lastrowid

async def link_customer_telegram(customer_id: int, telegram_id: int, full_name: str = None):
    """Qo'lda kiritilgan mijozni Telegram profiliga bog'lash"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
            cust = await cursor.fetchone()
            if not cust:
                return None
            
        await db.execute(
            "UPDATE customers SET telegram_id = ? WHERE id = ?",
            (telegram_id, customer_id)
        )
        await db.commit()
        
        async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor2:
            return await cursor2.fetchone()

async def register_telegram_customer(shop_id: int, telegram_id: int, full_name: str, phone: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Avval mavjudligini tekshiramiz
        async with db.execute(
            "SELECT * FROM customers WHERE shop_id = ? AND telegram_id = ?", 
            (shop_id, telegram_id)
        ) as cursor:
            cust = await cursor.fetchone()
            if cust:
                return cust
            
            # Agar mavjud bo'lmasa yangi qo'shamiz
            cursor2 = await db.execute(
                "INSERT INTO customers (shop_id, telegram_id, full_name, phone, balance) VALUES (?, ?, ?, ?, 0.0)",
                (shop_id, telegram_id, full_name, phone)
            )
            await db.commit()
            cust_id = cursor2.lastrowid
            
        async with db.execute("SELECT * FROM customers WHERE id = ?", (cust_id,)) as cursor3:
            return await cursor3.fetchone()

async def delete_customer(customer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM transactions WHERE customer_id = ?", (customer_id,))
        await db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        await db.commit()

async def get_customer(customer_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
            return await cursor.fetchone()

async def get_customers_by_telegram_id(telegram_id: int):
    """Mijoz bog'langan barcha do'konlardagi hisoblari"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT c.*, s.name as shop_name, s.phone as shop_phone 
            FROM customers c 
            JOIN shops s ON c.shop_id = s.id 
            WHERE c.telegram_id = ? AND s.is_active = 1
        """, (telegram_id,)) as cursor:
            return await cursor.fetchall()

async def list_shop_customers(shop_id: int, sort_by_debt: bool = True):
    """Do'kondagi mijozlar ro'yxati (default: eng katta qarz egalari tepada)"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM customers WHERE shop_id = ? "
        if sort_by_debt:
            query += "ORDER BY balance DESC, full_name ASC"
        else:
            query += "ORDER BY full_name ASC"
            
        async with db.execute(query, (shop_id,)) as cursor:
            return await cursor.fetchall()

async def search_customers(shop_id: int, query: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        search_pattern = f"%{query}%"
        async with db.execute("""
            SELECT * FROM customers 
            WHERE shop_id = ? AND (full_name LIKE ? OR phone LIKE ?) 
            ORDER BY balance DESC
        """, (shop_id, search_pattern, search_pattern)) as cursor:
            return await cursor.fetchall()

# ==================== TRANSACTIONS (QARZ / TO'LOV) ====================

async def add_transaction(shop_id: int, customer_id: int, amount: float, tx_type: str, description: str = None):
    """
    tx_type: 'debt' (qarz oshadi) yoki 'payment' (qarz kamayadi)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Tranzaksiyani kiritish
        await db.execute(
            "INSERT INTO transactions (shop_id, customer_id, amount, type, description) VALUES (?, ?, ?, ?, ?)",
            (shop_id, customer_id, amount, tx_type, description)
        )
        
        # 2. Balansni yangilash
        if tx_type == 'debt':
            await db.execute(
                "UPDATE customers SET balance = balance + ? WHERE id = ?",
                (amount, customer_id)
            )
        elif tx_type == 'payment':
            await db.execute(
                "UPDATE customers SET balance = balance - ? WHERE id = ?",
                (amount, customer_id)
            )
            
        await db.commit()
        
        # Yangilangan mijozni qaytarish
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
            return await cursor.fetchone()

async def get_customer_transactions(customer_id: int, limit: int = 15):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM transactions 
            WHERE customer_id = ? 
            ORDER BY id DESC 
            LIMIT ?
        """, (customer_id, limit)) as cursor:
            return await cursor.fetchall()

async def get_detailed_shop_statistics(shop_id: int, period: str = 'all'):
    """
    period: 'today', 'week', 'month', 'all'
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        
        # Vaqt filtri bo'yicha shart
        time_condition = ""
        if period == 'today':
            time_condition = " AND date(created_at) = date('now', 'localtime')"
        elif period == 'week':
            time_condition = " AND created_at >= datetime('now', '-7 days', 'localtime')"
        elif period == 'month':
            time_condition = " AND created_at >= datetime('now', '-30 days', 'localtime')"

        # 1. Davriy operatsiyalar (qarz va to'lovlar)
        async with db.execute(f"""
            SELECT 
                COALESCE(SUM(CASE WHEN type = 'debt' THEN amount ELSE 0 END), 0) as period_debt,
                COALESCE(SUM(CASE WHEN type = 'payment' THEN amount ELSE 0 END), 0) as period_payment,
                COUNT(id) as total_tx_count
            FROM transactions 
            WHERE shop_id = ? {time_condition}
        """, (shop_id,)) as cursor:
            tx_row = await cursor.fetchone()

        # 2. Umumiy mijozlar va qoldiq holati
        async with db.execute("""
            SELECT 
                COUNT(id) as total_customers,
                COUNT(CASE WHEN balance > 0 THEN 1 END) as indebted_customers,
                COUNT(CASE WHEN balance <= 0 THEN 1 END) as clear_customers,
                COALESCE(SUM(CASE WHEN balance > 0 THEN balance ELSE 0 END), 0) as total_active_debt
            FROM customers 
            WHERE shop_id = ?
        """, (shop_id,)) as cursor2:
            cust_row = await cursor2.fetchone()

        # 3. TOP-3 eng katta qarzdorlar
        async with db.execute("""
            SELECT full_name, balance 
            FROM customers 
            WHERE shop_id = ? AND balance > 0 
            ORDER BY balance DESC 
            LIMIT 3
        """, (shop_id,)) as cursor3:
            top_debtors = await cursor3.fetchall()

        return {
            "period": period,
            "period_debt": tx_row['period_debt'],
            "period_payment": tx_row['period_payment'],
            "total_tx_count": tx_row['total_tx_count'],
            "total_customers": cust_row['total_customers'],
            "indebted_customers": cust_row['indebted_customers'],
            "clear_customers": cust_row['clear_customers'],
            "total_active_debt": cust_row['total_active_debt'],
            "top_debtors": top_debtors
        }

async def get_shop_statistics(shop_id: int):
    return await get_detailed_shop_statistics(shop_id, 'all')
