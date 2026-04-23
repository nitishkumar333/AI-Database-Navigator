"""
seed_shop.py — Populates a local PostgreSQL database with dummy shop data.

Tables created:
  - users
  - products
  - orders
  - order_items

Usage:
  pip install psycopg2-binary faker
  python seed_shop.py

Environment variables (optional, defaults shown):
  DB_HOST      localhost
  DB_PORT      5432
  DB_NAME      shop
  DB_USER      postgres
  DB_PASSWORD  postgres
"""

import os
import random
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

# ─── Config ──────────────────────────────────────────────────────────────────

DB = dict(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", 5432)),
    dbname=os.getenv("DB_NAME", "shop"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD", "password"),
)

NUM_USERS    = 20
NUM_PRODUCTS = 30
NUM_ORDERS   = 50

fake = Faker()
random.seed(42)
Faker.seed(42)

# ─── Product catalogue ───────────────────────────────────────────────────────

CATEGORIES = {
    "Electronics": [
        ("Wireless Headphones",   49.99, 199.99),
        ("Bluetooth Speaker",     29.99, 129.99),
        ("USB-C Hub",             15.99,  59.99),
        ("Mechanical Keyboard",   59.99, 249.99),
        ("LED Desk Lamp",         19.99,  79.99),
        ("Webcam 1080p",          39.99,  99.99),
    ],
    "Clothing": [
        ("Classic T-Shirt",        9.99,  39.99),
        ("Slim-Fit Jeans",        29.99,  89.99),
        ("Hooded Sweatshirt",     24.99,  79.99),
        ("Running Shorts",        14.99,  49.99),
        ("Wool Socks (3-pack)",    7.99,  24.99),
    ],
    "Home & Kitchen": [
        ("Ceramic Coffee Mug",     8.99,  29.99),
        ("Cutting Board",         12.99,  44.99),
        ("Chef's Knife",          24.99,  99.99),
        ("French Press",          19.99,  59.99),
        ("Bamboo Utensil Set",    14.99,  39.99),
    ],
    "Books": [
        ("Python Crash Course",       19.99, 39.99),
        ("The Pragmatic Programmer",  24.99, 49.99),
        ("Clean Code",               29.99, 54.99),
        ("Atomic Habits",            14.99, 29.99),
    ],
    "Sports": [
        ("Yoga Mat",              19.99,  69.99),
        ("Resistance Bands Set",  12.99,  39.99),
        ("Water Bottle (1L)",      9.99,  34.99),
        ("Jump Rope",              6.99,  19.99),
        ("Foam Roller",           14.99,  44.99),
    ],
}

# Flat list of (category, name, min_price, max_price)
PRODUCT_POOL = [
    (cat, name, lo, hi)
    for cat, items in CATEGORIES.items()
    for name, lo, hi in items
]

# ─── Schema ──────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(50)  UNIQUE NOT NULL,
    email         VARCHAR(120) UNIQUE NOT NULL,
    full_name     VARCHAR(120),
    phone         VARCHAR(30),
    address       TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(200) NOT NULL,
    category      VARCHAR(80),
    description   TEXT,
    price         NUMERIC(10,2) NOT NULL,
    stock         INTEGER DEFAULT 0,
    image_url     TEXT,
    created_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id            SERIAL PRIMARY KEY,
    user_id       INTEGER REFERENCES users(id) ON DELETE CASCADE,
    status        VARCHAR(30) DEFAULT 'pending',
    total_amount  NUMERIC(10,2),
    shipping_addr TEXT,
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER REFERENCES orders(id) ON DELETE CASCADE,
    product_id  INTEGER REFERENCES products(id),
    quantity    INTEGER NOT NULL DEFAULT 1,
    unit_price  NUMERIC(10,2) NOT NULL
);
"""

# ─── Seed functions ──────────────────────────────────────────────────────────

def seed_users(cur, n: int) -> list[int]:
    print(f"  Inserting {n} users …")
    ids = []
    for _ in range(n):
        cur.execute(
            """
            INSERT INTO users (username, email, full_name, phone, address)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            RETURNING id
            """,
            (
                fake.unique.user_name(),
                fake.unique.email(),
                fake.name(),
                fake.phone_number()[:20],
                fake.address(),
            ),
        )
        row = cur.fetchone()
        if row:
            ids.append(row[0])
    return ids


def seed_products(cur, n: int) -> list[int]:
    print(f"  Inserting {n} products …")
    ids = []
    pool = random.sample(PRODUCT_POOL, min(n, len(PRODUCT_POOL)))
    # If n > pool size, fill with extras
    while len(pool) < n:
        pool.append(random.choice(PRODUCT_POOL))

    for cat, name, lo, hi in pool:
        price     = round(random.uniform(lo, hi), 2)
        stock     = random.randint(0, 200)
        slug      = name.lower().replace(" ", "-").replace("(", "").replace(")", "")
        image_url = f"https://example.com/products/{slug}.jpg"

        cur.execute(
            """
            INSERT INTO products
              (name, category, description, price, stock, image_url)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                name,
                cat,
                fake.sentence(nb_words=12),
                price,
                stock,
                image_url,
            ),
        )
        ids.append(cur.fetchone()[0])
    return ids


def seed_orders(cur, user_ids: list[int], product_ids: list[int], n: int):
    print(f"  Inserting {n} orders with line items …")
    statuses = ["pending", "confirmed", "shipped", "delivered", "cancelled"]

    for _ in range(n):
        uid        = random.choice(user_ids)
        status     = random.choices(statuses, weights=[10, 20, 20, 40, 10])[0]
        created_at = fake.date_time_between(start_date="-1y", end_date="now")
        updated_at = created_at + timedelta(days=random.randint(0, 10))

        cur.execute(
            """
            INSERT INTO orders (user_id, status, shipping_addr, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (uid, status, fake.address(), created_at, updated_at),
        )
        order_id = cur.fetchone()[0]

        # 1–5 distinct products per order
        items = random.sample(product_ids, k=random.randint(1, min(5, len(product_ids))))
        total = 0.0
        for pid in items:
            cur.execute("SELECT price FROM products WHERE id = %s", (pid,))
            unit_price = float(cur.fetchone()[0])
            qty        = random.randint(1, 4)
            total     += unit_price * qty
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)",
                (order_id, pid, qty, unit_price),
            )

        cur.execute(
            "UPDATE orders SET total_amount = %s WHERE id = %s",
            (round(total, 2), order_id),
        )


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL …")
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur  = conn.cursor()

    try:
        print("Creating schema …")
        cur.execute(DDL)

        user_ids    = seed_users(cur, NUM_USERS)
        product_ids = seed_products(cur, NUM_PRODUCTS)
        seed_orders(cur, user_ids, product_ids, NUM_ORDERS)

        conn.commit()
        print("\n✅ Done!")
        print(f"   {len(user_ids)} users")
        print(f"   {len(product_ids)} products")
        print(f"   {NUM_ORDERS} orders with line items")

    except Exception as exc:
        conn.rollback()
        print(f"\n❌ Error — rolled back: {exc}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()