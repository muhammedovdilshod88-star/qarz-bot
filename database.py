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

            # 4. Customers jadvali (due_date, balance_usd va ledger_type bilan)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    shop_id INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                    telegram_id BIGINT,
                    full_name TEXT NOT NULL,
                    phone TEXT,
                    balance DOUBLE PRECISION DEFAULT 0.0,
                    balance_usd DOUBLE PRECISION DEFAULT 0.0,
                    ledger_type VARCHAR(20) DEFAULT 'receivable',
                    due_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(shop_id, telegram_id)
                )
            """)
            # Ustun mavjud bo'lmasa qo'shish
            try:
                await conn.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS due_date TIMESTAMP")
                await conn.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS balance_usd DOUBLE PRECISION DEFAULT 0.0")
                await conn.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS ledger_type VARCHAR(20) DEFAULT 'receivable'")
            except Exception:
                pass

            # 5. Transactions jadvali (currency bilan)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id SERIAL PRIMARY KEY,
                    shop_id INT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
                    customer_id INT NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
                    amount DOUBLE PRECISION NOT NULL,
                    currency VARCHAR(10) DEFAULT 'UZS',
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            # 6. Users jadvali (Telefon raqamni majburiy tasdiqlash uchun)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id BIGINT PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    phone TEXT,
                    ledger_mode VARCHAR(20) DEFAULT 'receivable',
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS ledger_mode VARCHAR(20) DEFAULT 'receivable'")
        logger.info("PostgreSQL Database muvaffaqiyatli initsializatsiya qilindi!")
    else:
        # Fallback: SQLite
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    phone TEXT,
                    ledger_mode TEXT DEFAULT 'receivable',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            try:
                await db.execute("ALTER TABLE users ADD COLUMN ledger_mode TEXT DEFAULT 'receivable'")
            except Exception:
                pass
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
                    balance_usd REAL DEFAULT 0.0,
                    ledger_type TEXT DEFAULT 'receivable',
                    due_date TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(shop_id) REFERENCES shops(id),
                    UNIQUE(shop_id, telegram_id)
                )
            """)
            try:
                await db.execute("ALTER TABLE customers ADD COLUMN balance_usd REAL DEFAULT 0.0")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE customers ADD COLUMN due_date TIMESTAMP")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE customers ADD COLUMN ledger_type TEXT DEFAULT 'receivable'")
            except Exception:
                pass
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    shop_id INTEGER NOT NULL,
                    customer_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT DEFAULT 'UZS',
                    type TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(shop_id) REFERENCES shops(id),
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )
            """)
            try:
                await db.execute("ALTER TABLE transactions ADD COLUMN currency TEXT DEFAULT 'UZS'")
            except Exception:
                pass
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
            if cnt >= 5:
                return None, "Ushbu do'konga allaqachon maksimal (5 ta) sotuvchi/sherik biriktirilgan!"
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
                if row['cnt'] >= 5:
                    return None, "Ushbu do'konga allaqachon maksimal (5 ta) sotuvchi/sherik biriktirilgan!"
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
async def search_shops(query: str):
    """Do'kon nomi, telefon raqami yoki admin Telegram ID si bo'yicha tezkor qidirish"""
    clean_q = f"%{query.strip()}%"
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    s.id, s.name, s.admin_id, s.phone, s.is_active, s.subscription_until,
                    EXTRACT(DAY FROM (s.subscription_until - NOW()))::INT as days_left,
                    COUNT(DISTINCT c.id) as customers_count,
                    COALESCE(SUM(CASE WHEN c.balance > 0 THEN c.balance ELSE 0 END), 0) as total_debt
                FROM shops s
                LEFT JOIN customers c ON s.id = c.shop_id
                WHERE s.name ILIKE $1 
                   OR s.phone ILIKE $1 
                   OR CAST(s.admin_id AS TEXT) ILIKE $1
                   OR CAST(s.id AS TEXT) = $2
                GROUP BY s.id, s.name, s.admin_id, s.phone, s.is_active, s.subscription_until
                ORDER BY s.id DESC
                LIMIT 20
            """, clean_q, query.strip())
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            query_sql = """
                SELECT 
                    s.id, s.name, s.admin_id, s.phone, s.is_active, s.subscription_until,
                    CAST(JULIANDAY(s.subscription_until) - JULIANDAY('now') AS INTEGER) as days_left,
                    COUNT(DISTINCT c.id) as customers_count,
                    COALESCE(SUM(CASE WHEN c.balance > 0 THEN c.balance ELSE 0 END), 0) as total_debt
                FROM shops s
                LEFT JOIN customers c ON s.id = c.shop_id
                WHERE s.name LIKE ? 
                   OR s.phone LIKE ? 
                   OR CAST(s.admin_id AS TEXT) LIKE ?
                   OR CAST(s.id AS TEXT) = ?
                GROUP BY s.id, s.name, s.admin_id, s.phone, s.is_active, s.subscription_until
                ORDER BY s.id DESC
                LIMIT 20
            """
            async with db.execute(query_sql, (clean_q, clean_q, clean_q, query.strip())) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def update_shop_phone(shop_id: int, new_phone: str):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE shops SET phone = $1 WHERE id = $2", new_phone, shop_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE shops SET phone = ? WHERE id = ?", (new_phone, shop_id))
            await db.commit()

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
                LEFT JOIN shop_admins sa ON s.id = sa.shop_id
                WHERE s.admin_id = $1 OR sa.telegram_id = $1
                ORDER BY s.id DESC
                LIMIT 1
            """, admin_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT s.* FROM shops s
                LEFT JOIN shop_admins sa ON s.id = sa.shop_id
                WHERE s.admin_id = ? OR sa.telegram_id = ?
                ORDER BY s.id DESC
                LIMIT 1
            """, (admin_id, admin_id)) as cursor:
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
    """Super Admin uchun barcha do'konlarni mijozlar soni va faolligi bilan aniq tahlil qilish"""
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
                    COALESCE(c_stat.customers_count, 0) as customers_count,
                    COALESCE(c_stat.total_debt, 0) as total_debt,
                    COALESCE(c_stat.total_debt_usd, 0) as total_debt_usd,
                    COALESCE(t_stat.transactions_count, 0) as transactions_count
                FROM shops s
                LEFT JOIN (
                    SELECT shop_id, 
                           COUNT(id) as customers_count,
                           SUM(CASE WHEN balance > 0 THEN balance ELSE 0 END) as total_debt,
                           SUM(CASE WHEN balance_usd > 0 THEN balance_usd ELSE 0 END) as total_debt_usd
                    FROM customers
                    GROUP BY shop_id
                ) c_stat ON s.id = c_stat.shop_id
                LEFT JOIN (
                    SELECT shop_id, COUNT(id) as transactions_count
                    FROM transactions
                    GROUP BY shop_id
                ) t_stat ON s.id = t_stat.shop_id
                ORDER BY customers_count DESC, s.id DESC
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
                    COALESCE(c_stat.customers_count, 0) as customers_count,
                    COALESCE(c_stat.total_debt, 0) as total_debt,
                    COALESCE(c_stat.total_debt_usd, 0) as total_debt_usd,
                    COALESCE(t_stat.transactions_count, 0) as transactions_count
                FROM shops s
                LEFT JOIN (
                    SELECT shop_id, 
                           COUNT(id) as customers_count,
                           SUM(CASE WHEN balance > 0 THEN balance ELSE 0 END) as total_debt,
                           SUM(CASE WHEN balance_usd > 0 THEN balance_usd ELSE 0 END) as total_debt_usd
                    FROM customers
                    GROUP BY shop_id
                ) c_stat ON s.id = c_stat.shop_id
                LEFT JOIN (
                    SELECT shop_id, COUNT(id) as transactions_count
                    FROM transactions
                    GROUP BY shop_id
                ) t_stat ON s.id = t_stat.shop_id
                ORDER BY customers_count DESC, s.id DESC
            """
            async with db.execute(query) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

async def get_platform_users_summary():
    """Botga start bosib telefonini tasdiqlagan barcha foydalanuvchilar (Users) statistikasi"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            total_users = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
            recent_rows = await conn.fetch("""
                SELECT full_name, phone, telegram_id, created_at 
                FROM users 
                ORDER BY created_at DESC 
                LIMIT 8
            """)
            return {
                'total_users': total_users,
                'recent_users': [dict(r) for r in recent_rows]
            }
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                total_users = (await cur.fetchone())[0] or 0
            async with db.execute("SELECT full_name, phone, telegram_id, created_at FROM users ORDER BY created_at DESC LIMIT 8") as cur:
                recent_rows = await cur.fetchall()
            return {
                'total_users': total_users,
                'recent_users': [dict(r) for r in recent_rows]
            }
async def get_expiring_shops():
    """Obunasi tugashiga 3 kun, 1 kun qolgan yoki tugagan do'konlarni olish (Avtomatik billing eslatmasi uchun)"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    s.id, s.name, s.admin_id, s.phone, s.subscription_until,
                    EXTRACT(DAY FROM (s.subscription_until - NOW()))::INT as days_left
                FROM shops s
                WHERE s.is_active = 1
                  AND (
                      EXTRACT(DAY FROM (s.subscription_until - NOW()))::INT IN (3, 1, 0, -1)
                  )
            """)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT 
                    s.id, s.name, s.admin_id, s.phone, s.subscription_until,
                    CAST(JULIANDAY(s.subscription_until) - JULIANDAY('now') AS INTEGER) as days_left
                FROM shops s
                WHERE s.is_active = 1
                  AND (
                      CAST(JULIANDAY(s.subscription_until) - JULIANDAY('now') AS INTEGER) IN (3, 1, 0, -1)
                  )
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

# ==================== CUSTOMERS (MIJOZLAR VA HAQDORLAR) ====================

async def find_telegram_id_by_phone(phone: str):
    """Telefon raqam bo'yicha users jadvalidan foydalanuvchining Telegram ID sini topish"""
    if not phone:
        return None
    clean = "".join([c for c in str(phone) if c.isdigit()])
    if len(clean) < 7:
        return None
    last9 = clean[-9:]
    
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT telegram_id FROM users 
                WHERE RIGHT(REGEXP_REPLACE(COALESCE(phone, ''), '[^0-9]', '', 'g'), 9) = $1
                ORDER BY created_at DESC LIMIT 1
            """, last9)
            return row['telegram_id'] if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT telegram_id, phone FROM users WHERE phone IS NOT NULL") as cur:
                rows = await cur.fetchall()
                for r in rows:
                    u_clean = "".join([c for c in str(r['phone']) if c.isdigit()])
                    if len(u_clean) >= 9 and u_clean[-9:] == last9:
                        return r['telegram_id']
    return None

async def add_customer(shop_id: int, full_name: str, phone: str = None, telegram_id: int = None, ledger_type: str = 'receivable') -> int:
    ledger_type = ledger_type or 'receivable'
    if not telegram_id and phone:
        found_tg = await find_telegram_id_by_phone(phone)
        if found_tg:
            telegram_id = found_tg
            
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO customers (shop_id, full_name, phone, telegram_id, ledger_type)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
            """, shop_id, full_name, phone, telegram_id, ledger_type)
            return row['id']
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                "INSERT INTO customers (shop_id, full_name, phone, telegram_id, ledger_type) VALUES (?, ?, ?, ?, ?)",
                (shop_id, full_name, phone, telegram_id, ledger_type)
            )
            await db.commit()
            return cursor.lastrowid

add_manual_customer = add_customer

async def register_telegram_customer(shop_id: int, telegram_id: int, full_name: str, phone: str = None):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM customers WHERE shop_id = $1 AND telegram_id = $2", shop_id, telegram_id)
            if row:
                if phone and row['phone'] != phone:
                    await conn.execute("UPDATE customers SET phone = $1 WHERE id = $2", phone, row['id'])
                    row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", row['id'])
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
                    if phone and row['phone'] != phone:
                        await db.execute("UPDATE customers SET phone = ? WHERE id = ?", (phone, row['id']))
                        await db.commit()
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
            cust = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            if not cust:
                return None
            await conn.execute("UPDATE customers SET telegram_id = NULL WHERE shop_id = $1 AND telegram_id = $2 AND id != $3", cust['shop_id'], telegram_id, customer_id)
            await conn.execute("UPDATE customers SET telegram_id = $1 WHERE id = $2", telegram_id, customer_id)
            row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                cust = await cursor.fetchone()
            if not cust:
                return None
            await db.execute("UPDATE customers SET telegram_id = NULL WHERE shop_id = ? AND telegram_id = ? AND id != ?", (cust['shop_id'], telegram_id, customer_id))
            await db.execute("UPDATE customers SET telegram_id = ? WHERE id = ?", (telegram_id, customer_id))
            await db.commit()
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

async def update_customer_phone(customer_id: int, phone: str):
    """Mijozning telefon raqamini kiritish/yangilash va uni users bazasidagi Telegram ID ga avtomatik bog'lash"""
    telegram_id = None
    if phone:
        telegram_id = await find_telegram_id_by_phone(phone)
        
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            cust = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            if not cust:
                return None
            if telegram_id:
                await conn.execute("UPDATE customers SET telegram_id = NULL WHERE shop_id = $1 AND telegram_id = $2 AND id != $3", cust['shop_id'], telegram_id, customer_id)
                await conn.execute("UPDATE customers SET phone = $1, telegram_id = $2 WHERE id = $3", phone, telegram_id, customer_id)
            else:
                await conn.execute("UPDATE customers SET phone = $1 WHERE id = $2", phone, customer_id)
            row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", customer_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                cust = await cursor.fetchone()
            if not cust:
                return None
            if telegram_id:
                await db.execute("UPDATE customers SET telegram_id = NULL WHERE shop_id = ? AND telegram_id = ? AND id != ?", (cust['shop_id'], telegram_id, customer_id))
                await db.execute("UPDATE customers SET phone = ?, telegram_id = ? WHERE id = ?", (phone, telegram_id, customer_id))
            else:
                await db.execute("UPDATE customers SET phone = ? WHERE id = ?", (phone, customer_id))
            await db.commit()
            async with db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

async def set_customer_due_date(customer_id: int, days: int):
    """Mijoz uchun to'lov muddatini belgilash (kunlar hisobida)"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if days <= 0:
                await conn.execute("UPDATE customers SET due_date = NULL WHERE id = $1", customer_id)
            else:
                await conn.execute("UPDATE customers SET due_date = NOW() + ($1 || ' days')::INTERVAL WHERE id = $2", str(days), customer_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            if days <= 0:
                await db.execute("UPDATE customers SET due_date = NULL WHERE id = ?", (customer_id,))
            else:
                await db.execute("UPDATE customers SET due_date = datetime('now', ?) WHERE id = ?", (f"+{days} days", customer_id))
            await db.commit()

async def set_customer_due_specific_date(customer_id: int, date_val):
    """Mijoz uchun aniq sana bo'yicha muddat belgilash"""
    from datetime import datetime, date, time
    dt_obj = None
    if date_val:
        if isinstance(date_val, datetime):
            dt_obj = date_val
        elif isinstance(date_val, date):
            dt_obj = datetime.combine(date_val, time(10, 0, 0))
        elif isinstance(date_val, str):
            clean_str = date_val.strip().replace("/", ".").replace("-", ".")
            parts = [int(p) for p in clean_str.split(".") if p.isdigit()]
            if len(parts) == 3:
                if parts[0] > 1000:  # YYYY.MM.DD
                    dt_obj = datetime(parts[0], parts[1], parts[2], 10, 0, 0)
                else:  # DD.MM.YYYY
                    dt_obj = datetime(parts[2], parts[1], parts[0], 10, 0, 0)

    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if not dt_obj:
                await conn.execute("UPDATE customers SET due_date = NULL WHERE id = $1", customer_id)
            else:
                await conn.execute("UPDATE customers SET due_date = $1 WHERE id = $2", dt_obj, customer_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            if not dt_obj:
                await db.execute("UPDATE customers SET due_date = NULL WHERE id = ?", (customer_id,))
            else:
                await db.execute("UPDATE customers SET due_date = ? WHERE id = ?", (dt_obj.strftime("%Y-%m-%d %H:%M:%S"), customer_id))
            await db.commit()

async def get_due_reminders():
    """Bugun to'lov muddati yetib kelgan qarzdor va haqdorlarni olish (Avtomatik eslatma uchun)"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.*, s.name as shop_name, s.admin_id as shop_admin_id
                FROM customers c
                JOIN shops s ON c.shop_id = s.id
                WHERE (c.balance > 0 OR c.balance_usd > 0)
                  AND c.due_date IS NOT NULL 
                  AND c.due_date::DATE <= CURRENT_DATE
                  AND (c.ledger_type = 'payable' OR (COALESCE(c.ledger_type, 'receivable') = 'receivable' AND c.telegram_id IS NOT NULL))
                  AND s.is_active = 1
            """)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT c.*, s.name as shop_name, s.admin_id as shop_admin_id
                FROM customers c
                JOIN shops s ON c.shop_id = s.id
                WHERE (c.balance > 0 OR c.balance_usd > 0)
                  AND c.due_date IS NOT NULL 
                  AND date(c.due_date) <= date('now')
                  AND (c.ledger_type = 'payable' OR (COALESCE(c.ledger_type, 'receivable') = 'receivable' AND c.telegram_id IS NOT NULL))
                  AND s.is_active = 1
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def get_customers_by_shop(shop_id: int, ledger_type: str = None, user_telegram_id: int = None):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if ledger_type == 'payable' and user_telegram_id:
                # 1. O'zining payable haqdorlari
                rows_own = await conn.fetch("SELECT * FROM customers WHERE shop_id = $1 AND COALESCE(ledger_type, 'receivable') = 'payable' ORDER BY balance DESC, balance_usd DESC, full_name ASC", shop_id)
                # 2. Boshqa do'konlar ushbu userga receivable (qarz) yozgan holat -> Bu inson uchun Haqdor (payable)
                rows_ext = await conn.fetch("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'payable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = $1 AND c.shop_id != $2 AND s.is_active = 1 AND COALESCE(c.ledger_type, 'receivable') = 'receivable' AND (c.balance > 0 OR c.balance_usd > 0)
                    ORDER BY c.balance DESC, c.balance_usd DESC
                """, user_telegram_id, shop_id)
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif (ledger_type == 'receivable' or ledger_type is None) and user_telegram_id:
                # 1. O'zining receivable qarzdorlari
                rows_own = await conn.fetch("SELECT * FROM customers WHERE shop_id = $1 AND COALESCE(ledger_type, 'receivable') = 'receivable' ORDER BY balance DESC, balance_usd DESC, full_name ASC", shop_id)
                # 2. Boshqa do'konlar ushbu userdan payable (qarz oldim) deb ochgan holat -> Bu inson uchun Qarzdor (receivable)
                rows_ext = await conn.fetch("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Qarz olgan do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'receivable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = $1 AND c.shop_id != $2 AND s.is_active = 1 AND c.ledger_type = 'payable' AND (c.balance > 0 OR c.balance_usd > 0)
                    ORDER BY c.balance DESC, c.balance_usd DESC
                """, user_telegram_id, shop_id)
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif ledger_type:
                rows = await conn.fetch("SELECT * FROM customers WHERE shop_id = $1 AND COALESCE(ledger_type, 'receivable') = $2 ORDER BY balance DESC, balance_usd DESC, full_name ASC", shop_id, ledger_type)
            else:
                rows = await conn.fetch("SELECT * FROM customers WHERE shop_id = $1 ORDER BY balance DESC, balance_usd DESC, full_name ASC", shop_id)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if ledger_type == 'payable' and user_telegram_id:
                async with db.execute("SELECT * FROM customers WHERE shop_id = ? AND COALESCE(ledger_type, 'receivable') = 'payable' ORDER BY balance DESC, balance_usd DESC, full_name ASC", (shop_id,)) as cursor:
                    rows_own = await cursor.fetchall()
                async with db.execute("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'payable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = ? AND c.shop_id != ? AND s.is_active = 1 AND COALESCE(c.ledger_type, 'receivable') = 'receivable' AND (c.balance > 0 OR c.balance_usd > 0)
                    ORDER BY c.balance DESC, c.balance_usd DESC
                """, (user_telegram_id, shop_id)) as cursor2:
                    rows_ext = await cursor2.fetchall()
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif (ledger_type == 'receivable' or ledger_type is None) and user_telegram_id:
                async with db.execute("SELECT * FROM customers WHERE shop_id = ? AND COALESCE(ledger_type, 'receivable') = 'receivable' ORDER BY balance DESC, balance_usd DESC, full_name ASC", (shop_id,)) as cursor:
                    rows_own = await cursor.fetchall()
                async with db.execute("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Qarz olgan do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'receivable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = ? AND c.shop_id != ? AND s.is_active = 1 AND c.ledger_type = 'payable' AND (c.balance > 0 OR c.balance_usd > 0)
                    ORDER BY c.balance DESC, c.balance_usd DESC
                """, (user_telegram_id, shop_id)) as cursor2:
                    rows_ext = await cursor2.fetchall()
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif ledger_type:
                async with db.execute("SELECT * FROM customers WHERE shop_id = ? AND COALESCE(ledger_type, 'receivable') = ? ORDER BY balance DESC, balance_usd DESC, full_name ASC", (shop_id, ledger_type)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]
            else:
                async with db.execute("SELECT * FROM customers WHERE shop_id = ? ORDER BY balance DESC, balance_usd DESC, full_name ASC", (shop_id,)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]

async def search_customers(shop_id: int, query: str, ledger_type: str = None, user_telegram_id: int = None):
    search = f"%{query.strip()}%"
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if ledger_type == 'payable' and user_telegram_id:
                rows_own = await conn.fetch("""
                    SELECT * FROM customers 
                    WHERE shop_id = $1 AND COALESCE(ledger_type, 'receivable') = 'payable' AND (full_name ILIKE $2 OR phone ILIKE $2)
                    ORDER BY full_name ASC
                """, shop_id, search)
                rows_ext = await conn.fetch("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'payable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = $1 AND c.shop_id != $2 AND s.is_active = 1 AND COALESCE(c.ledger_type, 'receivable') = 'receivable' AND (s.name ILIKE $3 OR s.phone ILIKE $3)
                    ORDER BY c.balance DESC
                """, user_telegram_id, shop_id, search)
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif (ledger_type == 'receivable' or ledger_type is None) and user_telegram_id:
                rows_own = await conn.fetch("""
                    SELECT * FROM customers 
                    WHERE shop_id = $1 AND COALESCE(ledger_type, 'receivable') = 'receivable' AND (full_name ILIKE $2 OR phone ILIKE $2)
                    ORDER BY full_name ASC
                """, shop_id, search)
                rows_ext = await conn.fetch("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Qarz olgan do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'receivable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = $1 AND c.shop_id != $2 AND s.is_active = 1 AND c.ledger_type = 'payable' AND (s.name ILIKE $3 OR s.phone ILIKE $3)
                    ORDER BY c.balance DESC
                """, user_telegram_id, shop_id, search)
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif ledger_type:
                rows = await conn.fetch("""
                    SELECT * FROM customers 
                    WHERE shop_id = $1 AND COALESCE(ledger_type, 'receivable') = $2 AND (full_name ILIKE $3 OR phone ILIKE $3)
                    ORDER BY full_name ASC
                """, shop_id, ledger_type, search)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM customers 
                    WHERE shop_id = $1 AND (full_name ILIKE $2 OR phone ILIKE $2)
                    ORDER BY full_name ASC
                """, shop_id, search)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if ledger_type == 'payable' and user_telegram_id:
                async with db.execute("""
                    SELECT * FROM customers 
                    WHERE shop_id = ? AND COALESCE(ledger_type, 'receivable') = 'payable' AND (full_name LIKE ? OR phone LIKE ?)
                    ORDER BY full_name ASC
                """, (shop_id, search, search)) as cursor:
                    rows_own = await cursor.fetchall()
                async with db.execute("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'payable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = ? AND c.shop_id != ? AND s.is_active = 1 AND COALESCE(c.ledger_type, 'receivable') = 'receivable' AND (s.name LIKE ? OR s.phone LIKE ?)
                    ORDER BY c.balance DESC
                """, (user_telegram_id, shop_id, search, search)) as cursor2:
                    rows_ext = await cursor2.fetchall()
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif (ledger_type == 'receivable' or ledger_type is None) and user_telegram_id:
                async with db.execute("""
                    SELECT * FROM customers 
                    WHERE shop_id = ? AND COALESCE(ledger_type, 'receivable') = 'receivable' AND (full_name LIKE ? OR phone LIKE ?)
                    ORDER BY full_name ASC
                """, (shop_id, search, search)) as cursor:
                    rows_own = await cursor.fetchall()
                async with db.execute("""
                    SELECT c.id, c.shop_id, ('🏪 ' || s.name || ' (Qarz olgan do''kon)') as full_name, s.phone, c.telegram_id, c.balance, c.balance_usd, c.due_date, 'receivable' as ledger_type, 1 as is_external
                    FROM customers c
                    JOIN shops s ON c.shop_id = s.id
                    WHERE c.telegram_id = ? AND c.shop_id != ? AND s.is_active = 1 AND c.ledger_type = 'payable' AND (s.name LIKE ? OR s.phone LIKE ?)
                    ORDER BY c.balance DESC
                """, (user_telegram_id, shop_id, search, search)) as cursor2:
                    rows_ext = await cursor2.fetchall()
                return [dict(r) for r in rows_own] + [dict(r) for r in rows_ext]
            elif ledger_type:
                async with db.execute("""
                    SELECT * FROM customers 
                    WHERE shop_id = ? AND COALESCE(ledger_type, 'receivable') = ? AND (full_name LIKE ? OR phone LIKE ?)
                    ORDER BY full_name ASC
                """, (shop_id, ledger_type, search, search)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]
            else:
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

async def add_transaction(shop_id: int, customer_id: int, amount: float, tx_type: str, description: str = None, currency: str = 'UZS'):
    balance_delta = amount if tx_type == 'debt' else -amount
    currency = currency.upper() if currency else 'UZS'
    
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("""
                    INSERT INTO transactions (shop_id, customer_id, amount, currency, type, description)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """, shop_id, customer_id, amount, currency, tx_type, description)
                
                if currency == 'USD':
                    row = await conn.fetchrow("""
                        UPDATE customers 
                        SET balance_usd = COALESCE(balance_usd, 0) + $1
                        WHERE id = $2
                        RETURNING *
                    """, balance_delta, customer_id)
                else:
                    row = await conn.fetchrow("""
                        UPDATE customers 
                        SET balance = COALESCE(balance, 0) + $1
                        WHERE id = $2
                        RETURNING *
                    """, balance_delta, customer_id)
                return dict(row)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO transactions (shop_id, customer_id, amount, currency, type, description) VALUES (?, ?, ?, ?, ?, ?)",
                (shop_id, customer_id, amount, currency, tx_type, description)
            )
            if currency == 'USD':
                await db.execute("UPDATE customers SET balance_usd = COALESCE(balance_usd, 0) + ? WHERE id = ?", (balance_delta, customer_id))
            else:
                await db.execute("UPDATE customers SET balance = COALESCE(balance, 0) + ? WHERE id = ?", (balance_delta, customer_id))
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

async def get_shop_transactions(shop_id: int, limit: int = 500):
    """Do'kon bo'yicha barcha amallar tarixini mijoz ismi bilan olish"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT t.*, c.full_name as customer_name
                FROM transactions t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.shop_id = $1
                ORDER BY t.created_at DESC, t.id DESC
                LIMIT $2
            """, shop_id, limit)
            return [dict(r) for r in rows]
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT t.*, c.full_name as customer_name
                FROM transactions t
                LEFT JOIN customers c ON t.customer_id = c.id
                WHERE t.shop_id = ?
                ORDER BY t.created_at DESC, t.id DESC
                LIMIT ?
            """, (shop_id, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

async def get_shop_statistics(shop_id: int, period: str = 'all', ledger_type: str = None) -> dict:
    period_filter_pg = {
        'today': "AND t.created_at >= CURRENT_DATE",
        'week': "AND t.created_at >= NOW() - INTERVAL '7 days'",
        'month': "AND t.created_at >= NOW() - INTERVAL '30 days'",
        'all': ""
    }.get(period, "")

    period_filter_sqlite = {
        'today': "AND t.created_at >= date('now')",
        'week': "AND t.created_at >= datetime('now', '-7 days')",
        'month': "AND t.created_at >= datetime('now', '-30 days')",
        'all': ""
    }.get(period, "")

    ledger_clause_pg = "AND COALESCE(c.ledger_type, 'receivable') = $2" if ledger_type else ""
    ledger_clause_sqlite = "AND COALESCE(c.ledger_type, 'receivable') = ?" if ledger_type else ""

    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if ledger_type:
                total_customers = await conn.fetchval(f"SELECT COUNT(*) FROM customers c WHERE c.shop_id = $1 {ledger_clause_pg}", shop_id, ledger_type) or 0
                total_active_debt = await conn.fetchval(f"SELECT SUM(c.balance) FROM customers c WHERE c.shop_id = $1 AND c.balance > 0 {ledger_clause_pg}", shop_id, ledger_type) or 0.0
                total_active_debt_usd = await conn.fetchval(f"SELECT SUM(c.balance_usd) FROM customers c WHERE c.shop_id = $1 AND c.balance_usd > 0 {ledger_clause_pg}", shop_id, ledger_type) or 0.0
                
                period_debt = await conn.fetchval(f"""
                    SELECT SUM(t.amount) FROM transactions t 
                    JOIN customers c ON t.customer_id = c.id 
                    WHERE t.shop_id = $1 AND t.type = 'debt' {ledger_clause_pg} {period_filter_pg}
                """, shop_id, ledger_type) or 0.0
                
                period_payment = await conn.fetchval(f"""
                    SELECT SUM(t.amount) FROM transactions t 
                    JOIN customers c ON t.customer_id = c.id 
                    WHERE t.shop_id = $1 AND t.type = 'payment' {ledger_clause_pg} {period_filter_pg}
                """, shop_id, ledger_type) or 0.0
                
                total_tx_count = await conn.fetchval(f"""
                    SELECT COUNT(*) FROM transactions t 
                    JOIN customers c ON t.customer_id = c.id 
                    WHERE t.shop_id = $1 {ledger_clause_pg} {period_filter_pg}
                """, shop_id, ledger_type) or 0
                
                top_rows = await conn.fetch(f"""
                    SELECT c.full_name, c.balance, c.balance_usd 
                    FROM customers c 
                    WHERE c.shop_id = $1 AND (c.balance > 0 OR c.balance_usd > 0) {ledger_clause_pg}
                    ORDER BY c.balance DESC, c.balance_usd DESC 
                    LIMIT 5
                """, shop_id, ledger_type)
            else:
                total_customers = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1", shop_id) or 0
                total_active_debt = await conn.fetchval("SELECT SUM(balance) FROM customers WHERE shop_id = $1 AND balance > 0", shop_id) or 0.0
                total_active_debt_usd = await conn.fetchval("SELECT SUM(balance_usd) FROM customers WHERE shop_id = $1 AND balance_usd > 0", shop_id) or 0.0
                
                period_debt = await conn.fetchval(f"SELECT SUM(amount) FROM transactions t WHERE t.shop_id = $1 AND t.type = 'debt' {period_filter_pg}", shop_id) or 0.0
                period_payment = await conn.fetchval(f"SELECT SUM(amount) FROM transactions t WHERE t.shop_id = $1 AND t.type = 'payment' {period_filter_pg}", shop_id) or 0.0
                total_tx_count = await conn.fetchval(f"SELECT COUNT(*) FROM transactions t WHERE t.shop_id = $1 {period_filter_pg}", shop_id) or 0
                
                top_rows = await conn.fetch("""
                    SELECT full_name, balance, balance_usd 
                    FROM customers 
                    WHERE shop_id = $1 AND (balance > 0 OR balance_usd > 0) 
                    ORDER BY balance DESC, balance_usd DESC 
                    LIMIT 5
                """, shop_id)
                
            top_debtors = [dict(r) for r in top_rows]
            
            return {
                'total_customers': total_customers,
                'total_debt': total_active_debt,
                'total_debt_usd': total_active_debt_usd,
                'total_active_debt': total_active_debt,
                'period_debt': period_debt,
                'period_payment': period_payment,
                'total_tx_count': total_tx_count,
                'top_debtors': top_debtors,
                'period': period,
                'ledger_type': ledger_type or 'receivable'
            }
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            if ledger_type:
                async with db.execute(f"SELECT COUNT(*) as total_customers, SUM(CASE WHEN balance > 0 THEN balance ELSE 0 END) as total_debt, SUM(CASE WHEN balance_usd > 0 THEN balance_usd ELSE 0 END) as total_debt_usd FROM customers c WHERE c.shop_id = ? {ledger_clause_sqlite}", (shop_id, ledger_type)) as cur:
                    r1 = dict(await cur.fetchone() or {})
                async with db.execute(f"SELECT SUM(CASE WHEN t.type = 'debt' THEN t.amount ELSE 0 END) as period_debt, SUM(CASE WHEN t.type = 'payment' THEN t.amount ELSE 0 END) as period_payment, COUNT(*) as total_tx_count FROM transactions t JOIN customers c ON t.customer_id = c.id WHERE t.shop_id = ? {ledger_clause_sqlite} {period_filter_sqlite}", (shop_id, ledger_type)) as cur:
                    r2 = dict(await cur.fetchone() or {})
                async with db.execute(f"SELECT c.full_name, c.balance, c.balance_usd FROM customers c WHERE c.shop_id = ? AND (c.balance > 0 OR c.balance_usd > 0) {ledger_clause_sqlite} ORDER BY c.balance DESC, c.balance_usd DESC LIMIT 5", (shop_id, ledger_type)) as cur:
                    top_debtors = [dict(r) for r in await cur.fetchall()]
            else:
                async with db.execute("SELECT COUNT(*) as total_customers, SUM(CASE WHEN balance > 0 THEN balance ELSE 0 END) as total_debt, SUM(CASE WHEN balance_usd > 0 THEN balance_usd ELSE 0 END) as total_debt_usd FROM customers WHERE shop_id = ?", (shop_id,)) as cur:
                    r1 = dict(await cur.fetchone() or {})
                async with db.execute(f"SELECT SUM(CASE WHEN t.type = 'debt' THEN t.amount ELSE 0 END) as period_debt, SUM(CASE WHEN t.type = 'payment' THEN t.amount ELSE 0 END) as period_payment, COUNT(*) as total_tx_count FROM transactions t WHERE t.shop_id = ? {period_filter_sqlite}", (shop_id,)) as cur:
                    r2 = dict(await cur.fetchone() or {})
                async with db.execute("SELECT full_name, balance, balance_usd FROM customers WHERE shop_id = ? AND (balance > 0 OR balance_usd > 0) ORDER BY balance DESC, balance_usd DESC LIMIT 5", (shop_id,)) as cur:
                    top_debtors = [dict(r) for r in await cur.fetchall()]

            return {
                'total_customers': r1.get('total_customers') or 0,
                'total_debt': r1.get('total_debt') or 0.0,
                'total_debt_usd': r1.get('total_debt_usd') or 0.0,
                'total_active_debt': r1.get('total_debt') or 0.0,
                'period_debt': r2.get('period_debt') or 0.0,
                'period_payment': r2.get('period_payment') or 0.0,
                'total_tx_count': r2.get('total_tx_count') or 0,
                'top_debtors': top_debtors,
                'period': period,
                'ledger_type': ledger_type or 'receivable'
            }

async def list_shop_customers(shop_id: int, sort_by_debt: bool = True, ledger_type: str = None, user_telegram_id: int = None):
    return await get_customers_by_shop(shop_id, ledger_type=ledger_type, user_telegram_id=user_telegram_id)

async def list_shop_admins(shop_id: int):
    return await get_shop_staff(shop_id)

async def delete_shop_staff(staff_id: int, shop_id: int):
    return await remove_staff_member(shop_id, staff_id)

async def get_detailed_shop_statistics(shop_id: int, period: str = 'all', ledger_type: str = None) -> dict:
    stats = await get_shop_statistics(shop_id, period, ledger_type=ledger_type)
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            if ledger_type:
                indebted = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1 AND (balance > 0 OR balance_usd > 0) AND COALESCE(ledger_type, 'receivable') = $2", shop_id, ledger_type) or 0
                clear = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1 AND (balance <= 0 AND balance_usd <= 0) AND COALESCE(ledger_type, 'receivable') = $2", shop_id, ledger_type) or 0
            else:
                indebted = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1 AND (balance > 0 OR balance_usd > 0)", shop_id) or 0
                clear = await conn.fetchval("SELECT COUNT(*) FROM customers WHERE shop_id = $1 AND (balance <= 0 AND balance_usd <= 0)", shop_id) or 0
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            if ledger_type:
                async with db.execute("SELECT COUNT(*) FROM customers WHERE shop_id = ? AND (balance > 0 OR balance_usd > 0) AND COALESCE(ledger_type, 'receivable') = ?", (shop_id, ledger_type)) as cur:
                    indebted = (await cur.fetchone())[0]
                async with db.execute("SELECT COUNT(*) FROM customers WHERE shop_id = ? AND (balance <= 0 AND balance_usd <= 0) AND COALESCE(ledger_type, 'receivable') = ?", (shop_id, ledger_type)) as cur:
                    clear = (await cur.fetchone())[0]
            else:
                async with db.execute("SELECT COUNT(*) FROM customers WHERE shop_id = ? AND (balance > 0 OR balance_usd > 0)", (shop_id,)) as cur:
                    indebted = (await cur.fetchone())[0]
                async with db.execute("SELECT COUNT(*) FROM customers WHERE shop_id = ? AND (balance <= 0 AND balance_usd <= 0)", (shop_id,)) as cur:
                    clear = (await cur.fetchone())[0]
                
    stats['indebted_customers'] = indebted
    stats['clear_customers'] = clear
    return stats

# ==================== USERS & AUTO-LINK BY PHONE ====================

async def get_user(telegram_id: int):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
            return dict(row) if row else None
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

async def save_user(telegram_id: int, full_name: str = None, username: str = None, phone: str = None):
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (telegram_id, full_name, username, phone)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (telegram_id) DO UPDATE 
                SET full_name = EXCLUDED.full_name,
                    username = EXCLUDED.username,
                    phone = COALESCE(EXCLUDED.phone, users.phone)
            """, telegram_id, full_name, username, phone)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO users (telegram_id, full_name, username, phone)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE 
                SET full_name=excluded.full_name,
                    username=excluded.username,
                    phone=COALESCE(excluded.phone, users.phone)
            """, (telegram_id, full_name, username, phone))
            await db.commit()

async def auto_link_customer_by_phone(telegram_id: int, phone: str, full_name: str = None):
    """Telefon raqam orqali avval kiritilgan barcha qarz hisoblarini yangi foydalanuvchiga avtomatik ulash (bo'shliq va belgilardan xoli)"""
    if not phone:
        return []
    clean_digits = "".join([c for c in str(phone) if c.isdigit()])
    if len(clean_digits) < 7:
        return []
    last9 = clean_digits[-9:]
    linked = []
    
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT c.*, s.name as shop_name, s.admin_id 
                FROM customers c
                JOIN shops s ON c.shop_id = s.id
                WHERE c.telegram_id IS NULL 
                  AND RIGHT(REGEXP_REPLACE(COALESCE(c.phone, ''), '[^0-9]', '', 'g'), 9) = $1
            """, last9)
            for r in rows:
                await conn.execute("""
                    UPDATE customers 
                    SET telegram_id = $1, full_name = COALESCE($2, full_name)
                    WHERE id = $3
                """, telegram_id, full_name, r['id'])
                linked.append(dict(r))
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT c.*, s.name as shop_name, s.admin_id FROM customers c JOIN shops s ON c.shop_id = s.id WHERE c.telegram_id IS NULL") as cur:
                rows = await cur.fetchall()
                for r in rows:
                    c_clean = "".join([c for c in str(r['phone']) if c.isdigit()])
                    if len(c_clean) >= 9 and c_clean[-9:] == last9:
                        await db.execute("UPDATE customers SET telegram_id = ?, full_name = COALESCE(?, full_name) WHERE id = ?", (telegram_id, full_name, r['id']))
                        linked.append(dict(r))
            await db.commit()
    return linked

async def sync_all_unlinked_customers():
    """Bot ishga tushganda yoki fon rejimida mavjud barcha ulanmagan mijozlarni users bazasi bilan sinxronizatsiya qilish"""
    linked_count = 0
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # PostgreSQL da to'g'ridan-to'g'ri regex orqali users va customers ni bog'laymiz
            res = await conn.execute("""
                UPDATE customers c
                SET telegram_id = u.telegram_id
                FROM users u
                WHERE c.telegram_id IS NULL
                  AND c.phone IS NOT NULL
                  AND u.phone IS NOT NULL
                  AND RIGHT(REGEXP_REPLACE(c.phone, '[^0-9]', '', 'g'), 9) = RIGHT(REGEXP_REPLACE(u.phone, '[^0-9]', '', 'g'), 9)
                  AND LENGTH(REGEXP_REPLACE(c.phone, '[^0-9]', '', 'g')) >= 7
            """)
            logger.info(f"Sinxronizatsiya natijasi: {res}")
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT telegram_id, phone FROM users WHERE phone IS NOT NULL") as cur_u:
                users = await cur_u.fetchall()
            async with db.execute("SELECT id, phone FROM customers WHERE telegram_id IS NULL AND phone IS NOT NULL") as cur_c:
                customers = await cur_c.fetchall()
                
            for c in customers:
                c_clean = "".join([d for d in str(c['phone']) if d.isdigit()])
                if len(c_clean) < 7:
                    continue
                c_last9 = c_clean[-9:]
                for u in users:
                    u_clean = "".join([d for d in str(u['phone']) if d.isdigit()])
                    if len(u_clean) >= 9 and u_clean[-9:] == c_last9:
                        await db.execute("UPDATE customers SET telegram_id = ? WHERE id = ?", (u['telegram_id'], c['id']))
                        linked_count += 1
                        break
            await db.commit()
            logger.info(f"Sinxronizatsiya natijasi (SQLite): {linked_count} ta mijoz ulandi.")

async def get_user_ledger_mode(user_id: int) -> str:
    """Foydalanuvchining oxirgi faol rejimini (receivable/payable) olish"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT ledger_mode FROM users WHERE telegram_id = $1", user_id)
            return val if val else 'receivable'
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT ledger_mode FROM users WHERE telegram_id = ?", (user_id,)) as cur:
                row = await cur.fetchone()
                return row[0] if (row and row[0]) else 'receivable'

async def set_user_ledger_mode(user_id: int, mode: str):
    """Foydalanuvchining faol rejimini bazada qat'iy saqlash"""
    if USE_POSTGRES:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET ledger_mode = $1 WHERE telegram_id = $2", mode, user_id)
    else:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE users SET ledger_mode = ? WHERE telegram_id = ?", (mode, user_id))
            await db.commit()

