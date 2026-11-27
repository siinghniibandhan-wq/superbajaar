import test from "node:test";
import assert from "node:assert/strict";
import { filterLeaveRequests } from "./hrLeaveRequests.js";
const rows=[
{id:1,employee_code:"SB-01",first_name:"Asha",leave_type:"annual",status:"pending",reason:"Family event"},
{id:2,employee_code:"SB-02",first_name:"Ravi",leave_type:"sick",status:"approved",reason:"Fever"},
{id:3,employee_code:"SB-03",first_name:"Meera",leave_type:"annual",status:"rejected",reason:"Personal"}];
test("filters by status and leave type together",()=>{
assert.deepEqual(filterLeaveRequests(rows,{status:"pending",leaveType:"annual"}).map(x=>x.id),[1]);
assert.deepEqual(filterLeaveRequests(rows,{leaveType:"sick"}).map(x=>x.id),[2]);});
test("search covers employee, type and request notes without case sensitivity",()=>{
assert.deepEqual(filterLeaveRequests(rows,{query:"  RAVI "}).map(x=>x.id),[2]);
assert.deepEqual(filterLeaveRequests(rows,{query:"fever"}).map(x=>x.id),[2]);});
test("empty or invalid input is safe",()=>{
assert.deepEqual(filterLeaveRequests(rows).map(x=>x.id),[1,2,3]);
assert.deepEqual(filterLeaveRequests(null),[]);});
