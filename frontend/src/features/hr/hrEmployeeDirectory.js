export function filterEmployees(employees, { query = "", status = "", departmentId = "" } = {}) {
  const records = Array.isArray(employees) ? employees : [];
  const search = String(query || "").trim().toLowerCase();
  return records.filter(employee => {
    if (status && employee.status !== status) return false;
    if (departmentId && String(employee.department_id || "") !== String(departmentId)) return false;
    if (!search) return true;
    return [
      employee.employee_code,
      employee.first_name,
      employee.last_name,
      employee.email,
      employee.department_name,
      employee.designation,
    ].some(value => String(value || "").toLowerCase().includes(search));
  });
}
