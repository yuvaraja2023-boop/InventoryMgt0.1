"""
Pytest configuration and shared test fixtures for Smart Inventory Management System.
Uses isolated temporary SQLite databases so tests never alter live inventory records.
"""

import os
import tempfile
import pytest
from app import create_app
import database


@pytest.fixture
def app():
    """Create and configure a clean Flask test application instance with an isolated database."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)

    app = create_app({
        'TESTING': True,
        'DATABASE': db_path,
        'SECRET_KEY': 'test-secret-key-scm'
    })

    with app.app_context():
        database.init_db(db_path=db_path)
        # Clear out any auto-seeded data so tests start in known state
        database.clear_all_data(db_path=db_path)

        # Seed minimal baseline for testing
        conn = database.get_db()
        # Add 1 test supplier
        conn.execute("""
            INSERT INTO suppliers (id, supplier_name, company_name, contact_person, phone, email, address, notes)
            VALUES (1, 'Test Vendor Global', 'Vendor Corp', 'John Doe', '+1-555-1234', 'john@vendor.com', '123 Test St', 'Reliable supplier')
        """)

        # Add 3 test products: Normal stock, Low stock, Out of stock
        conn.execute("""
            INSERT INTO products (id, sku, name, category, supplier_id, purchase_price, selling_price, quantity, minimum_stock, unit)
            VALUES (1, 'TEST-SKU-001', 'Test Monitor', 'Electronics', 1, 100.0, 150.0, 50, 10, 'Units')
        """)
        conn.execute("""
            INSERT INTO products (id, sku, name, category, supplier_id, purchase_price, selling_price, quantity, minimum_stock, unit)
            VALUES (2, 'TEST-SKU-002', 'Test Keyboard', 'Electronics', 1, 30.0, 60.0, 4, 10, 'Units')
        """)
        conn.execute("""
            INSERT INTO products (id, sku, name, category, supplier_id, purchase_price, selling_price, quantity, minimum_stock, unit)
            VALUES (3, 'TEST-SKU-003', 'Test Mouse', 'Electronics', 1, 15.0, 30.0, 0, 5, 'Units')
        """)

        conn.commit()

    yield app

    # Cleanup temporary test database file
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    """A test client for making HTTP requests."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test CLI runner for app commands."""
    return app.test_cli_runner()
