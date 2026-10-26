/**
 * Smart Inventory Management System - Chart.js Visualizations
 * Provides reusable functions for:
 * 1. Stock Distribution by Category (Doughnut)
 * 2. Top Products by Quantity (Horizontal Bar)
 * 3. Monthly Stock-In vs Stock-Out (Grouped Bar)
 * 4. Stock Health Overview (Status Breakdown Doughnut/Bar)
 */

const InventoryCharts = (() => {
  let categoryChartInstance = null;
  let topProductsChartInstance = null;
  let timelineChartInstance = null;
  let statusChartInstance = null;

  // Modern blue/slate palette
  const colors = {
    primary: '#173B67',
    secondary: '#3478F6',
    teal: '#0D9488',
    amber: '#F59E0B',
    red: '#DC2626',
    purple: '#8B5CF6',
    emerald: '#10B981',
    cyan: '#06B6D4',
    pink: '#EC4899',
    indigo: '#6366F1'
  };

  const palette = [
    '#3478F6', '#173B67', '#0D9488', '#F59E0B', 
    '#8B5CF6', '#10B981', '#06B6D4', '#EC4899'
  ];

  function getTextColor() {
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    return isDark ? '#94A3B8' : '#64748B';
  }

  function getGridColor() {
    const isDark = document.documentElement.getAttribute('data-bs-theme') === 'dark';
    return isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.06)';
  }

  // 1. Stock Distribution by Category
  function renderCategoryChart(canvasId, labels, quantities) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    if (categoryChartInstance) {
      categoryChartInstance.destroy();
    }

    if (!labels || labels.length === 0) {
      // Empty state
      return;
    }

    categoryChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: quantities,
          backgroundColor: palette.slice(0, labels.length),
          borderColor: document.documentElement.getAttribute('data-bs-theme') === 'dark' ? '#131E33' : '#FFFFFF',
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              boxWidth: 12,
              padding: 14,
              color: getTextColor(),
              font: { family: 'Plus Jakarta Sans', size: 12 }
            }
          },
          tooltip: {
            callbacks: {
              label: function(context) {
                const val = context.raw || 0;
                return ` ${context.label}: ${val.toLocaleString()} units`;
              }
            }
          }
        },
        cutout: '68%'
      }
    });
  }

  // 2. Top Products by Quantity
  function renderTopProductsChart(canvasId, labels, quantities) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    if (topProductsChartInstance) {
      topProductsChartInstance.destroy();
    }

    if (!labels || labels.length === 0) return;

    topProductsChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [{
          label: 'Units in Stock',
          data: quantities,
          backgroundColor: '#3478F6',
          borderRadius: 6,
          maxBarThickness: 22
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` Stock: ${ctx.raw} units`
            }
          }
        },
        scales: {
          x: {
            grid: { color: getGridColor() },
            ticks: { color: getTextColor(), font: { family: 'Plus Jakarta Sans', size: 11 } }
          },
          y: {
            grid: { display: false },
            ticks: { color: getTextColor(), font: { family: 'Plus Jakarta Sans', size: 11 } }
          }
        }
      }
    });
  }

  // 3. Monthly Stock In vs Stock Out
  function renderTimelineChart(canvasId, labels, stockIn, stockOut) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    if (timelineChartInstance) {
      timelineChartInstance.destroy();
    }

    timelineChartInstance = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: 'Stock In',
            data: stockIn,
            backgroundColor: '#16A34A',
            borderRadius: 6,
            maxBarThickness: 28
          },
          {
            label: 'Stock Out',
            data: stockOut,
            backgroundColor: '#DC2626',
            borderRadius: 6,
            maxBarThickness: 28
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: {
              boxWidth: 12,
              color: getTextColor(),
              font: { family: 'Plus Jakarta Sans', size: 12 }
            }
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: getTextColor(), font: { family: 'Plus Jakarta Sans', size: 11 } }
          },
          y: {
            grid: { color: getGridColor() },
            ticks: { color: getTextColor(), font: { family: 'Plus Jakarta Sans', size: 11 } }
          }
        }
      }
    });
  }

  // 4. Stock Health Breakdown
  function renderStatusChart(canvasId, labels, counts) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    if (statusChartInstance) {
      statusChartInstance.destroy();
    }

    statusChartInstance = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: counts,
          backgroundColor: ['#16A34A', '#F59E0B', '#DC2626'],
          borderColor: document.documentElement.getAttribute('data-bs-theme') === 'dark' ? '#131E33' : '#FFFFFF',
          borderWidth: 2,
          hoverOffset: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              boxWidth: 12,
              padding: 14,
              color: getTextColor(),
              font: { family: 'Plus Jakarta Sans', size: 12 }
            }
          }
        },
        cutout: '68%'
      }
    });
  }

  // Re-render when theme changes to update axis and label colors
  window.addEventListener('themeChanged', () => {
    if (categoryChartInstance) categoryChartInstance.update();
    if (topProductsChartInstance) {
      topProductsChartInstance.options.scales.x.ticks.color = getTextColor();
      topProductsChartInstance.options.scales.x.grid.color = getGridColor();
      topProductsChartInstance.options.scales.y.ticks.color = getTextColor();
      topProductsChartInstance.update();
    }
    if (timelineChartInstance) {
      timelineChartInstance.options.scales.x.ticks.color = getTextColor();
      timelineChartInstance.options.scales.y.ticks.color = getTextColor();
      timelineChartInstance.options.scales.y.grid.color = getGridColor();
      timelineChartInstance.update();
    }
    if (statusChartInstance) statusChartInstance.update();
  });

  return {
    renderCategoryChart,
    renderTopProductsChart,
    renderTimelineChart,
    renderStatusChart
  };
})();
