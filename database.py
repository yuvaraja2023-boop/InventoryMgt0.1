"""
Database access and schema management for Smart Inventory Management System.
Uses SQLite with foreign keys, parameterization, transactions, and indexing.
"""

import os
import sqlite3
from datetime import datetime
from flask import g, current_app

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'inventory.db')


def get_db(db_path=None):
    """
    Get a database connection.
    If running within a Flask application context, cache the connection in flask.g.
    """
    if db_path is None:
        try:
            db_path = current_app.config.get('DATABASE', DEFAULT_DB_PATH)
        except RuntimeError:
            db_path = DEFAULT_DB_PATH

    # If within request context, use g
    try:
        if 'db' not in g:
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
            conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA journal_mode = WAL;")
            g.db = conn
        return g.db
    except RuntimeError:
        # Outside Flask application context (e.g., CLI or standalone script)
        if db_path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn


def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(db_path=None):
    """
    Initialize SQLite tables, constraints, indexes, and default settings.
    Safe to run repeatedly; uses CREATE TABLE IF NOT EXISTS.
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    # 1. Suppliers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_name TEXT NOT NULL,
            company_name TEXT,
            contact_person TEXT,
            phone TEXT,
            email TEXT,
            address TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # 2. Products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            supplier_id INTEGER,
            purchase_price REAL NOT NULL DEFAULT 0.0,
            selling_price REAL NOT NULL DEFAULT 0.0,
            quantity INTEGER NOT NULL DEFAULT 0,
            minimum_stock INTEGER NOT NULL DEFAULT 5,
            unit TEXT NOT NULL DEFAULT 'Units',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE SET NULL
        );
    """)

    # 3. Inventory transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            product_name_cache TEXT NOT NULL,
            product_sku_cache TEXT,
            transaction_type TEXT NOT NULL,
            quantity_changed INTEGER NOT NULL,
            previous_quantity INTEGER NOT NULL,
            new_quantity INTEGER NOT NULL,
            supplier_id INTEGER,
            reference_number TEXT,
            reason TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL,
            FOREIGN KEY (supplier_id) REFERENCES suppliers (id) ON DELETE SET NULL
        );
    """)

    # 4. Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # Indexes for performance
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_sku ON products(sku);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_supplier ON products(supplier_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_products_is_deleted ON products(is_deleted);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_product ON inventory_transactions(product_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_type ON inventory_transactions(transaction_type);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_created ON inventory_transactions(created_at);")

    # Default settings
    default_settings = [
        ('company_name', 'Apex Inventory Solutions'),
        ('currency_symbol', '$'),
        ('target_stock_multiplier', '2.0'),
        ('enable_low_stock_banner', '1'),
        ('is_demo_loaded', '0')
    ]
    for key, val in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?);", (key, val))

    conn.commit()


def get_setting(key, default=None, db_path=None):
    """Retrieve a setting value by key."""
    conn = get_db(db_path)
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value, db_path=None):
    """Set or update a setting value."""
    conn = get_db(db_path)
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, str(value))
    )
    conn.commit()


def seed_demo_data(db_path=None):
    """
    Populate database with rich, realistic demonstration data.
    Marks records as demonstration data in settings.
    """
    conn = get_db(db_path)
    cursor = conn.cursor()

    # Clear existing demo data or start clean if empty
    # Check if products already exist
    count = cursor.execute("SELECT COUNT(*) as c FROM products WHERE is_deleted = 0").fetchone()['c']
    if count > 0:
        return False, "Database already contains product records. Clear or reset before seeding demo data."

    # Sample Suppliers
    sample_suppliers = [
        ("TechSupply Global", "TechSupply International LLC", "Marcus Vance", "+1 (555) 234-5678", "contact@techsupply.io", "450 Industrial Parkway, Austin, TX", "Primary distributor for computer parts and microcontrollers."),
        ("Precision Components", "Precision Dynamics Corp", "Elena Rostova", "+1 (555) 876-5432", "elena@precisioncomp.com", "120 Silicon Blvd, San Jose, CA", "Certified ISO-9001 electronic components and cabling."),
        ("Apex Packaging & Logistics", "Apex Warehouse & Logistics", "Devon Miller", "+1 (555) 345-9876", "sales@apexlogistics.net", "88 Freight Way, Chicago, IL", "Boxes, anti-static packing materials, and shipping supplies."),
        ("Nordic Raw Materials", "Nordic Metals & Plastics Ltd", "Astrid Lind", "+1 (555) 654-3210", "astrid@nordicmaterials.com", "72 Harbor Terminal, Seattle, WA", "Aluminum extrusions, thermal pastes, and acrylic casings.")
    ]

    supplier_ids = []
    for supp in sample_suppliers:
        cursor.execute("""
            INSERT INTO suppliers (supplier_name, company_name, contact_person, phone, email, address, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, supp)
        supplier_ids.append(cursor.lastrowid)

    # Sample Products across categories
    # (SKU, Name, Category, Description, Supplier_idx, Purchase, Selling, InitialStock, MinStock, Unit)
    sample_products = [
        ("PRD-1001", "UltraHD 4K Curved Monitor 27-inch", "Electronics", "IPS 144Hz HDR panel with USB-C Hub integration", 0, 185.00, 299.99, 45, 10, "Units"),
        ("PRD-1002", "Ergonomic Mechanical Keyboard (Brown Switch)", "Electronics", "Wireless Bluetooth & 2.4GHz with RGB backlighting", 1, 42.50, 89.90, 78, 15, "Units"),
        ("PRD-1003", "Precision Wireless Laser Mouse", "Electronics", "4000 DPI rechargeable silent click mouse", 1, 16.20, 34.50, 110, 20, "Units"),
        ("PRD-1004", "Heavy-Duty Anti-Static Corrugated Boxes (Medium)", "Packaging", "Reinforced 5-ply shipping boxes 16x12x10 inches", 2, 1.85, 4.50, 450, 100, "Boxes"),
        ("PRD-1005", "Industrial Grade Thermal Conductive Paste (30g)", "Raw Materials", "High performance 8.5 W/mK compound syringe", 3, 5.20, 14.99, 8, 12, "Tubes"),  # LOW STOCK
        ("PRD-1006", "Cat6A Shielded Ethernet Cable (15m)", "Networking", "Pure bare copper 10Gbps patch cord with snagless boot", 0, 4.10, 12.50, 14, 15, "Pieces"),  # LOW STOCK
        ("PRD-1007", "100W GaN Fast Charger Multi-Port", "Electronics", "Dual USB-C PD 3.0 with foldable pins", 0, 19.80, 45.00, 0, 10, "Units"),  # OUT OF STOCK
        ("PRD-1008", "Anodized Aluminum Mini-ITX Chassis", "Raw Materials", "Sandblasted matte finish compact server enclosure", 3, 38.00, 79.99, 22, 5, "Units"),
        ("PRD-1009", "Biodegradable Air Cushion Bubble Roll (300m)", "Packaging", "Eco-friendly protective packing void fill material", 2, 24.50, 52.00, 3, 8, "Rolls"),  # LOW STOCK
        ("PRD-1010", "Uninterruptible Power Supply (UPS) 1500VA", "Power Equipment", "Sine wave battery backup with LCD display", 0, 110.00, 189.95, 18, 5, "Units"),
        ("PRD-1011", "High-Speed Thermal Receipt Printer", "Retail Hardware", "80mm USB & Ethernet thermal receipt mechanism", 1, 55.00, 119.00, 0, 6, "Units"),  # OUT OF STOCK
        ("PRD-1012", "Barcode & QR Code Handheld Scanner 2D", "Retail Hardware", "Wireless handheld scanner with charging cradle", 1, 28.50, 64.99, 32, 8, "Units")
    ]

    for item in sample_products:
        sku, name, category, desc, s_idx, pur_price, sel_price, qty, min_stock, unit = item
        supp_id = supplier_ids[s_idx] if s_idx < len(supplier_ids) else None

        cursor.execute("""
            INSERT INTO products (sku, name, category, description, supplier_id, purchase_price, selling_price, quantity, minimum_stock, unit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (sku, name, category, desc, supp_id, pur_price, sel_price, qty, min_stock, unit))
        p_id = cursor.lastrowid

        # Record Opening Stock transaction
        if qty > 0:
            cursor.execute("""
                INSERT INTO inventory_transactions 
                (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
                VALUES (?, ?, ?, 'Opening Stock', ?, 0, ?, ?, 'INIT-STARTUP', 'Initial System Inventory Count', 'Setup of opening warehouse balance')
            """, (p_id, name, sku, qty, qty, supp_id))
        else:
            cursor.execute("""
                INSERT INTO inventory_transactions 
                (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
                VALUES (?, ?, ?, 'Opening Stock', 0, 0, 0, ?, 'INIT-ZERO', 'Product Registered Without Initial Stock', 'Registered catalog item with zero baseline')
            """, (p_id, name, sku, supp_id))

    # Add realistic subsequent transactions (Stock In and Stock Out)
    # 1. Stock In for PRD-1001
    cursor.execute("""
        INSERT INTO inventory_transactions
        (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
        VALUES (1, 'UltraHD 4K Curved Monitor 27-inch', 'PRD-1001', 'Stock In', 15, 30, 45, ?, 'PO-2026-0891', 'Purchase Order Fulfillment', 'Batch received in good condition at dock B')
    """, (supplier_ids[0],))

    # 2. Stock Out for PRD-1002
    cursor.execute("""
        INSERT INTO inventory_transactions
        (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
        VALUES (2, 'Ergonomic Mechanical Keyboard (Brown Switch)', 'PRD-1002', 'Stock Out', -12, 90, 78, NULL, 'SO-44021', 'Customer Order Dispatch', 'Shipped via Express Logistics')
    """)

    # 3. Stock Adjustment for PRD-1005 (Audit difference)
    cursor.execute("""
        INSERT INTO inventory_transactions
        (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
        VALUES (5, 'Industrial Grade Thermal Conductive Paste (30g)', 'PRD-1005', 'Stock Adjustment', -2, 10, 8, NULL, 'AUDIT-Q3', 'Physical Inventory Count Audit', 'Damaged tubes discarded during weekly audit')
    """)

    set_setting('is_demo_loaded', '1', db_path=db_path)
    conn.commit()
    return True, "Demonstration inventory, suppliers, and transaction history loaded successfully!"


def clear_all_data(db_path=None):
    """Safely clear all inventory data and transactions while preserving table structure."""
    conn = get_db(db_path)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM inventory_transactions;")
    cursor.execute("DELETE FROM products;")
    cursor.execute("DELETE FROM suppliers;")
    set_setting('is_demo_loaded', '0', db_path=db_path)
    conn.commit()
    return True, "All inventory and transaction records have been cleared."


def init_app(app):
    """Register teardown and initialize database for a Flask app instance."""
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()
