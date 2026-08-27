import os
import asyncio
import logging
import secrets
from typing import Optional, List, Dict, Any
import config

logger = logging.getLogger(__name__)

# Database ulanish turi: PostgreSQL (agar DATABASE_URL berilgan bo'lsa) yoki SQLite
DATABASE_URL = config.DATABASE_URL
USE_POSTGRES = bool(DATABASE_URL and DATABASE_URL.startswith("postgres"))

if USE_POSTGRES:
    import asyncpg
    _pool: Optional[asyncpg.Pool] = None
else:
    import aiosqlite
    DB_PATH = "qarz_daftari.db"

async def get_db_pool():
    global _pool
    if USE_POSTGRES and _pool is None:
        # Render internal PostgreSQL ga ulanish
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)
    return _pool

# ==================== DATABASE INITIALIZATION ====================

async def init_db():
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # 1. Shops jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS shops (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL,
                    admin_id BIGINT NOT NULL,
                    phone TEXT,
                    is_active INT DEFAULT 1,
                    subscription_until TIMESTAMP DEFAULT NOW() + INTERVAL '30 days',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)

            # 2. Shop Admins jadvali (Sheriklar)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS shop_admins (
                    id SERIAL PRIMARY KEY,
                    shop_id INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                    telegram_id BIGINT NOT NULL,
                    name TEXT,
                    role TEXT DEFAULT 'staff',
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(shop_id, telegram_id)
                )
            """)

            # 3. Staff invites
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS shop_staff_invites (
                    token TEXT PRIMARY KEY,
                    shop_id INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    is_used INT DEFAULT 0
                )
            """)

            # 4. Customers jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    shop_id INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                    telegram_id BIGINT,
                    full_name TEXT NOT NULL,
                    phone TEXT,
                    balance DOUBLE PRECISION DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(shop_id, telegram_id)
                )
            """)

            # 5. Transactions jadvali
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    shop_id INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    amount DOUBLE PRECISION NOT NULL,
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
        logger.info("PostgreSQL Database muvaffaqiyatli initsializatsiya qilindi!")
    else:
        # Fallback: SQLite
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
            try:
                await db.execute("ALTER TABLE shops ADD COLUMN subscription_until TIMESTAMP")
            except Exception:
                pass
            await db.execute("""
                CREATE TABLE IF NOT EXISTS shop_admins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shop_id INTEGER NOT NULL,
                    telegram_id INTEGER NOT NULL,
                    name TEXT,
                    role TEXT DEFAULT 'staff',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(shop_id) REFERENCES shops(id),
                    UNIQUE(shop_id, telegram_id)
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
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(shop_id) REFERENCES shops(id),
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )
            """)
            await db.commit()

# ==================== SHOPS & ADMINS (DO'KONLAR VA SHERIKLAR) ====================

async def create_shop(name: str, admin_id: int, phone: str = None, days: int = 30) -> int:
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow("""
                    INSERT INTO shops (name, admin_id, phone, is_active, subscription_until)
                    VALUES ($1, $2, $3, 1, NOW() + ($4 || ' days')::INTERVAL)
                    RETURNING id
                """, name, admin_id, phone, str(days))
                shop_id = row['id']
                await conn.execute("""
                    INSERT INTO shop_admins (shop_id, telegram_id, name, role)
                    VALUES ($1, $2, 'Do''kon egasi', 'owner')
                    ON CONFLICT (shop_id, telegram_id) DO NOTHING
                """, shop_id, admin_id)
                return shop_id
    else:
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
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    is_active,
                    subscription_until,
                    EXTRACT(DAY FROM (subscription_until - NOW()))::INT as days_left
                FROM shops 
                WHERE id = $1
            """, shop_id)
            if not row:
                return False, 0, None
            days_left = row['days_left'] if row['days_left'] is not None else 30
            is_valid = bool(row['is_active']) and (days_left >= 0)
            return is_valid, max(0, days_left), row['subscription_until']
    else:
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
                days_left = row['days_left'] if row['days_left'] is not None else 30
                is_valid = bool(row['is_active']) and (days_left >= 0)
                return is_valid, max(0, days_left), row['subscription_until']

async def extend_shop_subscription(shop_id: int, days: int = 30):
    """Do'kon obunasini uzaytirish"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE shops 
                SET subscription_until = (
                    CASE 
                        WHEN subscription_until > NOW() THEN subscription_until 
                        ELSE NOW() 
                    END
                ) + ($1 || ' days')::INTERVAL,
                is_active = 1
                WHERE id = $2
            """, str(days), shop_id)
    else:
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

async def create_staff_invite(shop_id: int) -> str:
    token = secrets.token_hex(6)
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("INSERT INTO shop_staff_invites (token, shop_id, is_used) VALUES ($1, $2, 0)", token, shop_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO shop_staff_invites (token, shop_id, is_used) VALUES (?, ?, 0)", (token, shop_id))
            await db.commit()
    return token

async def use_staff_invite(token: str, telegram_id: int, full_name: str):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            invite = await conn.fetchrow("SELECT * FROM shop_staff_invites WHERE token = $1 AND is_used = 0", token)
            if not invite:
                return None, "Yaroqsiz yoki allaqachon ishlatilgan taklif havolasi!"
            shop_id = invite['shop_id']
            cnt = await conn.fetchval("SELECT COUNT(*) FROM shop_admins WHERE shop_id = $1 AND role = 'staff'", shop_id)
            if cnt >= 2:
                return None, "Ushbu do'konga allaqachon maksimal (2 ta) sherik biriktirilgan!"
            await conn.execute("""
                INSERT INTO shop_admins (shop_id, telegram_id, name, role) 
                VALUES ($1, $2, $3, 'staff')
                ON CONFLICT (shop_id, telegram_id) DO UPDATE SET name = $3
            """, shop_id, telegram_id, full_name)
            await conn.execute("UPDATE shop_staff_invites SET is_used = 1 WHERE token = $1", token)
            shop = await conn.fetchrow("SELECT * FROM shops WHERE id = $1", shop_id)
            return dict(shop), "Muvaffaqiyatli qo'shildi!"
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM shop_staff_invites WHERE token = ? AND is_used = 0", (token,)) as cursor:
                invite = await cursor.fetchone()
                if not invite:
                    return None, "Yaroqsiz yoki allaqachon ishlatilgan taklif havolasi!"
            shop_id = invite['shop_id']
            async with db.execute("SELECT COUNT(*) as cnt FROM shop_admins WHERE shop_id = ? AND role = 'staff'", (shop_id,)) as cursor2:
                row = await cursor2.fetchone()
                if row['cnt'] >= 2:
                    return None, "Ushbu do'konga allaqachon maksimal (2 ta) sherik biriktirilgan!"
            await db.execute(
                "INSERT OR REPLACE INTO shop_admins (shop_id, telegram_id, name, role) VALUES (?, ?, ?, 'staff')",
                (shop_id, telegram_id, full_name)
            )
            await db.execute("UPDATE shop_staff_invites SET is_used = 1 WHERE token = ?", (token,))
            await db.commit()
            async with db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)) as cursor3:
                shop = await cursor3.fetchone()
                return dict(shop), "Muvaffaqiyatli qo'shildi!"

async def get_shop_by_phone(phone: str):
    if not phone:
        return None
    clean_phone = "".join(filter(str.isdigit, phone))
    last_9 = clean_phone[-9:] if len(clean_phone) >= 9 else clean_phone
    
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            shops = await conn.fetch("SELECT * FROM shops")
            for s in shops:
                if s['phone']:
                    s_clean = "".join(filter(str.isdigit, s['phone']))
                    if last_9 in s_clean:
                        return dict(s)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM shops") as cursor:
                shops = await cursor.fetchall()
                for s in shops:
                    if s['phone']:
                        s_clean = "".join(filter(str.isdigit, s['phone']))
                        if last_9 in s_clean:
                            return dict(s)
    return None

async def transfer_shop_ownership(shop_id: int, new_admin_id: int, new_name: str = "Do'kon egasi"):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE shops SET admin_id = $1 WHERE id = $2", new_admin_id, shop_id)
                await conn.execute("DELETE FROM shop_admins WHERE shop_id = $1 AND role = 'owner'", shop_id)
                await conn.execute("""
                    INSERT INTO shop_admins (shop_id, telegram_id, name, role)
                    VALUES ($1, $2, $3, 'owner')
                    ON CONFLICT (shop_id, telegram_id) DO UPDATE SET role = 'owner', name = $3
                """, shop_id, new_admin_id, new_name)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE shops SET admin_id = ? WHERE id = ?", (new_admin_id, shop_id))
            await db.execute("DELETE FROM shop_admins WHERE shop_id = ? AND role = 'owner'", (shop_id,))
            await db.execute(
                "INSERT OR REPLACE INTO shop_admins (shop_id, telegram_id, name, role) VALUES (?, ?, ?, 'owner')",
                (shop_id, new_admin_id, new_name)
            )
            await db.commit()

async def get_shop_by_admin(admin_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT s.* FROM shops s
                JOIN shop_admins sa ON s.id = sa.shop_id
                WHERE sa.telegram_id = $1
                LIMIT 1
            """, admin_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT s.* FROM shops s
                JOIN shop_admins sa ON s.id = sa.shop_id
                WHERE sa.telegram_id = ?
                LIMIT 1
            """, (admin_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

async def get_shop_staff(shop_id: int) -> List[Dict[str, Any]]:
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM shop_admins WHERE shop_id = $1 ORDER BY id ASC", shop_id)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM shop_admins WHERE shop_id = ? ORDER BY id ASC", (shop_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def remove_staff_member(shop_id: int, staff_id: int) -> bool:
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            res = await conn.execute("DELETE FROM shop_admins WHERE id = $1 AND shop_id = $2 AND role = 'staff'", staff_id, shop_id)
            return "DELETE 1" in res
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("DELETE FROM shop_admins WHERE id = ? AND shop_id = ? AND role = 'staff'", (staff_id, shop_id))
            await db.commit()
            return cursor.rowcount > 0

async def get_shop_by_id(shop_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM shops WHERE id = $1", shop_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM shops WHERE id = ?", (shop_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

async def list_all_shops():
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM shops ORDER BY id DESC")
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM shops ORDER BY id DESC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def get_detailed_shops_analysis():
    """Super Admin uchun barcha do'konlarni mijozlar soni va faolligi bilan tahlil qilish"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    s.id,
                    s.name,
                    s.admin_id,
                    s.phone,
                    s.is_active,
                    s.subscription_until,
                    EXTRACT(DAY FROM (s.subscription_until - NOW()))::INT as days_left,
                    COUNT(DISTINCT c.id) as customers_count,
                    COUNT(DISTINCT t.id) as transactions_count,
                    COALESCE(SUM(CASE WHEN c.balance > 0 THEN c.balance ELSE 0 END), 0) as total_debt
                FROM shops s
                LEFT JOIN customers c ON s.id = c.shop_id
                LEFT JOIN transactions t ON s.id = t.shop_id
                GROUP BY s.id, s.name, s.admin_id, s.phone, s.is_active, s.subscription_until
                ORDER BY customers_count DESC, transactions_count DESC, s.id DESC
            """)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT 
                    s.id,
                    s.name,
                    s.admin_id,
                    s.phone,
                    s.is_active,
                    s.subscription_until,
                    CAST(JULIANDAY(s.subscription_until) - JULIANDAY('now') AS INTEGER) as days_left,
                    COUNT(DISTINCT c.id) as customers_count,
                    COUNT(DISTINCT t.id) as transactions_count,
                    COALESCE(SUM(CASE WHEN c.balance > 0 THEN c.balance ELSE 0 END), 0) as total_debt
                FROM shops s
                LEFT JOIN customers c ON s.id = c.shop_id
                LEFT JOIN transactions t ON s.id = t.shop_id
                GROUP BY s.id, s.name, s.admin_id, s.phone, s.is_active, s.subscription_until
                ORDER BY customers_count DESC, transactions_count DESC, s.id DESC
            """
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def update_shop_name(shop_id: int, new_name: str):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE shops SET name = $1 WHERE id = $2", new_name, shop_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE shops SET name = ? WHERE id = ?", (new_name, shop_id))
            await db.commit()

async def toggle_shop_status(shop_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE shops SET is_active = 1 - is_active WHERE id = $1", shop_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE shops SET is_active = 1 - is_active WHERE id = ?", (shop_id,))
            await db.commit()

async def delete_shop(shop_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM shops WHERE id = $1", shop_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM shops WHERE id = ?", (shop_id,))
            await db.commit()

# ==================== CUSTOMERS (MIJOZLAR) ====================

async def add_customer(shop_id: int, full_name: str, phone: str = None, telegram_id: int = None) -> int:
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO customers (shop_id, full_name, phone, telegram_id)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, shop_id, full_name, phone, telegram_id)
            return row['id']
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO customers (shop_id, full_name, phone, telegram_id) VALUES (?, ?, ?, ?)",
                (shop_id, full_name, phone, telegram_id)
            )
            await db.commit()
            return cursor.lastrowid

async def register_telegram_customer(shop_id: int, telegram_id: int, full_name: str, phone: str = None):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM customers WHERE shop_id = $1 AND telegram_id = $2", shop_id, telegram_id)
            if row:
                return dict(row)
            row = await conn.fetchrow("""
                INSERT INTO customers (shop_id, telegram_id, full_name, phone)
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """, shop_id, telegram_id, full_name, phone)
            return dict(row)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM customers WHERE shop_id = ? AND telegram_id = ?", (shop_id, telegram_id)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
            cursor = await db.execute(
                "INSERT INTO customers (shop_id, telegram_id, full_name, phone) VALUES (?, ?, ?, ?)",
                (shop_id, telegram_id, full_name, phone)
            )
            cust_id = cursor.lastrowid
            await db.commit()
            async with db.execute("SELECT * FROM customers WHERE id = ?", (cust_id,)) as cursor2:
                row2 = await cursor2.fetchone()
                return dict(row2)

async def link_customer_telegram(customer_id: int, telegram_id: int, full_name: str = None):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE customers SET telegram_id = $1 WHERE id = $2", telegram_id, customer_id)
            row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("UPDATE customers SET telegram_id = ? WHERE id = ?", (telegram_id, customer_id))
            await db.commit()
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

async def get_customers_by_shop(shop_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM customers WHERE shop_id = $1 ORDER BY balance DESC, full_name ASC", shop_id)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM customers WHERE shop_id = ? ORDER BY balance DESC, full_name ASC", (shop_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def search_customers(shop_id: int, query: str):
    search = f"%{query.strip()}%"
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM customers 
                WHERE shop_id = $1 AND (full_name ILIKE $2 OR phone ILIKE $2)
                ORDER BY full_name ASC
            """, shop_id, search)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM customers 
                WHERE shop_id = ? AND (full_name LIKE ? OR phone LIKE ?)
                ORDER BY full_name ASC
            """, (shop_id, search, search)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def get_customer(customer_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

async def get_customers_by_telegram_id(telegram_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.*, s.name as shop_name, s.phone as shop_phone
                FROM customers c
                JOIN shops s ON c.shop_id = s.id
                WHERE c.telegram_id = $1 AND s.is_active = 1
            """, telegram_id)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT c.*, s.name as shop_name, s.phone as shop_phone
                FROM customers c
                JOIN shops s ON c.shop_id = s.id
                WHERE c.telegram_id = ? AND s.is_active = 1
            """, (telegram_id,)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def delete_customer(customer_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM customers WHERE id = $1", customer_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
            await db.commit()

# ==================== TRANSACTIONS & STATS ====================

async def add_transaction(shop_id: int, customer_id: int, amount: float, tx_type: str, description: str = None):
    balance_delta = amount if tx_type == 'debt' else -amount
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO transactions (shop_id, customer_id, amount, type, description)
                    VALUES ($1, $2, $3, $4, $5)
                """, shop_id, customer_id, amount, tx_type, description)
                row = await conn.fetchrow("""
                    UPDATE customers 
                    SET balance = balance + $1
                    WHERE id = $2
                    RETURNING *
                """, balance_delta, customer_id)
                return dict(row)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO transactions (shop_id, customer_id, amount, type, description) VALUES (?, ?, ?, ?, ?)",
                (shop_id, customer_id, amount, tx_type, description)
            )
            await db.execute("UPDATE customers SET balance = balance + ? WHERE id = ?", (balance_delta, customer_id))
            await db.commit()
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row)

async def get_customer_transactions(customer_id: int, limit: int = 10):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM transactions 
                WHERE customer_id = $1 
                ORDER BY created_at DESC, id DESC 
                LIMIT $2
            """, customer_id, limit)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM transactions 
                WHERE customer_id = ? 
                ORDER BY created_at DESC, id DESC 
                LIMIT ?
            """, (customer_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def get_shop_statistics(shop_id: int, period: str = 'all') -> dict:
    period_filter_pg = {
        'today': "AND created_at >= CURRENT_DATE",
        'week': "AND created_at >= NOW() - INTERVAL '7 days'",
        'month': "AND created_at >= NOW() - INTERVAL '30 days'",
        'all': ""
    }.get(period, "")

    period_filter_sqlite = {
        'today': "AND created_at >= date('now')",
        'week': "AND created_at >= datetime('now', '-7 days')",
        'month': "AND created_at >= datetime('now', '-30 days')",
        'all': ""
    }.get(period, "")

    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            total_customers = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1", shop_id) or 0
            total_active_debt = await conn.fetchval("SELECT SUM(balance) FROM customers WHERE shop_id = $1 AND balance > 0", shop_id) or 0.0
            
            period_debt = await conn.fetchval(f"SELECT SUM(amount) FROM transactions WHERE shop_id = $1 AND type = 'debt' {period_filter_pg}", shop_id) or 0.0
            period_payment = await conn.fetchval(f"SELECT SUM(amount) FROM transactions WHERE shop_id = $1 AND type = 'payment' {period_filter_pg}", shop_id) or 0.0
            total_tx_count = await conn.fetchval(f"SELECT COUNT(*) FROM transactions WHERE shop_id = $1 {period_filter_pg}", shop_id) or 0
            
            top_rows = await conn.fetch("""
                SELECT full_name, balance 
                FROM customers 
                WHERE shop_id = $1 AND balance > 0 
                ORDER BY balance DESC 
                LIMIT 5
            """, shop_id)
            top_debtors = [dict(r) for r in top_rows]
            
            return {
                'total_customers': total_customers,
                'total_debt': total_active_debt,
                'total_active_debt': total_active_debt,
                'period_debt': period_debt,
                'period_payment': period_payment,
                'total_tx_count': total_tx_count,
                'top_debtors': top_debtors,
                'period': period
            }
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) as total_customers, SUM(CASE WHEN balance > 0 THEN balance ELSE 0 END) as total_debt FROM customers WHERE shop_id = ?", (shop_id,)) as cur:
                r1 = dict(await cur.fetchone() or {})
            async with db.execute(f"SELECT SUM(CASE WHEN type = 'debt' THEN amount ELSE 0 END) as period_debt, SUM(CASE WHEN type = 'payment' THEN amount ELSE 0 END) as period_payment, COUNT(*) as total_tx_count FROM transactions WHERE shop_id = ? {period_filter_sqlite}", (shop_id,)) as cur:
                r2 = dict(await cur.fetchone() or {})
            async with db.execute("SELECT full_name, balance FROM customers WHERE shop_id = ? AND balance > 0 ORDER BY balance DESC LIMIT 5", (shop_id,)) as cur:
                top_debtors = [dict(r) for r in await cur.fetchall()]

            return {
                'total_customers': r1.get('total_customers') or 0,
                'total_debt': r1.get('total_debt') or 0.0,
                'total_active_debt': r1.get('total_debt') or 0.0,
                'period_debt': r2.get('period_debt') or 0.0,
                'period_payment': r2.get('period_payment') or 0.0,
                'total_tx_count': r2.get('total_tx_count') or 0,
                'top_debtors': top_debtors,
                'period': period
            }

async def list_shop_customers(shop_id: int, sort_by_debt: bool = True):
    return await get_customers_by_shop(shop_id)

async def list_shop_admins(shop_id: int):
    return await get_shop_staff(shop_id)

async def delete_shop_staff(staff_id: int, shop_id: int):
    return await remove_staff_member(shop_id, staff_id)

async def get_detailed_shop_statistics(shop_id: int, period: str = 'all') -> dict:
    stats = await get_shop_statistics(shop_id, period)
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            indebted = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1 AND balance > 0", shop_id) or 0
            clear = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1 AND balance <= 0", shop_id) or 0
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT COUNT(*) FROM customers WHERE shop_id = ? AND balance > 0", (shop_id,)) as cur:
                indebted = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM customers WHERE shop_id = ? AND balance <= 0", (shop_id,)) as cur:
                clear = (await cur.fetchone())[0]
                
    stats['indebted_customers'] = indebted
    stats['clear_customers'] = clear
    return stats

