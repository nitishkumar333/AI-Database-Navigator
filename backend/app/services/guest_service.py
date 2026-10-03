"""
Guest User Service
==================
Handles the creation of guest demo user accounts with preloaded database connection
(PostgreSQL "shop" database) and realistic mock conversation history.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.user import User
from app.models.connection import DBConnection
from app.models.knowledge import KnowledgeBase
from app.models.conversation import Conversation, ConversationMessage
from app.models.query_history import QueryHistory
from app.utils.security import hash_password, encrypt_value


def create_guest_account(db: Session) -> User:
    """
    Creates a new guest user account initialized with:
    1. Preloaded PostgreSQL connection to the 'shop' database (configurable via env vars).
    2. Preloaded KnowledgeBase group with all e-commerce tables.
    3. Realistic mock conversations and query history showcasing NL-to-SQL capabilities.
    """
    settings = get_settings()

    # 1. Create unique Guest User
    guest_uid = uuid.uuid4().hex[:8]
    random_pw = uuid.uuid4().hex
    guest_user = User(
        email=f"guest_{guest_uid}@sqlnav.demo",
        username=f"guest_{guest_uid}",
        hashed_password=hash_password(random_pw),
    )
    db.add(guest_user)
    db.commit()
    db.refresh(guest_user)

    # 2. Preload Database Connection
    # Uses settings (GUEST_DB_HOST, GUEST_DB_PORT, GUEST_DB_NAME, GUEST_DB_USER, GUEST_DB_PASSWORD)
    # Defaulting to localhost:5432 / shop / postgres / password
    guest_conn = DBConnection(
        user_id=guest_user.id,
        name="Shop Database",
        host=settings.GUEST_DB_HOST,
        port=settings.GUEST_DB_PORT,
        db_name=settings.GUEST_DB_NAME,
        username=settings.GUEST_DB_USER,
        encrypted_password=encrypt_value(settings.GUEST_DB_PASSWORD),
    )
    db.add(guest_conn)
    db.commit()
    db.refresh(guest_conn)

    # 3. Preload Knowledge Base (All e-commerce shop tables)
    shop_tables = [
        "categories",
        "products",
        "users",
        "addresses",
        "product_reviews",
        "orders",
        "coupons",
        "order_items",
        "payments",
    ]
    guest_kb = KnowledgeBase(
        name="Shop Catalog & Orders",
        tables=shop_tables,
        connection_id=guest_conn.id,
    )
    db.add(guest_kb)
    db.commit()
    db.refresh(guest_kb)

    # 4. Create Mock Conversations and Query History
    now = datetime.now(timezone.utc)

    # Conversation 1: Top Revenue Products & Categories
    conv1_id = str(uuid.uuid4())
    conv1_time = now - timedelta(hours=2)
    conv1 = Conversation(
        id=conv1_id,
        user_id=guest_user.id,
        name="Top Revenue Products & Categories",
        created_at=conv1_time,
        updated_at=conv1_time + timedelta(minutes=15),
    )
    db.add(conv1)

    # Conv 1 - Query 1: Top products by revenue (features images for ProductDisplay)
    q1_id = str(uuid.uuid4())
    q1_sql = (
        "SELECT p.id, p.name, p.price, p.image_url, p.rating, "
        "SUM(oi.quantity) AS units_sold, ROUND(SUM(oi.total_price), 2) AS total_revenue "
        "FROM products p JOIN order_items oi ON p.id = oi.product_id "
        "GROUP BY p.id, p.name, p.price, p.image_url, p.rating "
        "ORDER BY total_revenue DESC LIMIT 5;"
    )
    q1_rows = [
        {
            "id": 14,
            "name": "Samsung 49-Inch CHG90 144Hz Curved Gaming Monitor",
            "price": 999.99,
            "image_url": "https://fakestoreapi.com/img/81Zt42ioCgL._AC_SX679_t.png",
            "rating": 4.8,
            "units_sold": 22,
            "total_revenue": 21999.78,
        },
        {
            "id": 13,
            "name": "Acer SB220Q bi 21.5 inches Full HD IPS Ultra-Thin",
            "price": 599.00,
            "image_url": "https://fakestoreapi.com/img/81QpkIctqPL._AC_SX679_t.png",
            "rating": 4.6,
            "units_sold": 25,
            "total_revenue": 14975.00,
        },
        {
            "id": 5,
            "name": "John Hardy Women's Legends Naga Gold & Silver Dragon Station Chain Bracelet",
            "price": 695.00,
            "image_url": "https://fakestoreapi.com/img/71pWzhdJNwL._AC_UL640_QL65_ML3_t.png",
            "rating": 4.6,
            "units_sold": 20,
            "total_revenue": 13900.00,
        },
        {
            "id": 10,
            "name": "SanDisk SSD PLUS 1TB Internal SSD - SATA III 6 Gb/s",
            "price": 109.00,
            "image_url": "https://fakestoreapi.com/img/61U7T1koQqL._AC_SX679_t.png",
            "rating": 4.4,
            "units_sold": 32,
            "total_revenue": 3488.00,
        },
        {
            "id": 6,
            "name": "Solid Gold Petite Micropave",
            "price": 168.00,
            "image_url": "https://fakestoreapi.com/img/61sbMiUnoGL._AC_UL640_QL65_ML3_t.png",
            "rating": 4.2,
            "units_sold": 15,
            "total_revenue": 2520.00,
        },
    ]
    q1_assistant_text = (
        "Here are the **top 5 products by total revenue** from your store:\n\n"
        "1. **Samsung 49-Inch Curved Gaming Monitor** leads with **$21,999.78** (22 units sold).\n"
        "2. **Acer SB220Q 21.5\" Full HD Monitor** generated **$14,975.00** across 25 units.\n"
        "3. **John Hardy Legends Naga Gold Ring** generated **$13,900.00** (20 units).\n"
        "4. **SanDisk SSD PLUS 1TB** reached **$3,488.00** with high volume (32 units).\n"
        "5. **Solid Gold Petite Micropave** accounted for **$2,520.00** across 15 units.\n\n"
        "High-ticket electronics and fine jewelry are clearly driving the largest share of gross sales."
    )

    db.add(
        ConversationMessage(
            conversation_id=conv1_id,
            role="user",
            content="What are the top 5 products by total revenue? Include their image and sales count.",
            message_type="text",
            query_id=q1_id,
            created_at=conv1_time,
        )
    )
    db.add(
        ConversationMessage(
            conversation_id=conv1_id,
            role="assistant",
            content=q1_assistant_text,
            message_type="result",
            metadata_json=json.dumps(
                {
                    "generated_sql": q1_sql,
                    "columns": ["id", "name", "price", "image_url", "rating", "units_sold", "total_revenue"],
                    "rows": q1_rows,
                    "success": True,
                    "error": "",
                }
            ),
            query_id=q1_id,
            created_at=conv1_time + timedelta(seconds=2),
        )
    )
    db.add(
        QueryHistory(
            user_id=guest_user.id,
            connection_id=guest_conn.id,
            nl_query="What are the top 5 products by total revenue? Include their image and sales count.",
            generated_sql=q1_sql,
            success=True,
            created_at=conv1_time,
        )
    )

    # Conv 1 - Query 2: Follow-up category revenue
    q2_id = str(uuid.uuid4())
    q2_time = conv1_time + timedelta(minutes=10)
    q2_sql = (
        "SELECT c.name AS category, COUNT(DISTINCT o.id) AS orders_count, "
        "SUM(oi.quantity) AS items_sold, ROUND(SUM(oi.total_price), 2) AS total_sales "
        "FROM categories c JOIN products p ON p.category_id = c.id "
        "JOIN order_items oi ON oi.product_id = p.id "
        "JOIN orders o ON o.id = oi.order_id "
        "GROUP BY c.id, c.name ORDER BY total_sales DESC;"
    )
    q2_rows = [
        {"category": "electronics", "orders_count": 50, "items_sold": 130, "total_sales": 45016.78},
        {"category": "jewelery", "orders_count": 30, "items_sold": 67, "total_sales": 16754.68},
        {"category": "women's clothing", "orders_count": 50, "items_sold": 119, "total_sales": 3800.27},
        {"category": "men's clothing", "orders_count": 32, "items_sold": 72, "total_sales": 3507.69},
    ]
    q2_assistant_text = (
        "### Category Revenue Breakdown\n\n"
        "* **Electronics** dominates overall revenue at **$45,016.78** (130 items sold across 50 orders).\n"
        "* **Jewelry** ranks second with **$16,754.68**.\n"
        "* **Apparel** (Women's and Men's clothing) accounts for steady volume (**191 combined units**) "
        "with $7,307.96 total.\n\n"
        "Promotional campaigns on higher-ticket electronics and jewelry yield the highest ROI."
    )
    db.add(
        ConversationMessage(
            conversation_id=conv1_id,
            role="user",
            content="Which categories generated the most revenue from these items?",
            message_type="text",
            query_id=q2_id,
            created_at=q2_time,
        )
    )
    db.add(
        ConversationMessage(
            conversation_id=conv1_id,
            role="assistant",
            content=q2_assistant_text,
            message_type="result",
            metadata_json=json.dumps(
                {
                    "generated_sql": q2_sql,
                    "columns": ["category", "orders_count", "items_sold", "total_sales"],
                    "rows": q2_rows,
                    "success": True,
                    "error": "",
                }
            ),
            query_id=q2_id,
            created_at=q2_time + timedelta(seconds=2),
        )
    )
    db.add(
        QueryHistory(
            user_id=guest_user.id,
            connection_id=guest_conn.id,
            nl_query="Which categories generated the most revenue from these items?",
            generated_sql=q2_sql,
            success=True,
            created_at=q2_time,
        )
    )

    # Conversation 2: High-Value Customer Analysis
    conv2_id = str(uuid.uuid4())
    conv2_time = now - timedelta(hours=1, minutes=20)
    conv2 = Conversation(
        id=conv2_id,
        user_id=guest_user.id,
        name="High-Value Customer Analysis",
        created_at=conv2_time,
        updated_at=conv2_time + timedelta(minutes=5),
    )
    db.add(conv2)

    q3_id = str(uuid.uuid4())
    q3_sql = (
        "SELECT u.first_name || ' ' || u.last_name AS customer_name, u.email, "
        "COUNT(o.id) AS total_orders, ROUND(SUM(o.total_amount), 2) AS total_spent, "
        "ROUND(AVG(o.total_amount), 2) AS avg_order_value "
        "FROM users u JOIN orders o ON o.user_id = u.id "
        "GROUP BY u.id, customer_name, u.email ORDER BY total_spent DESC LIMIT 5;"
    )
    q3_rows = [
        {"customer_name": "Leslie Adams", "email": "robinbradley@example.net", "total_orders": 4, "total_spent": 6048.30, "avg_order_value": 1512.08},
        {"customer_name": "Justin Nelson", "email": "patricia12@example.org", "total_orders": 3, "total_spent": 5710.38, "avg_order_value": 1903.46},
        {"customer_name": "Jade Carr", "email": "contrerasangela@example.net", "total_orders": 4, "total_spent": 5031.92, "avg_order_value": 1257.98},
        {"customer_name": "Danielle Johnson", "email": "john21@example.net", "total_orders": 3, "total_spent": 4510.03, "avg_order_value": 1503.34},
        {"customer_name": "Perry Carrillo", "email": "gateskathy@example.com", "total_orders": 4, "total_spent": 4327.39, "avg_order_value": 1081.85},
    ]
    q3_assistant_text = (
        "**Top 5 VIP Customers by Lifetime Value:**\n\n"
        "* **Leslie Adams** is the top spender with **$6,048.30** across 4 orders (AOV: $1,512.08).\n"
        "* **Justin Nelson** follows closely with **$5,710.38** across 3 orders with highest AOV (**$1,903.46**).\n"
        "* **Jade Carr**, **Danielle Johnson**, and **Perry Carrillo** also exceed $4,300+ in spend.\n\n"
        "Recommendation: Enroll these 5 customers in an exclusive VIP loyalty tier with personalized offers."
    )
    db.add(
        ConversationMessage(
            conversation_id=conv2_id,
            role="user",
            content="Who are our top 5 customers by total spending and order count?",
            message_type="text",
            query_id=q3_id,
            created_at=conv2_time,
        )
    )
    db.add(
        ConversationMessage(
            conversation_id=conv2_id,
            role="assistant",
            content=q3_assistant_text,
            message_type="result",
            metadata_json=json.dumps(
                {
                    "generated_sql": q3_sql,
                    "columns": ["customer_name", "email", "total_orders", "total_spent", "avg_order_value"],
                    "rows": q3_rows,
                    "success": True,
                    "error": "",
                }
            ),
            query_id=q3_id,
            created_at=conv2_time + timedelta(seconds=2),
        )
    )
    db.add(
        QueryHistory(
            user_id=guest_user.id,
            connection_id=guest_conn.id,
            nl_query="Who are our top 5 customers by total spending and order count?",
            generated_sql=q3_sql,
            success=True,
            created_at=conv2_time,
        )
    )

    # Conversation 3: Order Fulfillment Breakdown
    conv3_id = str(uuid.uuid4())
    conv3_time = now - timedelta(minutes=45)
    conv3 = Conversation(
        id=conv3_id,
        user_id=guest_user.id,
        name="Order Fulfillment Breakdown",
        created_at=conv3_time,
        updated_at=conv3_time + timedelta(minutes=2),
    )
    db.add(conv3)

    q4_id = str(uuid.uuid4())
    q4_sql = (
        "SELECT status, COUNT(*) AS order_count, "
        "ROUND(SUM(total_amount), 2) AS total_value, "
        "ROUND(AVG(total_amount), 2) AS avg_value "
        "FROM orders GROUP BY status ORDER BY order_count DESC;"
    )
    q4_rows = [
        {"status": "delivered", "order_count": 42, "total_value": 35412.80, "avg_value": 843.16},
        {"status": "shipped", "order_count": 18, "total_value": 16240.50, "avg_value": 902.25},
        {"status": "processing", "order_count": 9, "total_value": 8120.30, "avg_value": 902.26},
        {"status": "pending", "order_count": 5, "total_value": 4350.20, "avg_value": 870.04},
        {"status": "cancelled", "order_count": 4, "total_value": 3210.15, "avg_value": 802.54},
        {"status": "refunded", "order_count": 2, "total_value": 1745.00, "avg_value": 872.50},
    ]
    q4_assistant_text = (
        "### Order Fulfillment Summary\n\n"
        "* **Delivered Orders:** 42 ($35,412.80)\n"
        "* **In Transit (Shipped):** 18 ($16,240.50)\n"
        "* **Awaiting Dispatch (Processing/Pending):** 14 ($12,470.50)\n"
        "* **Exceptions (Cancelled/Refunded):** 6 ($4,955.15)\n\n"
        "Fulfillment rate is healthy at over **75% completed or in transit**."
    )
    db.add(
        ConversationMessage(
            conversation_id=conv3_id,
            role="user",
            content="Show breakdown of current order fulfillment statuses and total value",
            message_type="text",
            query_id=q4_id,
            created_at=conv3_time,
        )
    )
    db.add(
        ConversationMessage(
            conversation_id=conv3_id,
            role="assistant",
            content=q4_assistant_text,
            message_type="result",
            metadata_json=json.dumps(
                {
                    "generated_sql": q4_sql,
                    "columns": ["status", "order_count", "total_value", "avg_value"],
                    "rows": q4_rows,
                    "success": True,
                    "error": "",
                }
            ),
            query_id=q4_id,
            created_at=conv3_time + timedelta(seconds=2),
        )
    )
    db.add(
        QueryHistory(
            user_id=guest_user.id,
            connection_id=guest_conn.id,
            nl_query="Show breakdown of current order fulfillment statuses and total value",
            generated_sql=q4_sql,
            success=True,
            created_at=conv3_time,
        )
    )

    db.commit()
    return guest_user
