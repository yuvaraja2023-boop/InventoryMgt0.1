"""
Tests for Product Management module and direct dashboard loading.
Verifies CRUD operations, duplicate SKU rejection, price validation, and transaction history preservation.
"""

import json


def test_dashboard_direct_access_no_login(client):
    """Verify that opening the home page loads the inventory dashboard directly without login/signup."""
    response = client.get('/')
    assert response.status_code == 200
    # Must contain dashboard header and not contain login forms or redirects
    html = response.data.decode('utf-8')
    assert 'Inventory Dashboard' in html
    assert 'type="password"' not in html.lower()
    assert 'action="/login"' not in html.lower()
    assert 'sign in' not in html.lower()
    assert 'sign up' not in html.lower()
    assert 'user registration' not in html.lower()


def test_get_products_list(client):
    """Test retrieving products via API."""
    response = client.get('/api/products')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['count'] == 3
    # Verify stock status calculation
    skus = {p['sku']: p['stock_status'] for p in data['products']}
    assert skus['TEST-SKU-001'] == 'In Stock'
    assert skus['TEST-SKU-002'] == 'Low Stock'
    assert skus['TEST-SKU-003'] == 'Out of Stock'


def test_create_product_success(client):
    """Test successful product creation and automatic opening stock transaction."""
    payload = {
        'name': 'Ergonomic Desk Mat',
        'sku': 'MAT-2001',
        'category': 'Office Supplies',
        'supplier_id': 1,
        'purchase_price': 12.50,
        'selling_price': 25.00,
        'quantity': 35,
        'minimum_stock': 8,
        'unit': 'Pieces',
        'description': 'Waterproof desk mat'
    }
    response = client.post('/api/products', json=payload)
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['success'] is True
    assert 'MAT-2001' in data['message']

    # Verify product appears in list
    verify_res = client.get('/api/products?search=MAT-2001')
    v_data = json.loads(verify_res.data)
    assert v_data['count'] == 1
    assert v_data['products'][0]['quantity'] == 35


def test_create_product_duplicate_sku_rejected(client):
    """Test that creating a product with an already existing SKU is strictly rejected."""
    payload = {
        'name': 'Duplicate Product',
        'sku': 'TEST-SKU-001',  # Already exists in conftest baseline
        'category': 'Electronics',
        'purchase_price': 50.0,
        'selling_price': 80.0,
        'quantity': 10,
        'minimum_stock': 5
    }
    response = client.post('/api/products', json=payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False
    assert 'already exists' in data['error'].lower()


def test_create_product_negative_values_rejected(client):
    """Test validation rejecting negative prices and quantities."""
    payload = {
        'name': 'Invalid Values Product',
        'sku': 'NEG-001',
        'category': 'General',
        'purchase_price': -10.0,  # Negative price
        'selling_price': 20.0,
        'quantity': 5,
        'minimum_stock': 2
    }
    response = client.post('/api/products', json=payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False
    assert 'negative' in data['error'].lower()


def test_update_product(client):
    """Test updating existing product information."""
    payload = {
        'name': 'Updated Test Monitor 4K',
        'sku': 'TEST-SKU-001',
        'category': 'Electronics',
        'purchase_price': 110.0,
        'selling_price': 175.0,
        'minimum_stock': 12,
        'unit': 'Units',
        'description': 'Upgraded specification'
    }
    response = client.put('/api/products/1', json=payload)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True

    # Check updated values
    get_res = client.get('/api/products/1')
    p_data = json.loads(get_res.data)['product']
    assert p_data['name'] == 'Updated Test Monitor 4K'
    assert p_data['purchase_price'] == 110.0


def test_delete_product_preserves_history(client):
    """Test deleting product removes it from active list while preserving past transactions."""
    # Delete product 1
    del_res = client.delete('/api/products/1')
    assert del_res.status_code == 200
    assert json.loads(del_res.data)['success'] is True

    # Product should no longer appear in active product list
    list_res = client.get('/api/products')
    active_ids = [p['id'] for p in json.loads(list_res.data)['products']]
    assert 1 not in active_ids
