const TERMINAL = new Set(["completed","waived","cancelled"]);
export function filterLifecycleTasks(tasks, { status = "", query = "" } = {}) {
  if (!Array.isArray(tasks)) return [];
  const needle = String(query || "").trim().toLowerCase();
  return tasks.filter(task =>
    (!status || task.status === status) &&
    (!needle || [task.employee_code, task.first_name, task.last_name, task.label, task.task_key, task.owner_role]
      .some(value => String(value || "").toLowerCase().includes(needle)))
  );
}
export function summarizeLifecycleTasks(tasks, today) {
  const rows = Array.isArray(tasks) ? tasks : [];
  return {
    total: rows.length,
    active: rows.filter(task => ["pending","in_progress"].includes(task.status)).length,
    overdue: rows.filter(task => task.due_date && task.due_date < today && !TERMINAL.has(task.status)).length,
    completed: rows.filter(task => task.status === "completed").length
  };
}
