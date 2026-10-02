"""
E-Commerce PostgreSQL Seed Script
==================================
Tables created and populated:
  • users           – customers with realistic profile data
  • addresses       – shipping/billing addresses per user
  • categories      – product categories
  • products        – items with REAL image URLs (fetched from fakestoreapi.com)
  • product_reviews – star ratings + comments
  • orders          – purchase records per user
  • order_items     – line items inside each order
  • payments        – payment records linked to orders
  • coupons         – discount codes

Usage
-----
1. Install dependencies:
       pip install psycopg2-binary faker requests

2. Set your Postgres connection string as an environment variable:
       export DATABASE_URL="postgresql://user:password@localhost:5432/mydb"

   Or edit DB_URL directly in this file.

3. Run:
       python seed_ecommerce.py
"""

import os
import sys
import random
import requests
import psycopg2
from psycopg2.extras import execute_values
from faker import Faker
from datetime import datetime, timedelta

# ──────────────────────────────────────────────
# CONFIG  –  edit or set env var DATABASE_URL
# ──────────────────────────────────────────────
DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/ecommerce"
)

NUM_USERS       = 40
NUM_ORDERS      = 80   # spread across users
REVIEWS_PER_PRODUCT = 3

fake = Faker()
Faker.seed(42)
random.seed(42)


# ══════════════════════════════════════════════
# STEP 1 – Fetch real product data (with images)
# ══════════════════════════════════════════════

def fetch_real_products() -> list[dict]:
    """Pull all 20 products from FakeStoreAPI – includes real hosted image URLs."""
    print("⬇  Fetching real product data from fakestoreapi.com …")
    try:
        resp = requests.get("https://fakestoreapi.com/products", timeout=15)
        resp.raise_for_status()
        products = resp.json()
        print(f"   ✓ Got {len(products)} products with real image URLs.")
        return products
    except Exception as exc:
        print(f"   ✗ Could not reach fakestoreapi.com: {exc}")
        print("     Falling back to built-in product list with Unsplash image URLs.")
        return FALLBACK_PRODUCTS


# Fallback in case the API is unreachable
FALLBACK_PRODUCTS = [
    {"id": 1,  "title": "Fjallraven - Foldsack No. 1 Backpack",      "price": 109.95, "description": "Your perfect pack for everyday use and walks in the forest.",          "category": "men's clothing",    "image": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=400"},
    {"id": 2,  "title": "Mens Casual Premium Slim Fit T-Shirts",      "price": 22.30,  "description": "Slim-fit, premium quality casual shirt for everyday use.",               "category": "men's clothing",    "image": "https://images.unsplash.com/photo-1512327428889-c8db4cf5562b?w=400"},
    {"id": 3,  "title": "Mens Cotton Jacket",                          "price": 55.99,  "description": "Great outerwear jackets for Spring/Autumn/Winter, suitable for many occasions.", "category": "men's clothing", "image": "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=400"},
    {"id": 4,  "title": "Womens Casual Slim Fit Short Sleeves T-Shir", "price": 12.99,  "description": "The color could be slightly different between on the screen and in practice.", "category": "women's clothing", "image": "https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=400"},
    {"id": 5,  "title": "John Hardy Women's Legends Naga Gold Ring",  "price": 695.00, "description": "Inspired by the mythological water dragon, this gold ring is exquisitely crafted.", "category": "jewelery", "image": "https://images.unsplash.com/photo-1605100804763-247f67b3557e?w=400"},
    {"id": 6,  "title": "Solid Gold Petite Micropave",                 "price": 168.00, "description": "Satisfaction guaranteed. Return or exchange any order within 30 days.", "category": "jewelery",          "image": "https://images.unsplash.com/photo-1573408301185-9519f94e59c6?w=400"},
    {"id": 7,  "title": "White Gold Plated Princess Cut Ring",         "price": 9.99,   "description": "Classic Created Wedding Engagement Solitaire Diamond Promise Ring.",     "category": "jewelery",          "image": "https://images.unsplash.com/photo-1589128777073-263566ae5e4d?w=400"},
    {"id": 8,  "title": "Pierced Owl Rose Gold Plated Stainless Steel","price": 10.99,  "description": "Rose Gold Plated Double Flared Tunnel Plug Earrings.",                  "category": "jewelery",          "image": "https://images.unsplash.com/photo-1561414927-6d86591d0c4f?w=400"},
    {"id": 9,  "title": "WD 2TB Elements Portable External Hard Drive","price": 64.00,  "description": "USB 3.0 and USB 2.0 Compatibility Fast data transfers Improve PC Performance.", "category": "electronics", "image": "https://images.unsplash.com/photo-1531492746076-161ca9bcad58?w=400"},
    {"id": 10, "title": "SanDisk SSD PLUS 1TB Internal SSD",           "price": 109.00, "description": "Easy upgrade for faster boot up, shutdown, and application load times.", "category": "electronics",      "image": "https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=400"},
    {"id": 11, "title": "Silicon Power 256GB SSD",                     "price": 109.00, "description": "3D NAND flash memory providing faster, more reliable performance.",      "category": "electronics",      "image": "https://images.unsplash.com/photo-1601737487795-dab272f52420?w=400"},
    {"id": 12, "title": "WD 4TB Gaming Drive Works with Playstation 4","price": 114.00, "description": "Expand your PS4 gaming experience with 4TB of additional storage.",      "category": "electronics",      "image": "https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=400"},
    {"id": 13, "title": "Acer SB220Q bi 21.5 inches Full HD Monitor",  "price": 599.00, "description": "21.5 inches Full HD (1920 x 1080) widescreen IPS display.",              "category": "electronics",      "image": "https://images.unsplash.com/photo-1527443224154-c4a3942d3acf?w=400"},
    {"id": 14, "title": "Samsung 49-Inch CHG90 144Hz Curved Gaming",   "price": 999.99, "description": "49 INCH SUPER ULTRAWIDE 32:9 Curved Gaming Monitor.",                   "category": "electronics",      "image": "https://images.unsplash.com/photo-1547119957-637f8679db1e?w=400"},
    {"id": 15, "title": "BIYLACLESEN Women's 3-in-1 Snowboard Jacket", "price": 56.99,  "description": "Note:The Jackets is US standard size, no need to worry on sizing.",     "category": "women's clothing", "image": "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=400"},
    {"id": 16, "title": "Lock and Love Women's Removable Hooded Faux Leather Moto Biker Jacket", "price": 29.95, "description": "100% POLYURETHANE(shell) 100% POLYESTER(lining).", "category": "women's clothing", "image": "https://images.unsplash.com/photo-1551488831-00ddcb6c6bd3?w=400"},
    {"id": 17, "title": "Rain Jacket Women Windbreaker Striped",        "price": 39.99,  "description": "Lightweight perfect for trip or casual wear, easy to clean.",           "category": "women's clothing", "image": "https://images.unsplash.com/photo-1544923246-77307dd654cb?w=400"},
    {"id": 18, "title": "MBJ Women's Solid Short Sleeve Boat Neck V",  "price": 9.85,   "description": "95% RAYON 5% SPANDEX, Made in USA or Imported.",                       "category": "women's clothing", "image": "https://images.unsplash.com/photo-1485462537746-965f33f7f6a7?w=400"},
    {"id": 19, "title": "Opna Women's Short Sleeve Moisture Tunic",    "price": 7.95,   "description": "100% Polyester, Machine wash, 100% Sport Tunic Tops.",                  "category": "women's clothing", "image": "https://images.unsplash.com/photo-1562572159-4efc207f5aff?w=400"},
    {"id": 20, "title": "DANVOUY Womens T Shirt Casual Cotton Short",  "price": 12.99,  "description": "95% COTTON, 5% SPANDEX. CasuaL Soft comfortable.",                    "category": "women's clothing", "image": "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=400"},
]


# ══════════════════════════════════════════════
# STEP 2 – DDL
# ══════════════════════════════════════════════

DDL = """
-- Drop in reverse dependency order
DROP TABLE IF EXISTS payments      CASCADE;
DROP TABLE IF EXISTS order_items   CASCADE;
DROP TABLE IF EXISTS orders        CASCADE;
DROP TABLE IF EXISTS product_reviews CASCADE;
DROP TABLE IF EXISTS products      CASCADE;
DROP TABLE IF EXISTS categories    CASCADE;
DROP TABLE IF EXISTS addresses     CASCADE;
DROP TABLE IF EXISTS coupons       CASCADE;
DROP TABLE IF EXISTS users         CASCADE;

-- USERS
CREATE TABLE users (
    id            SERIAL PRIMARY KEY,
    first_name    VARCHAR(80)  NOT NULL,
    last_name     VARCHAR(80)  NOT NULL,
    email         VARCHAR(255) NOT NULL UNIQUE,
    phone         VARCHAR(30),
    password_hash VARCHAR(255) NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- ADDRESSES
CREATE TABLE addresses (
    id          SERIAL PRIMARY KEY,
    user_id     INT          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type        VARCHAR(20)  NOT NULL DEFAULT 'shipping',  -- shipping | billing
    street      VARCHAR(255) NOT NULL,
    city        VARCHAR(100) NOT NULL,
    state       VARCHAR(100),
    postal_code VARCHAR(20)  NOT NULL,
    country     VARCHAR(80)  NOT NULL DEFAULT 'US',
    is_default  BOOLEAN      NOT NULL DEFAULT FALSE
);

-- CATEGORIES
CREATE TABLE categories (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(120) NOT NULL UNIQUE,
    slug        VARCHAR(120) NOT NULL UNIQUE,
    description TEXT
);

-- PRODUCTS
CREATE TABLE products (
    id           SERIAL PRIMARY KEY,
    category_id  INT            REFERENCES categories(id) ON DELETE SET NULL,
    name         VARCHAR(255)   NOT NULL,
    slug         VARCHAR(255)   NOT NULL UNIQUE,
    description  TEXT,
    price        NUMERIC(10,2)  NOT NULL,
    stock_qty    INT            NOT NULL DEFAULT 0,
    sku          VARCHAR(80)    NOT NULL UNIQUE,
    image_url    TEXT,                        -- real hosted URL
    rating       NUMERIC(3,2),
    is_active    BOOLEAN        NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- PRODUCT REVIEWS
CREATE TABLE product_reviews (
    id         SERIAL PRIMARY KEY,
    product_id INT    NOT NULL REFERENCES products(id)  ON DELETE CASCADE,
    user_id    INT    NOT NULL REFERENCES users(id)     ON DELETE CASCADE,
    rating     SMALLINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
    title      VARCHAR(200),
    body       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (product_id, user_id)
);

-- COUPONS
CREATE TABLE coupons (
    id              SERIAL PRIMARY KEY,
    code            VARCHAR(30)   NOT NULL UNIQUE,
    discount_type   VARCHAR(20)   NOT NULL DEFAULT 'percent',  -- percent | fixed
    discount_value  NUMERIC(8,2)  NOT NULL,
    min_order_value NUMERIC(10,2) DEFAULT 0,
    max_uses        INT           DEFAULT 100,
    used_count      INT           NOT NULL DEFAULT 0,
    expires_at      TIMESTAMPTZ,
    is_active       BOOLEAN       NOT NULL DEFAULT TRUE
);

-- ORDERS
CREATE TABLE orders (
    id              SERIAL PRIMARY KEY,
    user_id         INT            NOT NULL REFERENCES users(id),
    coupon_id       INT            REFERENCES coupons(id),
    status          VARCHAR(30)    NOT NULL DEFAULT 'pending',
    subtotal        NUMERIC(10,2)  NOT NULL,
    discount_amount NUMERIC(10,2)  NOT NULL DEFAULT 0,
    tax_amount      NUMERIC(10,2)  NOT NULL DEFAULT 0,
    shipping_amount NUMERIC(10,2)  NOT NULL DEFAULT 0,
    total_amount    NUMERIC(10,2)  NOT NULL,
    shipping_addr   JSONB,
    notes           TEXT,
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

-- ORDER ITEMS
CREATE TABLE order_items (
    id          SERIAL PRIMARY KEY,
    order_id    INT           NOT NULL REFERENCES orders(id)   ON DELETE CASCADE,
    product_id  INT           NOT NULL REFERENCES products(id),
    quantity    INT           NOT NULL DEFAULT 1,
    unit_price  NUMERIC(10,2) NOT NULL,
    total_price NUMERIC(10,2) NOT NULL
);

-- PAYMENTS
CREATE TABLE payments (
    id             SERIAL PRIMARY KEY,
    order_id       INT           NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    method         VARCHAR(30)   NOT NULL,   -- card | paypal | bank_transfer | cod
    status         VARCHAR(30)   NOT NULL DEFAULT 'pending',
    amount         NUMERIC(10,2) NOT NULL,
    transaction_id VARCHAR(100),
    paid_at        TIMESTAMPTZ,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
"""


# ══════════════════════════════════════════════
# STEP 3 – Seed helpers
# ══════════════════════════════════════════════

def slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def make_sku(prefix: str, idx: int) -> str:
    return f"{prefix.upper()[:3]}-{idx:04d}"


ORDER_STATUSES  = ["pending", "processing", "shipped", "delivered", "cancelled", "refunded"]
PAYMENT_METHODS = ["card", "paypal", "bank_transfer", "cod"]
PAYMENT_STATUSES = {"pending": "pending", "processing": "pending",
                    "shipped": "completed", "delivered": "completed",
                    "cancelled": "failed", "refunded": "refunded"}

REVIEW_TITLES = [
    "Great product!", "Highly recommend", "Decent for the price",
    "Not what I expected", "Excellent quality", "Five stars!", "Could be better",
    "Exactly as described", "Fast shipping", "My new favourite item",
]


# ══════════════════════════════════════════════
# STEP 4 – Main seeder
# ══════════════════════════════════════════════

def seed(conn, api_products: list[dict]):
    cur = conn.cursor()

    # ── Schema ──────────────────────────────────
    print("📐 Creating schema …")
    cur.execute(DDL)
    conn.commit()

    # ── Users ───────────────────────────────────
    print(f"👤 Inserting {NUM_USERS} users …")
    user_rows = []
    for _ in range(NUM_USERS):
        user_rows.append((
            fake.first_name(),
            fake.last_name(),
            fake.unique.email(),
            fake.phone_number()[:30],
            fake.sha256(),          # password_hash placeholder
            random.random() > 0.05, # 95% active
            fake.date_time_between(start_date="-2y", end_date="now"),
        ))
    execute_values(cur, """
        INSERT INTO users (first_name, last_name, email, phone, password_hash, is_active, created_at)
        VALUES %s RETURNING id
    """, user_rows)
    user_ids = [r[0] for r in cur.fetchall()]
    conn.commit()

    # ── Addresses ───────────────────────────────
    print("🏠 Inserting addresses …")
    addr_rows = []
    for uid in user_ids:
        for addr_type in random.sample(["shipping", "billing"], k=random.randint(1, 2)):
            addr_rows.append((
                uid, addr_type,
                fake.street_address(),
                fake.city(),
                fake.state(),
                fake.postcode(),
                "US",
                True,
            ))
    execute_values(cur, """
        INSERT INTO addresses (user_id, type, street, city, state, postal_code, country, is_default)
        VALUES %s
    """, addr_rows)
    conn.commit()

    # ── Categories ──────────────────────────────
    print("🗂  Inserting categories …")
    raw_cats = list({p["category"] for p in api_products})
    cat_rows = [(c, slugify(c), f"All items in the {c} category.") for c in raw_cats]
    execute_values(cur, """
        INSERT INTO categories (name, slug, description) VALUES %s
        ON CONFLICT (slug) DO NOTHING
    """, cat_rows)
    conn.commit()

    cur.execute("SELECT id, name FROM categories")
    cat_map = {name: cid for cid, name in cur.fetchall()}

    # ── Products ────────────────────────────────
    print(f"📦 Inserting {len(api_products)} products (with real image URLs) …")
    product_rows = []
    for idx, p in enumerate(api_products, start=1):
        slug = slugify(p["title"])
        product_rows.append((
            cat_map.get(p["category"]),
            p["title"],
            slug,
            p.get("description", ""),
            round(p["price"], 2),
            random.randint(0, 200),
            make_sku(p["category"], idx),
            p["image"],                          # ← REAL image URL from the API
            round(p.get("rating", {}).get("rate", random.uniform(3.0, 5.0)) if isinstance(p.get("rating"), dict) else random.uniform(3.5, 5.0), 2),
            True,
        ))
    execute_values(cur, """
        INSERT INTO products (category_id, name, slug, description, price, stock_qty,
                              sku, image_url, rating, is_active)
        VALUES %s RETURNING id
    """, product_rows)
    product_ids = [r[0] for r in cur.fetchall()]
    conn.commit()

    # ── Product Reviews ─────────────────────────
    print("⭐ Inserting product reviews …")
    used_pairs: set = set()
    review_rows = []
    for pid in product_ids:
        reviewers = random.sample(user_ids, min(REVIEWS_PER_PRODUCT, len(user_ids)))
        for uid in reviewers:
            if (pid, uid) in used_pairs:
                continue
            used_pairs.add((pid, uid))
            review_rows.append((
                pid, uid,
                random.randint(3, 5),
                random.choice(REVIEW_TITLES),
                fake.paragraph(nb_sentences=2),
                fake.date_time_between(start_date="-1y", end_date="now"),
            ))
    execute_values(cur, """
        INSERT INTO product_reviews (product_id, user_id, rating, title, body, created_at)
        VALUES %s
    """, review_rows)
    conn.commit()

    # ── Coupons ─────────────────────────────────
    print("🏷  Inserting coupons …")
    coupon_codes = ["WELCOME10", "SAVE20", "FREESHIP", "FLASH15", "VIP30"]
    coupon_rows  = [
        ("WELCOME10", "percent",  10.00, 0,      500, 0, datetime.now() + timedelta(days=90),  True),
        ("SAVE20",    "percent",  20.00, 50.00,  300, 0, datetime.now() + timedelta(days=60),  True),
        ("FREESHIP",  "fixed",     5.99,  0,     200, 0, datetime.now() + timedelta(days=30),  True),
        ("FLASH15",   "percent",  15.00, 30.00,  100, 0, datetime.now() + timedelta(days=7),   True),
        ("VIP30",     "percent",  30.00, 100.00,  50, 0, datetime.now() + timedelta(days=180), True),
    ]
    execute_values(cur, """
        INSERT INTO coupons (code, discount_type, discount_value, min_order_value,
                             max_uses, used_count, expires_at, is_active)
        VALUES %s RETURNING id
    """, coupon_rows)
    coupon_ids = [r[0] for r in cur.fetchall()]
    conn.commit()

    # ── Orders + Order Items + Payments ─────────
    print(f"🛒 Inserting {NUM_ORDERS} orders with line items and payments …")
    for _ in range(NUM_ORDERS):
        uid        = random.choice(user_ids)
        status     = random.choices(
            ORDER_STATUSES,
            weights=[5, 10, 20, 50, 10, 5],
        )[0]
        coupon_id  = random.choice(coupon_ids + [None, None, None])  # 25 % chance

        # Pick 1-4 products
        items = []
        for pid in random.sample(product_ids, k=random.randint(1, 4)):
            cur.execute("SELECT price FROM products WHERE id = %s", (pid,))
            price    = float(cur.fetchone()[0])
            qty      = random.randint(1, 3)
            items.append((pid, qty, price, round(price * qty, 2)))

        subtotal        = round(sum(i[3] for i in items), 2)
        discount_amount = round(subtotal * 0.10, 2) if coupon_id else 0.00
        tax_amount      = round(subtotal * 0.08, 2)
        shipping_amount = 0.00 if subtotal >= 50 else 5.99
        total_amount    = round(subtotal - discount_amount + tax_amount + shipping_amount, 2)

        addr = {
            "street":      fake.street_address(),
            "city":        fake.city(),
            "state":       fake.state(),
            "postal_code": fake.postcode(),
            "country":     "US",
        }

        order_date = fake.date_time_between(start_date="-1y", end_date="now")

        import json
        cur.execute("""
            INSERT INTO orders (user_id, coupon_id, status, subtotal, discount_amount,
                                tax_amount, shipping_amount, total_amount,
                                shipping_addr, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
        """, (uid, coupon_id, status, subtotal, discount_amount,
              tax_amount, shipping_amount, total_amount,
              json.dumps(addr), order_date))
        order_id = cur.fetchone()[0]

        # Order items
        execute_values(cur, """
            INSERT INTO order_items (order_id, product_id, quantity, unit_price, total_price)
            VALUES %s
        """, [(order_id, pid, qty, up, tp) for pid, qty, up, tp in items])

        # Payment
        method    = random.choice(PAYMENT_METHODS)
        p_status  = PAYMENT_STATUSES[status]
        paid_at   = (order_date + timedelta(minutes=random.randint(1, 30))
                     if p_status == "completed" else None)
        cur.execute("""
            INSERT INTO payments (order_id, method, status, amount, transaction_id, paid_at)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (order_id, method, p_status, total_amount,
              fake.uuid4() if p_status == "completed" else None, paid_at))

    conn.commit()
    cur.close()


# ══════════════════════════════════════════════
# STEP 5 – Summary query
# ══════════════════════════════════════════════

def print_summary(conn):
    cur = conn.cursor()
    tables = ["users", "addresses", "categories", "products",
              "product_reviews", "coupons", "orders", "order_items", "payments"]
    print("\n── Row counts ───────────────────────────")
    for t in tables:
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        print(f"  {t:<20} {cur.fetchone()[0]:>5} rows")

    print("\n── Sample products with image URLs ──────")
    cur.execute("SELECT name, price, image_url FROM products LIMIT 5")
    for name, price, url in cur.fetchall():
        print(f"  ${price:>7.2f}  {name[:45]:<45}  {url[:60]}")
    cur.close()


# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════

def main():
    api_products = fetch_real_products()

    print(f"\n🔌 Connecting to Postgres …  ({DB_URL[:40]}…)")
    try:
        conn = psycopg2.connect(DB_URL)
    except Exception as exc:
        print(f"   ✗ Connection failed: {exc}")
        sys.exit(1)

    try:
        seed(conn, api_products)
        print_summary(conn)
        print("\n✅  Seeding complete!")
    except Exception as exc:
        conn.rollback()
        print(f"\n✗  Error during seeding: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()