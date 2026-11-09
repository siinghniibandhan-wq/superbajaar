/** Read authoritative, unbounded dashboard aggregates without substituting page samples. */
export function dashboardMetrics(reportSummary, inventoryOverview) {
  const orders = reportSummary?.orders;
  const payments = reportSummary?.payments;
  const catalogue = reportSummary?.catalogue;
  const inventory = inventoryOverview?.totals;
  return {
    orderCount: orders ? Number(orders.order_count || 0) : null,
    activeOrderValue: orders ? Number(orders.active_order_value || 0) : null,
    capturedCount: payments ? Number(payments.captured_count || 0) : null,
    capturedAmount: payments ? Number(payments.captured_amount || 0) : null,
    activeProducts: catalogue ? Number(catalogue.active_products || 0) : null,
    stockOnHand: inventory ? Number(inventory.on_hand || 0) : null,
    lowStockRows: inventory ? Number(inventory.low_stock_rows || 0) : null,
    outOfStockRows: inventory ? Number(inventory.out_of_stock_rows || 0) : null,
    orderStatuses: Array.isArray(reportSummary?.order_statuses)
      ? reportSummary.order_statuses.map(row => ({ status: row.status, total: Number(row.count || 0) }))
      : null,
    stockByLocation: Array.isArray(inventoryOverview?.stock_by_location)
      ? inventoryOverview.stock_by_location
      : null,
  };
}
