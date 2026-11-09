import test from 'node:test';
import assert from 'node:assert/strict';
import { dashboardMetrics } from '../../src/features/dashboard/dashboardMetrics.js';

test('dashboard uses full-period report aggregates and full-dataset inventory totals', () => {
  const metrics = dashboardMetrics({
    orders: { order_count: 1250, active_order_value: '987654.50' },
    order_statuses: [{ status: 'processing', count: 900 }, { status: 'delivered', count: 350 }],
    payments: { captured_count: 800, captured_amount: '700000.00' },
    catalogue: { active_products: 321 },
  }, {
    totals: { on_hand: 12345, low_stock_rows: 19, out_of_stock_rows: 7 },
    stock_by_location: [{ location_id: 1, location_name: 'Warehouse', on_hand: 12345 }],
  });

  assert.equal(metrics.orderCount, 1250);
  assert.equal(metrics.activeOrderValue, 987654.5);
  assert.equal(metrics.capturedCount, 800);
  assert.equal(metrics.capturedAmount, 700000);
  assert.equal(metrics.activeProducts, 321);
  assert.equal(metrics.stockOnHand, 12345);
  assert.equal(metrics.lowStockRows, 19);
  assert.equal(metrics.outOfStockRows, 7);
  assert.deepEqual(metrics.orderStatuses, [
    { status: 'processing', total: 900 }, { status: 'delivered', total: 350 },
  ]);
});

test('dashboard marks missing aggregate sources unavailable instead of returning misleading zeroes', () => {
  const metrics = dashboardMetrics(null, null);
  assert.equal(metrics.orderCount, null);
  assert.equal(metrics.capturedAmount, null);
  assert.equal(metrics.stockOnHand, null);
  assert.equal(metrics.orderStatuses, null);
  assert.equal(metrics.stockByLocation, null);
});
