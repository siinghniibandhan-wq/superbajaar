import "./HROverview.css";

const money = value => value == null
  ? "Not available"
  : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value));

function Metric({ label, value, detail, tone = "default" }) {
  return <article className={"hr-metric hr-metric-" + tone}>
    <span>{label}</span><strong>{value ?? "—"}</strong>{detail && <small>{detail}</small>}
  </article>;
}

function Section({ title, action, children }) {
  return <section className="hr-dashboard-section">
    <div className="hr-dashboard-section-heading"><h2>{title}</h2>{action}</div>
    {children}
  </section>;
}

export default function HROverview({ data, loading, error, onNavigate, onRefresh }) {
  if (loading && !data) return <div className="hr-dashboard-state" role="status">Loading HR overview…</div>;
  if (error && !data) return <div className="hr-dashboard-state hr-dashboard-error" role="alert">
    <strong>HR overview could not be loaded.</strong><p>{error}</p>
    <button type="button" onClick={onRefresh}>Try again</button>
  </div>;
  if (!data) return <div className="hr-dashboard-state">No overview data is available.</div>;

  const { workforce = {}, attendance = {}, payroll = {}, approvals = {}, controls = {}, trends = {}, data_quality: quality = {} } = data;
  const unavailable = quality.unavailable_metrics || [];
  const attendanceDetail = attendance.available
    ? "Attendance rate " + (attendance.rate == null ? "not available" : attendance.rate + "%")
    : attendance.reason || "Shift and holiday data is incomplete";
  const runStates = (payroll.run_statuses || []).map(item => item.status + ": " + item.count).join(" · ") || "No runs in this period";

  return <div className="hr-management-overview">
    {error && <p className="hr-dashboard-inline-warning" role="status">Some overview data could not refresh: {error}</p>}
    <div className="hr-dashboard-heading"><div><span className="sb-eyebrow">MANAGEMENT OVERVIEW</span><h2>Workforce at a glance</h2><p>{data.period?.month || "Selected period"} · INR · Organisation-wide summary</p></div>
      <button type="button" className="hr-dashboard-refresh" onClick={onRefresh} disabled={loading}>{loading ? "Refreshing…" : "Refresh data"}</button>
    </div>

    <Section title="Workforce">
      <div className="hr-metric-grid">
        <Metric label="Active workforce" value={workforce.active ?? "—"} detail={(workforce.total ?? 0) + " total records"} />
        <Metric label="New joiners" value={workforce.joiners ?? "—"} detail="Joined in selected month" />
        <Metric label="Exits" value={workforce.exits ?? "—"} detail="Exit date in selected month" />
        <Metric label="Departments" value={workforce.department_count ?? "—"} detail="Active departments" />
      </div>
      <div className="hr-dashboard-table-wrap"><table><thead><tr><th>Department</th><th>Headcount</th></tr></thead><tbody>
        {(workforce.departments || []).map(item => <tr key={item.id}><td>{item.name}</td><td>{item.headcount}</td></tr>)}
        {!(workforce.departments || []).length && <tr><td colSpan="2">No active departments configured.</td></tr>}
      </tbody></table></div>
    </Section>

    <Section title="Attendance & time">
      <div className="hr-metric-grid">
        <Metric label="Employees with attendance" value={attendance.present ?? "—"} detail="Distinct employees with a clock-in" />
        <Metric label="On approved leave" value={attendance.on_leave ?? "—"} detail="Overlapping selected month" />
        <Metric label="Absent employees" value={attendance.absent ?? "Not available"} detail={attendance.scheduled_shift_days ? attendance.absent_shift_days + " missed scheduled shifts" : "No reliable published shift schedule"} tone={attendance.absent ? "warning" : "default"} />
        <Metric label="Open sessions" value={attendance.open_sessions ?? "—"} detail="Require review / clock-out" tone={attendance.open_sessions ? "warning" : "default"} />
        <Metric label="Attendance rate" value={attendance.rate == null ? "Not available" : attendance.rate + "%"} detail={attendanceDetail} />
      </div>
      {!attendance.available && <p className="hr-dashboard-note">Absence and lateness are not guessed. {attendance.reason}</p>}
      <button type="button" className="hr-dashboard-link" onClick={() => onNavigate("attendance")}>View time register →</button>
    </Section>

    <Section title="Payroll financials">
      <div className="hr-metric-grid">
        <Metric label="Gross payroll" value={money(payroll.gross)} detail={(payroll.run_count ?? 0) + " approved / paid runs"} />
        <Metric label="Employee deductions" value={money(payroll.employee_deductions)} detail="Deducted from employee earnings" />
        <Metric label="Employer contributions" value={money(payroll.employer_contributions)} detail="Separate employer cost" />
        <Metric label="Net payroll" value={money(payroll.net)} detail="Payable to employees" />
      </div>
      <div className="hr-dashboard-status"><strong>Payroll run status</strong><span>{runStates}</span><strong>Accounting accrual status</strong><span>{payroll.accounting_status || "Not available"}</span></div>
      <button type="button" className="hr-dashboard-link" onClick={() => onNavigate("payroll")}>Open payroll →</button>
      {(payroll.exceptions || 0) > 0 && <p className="hr-dashboard-note hr-dashboard-note-warning">{payroll.exceptions} payroll accounting exception(s) require review.</p>}
    </Section>

    <Section title="Approvals & action centre">
      <div className="hr-metric-grid">
        <Metric label="Pending leave" value={approvals.leave_count ?? "—"} detail="Awaiting manager review" />
        <Metric label="Pending expenses" value={approvals.expense_count ?? "—"} detail="Awaiting manager review" />
        <Metric label="Salary revisions" value={approvals.salary_revision_count ?? "—"} detail="Draft revisions" />
        <Metric label="Variable earnings" value={approvals.earning_count ?? "—"} detail="Pending overtime / bonus / incentive" />
      </div>
      <div className="hr-dashboard-actions">
        <button type="button" onClick={() => onNavigate("leave")}>Review leave</button>
        <button type="button" onClick={() => onNavigate("expenses")}>Review expenses</button>
        <button type="button" onClick={() => onNavigate("people")}>Review workforce</button>
        <button type="button" onClick={() => onNavigate("advanced")}>Lifecycle tasks ({approvals.lifecycle_overdue_count ?? 0} overdue)</button>
      </div>
    </Section>

    <Section title="Compliance & accounting controls">
      <div className="hr-metric-grid">
        <Metric label="Statutory policy readiness" value={controls.statutory_readiness || "Not available"} detail={(controls.establishments || []).length + " active establishment(s) checked"} tone={controls.statutory_readiness === "ready" ? "default" : "warning"} />
        <Metric label="Pending statutory remittances" value={controls.pending_remittances ?? "—"} detail="Payment / filing follow-up" tone={controls.pending_remittances ? "warning" : "default"} />
        <Metric label="Missing statutory profiles" value={controls.employees_without_statutory_profile ?? "—"} detail="Applicability still needs review" tone={controls.employees_without_statutory_profile ? "warning" : "default"} />
        <Metric label="Accounting exceptions" value={controls.accounting_exceptions ?? "—"} detail="Approved / paid runs without accrual posting" tone={controls.accounting_exceptions ? "warning" : "default"} />
        <Metric label="Employee data issues" value={controls.employee_data_issues ?? "—"} detail="Missing department or designation" />
        <Metric label="Employees without portal login" value={controls.employees_without_portal_user ?? "—"} detail="Employee records not linked to a staff account" tone={controls.employees_without_portal_user ? "warning" : "default"} />
        <Metric label="Pending employee invitations" value={controls.pending_employee_invitations ?? "—"} detail="Awaiting invitation acceptance" />
      </div>
      <button type="button" className="hr-dashboard-link" onClick={() => onNavigate("statutory")}>Open statutory policies & remittances →</button>
    </Section>

    <Section title="Trends">
      <div className="hr-dashboard-trends">
        <div><h3>Headcount</h3><ul>{(trends.headcount || []).map(point => <li key={point.month}><span>{point.month}</span><strong>{point.headcount}</strong></li>)}</ul></div>
        <div><h3>Gross payroll</h3><ul>{(trends.payroll_gross || []).map(point => <li key={point.month}><span>{point.month}</span><strong>{money(point.gross)}</strong></li>)}</ul></div>
      </div>
      {unavailable.length > 0 && <p className="hr-dashboard-note">Some analytics are not yet available from reliable source data: {unavailable.join(", ")}.</p>}
    </Section>
  </div>;
}
