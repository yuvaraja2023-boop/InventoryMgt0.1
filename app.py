"""
Smart Inventory Management System - Flask Application
A professional, modern inventory management web application.
Zero login/signup - opens directly to the inventory dashboard.
"""

import os
import csv
import io
import re
from datetime import datetime
from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for, flash
import database

def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='smart-inventory-management-secret-key-scm',
        DATABASE=os.path.join(app.instance_path, 'inventory.db'),
    )

    if test_config is not None:
        app.config.update(test_config)

    # Ensure the instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # Register teardown and initialize DB
    app.teardown_appcontext(database.close_db)

    with app.app_context():
        database.init_db()
        # Automatically load demo data on first start if products table is completely empty
        conn = database.get_db()
        cnt = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()['c']
        if cnt == 0:
            database.seed_demo_data()

    # Context processor to inject global variables into templates
    @app.context_processor
    def inject_globals():
        try:
            curr_symbol = database.get_setting('currency_symbol', '$')
            company_name = database.get_setting('company_name', 'Apex Inventory Solutions')
            conn = database.get_db()
            alert_count = conn.execute("""
                SELECT COUNT(*) as cnt FROM products 
                WHERE is_deleted = 0 AND quantity <= minimum_stock
            """).fetchone()['cnt']
        except Exception:
            curr_symbol = '$'
            company_name = 'Smart Inventory'
            alert_count = 0

        return dict(
            currency_symbol=curr_symbol,
            company_name=company_name,
            alert_count=alert_count,
            current_date=datetime.now().strftime('%A, %B %d, %Y')
        )

    # -------------------------------------------------------------
    # WEB PAGE ROUTES (Direct access, no authentication)
    # -------------------------------------------------------------
    @app.route('/')
    def dashboard():
        """Main Inventory Dashboard - first view opened by users."""
        return render_template('dashboard.html', active_page='dashboard')

    @app.route('/products')
    def products_page():
        return render_template('products.html', active_page='products')

    @app.route('/products/<int:product_id>')
    def product_details_page(product_id):
        conn = database.get_db()
        product = conn.execute("""
            SELECT p.*, s.supplier_name, s.company_name as supplier_company
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.id = ?
        """, (product_id,)).fetchone()

        if not product:
            flash('Product not found.', 'danger')
            return redirect(url_for('products_page'))

        transactions = conn.execute("""
            SELECT t.*, s.supplier_name
            FROM inventory_transactions t
            LEFT JOIN suppliers s ON t.supplier_id = s.id
            WHERE t.product_id = ?
            ORDER BY t.created_at DESC
        """, (product_id,)).fetchall()

        return render_template('product_details.html', product=product, transactions=transactions, active_page='products')

    @app.route('/stock')
    @app.route('/stock-management')
    def stock_page():
        return render_template('stock_management.html', active_page='stock')

    @app.route('/suppliers')
    def suppliers_page():
        return render_template('suppliers.html', active_page='suppliers')

    @app.route('/transactions')
    def transactions_page():
        return render_template('transactions.html', active_page='transactions')

    @app.route('/alerts')
    def alerts_page():
        return render_template('alerts.html', active_page='alerts')

    @app.route('/reports')
    def reports_page():
        return render_template('reports.html', active_page='reports')

    @app.route('/settings')
    def settings_page():
        return render_template('settings.html', active_page='settings')

    # -------------------------------------------------------------
    # API ENDPOINTS: DASHBOARD
    # -------------------------------------------------------------
    @app.route('/api/dashboard/stats', methods=['GET'])
    def get_dashboard_stats():
        conn = database.get_db()
        # 1. Total active products
        total_products = conn.execute("SELECT COUNT(*) as c FROM products WHERE is_deleted = 0").fetchone()['c']

        # 2. Total units in stock
        total_units = conn.execute("SELECT COALESCE(SUM(quantity), 0) as s FROM products WHERE is_deleted = 0").fetchone()['s']

        # 3. Low stock products (quantity > 0 and quantity <= minimum_stock)
        low_stock = conn.execute("""
            SELECT COUNT(*) as c FROM products 
            WHERE is_deleted = 0 AND quantity > 0 AND quantity <= minimum_stock
        """).fetchone()['c']

        # 4. Out of stock products (quantity = 0)
        out_of_stock = conn.execute("""
            SELECT COUNT(*) as c FROM products 
            WHERE is_deleted = 0 AND quantity = 0
        """).fetchone()['c']

        # 5. Total suppliers
        total_suppliers = conn.execute("SELECT COUNT(*) as c FROM suppliers").fetchone()['c']

        # 6. Total estimated inventory value (SUM(quantity * purchase_price))
        total_val = conn.execute("""
            SELECT COALESCE(SUM(quantity * purchase_price), 0.0) as val 
            FROM products WHERE is_deleted = 0
        """).fetchone()['val']

        currency = database.get_setting('currency_symbol', '$')

        return jsonify({
            'success': True,
            'stats': {
                'total_products': total_products,
                'total_units': total_units,
                'low_stock_products': low_stock,
                'out_of_stock_products': out_of_stock,
                'total_suppliers': total_suppliers,
                'total_inventory_value': round(total_val, 2),
                'currency_symbol': currency
            }
        })

    @app.route('/api/dashboard/charts', methods=['GET'])
    def get_dashboard_charts():
        conn = database.get_db()

        # 1. Category distribution (category, total quantity, total value)
        category_rows = conn.execute("""
            SELECT category, SUM(quantity) as total_qty, SUM(quantity * purchase_price) as total_val, COUNT(*) as product_count
            FROM products 
            WHERE is_deleted = 0 
            GROUP BY category 
            ORDER BY total_qty DESC
        """).fetchall()

        cat_labels = [row['category'] for row in category_rows]
        cat_quantities = [row['total_qty'] for row in category_rows]
        cat_values = [round(row['total_val'], 2) for row in category_rows]

        # 2. Top products by quantity (top 7)
        top_rows = conn.execute("""
            SELECT name, sku, quantity 
            FROM products 
            WHERE is_deleted = 0 
            ORDER BY quantity DESC 
            LIMIT 7
        """).fetchall()

        top_labels = [f"{row['name'][:18]}..." if len(row['name']) > 18 else row['name'] for row in top_rows]
        top_quantities = [row['quantity'] for row in top_rows]

        # 3. Monthly Stock In vs Stock Out (Recent transactions by month or day)
        # Group transactions by YYYY-MM
        timeline_rows = conn.execute("""
            SELECT 
                strftime('%Y-%m', created_at) as month_period,
                SUM(CASE WHEN transaction_type = 'Stock In' THEN quantity_changed ELSE 0 END) as stock_in_qty,
                SUM(CASE WHEN transaction_type = 'Stock Out' THEN ABS(quantity_changed) ELSE 0 END) as stock_out_qty
            FROM inventory_transactions
            GROUP BY strftime('%Y-%m', created_at)
            ORDER BY month_period DESC
            LIMIT 6
        """).fetchall()

        timeline_labels = [r['month_period'] for r in reversed(timeline_rows)] if timeline_rows else [datetime.now().strftime('%Y-%m')]
        stock_in_series = [r['stock_in_qty'] for r in reversed(timeline_rows)] if timeline_rows else [0]
        stock_out_series = [r['stock_out_qty'] for r in reversed(timeline_rows)] if timeline_rows else [0]

        # 4. Stock status breakdown
        status_in_stock = conn.execute("SELECT COUNT(*) as c FROM products WHERE is_deleted = 0 AND quantity > minimum_stock").fetchone()['c']
        status_low_stock = conn.execute("SELECT COUNT(*) as c FROM products WHERE is_deleted = 0 AND quantity > 0 AND quantity <= minimum_stock").fetchone()['c']
        status_out_of_stock = conn.execute("SELECT COUNT(*) as c FROM products WHERE is_deleted = 0 AND quantity = 0").fetchone()['c']

        return jsonify({
            'success': True,
            'category_distribution': {
                'labels': cat_labels,
                'quantities': cat_quantities,
                'values': cat_values
            },
            'top_products': {
                'labels': top_labels,
                'quantities': top_quantities
            },
            'timeline': {
                'labels': timeline_labels,
                'stock_in': stock_in_series,
                'stock_out': stock_out_series
            },
            'stock_status': {
                'labels': ['In Stock', 'Low Stock', 'Out of Stock'],
                'counts': [status_in_stock, status_low_stock, status_out_of_stock]
            }
        })

    @app.route('/api/dashboard/recent-activity', methods=['GET'])
    def get_recent_activity():
        conn = database.get_db()
        limit = request.args.get('limit', default=10, type=int)
        rows = conn.execute("""
            SELECT t.id, t.created_at, t.product_name_cache, t.product_sku_cache,
                   t.transaction_type, t.quantity_changed, t.previous_quantity, t.new_quantity,
                   t.reference_number, t.reason, p.id as product_id
            FROM inventory_transactions t
            LEFT JOIN products p ON t.product_id = p.id
            ORDER BY t.created_at DESC, t.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        activities = []
        for r in rows:
            activities.append({
                'id': r['id'],
                'date_time': r['created_at'],
                'product_name': r['product_name_cache'],
                'sku': r['product_sku_cache'],
                'product_id': r['product_id'],
                'transaction_type': r['transaction_type'],
                'quantity_changed': r['quantity_changed'],
                'previous_quantity': r['previous_quantity'],
                'new_quantity': r['new_quantity'],
                'reference_number': r['reference_number'] or '-',
                'reason': r['reason'] or '-'
            })

        return jsonify({'success': True, 'activities': activities})

    # -------------------------------------------------------------
    # API ENDPOINTS: PRODUCTS CRUD & LIST
    # -------------------------------------------------------------
    @app.route('/api/products', methods=['GET'])
    def get_products():
        search = request.args.get('search', '').strip()
        category = request.args.get('category', '').strip()
        status = request.args.get('status', '').strip()
        sort_by = request.args.get('sort_by', 'name').lower()
        order = request.args.get('order', 'asc').lower()

        allowed_sort = {
            'name': 'p.name',
            'sku': 'p.sku',
            'quantity': 'p.quantity',
            'purchase_price': 'p.purchase_price',
            'selling_price': 'p.selling_price',
            'category': 'p.category',
            'created_at': 'p.created_at'
        }
        order_col = allowed_sort.get(sort_by, 'p.name')
        order_dir = 'DESC' if order == 'desc' else 'ASC'

        query = """
            SELECT p.*, s.supplier_name, s.company_name as supplier_company
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.is_deleted = 0
        """
        params = []

        if search:
            query += " AND (p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])

        if category and category != 'All':
            query += " AND p.category = ?"
            params.append(category)

        if status:
            if status == 'in_stock':
                query += " AND p.quantity > p.minimum_stock"
            elif status == 'low_stock':
                query += " AND p.quantity > 0 AND p.quantity <= p.minimum_stock"
            elif status == 'out_of_stock':
                query += " AND p.quantity = 0"

        query += f" ORDER BY {order_col} {order_dir}"

        conn = database.get_db()
        rows = conn.execute(query, params).fetchall()

        products = []
        for r in rows:
            qty = r['quantity']
            min_stk = r['minimum_stock']
            if qty == 0:
                stock_status = 'Out of Stock'
                status_badge = 'danger'
            elif qty <= min_stk:
                stock_status = 'Low Stock'
                status_badge = 'warning'
            else:
                stock_status = 'In Stock'
                status_badge = 'success'

            products.append({
                'id': r['id'],
                'sku': r['sku'],
                'name': r['name'],
                'category': r['category'],
                'description': r['description'] or '',
                'supplier_id': r['supplier_id'],
                'supplier_name': r['supplier_name'] or 'None',
                'purchase_price': float(r['purchase_price']),
                'selling_price': float(r['selling_price']),
                'quantity': r['quantity'],
                'minimum_stock': r['minimum_stock'],
                'unit': r['unit'],
                'stock_status': stock_status,
                'status_badge': status_badge,
                'inventory_value': round(r['quantity'] * float(r['purchase_price']), 2),
                'created_at': r['created_at'],
                'updated_at': r['updated_at']
            })

        return jsonify({'success': True, 'count': len(products), 'products': products})

    @app.route('/api/products', methods=['POST'])
    def create_product():
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No input data provided.'}), 400

        name = data.get('name', '').strip()
        sku = data.get('sku', '').strip()
        category = data.get('category', '').strip()
        description = data.get('description', '').strip()
        supplier_id = data.get('supplier_id')
        unit = data.get('unit', 'Units').strip() or 'Units'

        if not name:
            return jsonify({'success': False, 'error': 'Product name is required.'}), 400
        if not category:
            return jsonify({'success': False, 'error': 'Category is required.'}), 400

        # Auto-generate SKU if not provided
        if not sku:
            timestamp_suffix = datetime.now().strftime('%y%m%d%H%M%S')
            sku = f"SKU-{timestamp_suffix}"

        # Clean numeric fields with validation
        try:
            purchase_price = float(data.get('purchase_price', 0.0))
            selling_price = float(data.get('selling_price', 0.0))
            quantity = int(data.get('quantity', 0))
            minimum_stock = int(data.get('minimum_stock', 5))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Prices and quantities must be valid numbers.'}), 400

        if purchase_price < 0 or selling_price < 0:
            return jsonify({'success': False, 'error': 'Prices cannot be negative.'}), 400
        if quantity < 0:
            return jsonify({'success': False, 'error': 'Initial quantity cannot be negative.'}), 400
        if minimum_stock < 0:
            return jsonify({'success': False, 'error': 'Minimum stock threshold cannot be negative.'}), 400

        # Convert supplier_id
        if supplier_id and str(supplier_id).isdigit():
            supplier_id = int(supplier_id)
        else:
            supplier_id = None

        conn = database.get_db()
        # Check SKU uniqueness among active products
        existing = conn.execute("SELECT id FROM products WHERE sku = ? AND is_deleted = 0", (sku,)).fetchone()
        if existing:
            return jsonify({'success': False, 'error': f"Product SKU '{sku}' already exists. Please choose a unique SKU."}), 400

        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO products (sku, name, category, description, supplier_id, purchase_price, selling_price, quantity, minimum_stock, unit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sku, name, category, description, supplier_id, purchase_price, selling_price, quantity, minimum_stock, unit))
            product_id = cursor.lastrowid

            # Record Opening Stock transaction
            cursor.execute("""
                INSERT INTO inventory_transactions
                (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
                VALUES (?, ?, ?, 'Opening Stock', ?, 0, ?, ?, 'INIT-CREATE', 'Initial Product Registration', ?)
            """, (product_id, name, sku, quantity, quantity, supplier_id, f"Initial inventory for new product: {name}"))

            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': f"Database error creating product: {str(e)}"}), 500

        return jsonify({
            'success': True,
            'message': f"Product '{name}' created successfully with SKU {sku}.",
            'product_id': product_id
        }), 201

    @app.route('/api/products/<int:product_id>', methods=['GET'])
    def get_product(product_id):
        conn = database.get_db()
        product = conn.execute("""
            SELECT p.*, s.supplier_name, s.company_name as supplier_company
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.id = ?
        """, (product_id,)).fetchone()

        if not product:
            return jsonify({'success': False, 'error': 'Product not found.'}), 404

        transactions = conn.execute("""
            SELECT t.*, s.supplier_name
            FROM inventory_transactions t
            LEFT JOIN suppliers s ON t.supplier_id = s.id
            WHERE t.product_id = ?
            ORDER BY t.created_at DESC
        """, (product_id,)).fetchall()

        tx_list = []
        for t in transactions:
            tx_list.append({
                'id': t['id'],
                'transaction_type': t['transaction_type'],
                'quantity_changed': t['quantity_changed'],
                'previous_quantity': t['previous_quantity'],
                'new_quantity': t['new_quantity'],
                'reference_number': t['reference_number'] or '-',
                'reason': t['reason'] or '-',
                'notes': t['notes'] or '',
                'created_at': t['created_at'],
                'supplier_name': t['supplier_name'] or 'N/A'
            })

        return jsonify({
            'success': True,
            'product': {
                'id': product['id'],
                'sku': product['sku'],
                'name': product['name'],
                'category': product['category'],
                'description': product['description'] or '',
                'supplier_id': product['supplier_id'],
                'supplier_name': product['supplier_name'] or 'None',
                'purchase_price': float(product['purchase_price']),
                'selling_price': float(product['selling_price']),
                'quantity': product['quantity'],
                'minimum_stock': product['minimum_stock'],
                'unit': product['unit'],
                'is_deleted': product['is_deleted'],
                'created_at': product['created_at'],
                'updated_at': product['updated_at']
            },
            'transactions': tx_list
        })

    @app.route('/api/products/<int:product_id>', methods=['PUT'])
    def update_product(product_id):
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No update data provided.'}), 400

        conn = database.get_db()
        current_prod = conn.execute("SELECT * FROM products WHERE id = ? AND is_deleted = 0", (product_id,)).fetchone()
        if not current_prod:
            return jsonify({'success': False, 'error': 'Product not found.'}), 404

        name = data.get('name', current_prod['name']).strip()
        sku = data.get('sku', current_prod['sku']).strip()
        category = data.get('category', current_prod['category']).strip()
        description = data.get('description', current_prod['description'] or '').strip()
        unit = data.get('unit', current_prod['unit']).strip()
        supplier_id = data.get('supplier_id', current_prod['supplier_id'])

        if not name:
            return jsonify({'success': False, 'error': 'Product name cannot be empty.'}), 400
        if not sku:
            return jsonify({'success': False, 'error': 'Product SKU cannot be empty.'}), 400

        # Validate unique SKU against other active products
        dup_sku = conn.execute("SELECT id FROM products WHERE sku = ? AND id != ? AND is_deleted = 0", (sku, product_id)).fetchone()
        if dup_sku:
            return jsonify({'success': False, 'error': f"SKU '{sku}' is already assigned to another product."}), 400

        try:
            purchase_price = float(data.get('purchase_price', current_prod['purchase_price']))
            selling_price = float(data.get('selling_price', current_prod['selling_price']))
            minimum_stock = int(data.get('minimum_stock', current_prod['minimum_stock']))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Prices and thresholds must be valid numbers.'}), 400

        if purchase_price < 0 or selling_price < 0:
            return jsonify({'success': False, 'error': 'Prices cannot be negative.'}), 400
        if minimum_stock < 0:
            return jsonify({'success': False, 'error': 'Minimum stock threshold cannot be negative.'}), 400

        if supplier_id and str(supplier_id).isdigit():
            supplier_id = int(supplier_id)
        else:
            supplier_id = None

        conn.execute("""
            UPDATE products 
            SET sku = ?, name = ?, category = ?, description = ?, supplier_id = ?,
                purchase_price = ?, selling_price = ?, minimum_stock = ?, unit = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (sku, name, category, description, supplier_id, purchase_price, selling_price, minimum_stock, unit, product_id))
        conn.commit()

        return jsonify({'success': True, 'message': f"Product '{name}' updated successfully."})

    @app.route('/api/products/<int:product_id>', methods=['DELETE'])
    def delete_product(product_id):
        conn = database.get_db()
        product = conn.execute("SELECT * FROM products WHERE id = ? AND is_deleted = 0", (product_id,)).fetchone()
        if not product:
            return jsonify({'success': False, 'error': 'Product not found or already deleted.'}), 404

        # Mark as deleted to preserve all past inventory transactions
        conn.execute("""
            UPDATE products 
            SET is_deleted = 1, updated_at = CURRENT_TIMESTAMP 
            WHERE id = ?
        """, (product_id,))
        conn.commit()

        return jsonify({
            'success': True, 
            'message': f"Product '{product['name']}' ({product['sku']}) deleted. Historical transaction records preserved."
        })

    # -------------------------------------------------------------
    # API ENDPOINTS: STOCK OPERATIONS (IN, OUT, ADJUST)
    # -------------------------------------------------------------
    @app.route('/api/stock/in', methods=['POST'])
    def stock_in():
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No input data.'}), 400

        product_id = data.get('product_id')
        if not product_id:
            return jsonify({'success': False, 'error': 'Product selection is required.'}), 400

        try:
            quantity_received = int(data.get('quantity', 0))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Quantity must be a valid whole number.'}), 400

        if quantity_received <= 0:
            return jsonify({'success': False, 'error': 'Quantity received must be greater than zero.'}), 400

        supplier_id = data.get('supplier_id')
        if supplier_id and str(supplier_id).isdigit():
            supplier_id = int(supplier_id)
        else:
            supplier_id = None

        reference_number = data.get('reference_number', '').strip() or f"IN-{datetime.now().strftime('%y%m%d%H%M')}"
        reason = data.get('reason', 'Purchase Receipt').strip() or 'Purchase Receipt'
        notes = data.get('notes', '').strip()

        conn = database.get_db()
        cursor = conn.cursor()

        try:
            product = cursor.execute("SELECT * FROM products WHERE id = ? AND is_deleted = 0", (product_id,)).fetchone()
            if not product:
                return jsonify({'success': False, 'error': 'Product not found.'}), 404

            prev_qty = product['quantity']
            new_qty = prev_qty + quantity_received

            # Update product quantity
            cursor.execute("""
                UPDATE products 
                SET quantity = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (new_qty, product_id))

            # Record transaction
            cursor.execute("""
                INSERT INTO inventory_transactions
                (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
                VALUES (?, ?, ?, 'Stock In', ?, ?, ?, ?, ?, ?, ?)
            """, (product_id, product['name'], product['sku'], quantity_received, prev_qty, new_qty, supplier_id or product['supplier_id'], reference_number, reason, notes))

            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': f"Failed to record stock in: {str(e)}"}), 500

        return jsonify({
            'success': True,
            'message': f"Added {quantity_received} units to '{product['name']}'. New stock: {new_qty} {product['unit']}.",
            'previous_quantity': prev_qty,
            'new_quantity': new_qty
        })

    @app.route('/api/stock/out', methods=['POST'])
    def stock_out():
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No input data.'}), 400

        product_id = data.get('product_id')
        if not product_id:
            return jsonify({'success': False, 'error': 'Product selection is required.'}), 400

        try:
            quantity_removed = int(data.get('quantity', 0))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Quantity must be a valid whole number.'}), 400

        if quantity_removed <= 0:
            return jsonify({'success': False, 'error': 'Quantity removed must be greater than zero.'}), 400

        reason = data.get('reason', 'Sale / Order Fulfillment').strip() or 'Sale / Order Fulfillment'
        reference_number = data.get('reference_number', '').strip() or f"OUT-{datetime.now().strftime('%y%m%d%H%M')}"
        notes = data.get('notes', '').strip()

        conn = database.get_db()
        cursor = conn.cursor()

        try:
            product = cursor.execute("SELECT * FROM products WHERE id = ? AND is_deleted = 0", (product_id,)).fetchone()
            if not product:
                return jsonify({'success': False, 'error': 'Product not found.'}), 404

            prev_qty = product['quantity']
            if prev_qty < quantity_removed:
                return jsonify({
                    'success': False,
                    'error': f"Insufficient stock! Available: {prev_qty} {product['unit']}, Requested: {quantity_removed} {product['unit']}. Negative stock is strictly disallowed."
                }), 400

            new_qty = prev_qty - quantity_removed

            # Update product quantity
            cursor.execute("""
                UPDATE products 
                SET quantity = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (new_qty, product_id))

            # Record transaction (negative quantity_changed)
            cursor.execute("""
                INSERT INTO inventory_transactions
                (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
                VALUES (?, ?, ?, 'Stock Out', ?, ?, ?, NULL, ?, ?, ?)
            """, (product_id, product['name'], product['sku'], -quantity_removed, prev_qty, new_qty, reference_number, reason, notes))

            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': f"Failed to record stock out: {str(e)}"}), 500

        return jsonify({
            'success': True,
            'message': f"Removed {quantity_removed} units from '{product['name']}'. Remaining stock: {new_qty} {product['unit']}.",
            'previous_quantity': prev_qty,
            'new_quantity': new_qty
        })

    @app.route('/api/stock/adjust', methods=['POST'])
    def stock_adjust():
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No input data.'}), 400

        product_id = data.get('product_id')
        if not product_id:
            return jsonify({'success': False, 'error': 'Product selection is required.'}), 400

        try:
            actual_quantity = int(data.get('actual_quantity', -1))
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Actual quantity must be a valid whole number.'}), 400

        if actual_quantity < 0:
            return jsonify({'success': False, 'error': 'Actual quantity cannot be negative.'}), 400

        reason = data.get('reason', 'Physical Inventory Audit').strip() or 'Physical Inventory Audit'
        notes = data.get('notes', '').strip()
        ref_number = data.get('reference_number', '').strip() or f"ADJ-{datetime.now().strftime('%y%m%d%H%M')}"

        conn = database.get_db()
        cursor = conn.cursor()

        try:
            product = cursor.execute("SELECT * FROM products WHERE id = ? AND is_deleted = 0", (product_id,)).fetchone()
            if not product:
                return jsonify({'success': False, 'error': 'Product not found.'}), 404

            prev_qty = product['quantity']
            delta = actual_quantity - prev_qty

            cursor.execute("""
                UPDATE products 
                SET quantity = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            """, (actual_quantity, product_id))

            cursor.execute("""
                INSERT INTO inventory_transactions
                (product_id, product_name_cache, product_sku_cache, transaction_type, quantity_changed, previous_quantity, new_quantity, supplier_id, reference_number, reason, notes)
                VALUES (?, ?, ?, 'Stock Adjustment', ?, ?, ?, ?, ?, ?, ?)
            """, (product_id, product['name'], product['sku'], delta, prev_qty, actual_quantity, product['supplier_id'], ref_number, reason, notes))

            conn.commit()
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': f"Failed to record adjustment: {str(e)}"}), 500

        return jsonify({
            'success': True,
            'message': f"Stock for '{product['name']}' adjusted from {prev_qty} to {actual_quantity} (Difference: {delta:+d}).",
            'previous_quantity': prev_qty,
            'new_quantity': actual_quantity,
            'delta': delta
        })

    # -------------------------------------------------------------
    # API ENDPOINTS: SUPPLIERS CRUD
    # -------------------------------------------------------------
    @app.route('/api/suppliers', methods=['GET'])
    def get_suppliers():
        search = request.args.get('search', '').strip()
        conn = database.get_db()

        query = """
            SELECT s.*, COUNT(p.id) as product_count
            FROM suppliers s
            LEFT JOIN products p ON s.id = p.supplier_id AND p.is_deleted = 0
            WHERE 1=1
        """
        params = []
        if search:
            query += " AND (s.supplier_name LIKE ? OR s.company_name LIKE ? OR s.contact_person LIKE ? OR s.email LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term])

        query += " GROUP BY s.id ORDER BY s.supplier_name ASC"

        rows = conn.execute(query, params).fetchall()
        suppliers = []
        for r in rows:
            suppliers.append({
                'id': r['id'],
                'supplier_name': r['supplier_name'],
                'company_name': r['company_name'] or '',
                'contact_person': r['contact_person'] or '',
                'phone': r['phone'] or '',
                'email': r['email'] or '',
                'address': r['address'] or '',
                'notes': r['notes'] or '',
                'product_count': r['product_count'],
                'created_at': r['created_at']
            })

        return jsonify({'success': True, 'count': len(suppliers), 'suppliers': suppliers})

    @app.route('/api/suppliers', methods=['POST'])
    def create_supplier():
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No supplier data provided.'}), 400

        name = data.get('supplier_name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': 'Supplier name is required.'}), 400

        company_name = data.get('company_name', '').strip()
        contact_person = data.get('contact_person', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip()
        address = data.get('address', '').strip()
        notes = data.get('notes', '').strip()

        # Validate email if provided
        if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return jsonify({'success': False, 'error': 'Invalid email address format.'}), 400

        conn = database.get_db()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO suppliers (supplier_name, company_name, contact_person, phone, email, address, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (name, company_name, contact_person, phone, email, address, notes))
            conn.commit()
            supplier_id = cursor.lastrowid
        except Exception as e:
            conn.rollback()
            return jsonify({'success': False, 'error': f"Database error creating supplier: {str(e)}"}), 500

        return jsonify({
            'success': True,
            'message': f"Supplier '{name}' registered successfully.",
            'supplier_id': supplier_id
        }), 201

    @app.route('/api/suppliers/<int:supplier_id>', methods=['GET'])
    def get_supplier(supplier_id):
        conn = database.get_db()
        supp = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if not supp:
            return jsonify({'success': False, 'error': 'Supplier not found.'}), 404

        products = conn.execute("""
            SELECT id, sku, name, category, quantity, unit, purchase_price, selling_price
            FROM products 
            WHERE supplier_id = ? AND is_deleted = 0
            ORDER BY name ASC
        """, (supplier_id,)).fetchall()

        prod_list = [dict(p) for p in products]

        return jsonify({
            'success': True,
            'supplier': dict(supp),
            'products': prod_list
        })

    @app.route('/api/suppliers/<int:supplier_id>', methods=['PUT'])
    def update_supplier(supplier_id):
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No input data.'}), 400

        conn = database.get_db()
        supp = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if not supp:
            return jsonify({'success': False, 'error': 'Supplier not found.'}), 404

        name = data.get('supplier_name', supp['supplier_name']).strip()
        if not name:
            return jsonify({'success': False, 'error': 'Supplier name cannot be blank.'}), 400

        company_name = data.get('company_name', supp['company_name'] or '').strip()
        contact_person = data.get('contact_person', supp['contact_person'] or '').strip()
        phone = data.get('phone', supp['phone'] or '').strip()
        email = data.get('email', supp['email'] or '').strip()
        address = data.get('address', supp['address'] or '').strip()
        notes = data.get('notes', supp['notes'] or '').strip()

        if email and not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            return jsonify({'success': False, 'error': 'Invalid email address format.'}), 400

        conn.execute("""
            UPDATE suppliers 
            SET supplier_name = ?, company_name = ?, contact_person = ?, phone = ?, email = ?, address = ?, notes = ?
            WHERE id = ?
        """, (name, company_name, contact_person, phone, email, address, notes, supplier_id))
        conn.commit()

        return jsonify({'success': True, 'message': f"Supplier '{name}' updated successfully."})

    @app.route('/api/suppliers/<int:supplier_id>', methods=['DELETE'])
    def delete_supplier(supplier_id):
        conn = database.get_db()
        supp = conn.execute("SELECT * FROM suppliers WHERE id = ?", (supplier_id,)).fetchone()
        if not supp:
            return jsonify({'success': False, 'error': 'Supplier not found.'}), 404

        # Association check
        linked_count = conn.execute("""
            SELECT COUNT(*) as c FROM products WHERE supplier_id = ? AND is_deleted = 0
        """, (supplier_id,)).fetchone()['c']

        if linked_count > 0:
            return jsonify({
                'success': False,
                'error': f"Cannot delete supplier '{supp['supplier_name']}' because it is associated with {linked_count} active product(s). Please reassign or update those products first."
            }), 400

        conn.execute("DELETE FROM suppliers WHERE id = ?", (supplier_id,))
        conn.commit()

        return jsonify({'success': True, 'message': f"Supplier '{supp['supplier_name']}' deleted successfully."})

    # -------------------------------------------------------------
    # API ENDPOINTS: LOW-STOCK ALERTS
    # -------------------------------------------------------------
    @app.route('/api/alerts', methods=['GET'])
    def get_alerts():
        conn = database.get_db()
        multiplier = float(database.get_setting('target_stock_multiplier', '2.0'))

        rows = conn.execute("""
            SELECT p.*, s.supplier_name, s.phone as supplier_phone, s.email as supplier_email
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.is_deleted = 0 AND p.quantity <= p.minimum_stock
            ORDER BY p.quantity ASC, p.minimum_stock DESC
        """).fetchall()

        alerts = []
        out_of_stock_count = 0
        low_stock_count = 0

        for r in rows:
            qty = r['quantity']
            min_thresh = r['minimum_stock']
            # Target replenishment: multiplier * minimum_stock or at least +10 units
            target_stock = int(max(min_thresh * multiplier, min_thresh + 10))
            suggested_replenish = max(target_stock - qty, 1)

            if qty == 0:
                out_of_stock_count += 1
                status = 'Out of Stock'
                badge_type = 'danger'
                severity = 1
            else:
                low_stock_count += 1
                status = 'Low Stock'
                badge_type = 'warning'
                severity = 2

            alerts.append({
                'id': r['id'],
                'sku': r['sku'],
                'name': r['name'],
                'category': r['category'],
                'quantity': qty,
                'minimum_stock': min_thresh,
                'unit': r['unit'],
                'status': status,
                'badge_type': badge_type,
                'severity': severity,
                'suggested_replenish': suggested_replenish,
                'target_stock': target_stock,
                'supplier_id': r['supplier_id'],
                'supplier_name': r['supplier_name'] or 'None',
                'supplier_contact': r['supplier_email'] or r['supplier_phone'] or 'N/A'
            })

        return jsonify({
            'success': True,
            'total_alerts': len(alerts),
            'out_of_stock_count': out_of_stock_count,
            'low_stock_count': low_stock_count,
            'alerts': alerts
        })

    # -------------------------------------------------------------
    # API ENDPOINTS: TRANSACTIONS & HISTORY
    # -------------------------------------------------------------
    @app.route('/api/transactions', methods=['GET'])
    def get_transactions():
        search = request.args.get('search', '').strip()
        trans_type = request.args.get('type', '').strip()
        product_id = request.args.get('product_id', type=int)
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        limit = request.args.get('limit', default=100, type=int)

        query = """
            SELECT t.*, s.supplier_name
            FROM inventory_transactions t
            LEFT JOIN suppliers s ON t.supplier_id = s.id
            WHERE 1=1
        """
        params = []

        if product_id:
            query += " AND t.product_id = ?"
            params.append(product_id)

        if search:
            query += " AND (t.product_name_cache LIKE ? OR t.product_sku_cache LIKE ? OR t.reference_number LIKE ? OR t.reason LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term, term])

        if trans_type and trans_type != 'All':
            query += " AND t.transaction_type = ?"
            params.append(trans_type)

        if start_date:
            query += " AND date(t.created_at) >= date(?)"
            params.append(start_date)

        if end_date:
            query += " AND date(t.created_at) <= date(?)"
            params.append(end_date)

        query += " ORDER BY t.created_at DESC, t.id DESC LIMIT ?"
        params.append(limit)

        conn = database.get_db()
        rows = conn.execute(query, params).fetchall()

        records = []
        for r in rows:
            records.append({
                'id': r['id'],
                'product_id': r['product_id'],
                'product_name': r['product_name_cache'],
                'product_sku': r['product_sku_cache'] or '-',
                'transaction_type': r['transaction_type'],
                'quantity_changed': r['quantity_changed'],
                'previous_quantity': r['previous_quantity'],
                'new_quantity': r['new_quantity'],
                'supplier_name': r['supplier_name'] or 'N/A',
                'reference_number': r['reference_number'] or '-',
                'reason': r['reason'] or '-',
                'notes': r['notes'] or '',
                'created_at': r['created_at']
            })

        return jsonify({'success': True, 'count': len(records), 'transactions': records})

    # -------------------------------------------------------------
    # API ENDPOINTS: REPORTS AND ANALYTICS
    # -------------------------------------------------------------
    @app.route('/api/reports/data', methods=['GET'])
    def get_report_data():
        report_type = request.args.get('type', 'current_inventory').strip()
        conn = database.get_db()

        if report_type == 'current_inventory':
            rows = conn.execute("""
                SELECT p.sku, p.name, p.category, p.quantity, p.minimum_stock, p.unit,
                       p.purchase_price, p.selling_price, (p.quantity * p.purchase_price) as total_valuation,
                       s.supplier_name
                FROM products p
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE p.is_deleted = 0
                ORDER BY p.category, p.name
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        elif report_type == 'low_stock':
            rows = conn.execute("""
                SELECT p.sku, p.name, p.category, p.quantity, p.minimum_stock, p.unit,
                       (p.minimum_stock * 2 - p.quantity) as recommended_reorder,
                       s.supplier_name, s.phone, s.email
                FROM products p
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE p.is_deleted = 0 AND p.quantity > 0 AND p.quantity <= p.minimum_stock
                ORDER BY p.quantity ASC
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        elif report_type == 'out_of_stock':
            rows = conn.execute("""
                SELECT p.sku, p.name, p.category, p.minimum_stock, p.unit,
                       (p.minimum_stock * 2) as recommended_reorder,
                       s.supplier_name, s.phone, s.email
                FROM products p
                LEFT JOIN suppliers s ON p.supplier_id = s.id
                WHERE p.is_deleted = 0 AND p.quantity = 0
                ORDER BY p.name ASC
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        elif report_type == 'stock_in':
            rows = conn.execute("""
                SELECT t.created_at, t.product_name_cache as product_name, t.product_sku_cache as sku,
                       t.quantity_changed, t.previous_quantity, t.new_quantity,
                       t.reference_number, t.reason, s.supplier_name
                FROM inventory_transactions t
                LEFT JOIN suppliers s ON t.supplier_id = s.id
                WHERE t.transaction_type = 'Stock In'
                ORDER BY t.created_at DESC
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        elif report_type == 'stock_out':
            rows = conn.execute("""
                SELECT t.created_at, t.product_name_cache as product_name, t.product_sku_cache as sku,
                       ABS(t.quantity_changed) as quantity_removed, t.previous_quantity, t.new_quantity,
                       t.reference_number, t.reason, t.notes
                FROM inventory_transactions t
                WHERE t.transaction_type = 'Stock Out'
                ORDER BY t.created_at DESC
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        elif report_type == 'supplier_report':
            rows = conn.execute("""
                SELECT s.supplier_name, s.company_name, s.contact_person, s.phone, s.email,
                       COUNT(p.id) as total_products_supplied,
                       COALESCE(SUM(p.quantity), 0) as total_units_in_stock,
                       COALESCE(SUM(p.quantity * p.purchase_price), 0.0) as total_inventory_value
                FROM suppliers s
                LEFT JOIN products p ON s.id = p.supplier_id AND p.is_deleted = 0
                GROUP BY s.id
                ORDER BY total_inventory_value DESC
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        elif report_type == 'inventory_valuation':
            summary = conn.execute("""
                SELECT 
                    COUNT(*) as total_items,
                    COALESCE(SUM(quantity), 0) as total_quantity,
                    COALESCE(SUM(quantity * purchase_price), 0.0) as total_cost_value,
                    COALESCE(SUM(quantity * selling_price), 0.0) as total_retail_value
                FROM products 
                WHERE is_deleted = 0
            """).fetchone()

            categories = conn.execute("""
                SELECT category, COUNT(*) as items, SUM(quantity) as total_qty,
                       SUM(quantity * purchase_price) as cost_value,
                       SUM(quantity * selling_price) as retail_value
                FROM products
                WHERE is_deleted = 0
                GROUP BY category
                ORDER BY cost_value DESC
            """).fetchall()

            cost = float(summary['total_cost_value'])
            retail = float(summary['total_retail_value'])
            margin = retail - cost

            return jsonify({
                'success': True,
                'report_type': report_type,
                'summary': {
                    'total_items': summary['total_items'],
                    'total_quantity': summary['total_quantity'],
                    'total_cost_value': round(cost, 2),
                    'total_retail_value': round(retail, 2),
                    'projected_margin': round(margin, 2),
                    'margin_percent': round((margin / cost * 100) if cost > 0 else 0, 1)
                },
                'categories': [dict(c) for c in categories]
            })

        elif report_type == 'transactions_report':
            rows = conn.execute("""
                SELECT t.id, t.created_at, t.product_name_cache as product_name, t.product_sku_cache as sku,
                       t.transaction_type, t.quantity_changed, t.previous_quantity, t.new_quantity,
                       t.reference_number, t.reason, s.supplier_name
                FROM inventory_transactions t
                LEFT JOIN suppliers s ON t.supplier_id = s.id
                ORDER BY t.created_at DESC
                LIMIT 500
            """).fetchall()
            return jsonify({'success': True, 'report_type': report_type, 'data': [dict(r) for r in rows]})

        return jsonify({'success': False, 'error': f"Unknown report type: '{report_type}'"}), 400

    # -------------------------------------------------------------
    # CSV EXPORTS (Products, Transactions, Low-Stock, Reports)
    # -------------------------------------------------------------
    @app.route('/export/products/csv')
    def export_products_csv():
        conn = database.get_db()
        rows = conn.execute("""
            SELECT p.sku, p.name, p.category, p.description, p.quantity, p.minimum_stock, p.unit,
                   p.purchase_price, p.selling_price, (p.quantity * p.purchase_price) as valuation,
                   s.supplier_name, p.created_at
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.is_deleted = 0
            ORDER BY p.name ASC
        """).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['SKU', 'Product Name', 'Category', 'Description', 'Current Stock', 'Min Stock', 'Unit', 'Purchase Price', 'Selling Price', 'Inventory Valuation', 'Supplier', 'Created At'])

        for r in rows:
            writer.writerow([
                r['sku'], r['name'], r['category'], r['description'], r['quantity'],
                r['minimum_stock'], r['unit'], f"{r['purchase_price']:.2f}",
                f"{r['selling_price']:.2f}", f"{r['valuation']:.2f}",
                r['supplier_name'] or 'N/A', r['created_at']
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f"attachment; filename=products_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response

    @app.route('/export/transactions/csv')
    def export_transactions_csv():
        trans_type = request.args.get('type', '').strip()
        search = request.args.get('search', '').strip()
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        query = """
            SELECT t.id, t.created_at, t.product_name_cache, t.product_sku_cache,
                   t.transaction_type, t.quantity_changed, t.previous_quantity, t.new_quantity,
                   t.reference_number, t.reason, t.notes, s.supplier_name
            FROM inventory_transactions t
            LEFT JOIN suppliers s ON t.supplier_id = s.id
            WHERE 1=1
        """
        params = []
        if trans_type and trans_type != 'All':
            query += " AND t.transaction_type = ?"
            params.append(trans_type)
        if search:
            query += " AND (t.product_name_cache LIKE ? OR t.product_sku_cache LIKE ? OR t.reference_number LIKE ?)"
            term = f"%{search}%"
            params.extend([term, term, term])
        if start_date:
            query += " AND date(t.created_at) >= date(?)"
            params.append(start_date)
        if end_date:
            query += " AND date(t.created_at) <= date(?)"
            params.append(end_date)

        query += " ORDER BY t.created_at DESC"

        conn = database.get_db()
        rows = conn.execute(query, params).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Transaction ID', 'Date & Time', 'Product SKU', 'Product Name', 'Transaction Type', 'Quantity Changed', 'Previous Stock', 'New Stock', 'Reference Number', 'Reason', 'Supplier', 'Notes'])

        for r in rows:
            writer.writerow([
                r['id'], r['created_at'], r['product_sku_cache'] or '-', r['product_name_cache'],
                r['transaction_type'], r['quantity_changed'], r['previous_quantity'],
                r['new_quantity'], r['reference_number'] or '-', r['reason'] or '-',
                r['supplier_name'] or 'N/A', r['notes'] or ''
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f"attachment; filename=transactions_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response

    @app.route('/export/low-stock/csv')
    def export_low_stock_csv():
        conn = database.get_db()
        rows = conn.execute("""
            SELECT p.sku, p.name, p.category, p.quantity, p.minimum_stock, p.unit,
                   CASE WHEN p.quantity = 0 THEN 'Out of Stock' ELSE 'Low Stock' END as alert_status,
                   (p.minimum_stock * 2 - p.quantity) as suggested_reorder,
                   s.supplier_name, s.contact_person, s.phone, s.email
            FROM products p
            LEFT JOIN suppliers s ON p.supplier_id = s.id
            WHERE p.is_deleted = 0 AND p.quantity <= p.minimum_stock
            ORDER BY p.quantity ASC, p.minimum_stock DESC
        """).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['SKU', 'Product Name', 'Category', 'Current Stock', 'Min Threshold', 'Unit', 'Alert Status', 'Suggested Replenishment', 'Supplier', 'Contact Person', 'Phone', 'Email'])

        for r in rows:
            writer.writerow([
                r['sku'], r['name'], r['category'], r['quantity'], r['minimum_stock'],
                r['unit'], r['alert_status'], max(r['suggested_reorder'], 1),
                r['supplier_name'] or 'None', r['contact_person'] or '-',
                r['phone'] or '-', r['email'] or '-'
            ])

        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = f"attachment; filename=low_stock_alerts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response

    # -------------------------------------------------------------
    # SETTINGS & DEMO DATA MANAGEMENT
    # -------------------------------------------------------------
    @app.route('/api/settings', methods=['GET'])
    def get_settings():
        conn = database.get_db()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings_dict = {r['key']: r['value'] for r in rows}
        return jsonify({'success': True, 'settings': settings_dict})

    @app.route('/api/settings', methods=['POST'])
    def save_settings():
        data = request.get_json() or request.form.to_dict()
        if not data:
            return jsonify({'success': False, 'error': 'No settings provided.'}), 400

        for key in ['company_name', 'currency_symbol', 'target_stock_multiplier', 'enable_low_stock_banner']:
            if key in data:
                database.set_setting(key, data[key])

        return jsonify({'success': True, 'message': 'System settings saved successfully.'})

    @app.route('/api/demo/seed', methods=['POST'])
    def seed_demo():
        ok, msg = database.seed_demo_data()
        if not ok:
            return jsonify({'success': False, 'error': msg}), 400
        return jsonify({'success': True, 'message': msg})

    @app.route('/api/demo/clear', methods=['POST'])
    def clear_demo():
        ok, msg = database.clear_all_data()
        return jsonify({'success': True, 'message': msg})

    # -------------------------------------------------------------
    # GLOBAL ERROR HANDLERS (No raw stack traces shown to end users)
    # -------------------------------------------------------------
    @app.errorhandler(404)
    def not_found_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'Requested API resource not found.'}), 404
        return render_template('base.html', not_found=True), 404

    @app.errorhandler(500)
    def internal_error(error):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'error': 'An internal server error occurred. Please try again.'}), 500
        return render_template('base.html', server_error=True), 500

    return app


app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
