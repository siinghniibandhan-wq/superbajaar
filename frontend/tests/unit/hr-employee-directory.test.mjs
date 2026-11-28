import test from "node:test";
import assert from "node:assert/strict";
import { filterEmployees } from "../../src/features/hr/hrEmployeeDirectory.js";

const employees = [
  { id: 1, employee_code: "SB-001", first_name: "Asha", last_name: "Kumar", email: "asha@example.com", department_id: 2, department_name: "Finance", designation: "Accountant", status: "active" },
  { id: 2, employee_code: "SB-002", first_name: "Ravi", last_name: "Singh", email: "ravi@example.com", department_id: 3, department_name: "Operations", designation: "Warehouse Lead", status: "probation" },
  { id: 3, employee_code: "SB-003", first_name: "Meera", last_name: "Das", email: "meera@example.com", department_id: 2, department_name: "Finance", designation: "Analyst", status: "active" },
];

test("search is case-insensitive, trims whitespace and checks employee fields", () => {
  assert.deepEqual(filterEmployees(employees, { query: "  SB-002 " }).map(x => x.id), [2]);
  assert.deepEqual(filterEmployees(employees, { query: "WAREHOUSE" }).map(x => x.id), [2]);
  assert.deepEqual(filterEmployees(employees, { query: "finance" }).map(x => x.id), [1, 3]);
});

test("department and status filters can be combined", () => {
  assert.deepEqual(filterEmployees(employees, { departmentId: "2", status: "active" }).map(x => x.id), [1, 3]);
  assert.deepEqual(filterEmployees(employees, { departmentId: 3, status: "active" }), []);
});

test("empty filters return every employee and invalid input returns an empty list", () => {
  assert.deepEqual(filterEmployees(employees).map(x => x.id), [1, 2, 3]);
  assert.deepEqual(filterEmployees(null), []);
});
