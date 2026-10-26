"""
Tests for Supplier Management module.
Verifies supplier creation, validation, contact details, and product association protections.
"""

import json


def test_get_suppliers(client):
    """Test retrieving list of suppliers."""
    response = client.get('/api/suppliers')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['count'] >= 1
    # Vendor 1 is associated with 3 products in conftest baseline
    vendor = next(s for s in data['suppliers'] if s['id'] == 1)
    assert vendor['supplier_name'] == 'Test Vendor Global'
    assert vendor['product_count'] == 3


def test_create_supplier_success(client):
    """Test registering a new supplier with valid fields."""
    payload = {
        'supplier_name': 'Precision Cables Ltd',
        'company_name': 'Precision Wire & Cable Inc',
        'contact_person': 'Alice Smith',
        'phone': '+1 (555) 765-4321',
        'email': 'alice@precisioncables.com',
        'address': '89 Copper Street, Phoenix, AZ',
        'notes': 'Preferred cabling vendor'
    }
    response = client.post('/api/suppliers', json=payload)
    assert response.status_code == 201
    data = json.loads(response.data)
    assert data['success'] is True
    assert data['supplier_id'] is not None


def test_create_supplier_invalid_email_rejected(client):
    """Test that invalid email formats are rejected."""
    payload = {
        'supplier_name': 'Invalid Email Vendor',
        'email': 'not-an-email-address',
        'phone': '123456'
    }
    response = client.post('/api/suppliers', json=payload)
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False
    assert 'email' in data['error'].lower()


def test_update_supplier(client):
    """Test modifying supplier profile details."""
    payload = {
        'supplier_name': 'Test Vendor Global LLC',
        'contact_person': 'Jane Doe',
        'phone': '+1 (555) 999-0000',
        'email': 'jane@vendor.com',
        'address': '500 Updated Parkway'
    }
    response = client.put('/api/suppliers/1', json=payload)
    assert response.status_code == 200
    assert json.loads(response.data)['success'] is True

    # Verify update
    get_res = client.get('/api/suppliers/1')
    supp = json.loads(get_res.data)['supplier']
    assert supp['supplier_name'] == 'Test Vendor Global LLC'
    assert supp['contact_person'] == 'Jane Doe'


def test_delete_supplier_protected_when_associated(client):
    """Test that deleting a supplier with linked active products is blocked."""
    # Supplier 1 is linked to products 1, 2, 3
    response = client.delete('/api/suppliers/1')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert data['success'] is False
    assert 'cannot delete supplier' in data['error'].lower()
    assert 'associated with' in data['error'].lower()


def test_delete_supplier_success_when_unlinked(client):
    """Test deleting a supplier with zero linked products succeeds."""
    # Create an unlinked supplier first
    create_res = client.post('/api/suppliers', json={
        'supplier_name': 'Temporary Supplier',
        'email': 'temp@example.com'
    })
    supp_id = json.loads(create_res.data)['supplier_id']

    # Delete unlinked supplier
    del_res = client.delete(f'/api/suppliers/{supp_id}')
    assert del_res.status_code == 200
    assert json.loads(del_res.data)['success'] is True
