export function buildMonthlyTrend(monthly) {
  const rows = Array.isArray(monthly) ? monthly : [];
  const labels = rows.map(row => String(row?.month || "—"));
  const income = rows.map(row => finiteAmount(row?.income));
  const expenses = rows.map(row => finiteAmount(row?.expense ?? row?.expenses));
  const maxValue = Math.max(1, ...income, ...expenses);
  return { labels, income, expenses, maxValue };
}

function finiteAmount(value) {
  const amount = Number(value);
  return Number.isFinite(amount) && amount > 0 ? amount : 0;
}
