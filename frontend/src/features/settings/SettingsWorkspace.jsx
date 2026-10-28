import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const roles = ["admin", "manager", "staff", "viewer"];
export default function SettingsWorkspace({ onBack, currentUser }) {
  const [users, setUsers] = useState([]);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "staff" });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loyaltyRules, setLoyaltyRules] = useState([]);
  const [ruleForm, setRuleForm] = useState({ scope_type: "default", scope_id: "", coins_per_100: "1", is_active: true });
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const result = await apiRequest("/auth/users"); setUsers(result.items || []); }
    catch (e) { setError(e.message || "Unable to load user accounts."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { apiRequest("/loyalty/rules").then(result => setLoyaltyRules(result.items || [])).catch(() => setLoyaltyRules([])); }, []);

  async function create(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/auth/users", { method: "POST", body: JSON.stringify(form) });
      setForm({ email: "", full_name: "", password: "", role: "staff" });
      setNotice("Staff account created."); await load();
    } catch (e) { setError(e.message || "Unable to create account."); }
    finally { setSaving(false); }
  }
  async function update(id, payload) {
    setSaving(true); setError(""); setNotice("");
    try { await apiRequest("/auth/users/" + id, { method: "PATCH", body: JSON.stringify(payload) }); setNotice("User access updated."); await load(); }
    catch (e) { setError(e.message || "Unable to update user access."); }
    finally { setSaving(false); }
  }
  async function saveLoyaltyRule(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    const payload = { scope_type: ruleForm.scope_type, scope_id: ruleForm.scope_type === "default" ? null : Number(ruleForm.scope_id), coins_per_100: Number(ruleForm.coins_per_100), is_active: ruleForm.is_active };
    try {
      await apiRequest("/loyalty/rules", { method: "PUT", body: JSON.stringify(payload) });
      const result = await apiRequest("/loyalty/rules");
      setLoyaltyRules(result.items || []); setNotice("Loyalty earning rule saved.");
    } catch (e) { setError(e.message || "Unable to save loyalty rule."); }
    finally { setSaving(false); }
  }
  const ownerOrAdmin = ["owner", "admin"].includes(currentUser?.role);
  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">BUSINESS MANAGEMENT · ACCESS</p><h1>Settings & Access</h1>
    <p>Manage staff accounts and roles. Only owner/admin accounts can access this workspace; only owners can grant owner/admin roles.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}{notice && <p className="sb-success" role="status">{notice}</p>}
    <form className="sb-form" onSubmit={create}>
      <h2>Create staff account</h2><div className="sb-form-grid">
        <label>Full name<input required minLength="1" maxLength="200" value={form.full_name} onChange={e=>setForm(v=>({...v,full_name:e.target.value}))}/></label>
        <label>Email<input required type="email" maxLength="254" value={form.email} onChange={e=>setForm(v=>({...v,email:e.target.value}))}/></label>
        <label>Temporary password (minimum 12 characters)<input required type="password" minLength="12" maxLength="1024" autoComplete="new-password" value={form.password} onChange={e=>setForm(v=>({...v,password:e.target.value}))}/></label>
        <label>Role<select value={form.role} onChange={e=>setForm(v=>({...v,role:e.target.value}))}><option value="staff">Staff</option><option value="manager">Manager</option><option value="viewer">Viewer</option>{currentUser?.role === "owner" && <><option value="admin">Admin</option><option value="owner">Owner</option></>}</select></label>
      </div><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create account"}</button>
    </form>
    <div className="sb-data-card"><div className="sb-data-heading"><h2>Accounts ({users.length})</h2><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
      {loading ? <p className="sb-empty">Loading user accounts…</p> : users.length ? <div className="sb-table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>{users.map(u=><tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td><td>{u.is_active ? "Active" : "Inactive"}</td><td><div className="sb-access-actions"><select aria-label={"Role for "+u.email} value={u.role} disabled={saving || (u.role === "owner" && currentUser?.role !== "owner")} onChange={e=>update(u.id,{role:e.target.value})}><option value="owner" disabled={currentUser?.role !== "owner"}>Owner</option><option value="admin" disabled={currentUser?.role !== "owner"}>Admin</option>{roles.filter(r=>r!=="admin").map(r=><option key={r} value={r}>{r}</option>)}</select><button type="button" disabled={saving || u.id === currentUser?.id} onClick={()=>update(u.id,{is_active:!u.is_active})}>{u.is_active ? "Deactivate" : "Activate"}</button></div></td></tr>)}</tbody></table></div> : <p className="sb-empty">No user accounts found.</p>}
    </div>
    <form className="sb-form" onSubmit={saveLoyaltyRule}>
      <h2>Loyalty rewards rules</h2>
      <p>Set the default Super Coins rate or override it for a product/category. Default: 1 coin per ₹100 eligible spend. Coins expire one year after credit.</p>
      <div className="sb-form-grid">
        <label>Rule scope<select value={ruleForm.scope_type} onChange={e=>setRuleForm(v=>({...v,scope_type:e.target.value,scope_id:""}))}><option value="default">Default store rule</option><option value="category">Category override</option><option value="product">Product override</option></select></label>
        {ruleForm.scope_type !== "default" && <label>{ruleForm.scope_type === "category" ? "Category ID" : "Product ID"}<input required type="number" min="1" step="1" value={ruleForm.scope_id} onChange={e=>setRuleForm(v=>({...v,scope_id:e.target.value}))}/></label>}
        <label>Coins per ₹100 eligible spend<input required type="number" min="0" max="100000" step="0.25" value={ruleForm.coins_per_100} onChange={e=>setRuleForm(v=>({...v,coins_per_100:e.target.value}))}/></label>
        <label className="sb-inline-check"><input type="checkbox" checked={ruleForm.is_active} onChange={e=>setRuleForm(v=>({...v,is_active:e.target.checked}))}/> Rule active</label>
      </div>
      <button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Save earning rule"}</button>
      <div className="sb-table-wrap"><table><thead><tr><th>Scope</th><th>ID</th><th>Coins per ₹100</th><th>Status</th></tr></thead><tbody>{loyaltyRules.map((r,i)=><tr key={r.scope_type+"-"+r.scope_id+"-"+i}><td>{r.scope_type}</td><td>{r.scope_id ?? "—"}</td><td>{r.coins_per_100}</td><td>{r.is_active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div>
      <p className="sb-muted">Product overrides take precedence over category overrides, which take precedence over the default rule. Coins are rounded down to whole coins.</p>
    </form>
    <p className="sb-muted">Current role: {currentUser?.role || "unknown"}. User-management APIs are protected by the backend. The database schema is unchanged; this uses the existing access-control tables.</p>
  </section>;
}
