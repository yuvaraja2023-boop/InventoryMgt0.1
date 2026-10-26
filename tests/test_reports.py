"""
Tests for Dashboard Statistics, Reports Engine, Valuation, and CSV Exports.
Verifies real-time calculations from database and downloadable exports.
"""

import json


def test_dashboard_stats_calculation(client):
    """Test dashboard statistics calculated dynamically from SQLite database."""
    response = client.get('/api/dashboard/stats')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    stats = data['stats']

    # In conftest baseline:
    # Prod 1: qty 50, purchase 100.0 -> val 5000.0
    # Prod 2: qty 4, purchase 30.0 -> val 120.0 (low stock, min 10)
    # Prod 3: qty 0, purchase 15.0 -> val 0.0 (out of stock, min 5)
    # Supplier: 1
    assert stats['total_products'] == 3
    assert stats['total_units'] == 54
    assert stats['low_stock_products'] == 1
    assert stats['out_of_stock_products'] == 1
    assert stats['total_suppliers'] == 1
    assert stats['total_inventory_value'] == 5120.0


def test_reports_inventory_valuation(client):
    """Test inventory valuation statement reporting cost, retail, and gross margin."""
    response = client.get('/api/reports/data?type=inventory_valuation')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    summary = data['summary']

    # Total cost = 5120.0
    # Retail = (50 * 150.0) + (4 * 60.0) + (0 * 30.0) = 7500 + 240 = 7740.0
    assert summary['total_cost_value'] == 5120.0
    assert summary['total_retail_value'] == 7740.0
    assert summary['projected_margin'] == 7740.0 - 5120.0  # 2620.0


def test_reports_current_inventory(client):
    """Test current inventory master report data."""
    response = client.get('/api/reports/data?type=current_inventory')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert len(data['data']) == 3


def test_reports_low_stock(client):
    """Test low-stock report returns items where quantity <= minimum_stock."""
    response = client.get('/api/reports/data?type=low_stock')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    # In conftest, only product 2 is low stock (qty 4 <= min 10)
    assert len(data['data']) == 1
    assert data['data'][0]['sku'] == 'TEST-SKU-002'


def test_export_products_csv(client):
    """Test product catalog export to CSV."""
    response = client.get('/export/products/csv')
    assert response.status_code == 200
    assert 'text/csv' in response.headers['Content-Type']
    assert 'attachment' in response.headers['Content-Disposition']
    content = response.data.decode('utf-8')
    assert 'SKU,Product Name,Category' in content
    assert 'TEST-SKU-001' in content


def test_export_transactions_csv(client):
    """Test inventory transactions export to CSV."""
    response = client.get('/export/transactions/csv')
    assert response.status_code == 200
    assert 'text/csv' in response.headers['Content-Type']
    assert 'attachment' in response.headers['Content-Disposition']
    content = response.data.decode('utf-8')
    assert 'Transaction ID,Date & Time,Product SKU' in content


def test_export_low_stock_csv(client):
    """Test low stock alert export to CSV."""
    response = client.get('/export/low-stock/csv')
    assert response.status_code == 200
    assert 'text/csv' in response.headers['Content-Type']
    assert 'attachment' in response.headers['Content-Disposition']
    content = response.data.decode('utf-8')
    assert 'SKU,Product Name,Category,Current Stock' in content
    assert 'TEST-SKU-002' in content
