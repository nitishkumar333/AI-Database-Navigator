"""
Large E-Commerce Demo Database (shop_large)
===========================================
A copy of the `shop` database (its 9 tables and rows, unchanged) plus 93 more
tables of a mid-sized online + in-store retailer, for testing the agent on a
schema too big for one prompt (102 tables, ~225k rows):

  reference      currencies, countries, regions, cities, exchange_rates, tax_rates
  organisation   departments, stores, employees, pos_terminals, pos_transactions, ...
  catalog        brands, product_details, product_variants, product_images, tags, ...
  inventory      warehouses, inventory_levels, stock_movements, suppliers, purchase_orders, ...
  orders         carts, wishlists, order_status_history, invoices, refunds, returns, ...
  shipping       carriers, shipping_methods, shipping_zones, shipments, shipment_events, ...
  finance        saved_payment_methods, payment_attempts, gl_accounts, journal_entries, ...
  loyalty        loyalty_tiers, loyalty_accounts, loyalty_transactions, gift_cards
  support        customer_segments, user_sessions, support_tickets, ticket_messages, ...
  marketing      campaigns, email_sends, email_events, affiliates, promotions, ...
  analytics      page_views, product_views, search_queries, ab_tests, ...
  misc           review_votes, review_images, notifications, audit_log

The new tables reference the copied ones (users, products, orders, ...). Rows
are generated inside Postgres with a fixed random seed, so every run builds
the same database. Re-running drops and rebuilds `shop_large`.

Usage (from backend/, with `shop` already seeded):
    python seed_shop_large.py
Env: SHOP_DB_URL (source, default postgresql://postgres:password@localhost:5432/shop)
     SHOP_LARGE_DB (target database name, default shop_large)
"""

import io
import os
import sys
import time
from urllib.parse import urlparse, urlunparse

import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from seed_shop import DDL as SHOP_DDL

SOURCE_URL = os.getenv("SHOP_DB_URL", "postgresql://postgres:password@localhost:5432/shop")
TARGET_DB = os.getenv("SHOP_LARGE_DB", "shop_large")

# Copied from `shop` in this order (parents first).
SHOP_TABLES = ["users", "addresses", "categories", "products", "product_reviews",
               "coupons", "orders", "order_items", "payments"]


def db_url(url: str, database: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/" + database))


# ══════════════════════════════════════════════
# Helpers (session-local, gone when the connection closes)
# ══════════════════════════════════════════════

HELPERS = r"""
SELECT setseed(0.42);
CREATE FUNCTION pg_temp.pick(a text[]) RETURNS text LANGUAGE sql VOLATILE AS
  $$ SELECT a[1 + floor(random() * array_length(a, 1))::int] $$;
CREATE FUNCTION pg_temp.rint(lo int, hi int) RETURNS int LANGUAGE sql VOLATILE AS
  $$ SELECT lo + floor(random() * (hi - lo + 1))::int $$;
CREATE FUNCTION pg_temp.rnum(lo numeric, hi numeric) RETURNS numeric LANGUAGE sql VOLATILE AS
  $$ SELECT round(lo + (random() * (hi - lo))::numeric, 2) $$;
-- a random moment in the `days` days before the data snapshot (2026-10-10)
CREATE FUNCTION pg_temp.rts(days int) RETURNS timestamptz LANGUAGE sql VOLATILE AS
  $$ SELECT timestamptz '2026-10-10 12:00+00' - random() * make_interval(days => days) $$;
CREATE FUNCTION pg_temp.person() RETURNS text LANGUAGE sql VOLATILE AS $$
  SELECT pg_temp.pick(ARRAY['James','Mary','Robert','Patricia','John','Jennifer','Michael','Linda',
    'David','Elizabeth','William','Barbara','Richard','Susan','Joseph','Jessica','Thomas','Sarah',
    'Priya','Arjun','Mei','Hiroshi','Fatima','Omar','Lucia','Mateo','Ingrid','Lars','Chloe','Noah'])
  || ' ' ||
  pg_temp.pick(ARRAY['Smith','Johnson','Williams','Brown','Jones','Garcia','Miller','Davis',
    'Rodriguez','Martinez','Patel','Sharma','Kim','Nguyen','Chen','Tanaka','Muller','Rossi',
    'Silva','Okafor','Hansen','Dubois','Kowalski','Novak','Ali']) $$;
CREATE TEMP TABLE k AS SELECT
  (SELECT max(id) FROM users) AS users,
  (SELECT max(id) FROM products) AS products,
  (SELECT max(id) FROM orders) AS orders,
  (SELECT max(id) FROM product_reviews) AS reviews;
"""


# ══════════════════════════════════════════════
# Reference data
# ══════════════════════════════════════════════

REFERENCE = r"""
CREATE TABLE currencies (
    code        CHAR(3)     PRIMARY KEY,
    name        VARCHAR(60) NOT NULL,
    symbol      VARCHAR(5)  NOT NULL,
    minor_units SMALLINT    NOT NULL DEFAULT 2
);
INSERT INTO currencies VALUES
  ('USD','US Dollar','$',2), ('EUR','Euro','€',2), ('GBP','Pound Sterling','£',2),
  ('INR','Indian Rupee','₹',2), ('JPY','Japanese Yen','¥',0), ('CAD','Canadian Dollar','C$',2),
  ('AUD','Australian Dollar','A$',2), ('BRL','Brazilian Real','R$',2);

CREATE TABLE countries (
    id            SERIAL PRIMARY KEY,
    iso2          CHAR(2)     NOT NULL UNIQUE,
    name          VARCHAR(80) NOT NULL,
    currency_code CHAR(3)     REFERENCES currencies(code),
    continent     VARCHAR(20) NOT NULL
);
INSERT INTO countries (iso2, name, currency_code, continent) VALUES
  ('US','United States','USD','North America'), ('CA','Canada','CAD','North America'),
  ('BR','Brazil','BRL','South America'), ('GB','United Kingdom','GBP','Europe'),
  ('DE','Germany','EUR','Europe'), ('FR','France','EUR','Europe'), ('IT','Italy','EUR','Europe'),
  ('ES','Spain','EUR','Europe'), ('NL','Netherlands','EUR','Europe'), ('IE','Ireland','EUR','Europe'),
  ('AT','Austria','EUR','Europe'), ('PT','Portugal','EUR','Europe'), ('IN','India','INR','Asia'),
  ('JP','Japan','JPY','Asia'), ('AU','Australia','AUD','Oceania');

CREATE TABLE regions (
    id         SERIAL PRIMARY KEY,
    country_id INT         NOT NULL REFERENCES countries(id),
    code       VARCHAR(10) NOT NULL,
    name       VARCHAR(80) NOT NULL,
    UNIQUE (country_id, code)
);
INSERT INTO regions (country_id, code, name)
SELECT c.id, r.code, r.name FROM (VALUES
  ('US','CA','California'), ('US','NY','New York'), ('US','TX','Texas'), ('US','FL','Florida'),
  ('US','WA','Washington'), ('US','IL','Illinois'), ('US','MA','Massachusetts'), ('US','GA','Georgia'),
  ('CA','ON','Ontario'), ('CA','BC','British Columbia'), ('CA','QC','Quebec'),
  ('IN','MH','Maharashtra'), ('IN','KA','Karnataka'), ('IN','DL','Delhi'), ('IN','TN','Tamil Nadu'),
  ('DE','BY','Bavaria'), ('DE','BE','Berlin'), ('DE','HH','Hamburg'),
  ('GB','ENG','England'), ('GB','SCT','Scotland'), ('AU','NSW','New South Wales'),
  ('AU','VIC','Victoria'), ('FR','IDF','Île-de-France'), ('JP','13','Tokyo'), ('JP','27','Osaka'),
  ('BR','SP','São Paulo')
) AS r(iso2, code, name) JOIN countries c ON c.iso2 = r.iso2;

CREATE TABLE cities (
    id         SERIAL PRIMARY KEY,
    region_id  INT          NOT NULL REFERENCES regions(id),
    name       VARCHAR(100) NOT NULL,
    population INT,
    timezone   VARCHAR(40)  NOT NULL
);
INSERT INTO cities (region_id, name, population, timezone)
SELECT r.id, c.name, c.pop, c.tz FROM (VALUES
  ('CA','Los Angeles',3820000,'America/Los_Angeles'), ('CA','San Francisco',808000,'America/Los_Angeles'),
  ('CA','San Diego',1380000,'America/Los_Angeles'), ('NY','New York City',8260000,'America/New_York'),
  ('NY','Buffalo',276000,'America/New_York'), ('TX','Houston',2300000,'America/Chicago'),
  ('TX','Austin',974000,'America/Chicago'), ('TX','Dallas',1300000,'America/Chicago'),
  ('FL','Miami',449000,'America/New_York'), ('FL','Orlando',316000,'America/New_York'),
  ('WA','Seattle',755000,'America/Los_Angeles'), ('IL','Chicago',2660000,'America/Chicago'),
  ('MA','Boston',654000,'America/New_York'), ('GA','Atlanta',510000,'America/New_York'),
  ('ON','Toronto',2790000,'America/Toronto'), ('ON','Ottawa',1020000,'America/Toronto'),
  ('BC','Vancouver',662000,'America/Vancouver'), ('QC','Montreal',1760000,'America/Toronto'),
  ('MH','Mumbai',12440000,'Asia/Kolkata'), ('MH','Pune',3120000,'Asia/Kolkata'),
  ('KA','Bengaluru',8440000,'Asia/Kolkata'), ('DL','New Delhi',257000,'Asia/Kolkata'),
  ('TN','Chennai',4650000,'Asia/Kolkata'), ('BY','Munich',1510000,'Europe/Berlin'),
  ('BE','Berlin',3760000,'Europe/Berlin'), ('HH','Hamburg',1850000,'Europe/Berlin'),
  ('ENG','London',8800000,'Europe/London'), ('ENG','Manchester',552000,'Europe/London'),
  ('SCT','Edinburgh',527000,'Europe/London'), ('NSW','Sydney',5300000,'Australia/Sydney'),
  ('VIC','Melbourne',5100000,'Australia/Melbourne'), ('IDF','Paris',2100000,'Europe/Paris'),
  ('13','Tokyo',13960000,'Asia/Tokyo'), ('27','Osaka',2750000,'Asia/Tokyo'),
  ('SP','São Paulo',12330000,'America/Sao_Paulo')
) AS c(region_code, name, pop, tz) JOIN regions r ON r.code = c.region_code;

CREATE TABLE exchange_rates (
    id             SERIAL PRIMARY KEY,
    base_currency  CHAR(3)       NOT NULL REFERENCES currencies(code),
    quote_currency CHAR(3)       NOT NULL REFERENCES currencies(code),
    rate_date      DATE          NOT NULL,
    rate           NUMERIC(14,6) NOT NULL,
    UNIQUE (base_currency, quote_currency, rate_date)
);
INSERT INTO exchange_rates (base_currency, quote_currency, rate_date, rate)
SELECT 'USD', q.code, d::date, round((q.mid * (0.97 + random() * 0.06))::numeric, 6)
FROM (VALUES ('EUR',0.92), ('GBP',0.79), ('INR',83.2), ('JPY',149.5), ('CAD',1.36),
             ('AUD',1.52), ('BRL',5.02)) AS q(code, mid)
CROSS JOIN generate_series(date '2025-10-11', date '2026-10-10', interval '1 day') AS d;

CREATE TABLE tax_rates (
    id          SERIAL PRIMARY KEY,
    country_id  INT          NOT NULL REFERENCES countries(id),
    region_id   INT          REFERENCES regions(id),
    category_id INT          REFERENCES categories(id),
    name        VARCHAR(60)  NOT NULL,
    rate_pct    NUMERIC(5,2) NOT NULL,
    valid_from  DATE         NOT NULL,
    valid_to    DATE
);
INSERT INTO tax_rates (country_id, region_id, name, rate_pct, valid_from)
SELECT r.country_id, r.id, r.code || ' sales tax', pg_temp.rnum(4, 9.5), date '2024-01-01'
FROM regions r JOIN countries c ON c.id = r.country_id WHERE c.iso2 = 'US';
INSERT INTO tax_rates (country_id, name, rate_pct, valid_from)
SELECT c.id, 'Standard VAT', v.rate, date '2024-01-01' FROM (VALUES
  ('GB',20), ('DE',19), ('FR',20), ('IT',22), ('ES',21), ('NL',21), ('IE',23), ('AT',20),
  ('PT',23), ('IN',18), ('JP',10), ('AU',10), ('CA',5), ('BR',17)) AS v(iso2, rate)
JOIN countries c ON c.iso2 = v.iso2;
INSERT INTO tax_rates (country_id, category_id, name, rate_pct, valid_from)
SELECT c.id, cat.id, 'Reduced VAT (clothing)', 5, date '2025-01-01'
FROM countries c, categories cat WHERE c.iso2 IN ('GB','IN') AND cat.name ILIKE '%clothing%';
"""


# ══════════════════════════════════════════════
# Organisation: departments, stores, employees
# ══════════════════════════════════════════════

ORGANISATION = r"""
CREATE TABLE departments (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,
    cost_center VARCHAR(10) NOT NULL
);
INSERT INTO departments (name, cost_center) VALUES
  ('Executive','CC100'), ('Customer Support','CC200'), ('Warehouse Operations','CC300'),
  ('Marketing','CC400'), ('Finance','CC500'), ('Engineering','CC600'),
  ('Retail Stores','CC700'), ('Procurement','CC800');

CREATE TABLE stores (
    id        SERIAL PRIMARY KEY,
    name      VARCHAR(120) NOT NULL,
    city_id   INT          NOT NULL REFERENCES cities(id),
    opened_on DATE         NOT NULL,
    sq_ft     INT,
    is_open   BOOLEAN      NOT NULL DEFAULT TRUE
);
INSERT INTO stores (name, city_id, opened_on, sq_ft, is_open)
SELECT s.name, c.id, s.opened::date, s.sqft, s.open FROM (VALUES
  ('Flagship SoHo','New York City','2019-04-12',12000,true),
  ('Union Square','San Francisco','2020-09-01',8500,true),
  ('Magnificent Mile','Chicago','2021-03-20',9000,true),
  ('Oxford Street','London','2022-06-15',7000,true),
  ('Indiranagar','Bengaluru','2023-11-02',5000,false)
) AS s(name, city, opened, sqft, open) JOIN cities c ON c.name = s.city;

CREATE TABLE employees (
    id            SERIAL PRIMARY KEY,
    department_id INT           NOT NULL REFERENCES departments(id),
    manager_id    INT           REFERENCES employees(id),
    store_id      INT           REFERENCES stores(id),
    full_name     VARCHAR(120)  NOT NULL,
    email         VARCHAR(255)  NOT NULL UNIQUE,
    job_title     VARCHAR(80)   NOT NULL,
    hire_date     DATE          NOT NULL,
    annual_salary NUMERIC(10,2) NOT NULL,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE
);
INSERT INTO employees (department_id, full_name, email, job_title, hire_date, annual_salary)
SELECT d, n, 'emp' || g || '@shopcorp.example',
       CASE d WHEN 1 THEN 'Director' WHEN 2 THEN 'Support Specialist' WHEN 3 THEN 'Warehouse Associate'
              WHEN 4 THEN 'Marketing Manager' WHEN 5 THEN 'Accountant' WHEN 6 THEN 'Software Engineer'
              WHEN 7 THEN 'Sales Associate' ELSE 'Buyer' END,
       (date '2026-10-10' - pg_temp.rint(30, 2400)),
       CASE d WHEN 1 THEN pg_temp.rnum(180000, 260000) WHEN 6 THEN pg_temp.rnum(110000, 170000)
              ELSE pg_temp.rnum(38000, 95000) END
FROM (SELECT g, CASE WHEN g <= 3 THEN 1 ELSE pg_temp.rint(2, 8) END AS d, pg_temp.person() AS n
      FROM generate_series(1, 60) g) x;
UPDATE employees SET manager_id = CASE WHEN id <= 3 THEN NULL ELSE 1 + (id % 3) END;
UPDATE employees SET store_id = 1 + (id % 5) WHERE department_id = 7;
UPDATE employees SET is_active = false WHERE id % 11 = 0;
"""


# ══════════════════════════════════════════════
# Catalog
# ══════════════════════════════════════════════

CATALOG = r"""
CREATE TABLE brands (
    id           SERIAL PRIMARY KEY,
    name         VARCHAR(80) NOT NULL UNIQUE,
    country_id   INT         REFERENCES countries(id),
    website      TEXT,
    founded_year SMALLINT,
    is_featured  BOOLEAN     NOT NULL DEFAULT FALSE
);
INSERT INTO brands (name, country_id, website, founded_year, is_featured)
SELECT b, pg_temp.rint(1, 15), 'https://www.' || lower(regexp_replace(b, '[^A-Za-z]', '', 'g')) || '.example',
       pg_temp.rint(1950, 2020), random() < 0.25
FROM unnest(ARRAY['Northpeak','Lumen & Co','Brightwave','Ironleaf','Kestrel Outdoor','Velvet Row',
  'Aurora Gems','Corelink','Bytehaus','Silverline','Harbor Thread','Maple & Moss','Solstice',
  'Urban Fable','Quantix','Pixelforge','Terra Nova','Bluefin','Crescent Atelier','Granite Gear',
  'Halcyon','Nimbus Tech','Oakridge','Pinnacle','Zephyr']) AS b;

-- one row per product (1:1 extension of products)
CREATE TABLE product_details (
    product_id           INT PRIMARY KEY REFERENCES products(id) ON DELETE CASCADE,
    brand_id             INT          REFERENCES brands(id),
    weight_grams         INT,
    dimensions_cm        VARCHAR(30),
    warranty_months      SMALLINT     NOT NULL DEFAULT 0,
    country_of_origin_id INT          REFERENCES countries(id),
    material             VARCHAR(60),
    care_instructions    TEXT
);
INSERT INTO product_details
SELECT p.id, pg_temp.rint(1, 25), pg_temp.rint(80, 9000),
       pg_temp.rint(5, 60) || 'x' || pg_temp.rint(5, 40) || 'x' || pg_temp.rint(1, 30),
       pg_temp.pick(ARRAY['0','6','12','24'])::smallint, pg_temp.rint(1, 15),
       pg_temp.pick(ARRAY['cotton','polyester','leather','stainless steel','gold','silver','plastic','aluminium']),
       pg_temp.pick(ARRAY['Machine wash cold','Hand wash only','Wipe with a dry cloth', NULL])
FROM products p;

CREATE TABLE product_variants (
    id           SERIAL PRIMARY KEY,
    product_id   INT           NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    sku          VARCHAR(40)   NOT NULL UNIQUE,
    color        VARCHAR(30),
    size         VARCHAR(20),
    price_delta  NUMERIC(10,2) NOT NULL DEFAULT 0,
    barcode      VARCHAR(14),
    is_default   BOOLEAN       NOT NULL DEFAULT FALSE,
    is_available BOOLEAN       NOT NULL DEFAULT TRUE
);
INSERT INTO product_variants (product_id, sku, color, size, price_delta, barcode, is_default, is_available)
SELECT p.id, p.sku || '-V' || v, pg_temp.pick(ARRAY['Black','White','Navy','Red','Silver','Gold','Olive','Grey']),
       pg_temp.pick(ARRAY['XS','S','M','L','XL','One Size']),
       CASE WHEN v = 1 THEN 0 ELSE pg_temp.rnum(-5, 15) END,
       lpad((pg_temp.rint(100000, 999999)::bigint * 1000000 + pg_temp.rint(0, 999999))::text, 13, '0'),
       v = 1, random() < 0.9
FROM products p CROSS JOIN generate_series(1, 4) v ORDER BY p.id, v;

CREATE TABLE product_images (
    id         SERIAL PRIMARY KEY,
    product_id INT      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    variant_id INT      REFERENCES product_variants(id),
    url        TEXT     NOT NULL,
    alt_text   VARCHAR(200),
    sort_order SMALLINT NOT NULL DEFAULT 0,
    is_primary BOOLEAN  NOT NULL DEFAULT FALSE
);
INSERT INTO product_images (product_id, variant_id, url, alt_text, sort_order, is_primary)
SELECT p.id, CASE WHEN n > 1 THEN (p.id - 1) * 4 + n END,
       'https://cdn.shopcorp.example/img/p' || p.id || '_' || n || '.jpg',
       left(p.name, 150) || ' (view ' || n || ')', n, n = 1
FROM products p CROSS JOIN generate_series(1, 3) n;

CREATE TABLE attributes (
    id        SERIAL PRIMARY KEY,
    code      VARCHAR(40) NOT NULL UNIQUE,
    label     VARCHAR(80) NOT NULL,
    data_type VARCHAR(20) NOT NULL
);
INSERT INTO attributes (code, label, data_type) VALUES
  ('fabric','Fabric','text'), ('fit','Fit','text'), ('capacity_gb','Storage capacity (GB)','number'),
  ('screen_size_in','Screen size (inches)','number'), ('metal','Metal','text'), ('style','Style','text');

CREATE TABLE attribute_values (
    id           SERIAL PRIMARY KEY,
    attribute_id INT         NOT NULL REFERENCES attributes(id),
    value        VARCHAR(80) NOT NULL,
    UNIQUE (attribute_id, value)
);
INSERT INTO attribute_values (attribute_id, value)
SELECT a.id, v FROM attributes a CROSS JOIN LATERAL unnest(CASE a.code
  WHEN 'fabric' THEN ARRAY['Cotton','Linen','Wool','Polyester','Denim']
  WHEN 'fit' THEN ARRAY['Slim','Regular','Relaxed','Oversized']
  WHEN 'capacity_gb' THEN ARRAY['256','512','1000','2000','4000']
  WHEN 'screen_size_in' THEN ARRAY['21.5','24','27','32','49']
  WHEN 'metal' THEN ARRAY['Sterling Silver','14k Gold','18k Gold','Platinum','Rose Gold']
  ELSE ARRAY['Casual','Formal','Sport','Vintage','Minimalist'] END) AS v;

CREATE TABLE variant_attribute_values (
    variant_id         INT NOT NULL REFERENCES product_variants(id) ON DELETE CASCADE,
    attribute_value_id INT NOT NULL REFERENCES attribute_values(id),
    PRIMARY KEY (variant_id, attribute_value_id)
);
INSERT INTO variant_attribute_values
SELECT v.id, pg_temp.rint(1, (SELECT count(*)::int FROM attribute_values))
FROM product_variants v CROSS JOIN generate_series(1, 2)
ON CONFLICT DO NOTHING;

CREATE TABLE tags (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(40) NOT NULL UNIQUE
);
INSERT INTO tags (name) SELECT unnest(ARRAY['bestseller','new-arrival','eco-friendly','gift-idea',
  'limited-edition','clearance','summer','winter','office','gaming','outdoor','luxury','handmade',
  'vegan','waterproof','wireless','bundle-eligible','staff-pick','trending','back-in-stock',
  'premium','budget','unisex','kids','travel','fitness','home','minimalist','vintage','exclusive']);

CREATE TABLE product_tags (
    product_id INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tag_id     INT NOT NULL REFERENCES tags(id),
    PRIMARY KEY (product_id, tag_id)
);
INSERT INTO product_tags SELECT p.id, pg_temp.rint(1, 30)
FROM products p CROSS JOIN generate_series(1, 3) ON CONFLICT DO NOTHING;

CREATE TABLE collections (
    id           SERIAL PRIMARY KEY,
    title        VARCHAR(120) NOT NULL,
    slug         VARCHAR(120) NOT NULL UNIQUE,
    starts_at    TIMESTAMPTZ,
    ends_at      TIMESTAMPTZ,
    is_published BOOLEAN      NOT NULL DEFAULT TRUE
);
INSERT INTO collections (title, slug, starts_at, ends_at, is_published) VALUES
  ('Summer Essentials','summer-essentials','2026-05-01','2026-08-31',true),
  ('Holiday Gift Guide','holiday-gift-guide','2025-11-15','2025-12-31',true),
  ('Work From Home','work-from-home',NULL,NULL,true),
  ('Black Friday Deals','black-friday-deals','2025-11-27','2025-12-01',true),
  ('New This Month','new-this-month',NULL,NULL,true),
  ('Jewelry Under $200','jewelry-under-200',NULL,NULL,true),
  ('Gamer Setup','gamer-setup',NULL,NULL,true),
  ('Spring Preview','spring-preview','2027-03-01',NULL,false);

CREATE TABLE collection_products (
    collection_id INT      NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    product_id    INT      NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    position      SMALLINT NOT NULL DEFAULT 0,
    PRIMARY KEY (collection_id, product_id)
);
INSERT INTO collection_products SELECT c.id, pg_temp.rint(1, (SELECT products FROM k)), n
FROM collections c CROSS JOIN generate_series(1, 6) n ON CONFLICT DO NOTHING;

CREATE TABLE price_history (
    id         SERIAL PRIMARY KEY,
    product_id INT           NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    old_price  NUMERIC(10,2) NOT NULL,
    new_price  NUMERIC(10,2) NOT NULL,
    reason     VARCHAR(40),
    changed_at TIMESTAMPTZ   NOT NULL,
    changed_by INT           REFERENCES employees(id)
);
INSERT INTO price_history (product_id, old_price, new_price, reason, changed_at, changed_by)
SELECT p.id, round(p.price * (0.85 + random()::numeric * 0.3), 2), round(p.price * (0.85 + random()::numeric * 0.3), 2),
       pg_temp.pick(ARRAY['promotion','cost increase','competitor match','end of promotion','clearance']),
       timestamptz '2024-10-10' + m * interval '1 month' + random() * interval '20 days',
       pg_temp.rint(1, 60)
FROM products p CROSS JOIN generate_series(0, 23) m;

CREATE TABLE product_questions (
    id          SERIAL PRIMARY KEY,
    product_id  INT         NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id     INT         NOT NULL REFERENCES users(id),
    question    TEXT        NOT NULL,
    answer      TEXT,
    answered_by INT         REFERENCES employees(id),
    asked_at    TIMESTAMPTZ NOT NULL,
    answered_at TIMESTAMPTZ
);
INSERT INTO product_questions (product_id, user_id, question, answer, answered_by, asked_at, answered_at)
SELECT pid, pg_temp.rint(1, (SELECT users FROM k)), q,
       CASE WHEN answered THEN 'Thanks for asking! ' || pg_temp.pick(ARRAY['Yes, it does.','No, unfortunately not.',
         'Please check the size guide.','It ships within 2 business days.']) END,
       CASE WHEN answered THEN pg_temp.rint(1, 60) END, asked, CASE WHEN answered THEN asked + interval '1 day' END
FROM (SELECT pg_temp.rint(1, (SELECT products FROM k)) AS pid, random() < 0.7 AS answered, pg_temp.rts(365) AS asked,
             pg_temp.pick(ARRAY['Is this true to size?','Does it come with a warranty?','Is it waterproof?',
               'Can I return it if it does not fit?','Is the color accurate in the photos?',
               'Does it work with a Mac?','How long does shipping take?']) AS q
      FROM generate_series(1, 50)) x;
"""


# ══════════════════════════════════════════════
# Inventory and suppliers
# ══════════════════════════════════════════════

INVENTORY = r"""
CREATE TABLE warehouses (
    id             SERIAL PRIMARY KEY,
    code           VARCHAR(10)  NOT NULL UNIQUE,
    name           VARCHAR(120) NOT NULL,
    city_id        INT          NOT NULL REFERENCES cities(id),
    capacity_units INT          NOT NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE
);
INSERT INTO warehouses (code, name, city_id, capacity_units)
SELECT w.code, w.name, c.id, w.cap FROM (VALUES
  ('NJ1','East Coast Fulfillment Center','New York City',120000),
  ('TX1','Central Distribution Hub','Dallas',90000),
  ('CA1','West Coast Fulfillment Center','Los Angeles',110000),
  ('UK1','UK Fulfillment Center','Manchester',45000)
) AS w(code, name, city, cap) JOIN cities c ON c.name = w.city;

CREATE TABLE warehouse_zones (
    id                    SERIAL PRIMARY KEY,
    warehouse_id          INT         NOT NULL REFERENCES warehouses(id),
    zone_code             VARCHAR(10) NOT NULL,
    purpose               VARCHAR(30) NOT NULL,
    temperature_controlled BOOLEAN    NOT NULL DEFAULT FALSE,
    UNIQUE (warehouse_id, zone_code)
);
INSERT INTO warehouse_zones (warehouse_id, zone_code, purpose, temperature_controlled)
SELECT w.id, z.code, z.purpose, z.code = 'D'
FROM warehouses w CROSS JOIN (VALUES ('A','receiving'), ('B','bulk storage'), ('C','pick face'),
  ('D','high value')) AS z(code, purpose)
ORDER BY w.id, z.code;

CREATE TABLE inventory_levels (
    id            SERIAL PRIMARY KEY,
    warehouse_id  INT         NOT NULL REFERENCES warehouses(id),
    variant_id    INT         NOT NULL REFERENCES product_variants(id),
    qty_on_hand   INT         NOT NULL DEFAULT 0,
    qty_reserved  INT         NOT NULL DEFAULT 0,
    reorder_level INT         NOT NULL DEFAULT 10,
    updated_at    TIMESTAMPTZ NOT NULL,
    UNIQUE (warehouse_id, variant_id)
);
INSERT INTO inventory_levels (warehouse_id, variant_id, qty_on_hand, qty_reserved, reorder_level, updated_at)
SELECT w.id, v.id, pg_temp.rint(0, 400), pg_temp.rint(0, 20), pg_temp.pick(ARRAY['10','20','25','50'])::int,
       pg_temp.rts(30)
FROM warehouses w CROSS JOIN product_variants v ORDER BY w.id, v.id;

CREATE TABLE stock_movements (
    id             SERIAL PRIMARY KEY,
    warehouse_id   INT         NOT NULL REFERENCES warehouses(id),
    zone_id        INT         REFERENCES warehouse_zones(id),
    variant_id     INT         NOT NULL REFERENCES product_variants(id),
    movement_type  VARCHAR(20) NOT NULL,
    qty            INT         NOT NULL,
    reference_type VARCHAR(20),
    reference_id   INT,
    moved_at       TIMESTAMPTZ NOT NULL
);
INSERT INTO stock_movements (warehouse_id, zone_id, variant_id, movement_type, qty, reference_type, reference_id, moved_at)
SELECT wh, (wh - 1) * 4 + pg_temp.rint(1, 4), pg_temp.rint(1, (SELECT products FROM k) * 4), mt,
       CASE WHEN mt IN ('sale','transfer_out','damage') THEN -pg_temp.rint(1, 5) ELSE pg_temp.rint(1, 60) END,
       CASE mt WHEN 'sale' THEN 'order' WHEN 'return' THEN 'return' WHEN 'receipt' THEN 'purchase_order'
               WHEN 'transfer_in' THEN 'stock_transfer' WHEN 'transfer_out' THEN 'stock_transfer' END,
       CASE WHEN mt IN ('sale','return') THEN pg_temp.rint(1, (SELECT orders FROM k))
            WHEN mt = 'receipt' THEN pg_temp.rint(1, 120) WHEN mt LIKE 'transfer%' THEN pg_temp.rint(1, 60) END,
       pg_temp.rts(365)
FROM (SELECT pg_temp.rint(1, 4) AS wh,
             pg_temp.pick(ARRAY['receipt','sale','sale','sale','return','adjustment','transfer_in',
                                'transfer_out','damage']) AS mt
      FROM generate_series(1, 20000)) x;

CREATE TABLE stock_transfers (
    id                SERIAL PRIMARY KEY,
    from_warehouse_id INT         NOT NULL REFERENCES warehouses(id),
    to_warehouse_id   INT         NOT NULL REFERENCES warehouses(id),
    status            VARCHAR(20) NOT NULL,
    requested_at      TIMESTAMPTZ NOT NULL,
    shipped_at        TIMESTAMPTZ,
    received_at       TIMESTAMPTZ,
    CHECK (from_warehouse_id <> to_warehouse_id)
);
INSERT INTO stock_transfers (from_warehouse_id, to_warehouse_id, status, requested_at, shipped_at, received_at)
SELECT f, (f + pg_temp.rint(0, 2)) % 4 + 1, st, req,
       CASE WHEN st IN ('in_transit','received') THEN req + interval '1 day' END,
       CASE WHEN st = 'received' THEN req + interval '4 days' END
FROM (SELECT pg_temp.rint(1, 4) AS f, pg_temp.pick(ARRAY['requested','in_transit','received','received','cancelled']) AS st,
             pg_temp.rts(365) AS req FROM generate_series(1, 60)) x;

CREATE TABLE stock_transfer_items (
    id          SERIAL PRIMARY KEY,
    transfer_id INT NOT NULL REFERENCES stock_transfers(id) ON DELETE CASCADE,
    variant_id  INT NOT NULL REFERENCES product_variants(id),
    qty         INT NOT NULL CHECK (qty > 0)
);
INSERT INTO stock_transfer_items (transfer_id, variant_id, qty)
SELECT t.id, pg_temp.rint(1, (SELECT products FROM k) * 4), pg_temp.rint(5, 80)
FROM stock_transfers t CROSS JOIN generate_series(1, 3);

CREATE TABLE suppliers (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(120) NOT NULL UNIQUE,
    country_id     INT          REFERENCES countries(id),
    rating         NUMERIC(2,1),
    lead_time_days SMALLINT     NOT NULL,
    payment_terms  VARCHAR(20)  NOT NULL,
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE
);
INSERT INTO suppliers (name, country_id, rating, lead_time_days, payment_terms, is_active)
SELECT s, pg_temp.rint(1, 15), pg_temp.rnum(2.5, 5)::numeric(2,1), pg_temp.rint(3, 45),
       pg_temp.pick(ARRAY['NET30','NET45','NET60','PREPAID']), random() < 0.9
FROM unnest(ARRAY['Pacific Textile Mills','Shenzhen Display Works','Golden Thread Jewelry',
  'Alpine Gear Manufacturing','Orion Storage Systems','Delta Apparel Group','Starlight Gems',
  'Coastal Leather Co','Vertex Electronics','Evergreen Fabrics','Summit Outdoor Supply',
  'Meridian Components','Blue Harbor Logistics','Crown Accessories','Nova Silicon']) AS s;

CREATE TABLE supplier_contacts (
    id          SERIAL PRIMARY KEY,
    supplier_id INT          NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    full_name   VARCHAR(120) NOT NULL,
    email       VARCHAR(255) NOT NULL,
    phone       VARCHAR(30),
    role        VARCHAR(40)  NOT NULL
);
INSERT INTO supplier_contacts (supplier_id, full_name, email, phone, role)
SELECT s.id, pg_temp.person(), 'contact' || s.id || '_' || n || '@supplier' || s.id || '.example',
       '+1-555-' || lpad(pg_temp.rint(0, 9999)::text, 4, '0'), CASE n WHEN 1 THEN 'account manager' ELSE 'logistics' END
FROM suppliers s CROSS JOIN generate_series(1, 2) n;

CREATE TABLE supplier_products (
    supplier_id  INT           NOT NULL REFERENCES suppliers(id),
    variant_id   INT           NOT NULL REFERENCES product_variants(id),
    supplier_sku VARCHAR(40)   NOT NULL,
    unit_cost    NUMERIC(10,2) NOT NULL,
    moq          INT           NOT NULL DEFAULT 1,
    PRIMARY KEY (supplier_id, variant_id)
);
INSERT INTO supplier_products
SELECT sid, v.id, 'S' || sid || '-' || v.id, round((p.price + v.price_delta) * (0.35 + random()::numeric * 0.25), 2),
       pg_temp.pick(ARRAY['1','10','25','50','100'])::int
FROM (SELECT pg_temp.rint(1, 15) AS sid, pg_temp.rint(1, (SELECT products FROM k) * 4) AS vid
      FROM generate_series(1, 70)) x
JOIN product_variants v ON v.id = x.vid JOIN products p ON p.id = v.product_id
ON CONFLICT DO NOTHING;

CREATE TABLE purchase_orders (
    id            SERIAL PRIMARY KEY,
    po_number     VARCHAR(20)   NOT NULL UNIQUE,
    supplier_id   INT           NOT NULL REFERENCES suppliers(id),
    warehouse_id  INT           NOT NULL REFERENCES warehouses(id),
    status        VARCHAR(20)   NOT NULL,
    ordered_at    TIMESTAMPTZ   NOT NULL,
    expected_at   TIMESTAMPTZ,
    total_cost    NUMERIC(12,2) NOT NULL DEFAULT 0,
    currency_code CHAR(3)       NOT NULL REFERENCES currencies(code),
    created_by    INT           REFERENCES employees(id)
);
INSERT INTO purchase_orders (po_number, supplier_id, warehouse_id, status, ordered_at, expected_at, currency_code, created_by)
SELECT 'PO-' || lpad(g::text, 6, '0'), s.id, pg_temp.rint(1, 4), st, ord,
       ord + make_interval(days => s.lead_time_days), pg_temp.pick(ARRAY['USD','USD','USD','EUR','GBP']),
       pg_temp.rint(1, 60)
FROM (SELECT g, pg_temp.rint(1, 15) AS sid, pg_temp.rts(365) AS ord,
             pg_temp.pick(ARRAY['draft','sent','partially_received','received','received','received','cancelled']) AS st
      FROM generate_series(1, 120) g) x JOIN suppliers s ON s.id = x.sid ORDER BY g;

CREATE TABLE purchase_order_items (
    id                SERIAL PRIMARY KEY,
    purchase_order_id INT           NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    variant_id        INT           NOT NULL REFERENCES product_variants(id),
    qty_ordered       INT           NOT NULL,
    qty_received      INT           NOT NULL DEFAULT 0,
    unit_cost         NUMERIC(10,2) NOT NULL
);
INSERT INTO purchase_order_items (purchase_order_id, variant_id, qty_ordered, qty_received, unit_cost)
SELECT po.id, v.id, q,
       CASE po.status WHEN 'received' THEN q WHEN 'partially_received' THEN q / 2 ELSE 0 END,
       round((p.price + v.price_delta) * (0.35 + random()::numeric * 0.25), 2)
FROM (SELECT po.id AS po_id, pg_temp.rint(1, (SELECT products FROM k) * 4) AS vid, pg_temp.rint(10, 200) AS q
      FROM purchase_orders po CROSS JOIN generate_series(1, 4) WHERE random() < 0.85) x
JOIN purchase_orders po ON po.id = x.po_id
JOIN product_variants v ON v.id = x.vid JOIN products p ON p.id = v.product_id;
UPDATE purchase_orders po SET total_cost = s.total
FROM (SELECT purchase_order_id, sum(qty_ordered * unit_cost) AS total FROM purchase_order_items
      GROUP BY purchase_order_id) s WHERE s.purchase_order_id = po.id;

CREATE TABLE goods_receipts (
    id                SERIAL PRIMARY KEY,
    purchase_order_id INT         NOT NULL REFERENCES purchase_orders(id),
    warehouse_id      INT         NOT NULL REFERENCES warehouses(id),
    received_at       TIMESTAMPTZ NOT NULL,
    received_by       INT         REFERENCES employees(id),
    damaged_units     INT         NOT NULL DEFAULT 0,
    notes             TEXT
);
INSERT INTO goods_receipts (purchase_order_id, warehouse_id, received_at, received_by, damaged_units, notes)
SELECT po.id, po.warehouse_id, po.expected_at + pg_temp.rint(-2, 6) * interval '1 day', pg_temp.rint(1, 60),
       CASE WHEN random() < 0.15 THEN pg_temp.rint(1, 8) ELSE 0 END,
       CASE WHEN random() < 0.2 THEN pg_temp.pick(ARRAY['Pallet wrap damaged','Late delivery','Short shipped']) END
FROM purchase_orders po WHERE po.status IN ('received','partially_received');
"""


# ══════════════════════════════════════════════
# Shipping
# ══════════════════════════════════════════════

SHIPPING = r"""
CREATE TABLE carriers (
    id                    SERIAL PRIMARY KEY,
    name                  VARCHAR(60) NOT NULL UNIQUE,
    tracking_url_template TEXT,
    is_active             BOOLEAN     NOT NULL DEFAULT TRUE
);
INSERT INTO carriers (name, tracking_url_template) VALUES
  ('UPS','https://www.ups.com/track?tracknum={tracking}'),
  ('FedEx','https://www.fedex.com/fedextrack/?trknbr={tracking}'),
  ('USPS','https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}'),
  ('DHL Express','https://www.dhl.com/track?id={tracking}'),
  ('Royal Mail','https://www.royalmail.com/track-your-item#/tracking-results/{tracking}');

CREATE TABLE shipping_methods (
    id            SERIAL PRIMARY KEY,
    carrier_id    INT           NOT NULL REFERENCES carriers(id),
    name          VARCHAR(60)   NOT NULL,
    service_level VARCHAR(20)   NOT NULL,
    est_days_min  SMALLINT      NOT NULL,
    est_days_max  SMALLINT      NOT NULL,
    base_cost     NUMERIC(8,2)  NOT NULL
);
INSERT INTO shipping_methods (carrier_id, name, service_level, est_days_min, est_days_max, base_cost) VALUES
  (1,'UPS Ground','standard',3,5,5.99), (1,'UPS Next Day Air','overnight',1,1,24.99),
  (2,'FedEx 2Day','express',2,2,14.99), (2,'FedEx International Priority','international',2,5,39.99),
  (3,'USPS Priority Mail','standard',2,4,7.49), (3,'USPS First-Class','economy',3,7,3.99),
  (4,'DHL Express Worldwide','international',2,6,44.00), (5,'Royal Mail Tracked 48','standard',2,3,4.20);

CREATE TABLE shipping_zones (
    id   SERIAL PRIMARY KEY,
    name VARCHAR(60) NOT NULL UNIQUE,
    free_shipping_threshold NUMERIC(10,2)
);
INSERT INTO shipping_zones (name, free_shipping_threshold) VALUES
  ('Domestic US',50), ('North America',100), ('Europe',120), ('Asia Pacific',150), ('Rest of World',NULL);

CREATE TABLE shipping_zone_countries (
    zone_id    INT NOT NULL REFERENCES shipping_zones(id) ON DELETE CASCADE,
    country_id INT NOT NULL REFERENCES countries(id),
    PRIMARY KEY (zone_id, country_id)
);
INSERT INTO shipping_zone_countries
SELECT CASE WHEN c.iso2 = 'US' THEN 1 WHEN c.continent = 'North America' THEN 2 WHEN c.continent = 'Europe' THEN 3
            WHEN c.continent IN ('Asia','Oceania') THEN 4 ELSE 5 END, c.id
FROM countries c;

CREATE TABLE shipments (
    id              SERIAL PRIMARY KEY,
    order_id        INT          NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    method_id       INT          NOT NULL REFERENCES shipping_methods(id),
    warehouse_id    INT          NOT NULL REFERENCES warehouses(id),
    tracking_number VARCHAR(40)  NOT NULL UNIQUE,
    status          VARCHAR(20)  NOT NULL,
    weight_grams    INT,
    cost            NUMERIC(8,2) NOT NULL,
    shipped_at      TIMESTAMPTZ  NOT NULL,
    delivered_at    TIMESTAMPTZ
);
INSERT INTO shipments (order_id, method_id, warehouse_id, tracking_number, status, weight_grams, cost, shipped_at, delivered_at)
SELECT o.id, m, pg_temp.rint(1, 3), 'TRK' || lpad(o.id::text, 6, '0') || pg_temp.rint(1000, 9999),
       CASE WHEN o.status = 'shipped' THEN 'in_transit' ELSE 'delivered' END, pg_temp.rint(200, 12000),
       sm.base_cost, sh, CASE WHEN o.status <> 'shipped' THEN sh + make_interval(days => sm.est_days_max) END
FROM (SELECT o.id AS oid, pg_temp.rint(1, 6) AS m, o.created_at + interval '1 day' + random() * interval '1 day' AS sh
      FROM orders o WHERE o.status IN ('shipped','delivered','refunded')) x
JOIN orders o ON o.id = x.oid JOIN shipping_methods sm ON sm.id = x.m ORDER BY o.id;

CREATE TABLE shipment_items (
    id            SERIAL PRIMARY KEY,
    shipment_id   INT NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    order_item_id INT NOT NULL REFERENCES order_items(id),
    qty           INT NOT NULL
);
INSERT INTO shipment_items (shipment_id, order_item_id, qty)
SELECT s.id, oi.id, oi.quantity FROM shipments s JOIN order_items oi ON oi.order_id = s.order_id;

CREATE TABLE shipment_events (
    id          SERIAL PRIMARY KEY,
    shipment_id INT          NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
    event_code  VARCHAR(30)  NOT NULL,
    description VARCHAR(200) NOT NULL,
    location    VARCHAR(100),
    occurred_at TIMESTAMPTZ  NOT NULL
);
INSERT INTO shipment_events (shipment_id, event_code, description, location, occurred_at)
SELECT s.id, e.code, e.descr, pg_temp.pick(ARRAY['Newark, NJ','Memphis, TN','Louisville, KY','Dallas, TX','Ontario, CA']),
       s.shipped_at + (e.n - 1) * interval '18 hours'
FROM shipments s CROSS JOIN LATERAL (VALUES
  (1,'label_created','Shipping label created'), (2,'picked_up','Picked up by carrier'),
  (3,'in_transit','In transit to destination facility'), (4,'out_for_delivery','Out for delivery'),
  (5,'delivered','Delivered')) AS e(n, code, descr)
WHERE e.n <= CASE WHEN s.status = 'delivered' THEN 5 ELSE 3 END;
"""


# ══════════════════════════════════════════════
# Carts, wishlists and order lifecycle
# ══════════════════════════════════════════════

ORDERS = r"""
CREATE TABLE carts (
    id                 SERIAL PRIMARY KEY,
    user_id            INT         REFERENCES users(id),
    status             VARCHAR(20) NOT NULL,
    converted_order_id INT         REFERENCES orders(id),
    created_at         TIMESTAMPTZ NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL
);
INSERT INTO carts (user_id, status, converted_order_id, created_at, updated_at)
SELECT CASE WHEN random() < 0.8 THEN pg_temp.rint(1, (SELECT users FROM k)) END, st,
       CASE WHEN st = 'converted' THEN pg_temp.rint(1, (SELECT orders FROM k)) END, c, c + random() * interval '3 days'
FROM (SELECT pg_temp.pick(ARRAY['active','abandoned','abandoned','converted']) AS st, pg_temp.rts(365) AS c
      FROM generate_series(1, 60)) x;

CREATE TABLE cart_items (
    id         SERIAL PRIMARY KEY,
    cart_id    INT         NOT NULL REFERENCES carts(id) ON DELETE CASCADE,
    variant_id INT         NOT NULL REFERENCES product_variants(id),
    qty        INT         NOT NULL DEFAULT 1,
    added_at   TIMESTAMPTZ NOT NULL
);
INSERT INTO cart_items (cart_id, variant_id, qty, added_at)
SELECT c.id, pg_temp.rint(1, (SELECT products FROM k) * 4), pg_temp.rint(1, 3), c.created_at + random() * interval '1 hour'
FROM carts c CROSS JOIN LATERAL generate_series(1, pg_temp.rint(1, 4) + 0 * c.id);

CREATE TABLE wishlists (
    id         SERIAL PRIMARY KEY,
    user_id    INT          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       VARCHAR(80)  NOT NULL DEFAULT 'My Wishlist',
    is_public  BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ  NOT NULL
);
INSERT INTO wishlists (user_id, name, is_public, created_at)
SELECT pg_temp.rint(1, (SELECT users FROM k)),
       pg_temp.pick(ARRAY['My Wishlist','Birthday ideas','Holiday gifts','Someday']), random() < 0.3, pg_temp.rts(365)
FROM generate_series(1, 30);

CREATE TABLE wishlist_items (
    wishlist_id INT         NOT NULL REFERENCES wishlists(id) ON DELETE CASCADE,
    product_id  INT         NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    added_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (wishlist_id, product_id)
);
INSERT INTO wishlist_items SELECT w.id, pg_temp.rint(1, (SELECT products FROM k)), w.created_at + random() * interval '60 days'
FROM wishlists w CROSS JOIN generate_series(1, 3) ON CONFLICT DO NOTHING;

CREATE TABLE order_status_history (
    id          SERIAL PRIMARY KEY,
    order_id    INT         NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    from_status VARCHAR(30),
    to_status   VARCHAR(30) NOT NULL,
    changed_at  TIMESTAMPTZ NOT NULL,
    changed_by  INT         REFERENCES employees(id)
);
INSERT INTO order_status_history (order_id, from_status, to_status, changed_at, changed_by)
SELECT o.id, lag(s.st) OVER (PARTITION BY o.id ORDER BY s.n), s.st,
       o.created_at + (s.n - 1) * interval '1 day', CASE WHEN s.n > 1 THEN 1 + (o.id * s.n) % 60 END
FROM orders o CROSS JOIN LATERAL unnest(CASE o.status
    WHEN 'delivered'  THEN ARRAY['pending','processing','shipped','delivered']
    WHEN 'shipped'    THEN ARRAY['pending','processing','shipped']
    WHEN 'processing' THEN ARRAY['pending','processing']
    WHEN 'cancelled'  THEN ARRAY['pending','cancelled']
    WHEN 'refunded'   THEN ARRAY['pending','processing','shipped','delivered','refunded']
    ELSE ARRAY[o.status::text] END) WITH ORDINALITY AS s(st, n)
ORDER BY o.id, s.n;

CREATE TABLE invoices (
    id            SERIAL PRIMARY KEY,
    order_id      INT           NOT NULL UNIQUE REFERENCES orders(id),
    invoice_no    VARCHAR(20)   NOT NULL UNIQUE,
    issued_at     TIMESTAMPTZ   NOT NULL,
    due_at        TIMESTAMPTZ   NOT NULL,
    currency_code CHAR(3)       NOT NULL REFERENCES currencies(code) DEFAULT 'USD',
    total_amount  NUMERIC(10,2) NOT NULL,
    status        VARCHAR(20)   NOT NULL
);
INSERT INTO invoices (order_id, invoice_no, issued_at, due_at, total_amount, status)
SELECT o.id, 'INV-' || to_char(o.created_at, 'YYYY') || '-' || lpad(o.id::text, 5, '0'),
       o.created_at + interval '1 hour', o.created_at + interval '30 days', o.total_amount,
       CASE p.status WHEN 'completed' THEN 'paid' WHEN 'refunded' THEN 'void' WHEN 'failed' THEN 'overdue' ELSE 'open' END
FROM orders o LEFT JOIN LATERAL (SELECT status FROM payments WHERE order_id = o.id ORDER BY id DESC LIMIT 1) p ON true
WHERE o.status <> 'cancelled' ORDER BY o.id;

CREATE TABLE invoice_lines (
    id            SERIAL PRIMARY KEY,
    invoice_id    INT           NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    order_item_id INT           REFERENCES order_items(id),
    description   VARCHAR(255)  NOT NULL,
    qty           INT           NOT NULL,
    unit_price    NUMERIC(10,2) NOT NULL,
    tax_rate_pct  NUMERIC(5,2)  NOT NULL,
    line_total    NUMERIC(10,2) NOT NULL
);
INSERT INTO invoice_lines (invoice_id, order_item_id, description, qty, unit_price, tax_rate_pct, line_total)
SELECT i.id, oi.id, left(p.name, 255), oi.quantity, oi.unit_price, 8.00, oi.total_price
FROM invoices i JOIN order_items oi ON oi.order_id = i.order_id JOIN products p ON p.id = oi.product_id
ORDER BY i.id, oi.id;

CREATE TABLE refunds (
    id          SERIAL PRIMARY KEY,
    payment_id  INT           NOT NULL REFERENCES payments(id),
    order_id    INT           NOT NULL REFERENCES orders(id),
    amount      NUMERIC(10,2) NOT NULL,
    reason      VARCHAR(60)   NOT NULL,
    status      VARCHAR(20)   NOT NULL,
    refunded_at TIMESTAMPTZ
);
INSERT INTO refunds (payment_id, order_id, amount, reason, status, refunded_at)
SELECT p.id, p.order_id, p.amount, pg_temp.pick(ARRAY['damaged item','wrong size','changed mind','late delivery']),
       'completed', coalesce(p.paid_at, p.created_at) + interval '9 days'
FROM payments p WHERE p.status = 'refunded';

CREATE TABLE returns (
    id           SERIAL PRIMARY KEY,
    order_id     INT         NOT NULL REFERENCES orders(id),
    user_id      INT         NOT NULL REFERENCES users(id),
    rma_number   VARCHAR(20) NOT NULL UNIQUE,
    status       VARCHAR(20) NOT NULL,
    reason_code  VARCHAR(30) NOT NULL,
    requested_at TIMESTAMPTZ NOT NULL,
    closed_at    TIMESTAMPTZ
);
INSERT INTO returns (order_id, user_id, rma_number, status, reason_code, requested_at, closed_at)
SELECT o.id, o.user_id, 'RMA-' || lpad(o.id::text, 6, '0'), st, pg_temp.pick(ARRAY['DEFECTIVE','WRONG_SIZE',
         'NOT_AS_DESCRIBED','NO_LONGER_NEEDED','ARRIVED_LATE']),
       o.created_at + interval '10 days', CASE WHEN st IN ('refunded','rejected') THEN o.created_at + interval '20 days' END
FROM (SELECT o.id AS oid, pg_temp.pick(ARRAY['requested','received','refunded','refunded','rejected']) AS st
      FROM orders o WHERE o.status IN ('delivered','refunded') AND random() < 0.35) x
JOIN orders o ON o.id = x.oid ORDER BY o.id;

CREATE TABLE return_items (
    id            SERIAL PRIMARY KEY,
    return_id     INT         NOT NULL REFERENCES returns(id) ON DELETE CASCADE,
    order_item_id INT         NOT NULL REFERENCES order_items(id),
    qty           INT         NOT NULL,
    condition     VARCHAR(20) NOT NULL,
    restock       BOOLEAN     NOT NULL
);
INSERT INTO return_items (return_id, order_item_id, qty, condition, restock)
SELECT r.id, oi.id, oi.quantity, c, c IN ('new','opened')
FROM returns r JOIN order_items oi ON oi.order_id = r.order_id
CROSS JOIN LATERAL (SELECT pg_temp.pick(ARRAY['new','opened','damaged']) AS c WHERE oi.id > 0) cond;

CREATE TABLE coupon_redemptions (
    id               SERIAL PRIMARY KEY,
    coupon_id        INT           NOT NULL REFERENCES coupons(id),
    order_id         INT           NOT NULL UNIQUE REFERENCES orders(id),
    user_id          INT           NOT NULL REFERENCES users(id),
    discount_applied NUMERIC(10,2) NOT NULL,
    redeemed_at      TIMESTAMPTZ   NOT NULL
);
INSERT INTO coupon_redemptions (coupon_id, order_id, user_id, discount_applied, redeemed_at)
SELECT coupon_id, id, user_id, discount_amount, created_at FROM orders WHERE coupon_id IS NOT NULL ORDER BY id;
"""


# ══════════════════════════════════════════════
# Payments and finance
# ══════════════════════════════════════════════

FINANCE = r"""
CREATE TABLE saved_payment_methods (
    id         SERIAL PRIMARY KEY,
    user_id    INT         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type       VARCHAR(20) NOT NULL,
    brand      VARCHAR(20),
    last4      CHAR(4),
    exp_month  SMALLINT,
    exp_year   SMALLINT,
    is_default BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL
);
INSERT INTO saved_payment_methods (user_id, type, brand, last4, exp_month, exp_year, is_default, created_at)
SELECT u, t, CASE WHEN t = 'card' THEN pg_temp.pick(ARRAY['visa','mastercard','amex','discover']) END,
       CASE WHEN t = 'card' THEN lpad(pg_temp.rint(0, 9999)::text, 4, '0') END,
       CASE WHEN t = 'card' THEN pg_temp.rint(1, 12) END, CASE WHEN t = 'card' THEN pg_temp.rint(2026, 2031) END,
       random() < 0.5, pg_temp.rts(700)
FROM (SELECT pg_temp.rint(1, (SELECT users FROM k)) AS u, pg_temp.pick(ARRAY['card','card','card','paypal','bank_account']) AS t
      FROM generate_series(1, 50)) x;

CREATE TABLE payment_attempts (
    id           SERIAL PRIMARY KEY,
    order_id     INT           NOT NULL REFERENCES orders(id),
    payment_id   INT           REFERENCES payments(id),
    gateway      VARCHAR(20)   NOT NULL,
    status       VARCHAR(20)   NOT NULL,
    error_code   VARCHAR(30),
    amount       NUMERIC(10,2) NOT NULL,
    attempted_at TIMESTAMPTZ   NOT NULL
);
INSERT INTO payment_attempts (order_id, payment_id, gateway, status, error_code, amount, attempted_at)
SELECT p.order_id, CASE WHEN n = t.tries THEN p.id END, pg_temp.pick(ARRAY['stripe','adyen','paypal']),
       CASE WHEN n < t.tries THEN 'declined' WHEN p.status = 'failed' THEN 'declined' ELSE 'succeeded' END,
       CASE WHEN n < t.tries OR p.status = 'failed' THEN pg_temp.pick(ARRAY['insufficient_funds','card_expired',
            'do_not_honor','incorrect_cvc','processing_error']) END,
       p.amount, p.created_at + (n - 1) * interval '3 minutes'
FROM payments p
CROSS JOIN LATERAL (SELECT 1 + (random() < 0.3)::int AS tries WHERE p.id > 0) t
CROSS JOIN LATERAL generate_series(1, t.tries) n
ORDER BY p.id, n;

CREATE TABLE gl_accounts (
    id        SERIAL PRIMARY KEY,
    acct_code VARCHAR(10)  NOT NULL UNIQUE,
    acct_name VARCHAR(80)  NOT NULL,
    acct_type VARCHAR(20)  NOT NULL,
    is_active BOOLEAN      NOT NULL DEFAULT TRUE
);
INSERT INTO gl_accounts (acct_code, acct_name, acct_type) VALUES
  ('1000','Cash','asset'), ('1100','Accounts Receivable','asset'), ('1200','Inventory','asset'),
  ('1300','Prepaid Expenses','asset'), ('1500','Equipment','asset'), ('2000','Accounts Payable','liability'),
  ('2100','Sales Tax Payable','liability'), ('2200','Accrued Liabilities','liability'),
  ('2300','Gift Card Liability','liability'), ('2400','Deferred Revenue','liability'),
  ('3000','Owner''s Equity','equity'), ('3100','Retained Earnings','equity'),
  ('4000','Product Revenue','revenue'), ('4100','Shipping Revenue','revenue'),
  ('4200','Sales Returns','contra_revenue'), ('4300','Sales Discounts','contra_revenue'),
  ('5000','Cost of Goods Sold','expense'), ('5100','Freight In','expense'), ('5200','Inventory Shrinkage','expense'),
  ('6000','Salaries and Wages','expense'), ('6100','Rent','expense'), ('6200','Utilities','expense'),
  ('6300','Marketing and Advertising','expense'), ('6400','Payment Processing Fees','expense'),
  ('6500','Software Subscriptions','expense'), ('6600','Travel','expense'), ('6700','Office Supplies','expense'),
  ('6800','Depreciation','expense'), ('6900','Customer Support Costs','expense'), ('7000','Interest Expense','expense');

CREATE TABLE journal_entries (
    id         SERIAL PRIMARY KEY,
    entry_no   VARCHAR(20) NOT NULL UNIQUE,
    entry_date DATE        NOT NULL,
    source     VARCHAR(20) NOT NULL,
    source_id  INT,
    memo       TEXT,
    posted_by  INT         REFERENCES employees(id)
);
INSERT INTO journal_entries (entry_no, entry_date, source, source_id, memo, posted_by)
SELECT 'JE-' || lpad(g::text, 6, '0'), pg_temp.rts(365)::date, src,
       CASE src WHEN 'order' THEN pg_temp.rint(1, (SELECT orders FROM k)) WHEN 'expense' THEN pg_temp.rint(1, 600) END,
       initcap(src) || ' posting', pg_temp.rint(1, 60)
FROM (SELECT g, pg_temp.pick(ARRAY['order','order','order','refund','expense','payroll','adjustment']) AS src
      FROM generate_series(1, 400) g) x ORDER BY g;

CREATE TABLE journal_lines (
    id               SERIAL PRIMARY KEY,
    journal_entry_id INT           NOT NULL REFERENCES journal_entries(id) ON DELETE CASCADE,
    gl_account_id    INT           NOT NULL REFERENCES gl_accounts(id),
    dr_amount        NUMERIC(12,2) NOT NULL DEFAULT 0,
    cr_amount        NUMERIC(12,2) NOT NULL DEFAULT 0,
    cost_center      VARCHAR(10)
);
CREATE TEMP TABLE je AS
SELECT e.id, e.source, a.amt FROM journal_entries e
CROSS JOIN LATERAL (SELECT pg_temp.rnum(20, 8000) AS amt WHERE e.id > 0) a;
INSERT INTO journal_lines (journal_entry_id, gl_account_id, dr_amount, cr_amount, cost_center)
SELECT id, dr, amt, 0, cc FROM (
  SELECT id, amt, CASE source WHEN 'order' THEN 2 WHEN 'refund' THEN 15 WHEN 'expense' THEN 23 WHEN 'payroll' THEN 20 ELSE 19 END AS dr,
         'CC' || (1 + id % 8) || '00' AS cc FROM je) x
UNION ALL
SELECT id, cr, 0, amt, NULL FROM (
  SELECT id, amt, CASE source WHEN 'order' THEN 13 WHEN 'refund' THEN 1 WHEN 'expense' THEN 6 WHEN 'payroll' THEN 1 ELSE 3 END AS cr
  FROM je) y
ORDER BY 1;

CREATE TABLE expense_categories (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(60) NOT NULL UNIQUE,
    gl_account_id INT         NOT NULL REFERENCES gl_accounts(id)
);
INSERT INTO expense_categories (name, gl_account_id)
SELECT n, g.id FROM (VALUES ('Advertising','6300'), ('Travel','6600'), ('Software','6500'), ('Rent','6100'),
  ('Utilities','6200'), ('Office Supplies','6700'), ('Freight','5100'), ('Card Fees','6400'),
  ('Contractors','6900'), ('Equipment','1500')) AS v(n, code) JOIN gl_accounts g ON g.acct_code = v.code;

CREATE TABLE expenses (
    id            SERIAL PRIMARY KEY,
    category_id   INT           NOT NULL REFERENCES expense_categories(id),
    department_id INT           NOT NULL REFERENCES departments(id),
    employee_id   INT           REFERENCES employees(id),
    vendor_name   VARCHAR(120)  NOT NULL,
    amount        NUMERIC(10,2) NOT NULL,
    currency_code CHAR(3)       NOT NULL REFERENCES currencies(code),
    incurred_on   DATE          NOT NULL,
    status        VARCHAR(20)   NOT NULL,
    receipt_url   TEXT
);
INSERT INTO expenses (category_id, department_id, employee_id, vendor_name, amount, currency_code, incurred_on, status, receipt_url)
SELECT c, pg_temp.rint(1, 8), pg_temp.rint(1, 60),
       CASE c WHEN 1 THEN pg_temp.pick(ARRAY['Google Ads','Meta Ads','TikTok Ads'])
              WHEN 2 THEN pg_temp.pick(ARRAY['Delta Air Lines','Marriott','Uber'])
              WHEN 3 THEN pg_temp.pick(ARRAY['Shopify','Slack','Atlassian','AWS','Figma'])
              WHEN 4 THEN 'Metro Properties LLC' WHEN 5 THEN 'City Power & Water'
              WHEN 6 THEN 'Staples' WHEN 7 THEN 'UPS Freight' WHEN 8 THEN 'Stripe'
              WHEN 9 THEN 'Upwork' ELSE 'Dell Technologies' END,
       CASE WHEN c IN (4, 10) THEN pg_temp.rnum(800, 12000) ELSE pg_temp.rnum(12, 2500) END,
       pg_temp.pick(ARRAY['USD','USD','USD','USD','EUR','GBP','INR']), pg_temp.rts(365)::date,
       pg_temp.pick(ARRAY['submitted','approved','approved','reimbursed','rejected']),
       CASE WHEN random() < 0.8 THEN 'https://receipts.shopcorp.example/' || md5(random()::text) || '.pdf' END
FROM (SELECT pg_temp.rint(1, 10) AS c FROM generate_series(1, 600)) x;
"""


# ══════════════════════════════════════════════
# Loyalty and gift cards
# ══════════════════════════════════════════════

LOYALTY = r"""
CREATE TABLE loyalty_tiers (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(20)  NOT NULL UNIQUE,
    min_points      INT          NOT NULL,
    earn_multiplier NUMERIC(3,2) NOT NULL,
    perks           TEXT
);
INSERT INTO loyalty_tiers (name, min_points, earn_multiplier, perks) VALUES
  ('Bronze',0,1.00,'Birthday coupon'), ('Silver',1000,1.25,'Free standard shipping'),
  ('Gold',5000,1.50,'Free express shipping, early access'), ('Platinum',15000,2.00,'Dedicated support, free returns');

CREATE TABLE loyalty_accounts (
    id              SERIAL PRIMARY KEY,
    user_id         INT         NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    tier_id         INT         NOT NULL REFERENCES loyalty_tiers(id),
    points_balance  INT         NOT NULL DEFAULT 0,
    lifetime_points INT         NOT NULL DEFAULT 0,
    joined_at       TIMESTAMPTZ NOT NULL
);
INSERT INTO loyalty_accounts (user_id, tier_id, joined_at)
SELECT u.id, 1, u.created_at FROM users u ORDER BY u.id;

CREATE TABLE loyalty_transactions (
    id         SERIAL PRIMARY KEY,
    account_id INT         NOT NULL REFERENCES loyalty_accounts(id) ON DELETE CASCADE,
    order_id   INT         REFERENCES orders(id),
    txn_type   VARCHAR(20) NOT NULL,
    points     INT         NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ
);
INSERT INTO loyalty_transactions (account_id, order_id, txn_type, points, created_at, expires_at)
SELECT a.id, o.id, 'earn', (o.total_amount * 10)::int, o.created_at, o.created_at + interval '1 year'
FROM orders o JOIN loyalty_accounts a ON a.user_id = o.user_id WHERE o.status NOT IN ('cancelled','refunded');
INSERT INTO loyalty_transactions (account_id, txn_type, points, created_at)
SELECT pg_temp.rint(1, (SELECT users FROM k)), t,
       CASE t WHEN 'redeem' THEN -pg_temp.rint(100, 1500) WHEN 'bonus' THEN pg_temp.rint(50, 500)
              WHEN 'expire' THEN -pg_temp.rint(50, 400) ELSE pg_temp.rint(10, 200) END, pg_temp.rts(365)
FROM (SELECT pg_temp.pick(ARRAY['redeem','redeem','bonus','expire','review_reward','referral']) AS t
      FROM generate_series(1, 520)) x;
UPDATE loyalty_accounts a SET lifetime_points = s.earned, points_balance = greatest(s.net, 0),
       tier_id = (SELECT max(id) FROM loyalty_tiers WHERE min_points <= s.earned)
FROM (SELECT account_id, sum(greatest(points, 0)) AS earned, sum(points) AS net
      FROM loyalty_transactions GROUP BY account_id) s WHERE s.account_id = a.id;

CREATE TABLE gift_cards (
    id                   SERIAL PRIMARY KEY,
    code                 VARCHAR(20)   NOT NULL UNIQUE,
    initial_value        NUMERIC(10,2) NOT NULL,
    balance              NUMERIC(10,2) NOT NULL,
    currency_code        CHAR(3)       NOT NULL REFERENCES currencies(code),
    purchased_by_user_id INT           REFERENCES users(id),
    recipient_email      VARCHAR(255),
    status               VARCHAR(20)   NOT NULL,
    issued_at            TIMESTAMPTZ   NOT NULL,
    expires_at           TIMESTAMPTZ
);
INSERT INTO gift_cards (code, initial_value, balance, currency_code, purchased_by_user_id, recipient_email, status, issued_at, expires_at)
SELECT 'GC-' || upper(substr(md5(g::text || random()::text), 1, 10)), v,
       CASE st WHEN 'active' THEN round(v * random()::numeric, 2) WHEN 'redeemed' THEN 0 ELSE v END,
       'USD', pg_temp.rint(1, (SELECT users FROM k)), 'friend' || g || '@example.com', st, iss, iss + interval '2 years'
FROM (SELECT g, pg_temp.pick(ARRAY['25','50','50','100','200'])::numeric AS v,
             pg_temp.pick(ARRAY['active','active','redeemed','expired','disabled']) AS st, pg_temp.rts(700) AS iss
      FROM generate_series(1, 50) g) x;
"""


# ══════════════════════════════════════════════
# Customers, sessions and support
# ══════════════════════════════════════════════

CUSTOMERS = r"""
CREATE TABLE customer_segments (
    id               SERIAL PRIMARY KEY,
    name             VARCHAR(60) NOT NULL UNIQUE,
    rule_description TEXT        NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL
);
INSERT INTO customer_segments (name, rule_description, created_at) VALUES
  ('VIP','Lifetime spend over $2,000','2025-01-10'), ('At Risk','No order in the last 120 days','2025-02-01'),
  ('New Customers','First order in the last 30 days','2025-02-01'), ('Bargain Hunters','Used 2+ coupons','2025-03-15'),
  ('Jewelry Lovers','Bought jewelry twice or more','2025-04-20'), ('Gamers','Bought electronics tagged gaming','2025-05-05');

CREATE TABLE segment_members (
    segment_id INT         NOT NULL REFERENCES customer_segments(id) ON DELETE CASCADE,
    user_id    INT         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    added_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (segment_id, user_id)
);
INSERT INTO segment_members SELECT pg_temp.rint(1, 6), pg_temp.rint(1, (SELECT users FROM k)), pg_temp.rts(300)
FROM generate_series(1, 100) ON CONFLICT DO NOTHING;

CREATE TABLE user_sessions (
    id            SERIAL PRIMARY KEY,
    user_id       INT         REFERENCES users(id),
    session_token CHAR(32)    NOT NULL UNIQUE,
    device_type   VARCHAR(20) NOT NULL,
    browser       VARCHAR(30),
    ip_address    INET,
    country_id    INT         REFERENCES countries(id),
    started_at    TIMESTAMPTZ NOT NULL,
    ended_at      TIMESTAMPTZ
);
INSERT INTO user_sessions (user_id, session_token, device_type, browser, ip_address, country_id, started_at, ended_at)
SELECT CASE WHEN random() < 0.65 THEN pg_temp.rint(1, (SELECT users FROM k)) END, md5(g::text || random()::text),
       pg_temp.pick(ARRAY['desktop','mobile','mobile','tablet']), pg_temp.pick(ARRAY['Chrome','Safari','Firefox','Edge','Samsung Internet']),
       (pg_temp.rint(11, 223) || '.' || pg_temp.rint(0, 255) || '.' || pg_temp.rint(0, 255) || '.' || pg_temp.rint(1, 254))::inet,
       CASE WHEN random() < 0.6 THEN 1 ELSE pg_temp.rint(1, 15) END, s, s + pg_temp.rint(1, 90) * interval '1 minute'
FROM (SELECT g, pg_temp.rts(365) AS s FROM generate_series(1, 6000) g) x;

CREATE TABLE user_preferences (
    user_id          INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    language         VARCHAR(5)  NOT NULL DEFAULT 'en',
    currency_code    CHAR(3)     NOT NULL REFERENCES currencies(code) DEFAULT 'USD',
    timezone         VARCHAR(40) NOT NULL DEFAULT 'America/New_York',
    marketing_opt_in BOOLEAN     NOT NULL DEFAULT FALSE,
    theme            VARCHAR(10) NOT NULL DEFAULT 'system'
);
INSERT INTO user_preferences
SELECT u.id, pg_temp.pick(ARRAY['en','en','en','es','fr','de','hi']), pg_temp.pick(ARRAY['USD','USD','USD','EUR','GBP','INR']),
       pg_temp.pick(ARRAY['America/New_York','America/Chicago','America/Los_Angeles','Europe/London','Asia/Kolkata']),
       random() < 0.55, pg_temp.pick(ARRAY['light','dark','system'])
FROM users u;

CREATE TABLE newsletter_subscriptions (
    id              SERIAL PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    user_id         INT          REFERENCES users(id),
    source          VARCHAR(30)  NOT NULL,
    subscribed_at   TIMESTAMPTZ  NOT NULL,
    unsubscribed_at TIMESTAMPTZ
);
INSERT INTO newsletter_subscriptions (email, user_id, source, subscribed_at, unsubscribed_at)
SELECT u.email, u.id, pg_temp.pick(ARRAY['checkout','footer_form','popup','account_settings']), u.created_at,
       CASE WHEN random() < 0.15 THEN u.created_at + interval '90 days' END
FROM users u WHERE random() < 0.75;
INSERT INTO newsletter_subscriptions (email, source, subscribed_at)
SELECT 'subscriber' || g || '@example.org', pg_temp.pick(ARRAY['footer_form','popup','instagram_giveaway']), pg_temp.rts(500)
FROM generate_series(1, 40) g;

CREATE TABLE support_agents (
    id               SERIAL PRIMARY KEY,
    employee_id      INT         NOT NULL UNIQUE REFERENCES employees(id),
    team             VARCHAR(30) NOT NULL,
    languages        VARCHAR(40) NOT NULL DEFAULT 'en',
    max_open_tickets SMALLINT    NOT NULL DEFAULT 25
);
INSERT INTO support_agents (employee_id, team, languages)
SELECT e.id, pg_temp.pick(ARRAY['orders','returns','technical','vip']), pg_temp.pick(ARRAY['en','en,es','en,fr','en,hi'])
FROM employees e WHERE e.department_id = 2 ORDER BY e.id;

CREATE TABLE support_tickets (
    id                SERIAL PRIMARY KEY,
    user_id           INT          NOT NULL REFERENCES users(id),
    order_id          INT          REFERENCES orders(id),
    agent_id          INT          REFERENCES support_agents(id),
    subject           VARCHAR(200) NOT NULL,
    category          VARCHAR(30)  NOT NULL,
    priority          VARCHAR(10)  NOT NULL,
    status            VARCHAR(20)  NOT NULL,
    channel           VARCHAR(20)  NOT NULL,
    opened_at         TIMESTAMPTZ  NOT NULL,
    first_response_at TIMESTAMPTZ,
    resolved_at       TIMESTAMPTZ,
    csat_score        SMALLINT     CHECK (csat_score BETWEEN 1 AND 5)
);
INSERT INTO support_tickets (user_id, order_id, agent_id, subject, category, priority, status, channel, opened_at,
                             first_response_at, resolved_at, csat_score)
SELECT o.user_id, o.id, pg_temp.rint(1, (SELECT count(*)::int FROM support_agents)),
       CASE cat WHEN 'shipping' THEN 'Where is my order #' || o.id || '?' WHEN 'return' THEN 'Return request for order #' || o.id
                WHEN 'payment' THEN 'Charged twice for order #' || o.id WHEN 'product' THEN 'Question about an item I bought'
                ELSE 'Problem logging in to my account' END,
       cat, pg_temp.pick(ARRAY['low','normal','normal','high','urgent']), st,
       pg_temp.pick(ARRAY['email','chat','chat','phone','social']), op,
       op + pg_temp.rint(5, 600) * interval '1 minute',
       CASE WHEN st IN ('resolved','closed') THEN op + pg_temp.rint(1, 96) * interval '1 hour' END,
       CASE WHEN st IN ('resolved','closed') AND random() < 0.7 THEN pg_temp.rint(1, 5) END
FROM (SELECT pg_temp.rint(1, (SELECT orders FROM k)) AS oid,
             pg_temp.pick(ARRAY['shipping','shipping','return','payment','product','account']) AS cat,
             pg_temp.pick(ARRAY['open','pending','resolved','resolved','closed']) AS st, pg_temp.rts(365) AS op
      FROM generate_series(1, 120)) x JOIN orders o ON o.id = x.oid;

CREATE TABLE ticket_messages (
    id              SERIAL PRIMARY KEY,
    ticket_id       INT         NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,
    sender_type     VARCHAR(10) NOT NULL,
    sender_agent_id INT         REFERENCES support_agents(id),
    body            TEXT        NOT NULL,
    is_internal     BOOLEAN     NOT NULL DEFAULT FALSE,
    sent_at         TIMESTAMPTZ NOT NULL
);
INSERT INTO ticket_messages (ticket_id, sender_type, sender_agent_id, body, is_internal, sent_at)
SELECT t.id, CASE WHEN n % 2 = 1 THEN 'customer' ELSE 'agent' END, CASE WHEN n % 2 = 0 THEN t.agent_id END,
       CASE WHEN n % 2 = 1 THEN pg_temp.pick(ARRAY['Hi, any update on this?','The tracking has not moved in days.',
              'I would like a refund please.','Thanks, that worked!','Can you check again?'])
            ELSE pg_temp.pick(ARRAY['Thanks for reaching out, I am looking into it.','I have issued a replacement.',
              'Your refund has been processed.','Could you share a photo of the item?']) END,
       n % 2 = 0 AND random() < 0.1, t.opened_at + (n - 1) * interval '5 hours'
FROM support_tickets t CROSS JOIN LATERAL generate_series(1, pg_temp.rint(2, 7) + 0 * t.id) n
ORDER BY t.id, n;
"""


# ══════════════════════════════════════════════
# Marketing
# ══════════════════════════════════════════════

MARKETING = r"""
CREATE TABLE campaigns (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(120)  NOT NULL,
    channel           VARCHAR(20)   NOT NULL,
    objective         VARCHAR(30)   NOT NULL,
    start_date        DATE          NOT NULL,
    end_date          DATE,
    budget            NUMERIC(12,2),
    currency_code     CHAR(3)       NOT NULL REFERENCES currencies(code) DEFAULT 'USD',
    status            VARCHAR(20)   NOT NULL,
    owner_employee_id INT           REFERENCES employees(id)
);
INSERT INTO campaigns (name, channel, objective, start_date, end_date, budget, status, owner_employee_id)
SELECT c.name, c.channel, c.objective, c.start::date, c.start::date + c.days, c.budget,
       CASE WHEN c.start::date + c.days < date '2026-10-10' THEN 'completed' ELSE 'running' END, pg_temp.rint(1, 60)
FROM (VALUES ('Spring Sale Email Blast','email','conversion','2026-03-15',14,5000),
  ('Black Friday 2025','email','conversion','2025-11-24',8,25000), ('Holiday Gift Guide','social','awareness','2025-11-15',40,18000),
  ('Back to School','search','conversion','2026-08-01',30,12000), ('Summer Essentials Launch','social','awareness','2026-05-01',60,15000),
  ('Win-back At Risk Customers','email','retention','2026-02-01',30,2000), ('Gaming Monitor Promo','search','conversion','2026-06-10',21,8000),
  ('Jewelry Valentine''s Day','email','conversion','2026-02-01',14,6000), ('Influencer Unboxing Series','social','awareness','2026-04-01',90,22000),
  ('Cart Abandonment Flow','email','conversion','2025-10-15',365,3000), ('Welcome Series','email','retention','2025-10-15',365,1500),
  ('Prime Day Counter-Sale','search','conversion','2026-07-08',4,9000), ('Earth Day Eco Picks','social','awareness','2026-04-18',7,2500),
  ('Loyalty Double Points Week','email','retention','2026-09-01',7,1000), ('Retargeting Always-On','display','conversion','2025-10-15',365,30000),
  ('Fall Outerwear','social','conversion','2026-09-15',45,11000), ('Cyber Monday 2025','email','conversion','2025-12-01',2,7000),
  ('New Year New Gear','search','conversion','2026-01-01',21,6500), ('Referral Program Push','email','acquisition','2026-03-01',60,3500),
  ('Podcast Sponsorship','audio','awareness','2026-05-15',90,14000)
) AS c(name, channel, objective, start, days, budget);

CREATE TABLE email_sends (
    id            SERIAL PRIMARY KEY,
    campaign_id   INT          NOT NULL REFERENCES campaigns(id),
    user_id       INT          NOT NULL REFERENCES users(id),
    template_code VARCHAR(40)  NOT NULL,
    subject_line  VARCHAR(200) NOT NULL,
    sent_at       TIMESTAMPTZ  NOT NULL
);
INSERT INTO email_sends (campaign_id, user_id, template_code, subject_line, sent_at)
SELECT c.id, pg_temp.rint(1, (SELECT users FROM k)), 'tpl_' || c.id || '_' || pg_temp.rint(1, 3),
       c.name || pg_temp.pick(ARRAY[': don''t miss out',' starts now',': last chance',' – just for you']),
       c.start_date + random() * (coalesce(c.end_date, c.start_date + 30) - c.start_date) * interval '1 day'
FROM (SELECT pg_temp.pick(ARRAY['1','2','6','8','10','11','14','17','19']) ::int AS cid FROM generate_series(1, 4000)) x
JOIN campaigns c ON c.id = x.cid;

CREATE TABLE email_events (
    id            SERIAL PRIMARY KEY,
    email_send_id INT         NOT NULL REFERENCES email_sends(id) ON DELETE CASCADE,
    event_type    VARCHAR(20) NOT NULL,
    link_url      TEXT,
    occurred_at   TIMESTAMPTZ NOT NULL
);
INSERT INTO email_events (email_send_id, event_type, link_url, occurred_at)
SELECT s.id, e.ev, CASE WHEN e.ev = 'clicked' THEN 'https://shopcorp.example/products/' || pg_temp.rint(1, (SELECT products FROM k)) END,
       s.sent_at + e.delay * interval '1 minute'
FROM email_sends s CROSS JOIN LATERAL (VALUES
  ('delivered', random() < 0.96 AND s.id > 0, 1), ('opened', random() < 0.42 AND s.id > 0, 95),
  ('clicked', random() < 0.11 AND s.id > 0, 110), ('unsubscribed', random() < 0.006 AND s.id > 0, 120),
  ('bounced', random() < 0.03 AND s.id > 0, 2)) AS e(ev, keep, delay)
WHERE e.keep ORDER BY s.id, e.delay;

CREATE TABLE affiliates (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(120) NOT NULL,
    website        TEXT,
    contact_email  VARCHAR(255) NOT NULL,
    commission_pct NUMERIC(4,2) NOT NULL,
    status         VARCHAR(20)  NOT NULL,
    joined_at      DATE         NOT NULL
);
INSERT INTO affiliates (name, website, contact_email, commission_pct, status, joined_at)
SELECT a, 'https://' || lower(replace(a, ' ', '')) || '.example', 'partners@' || lower(replace(a, ' ', '')) || '.example',
       pg_temp.pick(ARRAY['4','5','6','8','10'])::numeric, pg_temp.pick(ARRAY['active','active','active','paused']),
       pg_temp.rts(900)::date
FROM unnest(ARRAY['TechDeals Daily','Style Scout','Gear Guru','The Budget Shopper','Sparkle Reviews',
  'Gamer Den','Outdoor Life Blog','Coupon Cabin','Deal Radar','Gift Hunters','Minimal Wardrobe','PC Builders Hub']) AS a;

CREATE TABLE affiliate_clicks (
    id           SERIAL PRIMARY KEY,
    affiliate_id INT         NOT NULL REFERENCES affiliates(id),
    session_id   INT         REFERENCES user_sessions(id),
    product_id   INT         REFERENCES products(id),
    landing_url  TEXT        NOT NULL,
    converted    BOOLEAN     NOT NULL DEFAULT FALSE,
    clicked_at   TIMESTAMPTZ NOT NULL
);
INSERT INTO affiliate_clicks (affiliate_id, session_id, product_id, landing_url, converted, clicked_at)
SELECT pg_temp.rint(1, 12), s.id, pid, 'https://shopcorp.example/products/' || pid || '?ref=aff', random() < 0.03, s.started_at
FROM (SELECT pg_temp.rint(1, 6000) AS sid, pg_temp.rint(1, (SELECT products FROM k)) AS pid FROM generate_series(1, 8000)) x
JOIN user_sessions s ON s.id = x.sid;

CREATE TABLE affiliate_commissions (
    id           SERIAL PRIMARY KEY,
    affiliate_id INT           NOT NULL REFERENCES affiliates(id),
    order_id     INT           NOT NULL UNIQUE REFERENCES orders(id),
    amount       NUMERIC(10,2) NOT NULL,
    status       VARCHAR(20)   NOT NULL,
    payable_on   DATE          NOT NULL
);
INSERT INTO affiliate_commissions (affiliate_id, order_id, amount, status, payable_on)
SELECT a.id, o.id, round(o.subtotal * a.commission_pct / 100, 2),
       CASE WHEN o.status IN ('cancelled','refunded') THEN 'reversed' ELSE pg_temp.pick(ARRAY['pending','approved','paid','paid']) END,
       (o.created_at + interval '45 days')::date
FROM (SELECT o.id AS oid, pg_temp.rint(1, 12) AS aid FROM orders o WHERE random() < 0.3) x
JOIN orders o ON o.id = x.oid JOIN affiliates a ON a.id = x.aid ORDER BY o.id;

CREATE TABLE promotions (
    id           SERIAL PRIMARY KEY,
    campaign_id  INT          REFERENCES campaigns(id),
    name         VARCHAR(120) NOT NULL,
    promo_type   VARCHAR(20)  NOT NULL,
    discount_pct NUMERIC(5,2),
    starts_at    TIMESTAMPTZ  NOT NULL,
    ends_at      TIMESTAMPTZ  NOT NULL,
    is_active    BOOLEAN      NOT NULL
);
INSERT INTO promotions (campaign_id, name, promo_type, discount_pct, starts_at, ends_at, is_active)
SELECT c.id, c.name || ' – ' || t, t, CASE WHEN t = 'percent_off' THEN pg_temp.pick(ARRAY['10','15','20','25','30'])::numeric END,
       c.start_date, coalesce(c.end_date, c.start_date + 30), c.status = 'running'
FROM campaigns c CROSS JOIN LATERAL (SELECT pg_temp.pick(ARRAY['percent_off','percent_off','bogo','free_shipping']) AS t
                                     WHERE c.id > 0) tt
WHERE c.objective = 'conversion' ORDER BY c.id;

CREATE TABLE promotion_products (
    promotion_id INT NOT NULL REFERENCES promotions(id) ON DELETE CASCADE,
    product_id   INT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    PRIMARY KEY (promotion_id, product_id)
);
INSERT INTO promotion_products SELECT p.id, pg_temp.rint(1, (SELECT products FROM k))
FROM promotions p CROSS JOIN generate_series(1, 4) ON CONFLICT DO NOTHING;
"""


# ══════════════════════════════════════════════
# Web analytics and experiments
# ══════════════════════════════════════════════

ANALYTICS = r"""
CREATE TABLE page_views (
    id          BIGSERIAL PRIMARY KEY,
    session_id  INT          NOT NULL REFERENCES user_sessions(id),
    user_id     INT          REFERENCES users(id),
    url_path    VARCHAR(200) NOT NULL,
    referrer    TEXT,
    duration_ms INT,
    viewed_at   TIMESTAMPTZ  NOT NULL
);
INSERT INTO page_views (session_id, user_id, url_path, referrer, duration_ms, viewed_at)
SELECT s.id, s.user_id, path,
       pg_temp.pick(ARRAY['https://www.google.com/','https://www.instagram.com/','https://www.facebook.com/',
                          'https://www.bing.com/', NULL, NULL, NULL]),
       pg_temp.rint(800, 180000), s.started_at + random() * (coalesce(s.ended_at, s.started_at + interval '10 minutes') - s.started_at)
FROM (SELECT pg_temp.rint(1, 6000) AS sid,
             pg_temp.pick(ARRAY['/','/','/products','/products/' || pg_temp.rint(1, (SELECT products FROM k)),
               '/products/' || pg_temp.rint(1, (SELECT products FROM k)), '/categories/electronics', '/categories/jewelery',
               '/categories/mens-clothing', '/categories/womens-clothing', '/cart', '/checkout', '/account',
               '/account/orders', '/search', '/help/returns', '/collections/summer-essentials']) AS path
      FROM generate_series(1, 100000)) x
JOIN user_sessions s ON s.id = x.sid;

CREATE TABLE product_views (
    id         SERIAL PRIMARY KEY,
    session_id INT         NOT NULL REFERENCES user_sessions(id),
    product_id INT         NOT NULL REFERENCES products(id),
    variant_id INT         REFERENCES product_variants(id),
    source     VARCHAR(20) NOT NULL,
    viewed_at  TIMESTAMPTZ NOT NULL
);
INSERT INTO product_views (session_id, product_id, variant_id, source, viewed_at)
SELECT s.id, pid, CASE WHEN random() < 0.4 THEN (pid - 1) * 4 + pg_temp.rint(1, 4) END,
       pg_temp.pick(ARRAY['search','category','recommendation','email','ad','direct']), s.started_at + random() * interval '10 minutes'
FROM (SELECT pg_temp.rint(1, 6000) AS sid, pg_temp.rint(1, (SELECT products FROM k)) AS pid FROM generate_series(1, 30000)) x
JOIN user_sessions s ON s.id = x.sid;

CREATE TABLE search_queries (
    id                 SERIAL PRIMARY KEY,
    session_id         INT          NOT NULL REFERENCES user_sessions(id),
    user_id            INT          REFERENCES users(id),
    query_text         VARCHAR(200) NOT NULL,
    results_count      INT          NOT NULL,
    clicked_product_id INT          REFERENCES products(id),
    searched_at        TIMESTAMPTZ  NOT NULL
);
INSERT INTO search_queries (session_id, user_id, query_text, results_count, clicked_product_id, searched_at)
SELECT s.id, s.user_id, q, CASE WHEN q IN ('vr headset','air fryer','iphone case') THEN 0 ELSE pg_temp.rint(1, 40) END,
       CASE WHEN random() < 0.55 AND q NOT IN ('vr headset','air fryer','iphone case')
            THEN pg_temp.rint(1, (SELECT products FROM k)) END, s.started_at + random() * interval '5 minutes'
FROM (SELECT pg_temp.rint(1, 6000) AS sid,
             pg_temp.pick(ARRAY['backpack','gold bracelet','gaming monitor','ssd 1tb','rain jacket','womens t-shirt',
               'mens jacket','ring','hard drive','usb drive','silver ring','curved monitor','cotton shirt','gift for her',
               'external hard drive','jacket','monitor','bracelet','vr headset','air fryer','iphone case','slim fit',
               'snow jacket','sale','new arrivals']) AS q
      FROM generate_series(1, 6000)) x
JOIN user_sessions s ON s.id = x.sid;

CREATE TABLE ab_tests (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(120) NOT NULL UNIQUE,
    hypothesis     TEXT,
    primary_metric VARCHAR(40)  NOT NULL,
    status         VARCHAR(20)  NOT NULL,
    started_at     TIMESTAMPTZ  NOT NULL,
    ended_at       TIMESTAMPTZ
);
INSERT INTO ab_tests (name, hypothesis, primary_metric, status, started_at, ended_at) VALUES
  ('checkout_one_page','A single-page checkout raises conversion','checkout_conversion','completed','2026-01-10','2026-02-10'),
  ('free_ship_banner','Showing the free-shipping threshold raises AOV','avg_order_value','completed','2026-03-01','2026-03-31'),
  ('pdp_reviews_top','Reviews above the fold raise add-to-cart','add_to_cart_rate','running','2026-09-01',NULL),
  ('search_autocomplete_v2','New autocomplete raises search CTR','search_ctr','running','2026-09-15',NULL),
  ('homepage_hero_video','A hero video raises engagement','bounce_rate','stopped','2026-05-01','2026-05-09');

CREATE TABLE ab_test_variants (
    id          SERIAL PRIMARY KEY,
    test_id     INT          NOT NULL REFERENCES ab_tests(id) ON DELETE CASCADE,
    variant_key VARCHAR(20)  NOT NULL,
    traffic_pct NUMERIC(5,2) NOT NULL,
    is_control  BOOLEAN      NOT NULL,
    UNIQUE (test_id, variant_key)
);
INSERT INTO ab_test_variants (test_id, variant_key, traffic_pct, is_control)
SELECT t.id, v.key, CASE WHEN t.id = 3 THEN 33.33 ELSE 50 END, v.key = 'control'
FROM ab_tests t CROSS JOIN (VALUES ('control'), ('treatment'), ('treatment_b')) AS v(key)
WHERE v.key <> 'treatment_b' OR t.id = 3 ORDER BY t.id, v.key;

-- written by the experiment SDK, hence the camelCase columns
CREATE TABLE ab_test_assignments (
    id           SERIAL PRIMARY KEY,
    test_id      INT         NOT NULL REFERENCES ab_tests(id) ON DELETE CASCADE,
    "variantId"  INT         NOT NULL REFERENCES ab_test_variants(id),
    session_id   INT         NOT NULL REFERENCES user_sessions(id),
    "assignedAt" TIMESTAMPTZ NOT NULL,
    converted    BOOLEAN     NOT NULL DEFAULT FALSE
);
INSERT INTO ab_test_assignments (test_id, "variantId", session_id, "assignedAt", converted)
SELECT x.tid, (SELECT v.id FROM ab_test_variants v WHERE v.test_id = x.tid ORDER BY random() + x.g * 0 LIMIT 1),
       x.sid, s.started_at, random() < 0.06
FROM (SELECT g, pg_temp.rint(1, 5) AS tid, pg_temp.rint(1, 6000) AS sid FROM generate_series(1, 2000) g) x
JOIN user_sessions s ON s.id = x.sid;
"""


# ══════════════════════════════════════════════
# Physical stores and point of sale
# ══════════════════════════════════════════════

STORES = r"""
CREATE TABLE store_inventory (
    store_id      INT NOT NULL REFERENCES stores(id),
    variant_id    INT NOT NULL REFERENCES product_variants(id),
    qty_on_hand   INT NOT NULL DEFAULT 0,
    reorder_point INT NOT NULL DEFAULT 5,
    PRIMARY KEY (store_id, variant_id)
);
INSERT INTO store_inventory SELECT s.id, v.id, pg_temp.rint(0, 40), pg_temp.pick(ARRAY['3','5','8'])::int
FROM stores s CROSS JOIN product_variants v ORDER BY s.id, v.id;

CREATE TABLE pos_terminals (
    id           SERIAL PRIMARY KEY,
    store_id     INT         NOT NULL REFERENCES stores(id),
    serial_no    VARCHAR(30) NOT NULL UNIQUE,
    model        VARCHAR(40) NOT NULL,
    status       VARCHAR(20) NOT NULL,
    installed_at DATE        NOT NULL
);
INSERT INTO pos_terminals (store_id, serial_no, model, status, installed_at)
SELECT s.id, 'POS-' || s.id || '-' || n || '-' || pg_temp.rint(10000, 99999),
       pg_temp.pick(ARRAY['Verifone M400','Square Register','Clover Station']),
       CASE WHEN NOT s.is_open THEN 'retired' WHEN n = 3 AND random() < 0.3 THEN 'maintenance' ELSE 'active' END,
       s.opened_on + n
FROM stores s CROSS JOIN generate_series(1, 3) n ORDER BY s.id, n;

-- in-store sales (online sales are in `orders`)
CREATE TABLE pos_transactions (
    id           SERIAL PRIMARY KEY,
    terminal_id  INT           NOT NULL REFERENCES pos_terminals(id),
    employee_id  INT           REFERENCES employees(id),
    user_id      INT           REFERENCES users(id),
    txn_ts       TIMESTAMPTZ   NOT NULL,
    payment_type VARCHAR(20)   NOT NULL,
    tot_amt      NUMERIC(10,2) NOT NULL DEFAULT 0,
    tax_amt      NUMERIC(10,2) NOT NULL DEFAULT 0,
    status       VARCHAR(20)   NOT NULL
);
INSERT INTO pos_transactions (terminal_id, employee_id, user_id, txn_ts, payment_type, status)
SELECT t, (SELECT e.id FROM employees e WHERE e.store_id = (t - 1) / 3 + 1 ORDER BY random() + g * 0 LIMIT 1),
       CASE WHEN random() < 0.2 THEN pg_temp.rint(1, (SELECT users FROM k)) END,
       pg_temp.rts(365), pg_temp.pick(ARRAY['card','card','card','cash','mobile_wallet','gift_card']),
       pg_temp.pick(ARRAY['completed','completed','completed','completed','completed','voided','refunded'])
FROM (SELECT g, pg_temp.rint(1, 12) AS t FROM generate_series(1, 5000) g) x;

CREATE TABLE pos_transaction_items (
    id                 SERIAL PRIMARY KEY,
    pos_transaction_id INT           NOT NULL REFERENCES pos_transactions(id) ON DELETE CASCADE,
    variant_id         INT           NOT NULL REFERENCES product_variants(id),
    qty                INT           NOT NULL,
    unit_price         NUMERIC(10,2) NOT NULL,
    discount           NUMERIC(10,2) NOT NULL DEFAULT 0
);
INSERT INTO pos_transaction_items (pos_transaction_id, variant_id, qty, unit_price, discount)
SELECT x.tid, v.id, x.q, p.price + v.price_delta, CASE WHEN random() < 0.15 THEN round((p.price + v.price_delta) * 0.1, 2) ELSE 0 END
FROM (SELECT t.id AS tid, pg_temp.rint(1, (SELECT products FROM k) * 4) AS vid, pg_temp.rint(1, 3) AS q, n
      FROM pos_transactions t CROSS JOIN LATERAL generate_series(1, pg_temp.rint(1, 4) + 0 * t.id) n) x
JOIN product_variants v ON v.id = x.vid JOIN products p ON p.id = v.product_id
ORDER BY x.tid, x.n;
UPDATE pos_transactions t SET tot_amt = round(s.net * 1.08, 2), tax_amt = round(s.net * 0.08, 2)
FROM (SELECT pos_transaction_id, sum(qty * unit_price - discount) AS net FROM pos_transaction_items
      GROUP BY pos_transaction_id) s WHERE s.pos_transaction_id = t.id;
"""


# ══════════════════════════════════════════════
# Reviews, notifications, audit
# ══════════════════════════════════════════════

MISC = r"""
CREATE TABLE review_votes (
    id         SERIAL PRIMARY KEY,
    review_id  INT         NOT NULL REFERENCES product_reviews(id) ON DELETE CASCADE,
    user_id    INT         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_helpful BOOLEAN     NOT NULL,
    voted_at   TIMESTAMPTZ NOT NULL,
    UNIQUE (review_id, user_id)
);
INSERT INTO review_votes (review_id, user_id, is_helpful, voted_at)
SELECT pg_temp.rint(1, (SELECT reviews FROM k)), pg_temp.rint(1, (SELECT users FROM k)), random() < 0.8, pg_temp.rts(300)
FROM generate_series(1, 320) ON CONFLICT DO NOTHING;

CREATE TABLE review_images (
    id          SERIAL PRIMARY KEY,
    review_id   INT         NOT NULL REFERENCES product_reviews(id) ON DELETE CASCADE,
    url         TEXT        NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL
);
INSERT INTO review_images (review_id, url, uploaded_at)
SELECT r.id, 'https://cdn.shopcorp.example/reviews/' || r.id || '_' || n || '.jpg', r.created_at
FROM product_reviews r CROSS JOIN generate_series(1, 2) n WHERE (r.id + n) % 3 = 0 ORDER BY r.id, n;

CREATE TABLE notifications (
    id      SERIAL PRIMARY KEY,
    user_id INT          NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type    VARCHAR(30)  NOT NULL,
    channel VARCHAR(10)  NOT NULL,
    title   VARCHAR(200) NOT NULL,
    sent_at TIMESTAMPTZ  NOT NULL,
    read_at TIMESTAMPTZ
);
INSERT INTO notifications (user_id, type, channel, title, sent_at, read_at)
SELECT pg_temp.rint(1, (SELECT users FROM k)), t, pg_temp.pick(ARRAY['email','push','sms','in_app']),
       CASE t WHEN 'order_shipped' THEN 'Your order is on its way' WHEN 'order_delivered' THEN 'Your order was delivered'
              WHEN 'price_drop' THEN 'A wishlist item dropped in price' WHEN 'back_in_stock' THEN 'An item you wanted is back'
              WHEN 'points_expiring' THEN 'Your loyalty points expire soon' ELSE 'New offers picked for you' END,
       sent, CASE WHEN random() < 0.55 THEN sent + random() * interval '2 days' END
FROM (SELECT pg_temp.pick(ARRAY['order_shipped','order_delivered','price_drop','back_in_stock','points_expiring',
                                'promotion']) AS t, pg_temp.rts(365) AS sent FROM generate_series(1, 3000)) x;

CREATE TABLE audit_log (
    id             BIGSERIAL PRIMARY KEY,
    actor_type     VARCHAR(10) NOT NULL,
    actor_id       INT,
    action         VARCHAR(20) NOT NULL,
    entity_type    VARCHAR(30) NOT NULL,
    entity_id      INT,
    changed_fields JSONB,
    ip_address     INET,
    occurred_at    TIMESTAMPTZ NOT NULL
);
INSERT INTO audit_log (actor_type, actor_id, action, entity_type, entity_id, changed_fields, ip_address, occurred_at)
SELECT actor, CASE actor WHEN 'employee' THEN pg_temp.rint(1, 60) WHEN 'user' THEN pg_temp.rint(1, (SELECT users FROM k)) END,
       act, ent, pg_temp.rint(1, 500),
       CASE WHEN act = 'update' THEN jsonb_build_object(
         CASE ent WHEN 'order' THEN 'status' WHEN 'product' THEN 'price' WHEN 'user' THEN 'email'
                  WHEN 'inventory_level' THEN 'qty_on_hand' ELSE 'is_active' END,
         jsonb_build_object('old', pg_temp.rint(1, 100), 'new', pg_temp.rint(1, 100))) END,
       ('10.0.' || pg_temp.rint(0, 255) || '.' || pg_temp.rint(1, 254))::inet, pg_temp.rts(365)
FROM (SELECT pg_temp.pick(ARRAY['employee','employee','user','system']) AS actor,
             pg_temp.pick(ARRAY['create','update','update','update','delete','login','export']) AS act,
             pg_temp.pick(ARRAY['order','product','user','coupon','inventory_level','refund','gift_card']) AS ent
      FROM generate_series(1, 10000)) x;
"""

SECTIONS = [
    ("reference data", REFERENCE), ("organisation", ORGANISATION), ("catalog", CATALOG),
    ("inventory and suppliers", INVENTORY), ("shipping", SHIPPING), ("orders", ORDERS),
    ("finance", FINANCE), ("loyalty", LOYALTY), ("customers and support", CUSTOMERS),
    ("marketing", MARKETING), ("analytics", ANALYTICS), ("stores and POS", STORES), ("misc", MISC),
]


# ══════════════════════════════════════════════
# Steps
# ══════════════════════════════════════════════

def recreate_database(target: str) -> None:
    """Drop and create the target database (it is generated, never edited by hand)."""
    conn = psycopg2.connect(db_url(SOURCE_URL, "postgres"))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()", (target,))
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(target)))
        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(target)))
    conn.close()


def copy_shop(src, dst) -> None:
    """The 9 shop tables with the same DDL, rows and sequence positions."""
    with dst.cursor() as cur:
        cur.execute(SHOP_DDL)
        for table in SHOP_TABLES:
            buf = io.StringIO()
            with src.cursor() as scur:
                scur.copy_expert(f"COPY {table} TO STDOUT", buf)
            buf.seek(0)
            cur.copy_expert(f"COPY {table} FROM STDIN", buf)
            cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                        f"(SELECT coalesce(max(id), 1) FROM {table}))")
            cur.execute(f"SELECT count(*) FROM {table}")
            print(f"   {table:<16} {cur.fetchone()[0]:>7,} rows")
    dst.commit()


def print_summary(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("ANALYZE")
        cur.execute("""
            SELECT count(*), sum(n_live_tup) FROM pg_stat_user_tables WHERE schemaname = 'public'
        """)
        tables, rows = cur.fetchone()
        cur.execute("""
            SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public'
            ORDER BY n_live_tup DESC LIMIT 8
        """)
        biggest = cur.fetchall()
    print(f"\n📊 {TARGET_DB}: {tables} tables, ~{int(rows):,} rows")
    for name, n in biggest:
        print(f"   {name:<24} {n:>8,}")


def main() -> None:
    target_url = db_url(SOURCE_URL, TARGET_DB)
    print(f"🔌 Source: {SOURCE_URL.rsplit('@', 1)[-1]}  →  target database '{TARGET_DB}'")
    try:
        src = psycopg2.connect(SOURCE_URL)
    except Exception as exc:
        print(f"✗ Cannot connect to the shop database ({exc}). Seed it first: python seed_shop.py")
        sys.exit(1)

    started = time.perf_counter()
    print(f"\n🗑️  Recreating database '{TARGET_DB}' …")
    recreate_database(TARGET_DB)
    dst = psycopg2.connect(target_url)
    try:
        print("\n📋 Copying the shop tables …")
        copy_shop(src, dst)
        with dst.cursor() as cur:
            cur.execute(HELPERS)
            for name, block in SECTIONS:
                t = time.perf_counter()
                cur.execute(block)
                dst.commit()
                print(f"   ✓ {name:<24} {time.perf_counter() - t:5.1f}s")
        print_summary(dst)
        print(f"\n✅ Done in {time.perf_counter() - started:.0f}s. Add it in the app as a connection "
              f"to database '{TARGET_DB}' (same host and login as shop).")
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
