/**
 * Smart Inventory Management System - Global Application Logic
 * Manages Theme Toggle (Dark/Light), Sidebar Responsive Navigation,
 * Global Live Search, Toast Notifications, and Dynamic Modals.
 */

// Initialize immediately on DOM load
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initSidebarToggle();
  initGlobalSearch();
  initAlertsDropdown();
});

/* ==========================================================================
   THEME TOGGLE (DARK / LIGHT MODE)
   ========================================================================== */
function initTheme() {
  const savedTheme = localStorage.getItem('sims_theme') || 'light';
  document.documentElement.setAttribute('data-bs-theme', savedTheme);
  updateThemeIcon(savedTheme);

  const toggleBtn = document.getElementById('themeToggleBtn');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-bs-theme') || 'light';
      const newTheme = currentTheme === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-bs-theme', newTheme);
      localStorage.setItem('sims_theme', newTheme);
      updateThemeIcon(newTheme);

      // Trigger custom event so Chart.js charts can re-color if present
      window.dispatchEvent(new CustomEvent('themeChanged', { detail: { theme: newTheme } }));
    });
  }
}

function updateThemeIcon(theme) {
  const icon = document.getElementById('themeIcon');
  if (icon) {
    if (theme === 'dark') {
      icon.className = 'bi bi-sun-fill text-warning';
    } else {
      icon.className = 'bi bi-moon-stars-fill text-secondary';
    }
  }
}

/* ==========================================================================
   SIDEBAR TOGGLE (MOBILE & DESKTOP RESPONSIVENESS)
   ========================================================================== */
function initSidebarToggle() {
  const toggleBtn = document.getElementById('sidebarToggleBtn');
  const sidebar = document.getElementById('appSidebar');

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', () => {
      sidebar.classList.toggle('show-sidebar');
    });

    // Close on mobile when clicking outside
    document.addEventListener('click', (e) => {
      if (window.innerWidth < 992) {
        if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target) && sidebar.classList.contains('show-sidebar')) {
          sidebar.classList.remove('show-sidebar');
        }
      }
    });
  }
}

/* ==========================================================================
   GLOBAL SEARCH WITH LIVE DROPDOWN & CTRL+K
   ========================================================================== */
function initGlobalSearch() {
  const searchInput = document.getElementById('globalSearchInput');
  const resultsDropdown = document.getElementById('searchResultsDropdown');

  if (!searchInput || !resultsDropdown) return;

  // Keyboard shortcut: Ctrl + K or Cmd + K to focus search
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      searchInput.focus();
      searchInput.select();
    }
  });

  let debounceTimer;
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    const query = searchInput.value.trim();

    if (query.length < 2) {
      resultsDropdown.style.display = 'none';
      resultsDropdown.innerHTML = '';
      return;
    }

    debounceTimer = setTimeout(() => {
      fetchSearchResults(query);
    }, 250);
  });

  // Hide dropdown when clicking outside
  document.addEventListener('click', (e) => {
    if (!searchInput.contains(e.target) && !resultsDropdown.contains(e.target)) {
      resultsDropdown.style.display = 'none';
    }
  });

  async function fetchSearchResults(query) {
    try {
      const res = await fetch(`/api/products?search=${encodeURIComponent(query)}`);
      const data = await res.json();

      if (!data.success || !data.products || data.products.length === 0) {
        resultsDropdown.innerHTML = `
          <div class="p-3 text-center text-muted small">
            <i class="bi bi-search me-1"></i> No matching products found for "${escapeHtml(query)}"
          </div>`;
        resultsDropdown.style.display = 'block';
        return;
      }

      let html = '';
      data.products.slice(0, 6).forEach(p => {
        const badgeClass = p.status_badge === 'danger' ? 'badge-status-danger' : 
                          p.status_badge === 'warning' ? 'badge-status-warning' : 'badge-status-success';
        html += `
          <a href="/products/${p.id}" class="search-result-item">
            <div>
              <div class="fw-semibold text-truncate" style="max-width: 280px;">${escapeHtml(p.name)}</div>
              <div class="small text-muted">${escapeHtml(p.sku)} &bull; ${escapeHtml(p.category)}</div>
            </div>
            <div class="text-end">
              <span class="badge-status ${badgeClass}">${escapeHtml(p.stock_status)}</span>
              <div class="small fw-bold mt-1">${p.quantity} ${escapeHtml(p.unit)}</div>
            </div>
          </a>
        `;
      });

      resultsDropdown.innerHTML = html;
      resultsDropdown.style.display = 'block';
    } catch (err) {
      console.error('Search error:', err);
    }
  }
}

/* ==========================================================================
   ALERTS BELL DROPDOWN & LIVE REFRESH
   ========================================================================== */
async function initAlertsDropdown() {
  const notifList = document.getElementById('notifDropdownList');
  const notifCountBadge = document.getElementById('notifCountBadge');
  const sidebarAlertBadge = document.getElementById('sidebarAlertBadge');

  if (!notifList) return;

  try {
    const res = await fetch('/api/alerts');
    const data = await res.json();

    if (data.success) {
      const total = data.total_alerts;

      if (notifCountBadge) {
        if (total > 0) {
          notifCountBadge.textContent = total;
          notifCountBadge.style.display = 'flex';
        } else {
          notifCountBadge.style.display = 'none';
        }
      }

      if (sidebarAlertBadge) {
        if (total > 0) {
          sidebarAlertBadge.textContent = total;
          sidebarAlertBadge.style.display = 'inline-block';
        } else {
          sidebarAlertBadge.style.display = 'none';
        }
      }

      if (data.alerts.length === 0) {
        notifList.innerHTML = `
          <div class="p-4 text-center text-muted small">
            <i class="bi bi-check-circle-fill text-success fs-3 d-block mb-1"></i>
            All inventory levels healthy. No low stock alerts!
          </div>`;
      } else {
        let html = '';
        data.alerts.slice(0, 5).forEach(alert => {
          const icon = alert.quantity === 0 ? 'bi-x-circle-fill text-danger' : 'bi-exclamation-triangle-fill text-warning';
          html += `
            <a href="/alerts" class="notification-item text-decoration-none">
              <i class="bi ${icon} fs-5 mt-1"></i>
              <div class="flex-grow-1 overflow-hidden">
                <div class="fw-semibold text-truncate small">${escapeHtml(alert.name)}</div>
                <div class="text-muted" style="font-size: 0.75rem;">
                  Stock: <strong>${alert.quantity}</strong> / Min: ${alert.minimum_stock} ${escapeHtml(alert.unit)}
                </div>
              </div>
            </a>
          `;
        });
        notifList.innerHTML = html;
      }
    }
  } catch (err) {
    console.error('Failed to load alert notifications:', err);
  }
}

/* ==========================================================================
   TOAST NOTIFICATION HELPER
   ========================================================================== */
function showToast(message, type = 'success') {
  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    document.body.appendChild(container);
  }

  const icon = type === 'success' ? 'bi-check-circle-fill text-success' :
               type === 'danger' ? 'bi-x-circle-fill text-danger' :
               type === 'warning' ? 'bi-exclamation-triangle-fill text-warning' : 'bi-info-circle-fill text-info';

  const toastEl = document.createElement('div');
  toastEl.className = 'toast toast-custom align-items-center show shadow-lg';
  toastEl.setAttribute('role', 'alert');
  toastEl.setAttribute('aria-live', 'assertive');
  toastEl.setAttribute('aria-atomic', 'true');

  toastEl.innerHTML = `
    <div class="d-flex align-items-center p-3">
      <i class="bi ${icon} fs-5 me-2"></i>
      <div class="toast-body p-0 flex-grow-1 fw-medium" style="font-size: 0.88rem;">
        ${escapeHtml(message)}
      </div>
      <button type="button" class="btn-close ms-2" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
  `;

  container.appendChild(toastEl);

  const bsToast = new bootstrap.Toast(toastEl, { delay: 4500 });
  bsToast.show();

  toastEl.addEventListener('hidden.bs.toast', () => {
    toastEl.remove();
  });
}

/* ==========================================================================
   ESCAPE HTML UTILITY
   ========================================================================== */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
