export function filterLeaveRequests(requests, { status = "", leaveType = "", query = "" } = {}) {
  const rows = Array.isArray(requests) ? requests : [];
  const search = String(query || "").trim().toLowerCase();
  return rows.filter(request => {
    if (status && request.status !== status) return false;
    if (leaveType && request.leave_type !== leaveType) return false;
    if (!search) return true;
    return [request.employee_code,request.first_name,request.last_name,request.leave_type,request.reason,request.review_note]
      .some(value => String(value || "").toLowerCase().includes(search));
  });
}
