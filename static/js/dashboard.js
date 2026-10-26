/**
 * Smart Inventory Management System - Dashboard Controller
 * Fetches real-time statistics, updates summary cards, triggers Chart.js,
 * renders recent activity log, and binds quick action modals.
 */

document.addEventListener('DOMContentLoaded', () => {
  loadDashboardData();
  bindQuickActions();
});

let dashboardCurrency = '$';

async function loadDashboardData() {
  await Promise.all([
    fetchDashboardStats(),
    fetchDashboardCharts(),
    fetchRecentActivity()
  ]);
}

// 1. Fetch & Render Summary Cards
async function fetchDashboardStats() {
  try {
    const res = await fetch('/api/dashboard/stats');
    const data = await res.json();

    if (!data.success) return;
    const s = data.stats;
    dashboardCurrency = s.currency_symbol || '$';

    document.getElementById('statTotalProducts').textContent = Number(s.total_products).toLocaleString();
    document.getElementById('statTotalUnits').textContent = Number(s.total_units).toLocaleString();
    document.getElementById('statLowStock').textContent = Number(s.low_stock_products).toLocaleString();
    document.getElementById('statOutOfStock').textContent = Number(s.out_of_stock_products).toLocaleString();
    document.getElementById('statTotalSuppliers').textContent = Number(s.total_suppliers).toLocaleString();
    document.getElementById('statInventoryValue').textContent = `${dashboardCurrency} ${Number(s.total_inventory_value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    // Low stock warning banner if count > 0
    const alertBanner = document.getElementById('dashboardAlertBanner');
    if (alertBanner) {
      const alertTotal = s.low_stock_products + s.out_of_stock_products;
      if (alertTotal > 0) {
        document.getElementById('alertBannerText').textContent = 
          `Attention: ${alertTotal} item(s) require replenishment (${s.out_of_stock_products} out of stock, ${s.low_stock_products} low stock).`;
        alertBanner.classList.remove('d-none');
      } else {
        alertBanner.classList.add('d-none');
      }
    }
  } catch (err) {
    console.error('Failed to load dashboard stats:', err);
  }
}

// 2. Fetch & Render Charts
async function fetchDashboardCharts() {
  try {
    const res = await fetch('/api/dashboard/charts');
    const data = await res.json();

    if (!data.success) return;

    // Category Distribution
    const catData = data.category_distribution;
    const catEmpty = document.getElementById('catChartEmpty');
    const catCanvas = document.getElementById('categoryChart');
    if (catData.labels && catData.labels.length > 0) {
      if (catEmpty) catEmpty.classList.add('d-none');
      if (catCanvas) catCanvas.classList.remove('d-none');
      InventoryCharts.renderCategoryChart('categoryChart', catData.labels, catData.quantities);
    } else {
      if (catEmpty) catEmpty.classList.remove('d-none');
      if (catCanvas) catCanvas.classList.add('d-none');
    }

    // Top Products by Quantity
    const topData = data.top_products;
    const topEmpty = document.getElementById('topChartEmpty');
    const topCanvas = document.getElementById('topProductsChart');
    if (topData.labels && topData.labels.length > 0) {
      if (topEmpty) topEmpty.classList.add('d-none');
      if (topCanvas) topCanvas.classList.remove('d-none');
      InventoryCharts.renderTopProductsChart('topProductsChart', topData.labels, topData.quantities);
    } else {
      if (topEmpty) topEmpty.classList.remove('d-none');
      if (topCanvas) topCanvas.classList.add('d-none');
    }

    // Monthly Stock In vs Stock Out
    const timeline = data.timeline;
    InventoryCharts.renderTimelineChart('timelineChart', timeline.labels, timeline.stock_in, timeline.stock_out);

    // Stock Status Breakdown
    const statusData = data.stock_status;
    InventoryCharts.renderStatusChart('statusChart', statusData.labels, statusData.counts);

  } catch (err) {
    console.error('Failed to load charts:', err);
  }
}

// 3. Fetch & Render Recent Activity Table
async function fetchRecentActivity() {
  const tbody = document.getElementById('recentActivityBody');
  const emptyState = document.getElementById('recentActivityEmpty');
  const tableWrapper = document.getElementById('recentActivityWrapper');
  if (!tbody) return;

  try {
    const res = await fetch('/api/dashboard/recent-activity?limit=8');
    const data = await res.json();

    if (!data.success || !data.activities || data.activities.length === 0) {
      if (emptyState) emptyState.classList.remove('d-none');
      if (tableWrapper) tableWrapper.classList.add('d-none');
      return;
    }

    if (emptyState) emptyState.classList.add('d-none');
    if (tableWrapper) tableWrapper.classList.remove('d-none');

    let html = '';
    data.activities.forEach(act => {
      let badgeClass = 'badge-status-secondary';
      let icon = 'bi-arrow-left-right';

      if (act.transaction_type === 'Stock In') {
        badgeClass = 'badge-status-success';
        icon = 'bi-box-arrow-in-down';
      } else if (act.transaction_type === 'Stock Out') {
        badgeClass = 'badge-status-danger';
        icon = 'bi-box-arrow-up';
      } else if (act.transaction_type === 'Opening Stock') {
        badgeClass = 'badge-status-info';
        icon = 'bi-plus-circle';
      } else if (act.transaction_type === 'Stock Adjustment') {
        badgeClass = 'badge-status-warning';
        icon = 'bi-sliders';
      }

      const qtyPrefix = act.quantity_changed > 0 ? `+${act.quantity_changed}` : `${act.quantity_changed}`;

      html += `
        <tr>
          <td>
            <div class="small fw-semibold">${formatDate(act.date_time)}</div>
            <div class="text-muted" style="font-size: 0.72rem;">Ref: ${escapeHtml(act.reference_number)}</div>
          </td>
          <td>
            <a href="/products/${act.product_id || ''}" class="fw-bold text-decoration-none text-truncate d-inline-block" style="max-width: 220px;">
              ${escapeHtml(act.product_name)}
            </a>
            <div class="small text-muted font-monospace">${escapeHtml(act.sku)}</div>
          </td>
          <td>
            <span class="badge-status ${badgeClass}">
              <i class="bi ${icon}"></i> ${escapeHtml(act.transaction_type)}
            </span>
          </td>
          <td>
            <span class="fw-bold ${act.quantity_changed >= 0 ? 'text-success' : 'text-danger'}">
              ${qtyPrefix}
            </span>
          </td>
          <td>
            <div class="small text-muted">${act.previous_quantity} units</div>
          </td>
          <td>
            <div class="small fw-bold text-main">${act.new_quantity} units</div>
          </td>
        </tr>
      `;
    });

    tbody.innerHTML = html;
  } catch (err) {
    console.error('Failed to load recent activity:', err);
  }
}

// 4. Bind Quick Actions Modals (Product, Stock-In, Stock-Out)
function bindQuickActions() {
  // Populate products dropdown in Stock-In and Stock-Out modals
  const stockInModalEl = document.getElementById('quickStockInModal');
  const stockOutModalEl = document.getElementById('quickStockOutModal');

  if (stockInModalEl) {
    stockInModalEl.addEventListener('show.bs.modal', () => {
      populateProductSelect('stockInProductSelect');
      populateSupplierSelect('stockInSupplierSelect');
    });
  }

  if (stockOutModalEl) {
    stockOutModalEl.addEventListener('show.bs.modal', () => {
      populateProductSelect('stockOutProductSelect');
    });
  }

  // Stock In Form Submit
  const stockInForm = document.getElementById('quickStockInForm');
  if (stockInForm) {
    stockInForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const pId = document.getElementById('stockInProductSelect').value;
      const qty = document.getElementById('stockInQuantity').value;
      const suppId = document.getElementById('stockInSupplierSelect').value;
      const ref = document.getElementById('stockInRef').value;
      const notes = document.getElementById('stockInNotes').value;

      try {
        const res = await fetch('/api/stock/in', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_id: pId,
            quantity: qty,
            supplier_id: suppId,
            reference_number: ref,
            notes: notes
          })
        });
        const data = await res.json();
        if (data.success) {
          bootstrap.Modal.getInstance(stockInModalEl).hide();
          stockInForm.reset();
          showToast(data.message, 'success');
          loadDashboardData();
          initAlertsDropdown();
        } else {
          showToast(data.error || 'Failed to record stock in.', 'danger');
        }
      } catch (err) {
        showToast('Network error processing stock in.', 'danger');
      }
    });
  }

  // Stock Out Form Submit
  const stockOutForm = document.getElementById('quickStockOutForm');
  if (stockOutForm) {
    stockOutForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const pId = document.getElementById('stockOutProductSelect').value;
      const qty = document.getElementById('stockOutQuantity').value;
      const reason = document.getElementById('stockOutReason').value;
      const ref = document.getElementById('stockOutRef').value;
      const notes = document.getElementById('stockOutNotes').value;

      try {
        const res = await fetch('/api/stock/out', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            product_id: pId,
            quantity: qty,
            reason: reason,
            reference_number: ref,
            notes: notes
          })
        });
        const data = await res.json();
        if (data.success) {
          bootstrap.Modal.getInstance(stockOutModalEl).hide();
          stockOutForm.reset();
          showToast(data.message, 'success');
          loadDashboardData();
          initAlertsDropdown();
        } else {
          showToast(data.error || 'Failed to record stock out.', 'danger');
        }
      } catch (err) {
        showToast('Network error processing stock out.', 'danger');
      }
    });
  }
}

// Helper to populate product selects
async function populateProductSelect(elementId) {
  const select = document.getElementById(elementId);
  if (!select) return;

  try {
    const res = await fetch('/api/products');
    const data = await res.json();
    if (data.success) {
      let html = '<option value="">-- Choose Product --</option>';
      data.products.forEach(p => {
        html += `<option value="${p.id}" data-stock="${p.quantity}" data-unit="${escapeHtml(p.unit)}">
          ${escapeHtml(p.name)} (${escapeHtml(p.sku)}) - Available: ${p.quantity} ${escapeHtml(p.unit)}
        </option>`;
      });
      select.innerHTML = html;
    }
  } catch (err) {
    console.error('Failed to populate products:', err);
  }
}

// Helper to populate supplier selects
async function populateSupplierSelect(elementId) {
  const select = document.getElementById(elementId);
  if (!select) return;

  try {
    const res = await fetch('/api/suppliers');
    const data = await res.json();
    if (data.success) {
      let html = '<option value="">-- Default / None --</option>';
      data.suppliers.forEach(s => {
        html += `<option value="${s.id}">${escapeHtml(s.supplier_name)} (${escapeHtml(s.company_name || 'Individual')})</option>`;
      });
      select.innerHTML = html;
    }
  } catch (err) {
    console.error('Failed to populate suppliers:', err);
  }
}

function formatDate(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr.replace(' ', 'T'));
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
