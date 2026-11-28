import test from "node:test";
import assert from "node:assert/strict";
import { filterLifecycleTasks, summarizeLifecycleTasks } from "../../src/features/hr/hrLifecycleTasks.js";
const rows=[
 {id:1,employee_code:"SB-01",first_name:"Asha",label:"Issue laptop",task_key:"IT-01",owner_role:"it",status:"pending",due_date:"2026-11-20"},
 {id:2,employee_code:"SB-02",first_name:"Ravi",label:"Return badge",task_key:"OFF-02",owner_role:"employee",status:"completed",due_date:"2026-11-21"},
 {id:3,employee_code:"SB-03",first_name:"Meera",label:"Final settlement",task_key:"FIN-03",owner_role:"finance",status:"in_progress",due_date:"2026-12-02"}
];
test("filters lifecycle tasks by status and searchable task or employee fields",()=>{
 assert.deepEqual(filterLifecycleTasks(rows,{status:"pending",query:"asha"}).map(x=>x.id),[1]);
 assert.deepEqual(filterLifecycleTasks(rows,{query:"FIN-03"}).map(x=>x.id),[3]);
 assert.deepEqual(filterLifecycleTasks(rows,{query:"employee"}).map(x=>x.id),[2]);
});
test("summarizes active, overdue and completed tasks without counting terminal tasks as overdue",()=>{
 assert.deepEqual(summarizeLifecycleTasks(rows,"2026-11-28"),{total:3,active:2,overdue:1,completed:1});
});
test("handles absent task collections and empty filters safely",()=>{
 assert.deepEqual(filterLifecycleTasks(null),[]);
 assert.equal(summarizeLifecycleTasks(null,"2026-11-28").total,0);
 assert.deepEqual(filterLifecycleTasks(rows).map(x=>x.id),[1,2,3]);
});
