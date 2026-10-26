"""
Tests for Stock Management & Automatic Low-Stock Alerts.
Verifies Stock-In, Stock-Out, negative stock rejection, stock adjustment, and alert triggers.
"""

import json


def test_stock_in_increases_quantity(client):
    """Test that recording a stock-in transaction increases product stock balance."""
    # Product 1 starts with quantity 50
    payload = {
        'product_id': 1,
        'quantity': 25,
        'reference_number': 'PO-TEST-001',
        'reason': 'Purchase Fulfillment',
        'notes': 'Arrived in dock 1'
    }
    response = client.post('/api/stock/in', json=payload)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['previous_quantity'] == 50
    assert data['new_quantity'] == 75

    # Verify via product API
    prod_res = client.get('/api/products/1')
    assert json.loads(prod_res.data)['product']['quantity'] == 75


def test_stock_out_decreases_quantity(client):
    """Test that recording a stock-out decreases product stock balance."""
    # Product 1 has stock 75 (or 50 if standalone, conftest provides 50)
    # Let's perform stock out of 10
    payload = {
        'product_id': 1,
        'quantity': 10,
        'reference_number': 'SO-TEST-001',
        'reason': 'Customer Order Dispatch'
    }
    response = client.post('/api/stock/out', json=payload)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['new_quantity'] == data['previous_quantity'] - 10


def test_stock_out_insufficient_stock_rejected(client):
    """Test that attempting to remove more stock than available is strictly rejected (No negative stock)."""
    # Product 2 has quantity 4 in conftest
    payload = {
        'product_id': 2,
        'quantity': 20,  # 20 > 4
        'reason': 'Excessive order'
    }
    response = client.post('/api/stock/out', json=payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False
    assert 'insufficient stock' in data['error'].lower()

    # Verify stock remained untouched at 4
    prod_res = client.get('/api/products/2')
    assert json.loads(prod_res.data)['product']['quantity'] == 4


def test_stock_adjustment_reconciles_count(client):
    """Test physical stock adjustment records delta and updates system balance."""
    # Product 1 previous stock: let's adjust to 62
    get_res = client.get('/api/products/1')
    prev_qty = json.loads(get_res.data)['product']['quantity']

    payload = {
        'product_id': 1,
        'actual_quantity': 62,
        'reason': 'Physical Cycle Count Audit',
        'reference_number': 'AUDIT-TEST-01',
        'notes': 'Reconciled during shift change'
    }
    response = client.post('/api/stock/adjust', json=payload)
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['new_quantity'] == 62
    assert data['delta'] == 62 - prev_qty


def test_automatic_low_stock_detection(client):
    """Test low stock alert detection and suggested replenishment calculation."""
    response = client.get('/api/alerts')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True

    # Product 2 (qty 4 <= min 10) -> Low Stock
    # Product 3 (qty 0) -> Out of Stock
    # Total alerts should be 2
    assert data['total_alerts'] == 2
    assert data['out_of_stock_count'] == 1
    assert data['low_stock_count'] == 1

    alerts_by_sku = {a['sku']: a for a in data['alerts']}
    assert alerts_by_sku['TEST-SKU-003']['status'] == 'Out of Stock'
    assert alerts_by_sku['TEST-SKU-002']['status'] == 'Low Stock'
    assert alerts_by_sku['TEST-SKU-002']['suggested_replenish'] > 0
