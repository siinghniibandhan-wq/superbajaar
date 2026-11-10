import { buildMonthlyTrend } from "./monthlyTrend.js";

const money = value => new Intl.NumberFormat("en-IN", {
  style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1,
}).format(value);

function points(values, maxValue) {
  const left = 54, right = 690, top = 18, bottom = 176;
  return values.map((value, index) => {
    const x = values.length < 2 ? (left + right) / 2 : left + index * (right - left) / (values.length - 1);
    const y = bottom - (value / maxValue) * (bottom - top);
    return [x, y];
  });
}

export default function MonthlyTrendChart({ monthly = [] }) {
  const chart = buildMonthlyTrend(monthly);
  if (!chart.labels.length) return <p className="an-empty">No monthly accounting data is available for this period.</p>;
  const incomePoints = points(chart.income, chart.maxValue);
  const expensePoints = points(chart.expenses, chart.maxValue);
  const polyline = values => values.map(([x, y]) => x + "," + y).join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return <div className="an-trend-chart">
    <div className="an-trend-legend">
      <span><i className="income" /> Income</span>
      <span><i className="expense" /> Expenses</span>
    </div>
    <svg viewBox="0 0 720 224" role="img" aria-label="Monthly income and expenses trend in Indian rupees">
      {ticks.map(tick => {
        const y = 176 - tick * 158;
        return <g key={tick}>
          <line x1="54" x2="690" y1={y} y2={y} stroke="#e8edf2" strokeDasharray="4 5" />
          <text x="44" y={y + 4} textAnchor="end" fill="#87929d" fontSize="11">{money(chart.maxValue * tick)}</text>
        </g>;
      })}
      <polyline points={polyline(incomePoints)} fill="none" stroke="#397fbd" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <polyline points={polyline(expensePoints)} fill="none" stroke="#e49a4b" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      {incomePoints.map(([x, y], index) => <g key={"income-" + index}><circle cx={x} cy={y} r="4" fill="#397fbd" /><title>{chart.labels[index]} income: {money(chart.income[index])}</title></g>)}
      {expensePoints.map(([x, y], index) => <g key={"expense-" + index}><circle cx={x} cy={y} r="4" fill="#e49a4b" /><title>{chart.labels[index]} expenses: {money(chart.expenses[index])}</title></g>)}
      {chart.labels.map((label, index) => {
        const x = chart.labels.length < 2 ? 372 : 54 + index * (636 / (chart.labels.length - 1));
        return <text key={label + index} x={x} y="202" textAnchor="middle" fill="#74808b" fontSize="11">{label}</text>;
      })}
    </svg>
  </div>;
}
