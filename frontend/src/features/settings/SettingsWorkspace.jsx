import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../services/api.js";

const roles = ["super_admin", "owner", "admin", "manager", "staff", "viewer"];
function assignableRoles(currentRole) {
  if (currentRole === "super_admin") return roles;
  if (currentRole === "owner") return ["owner", "admin", "manager", "staff", "viewer"];
  if (currentRole === "admin") return ["manager", "staff", "viewer"];
  return [];
}
export default function SettingsWorkspace({ onBack, currentUser }) {
  const [users, setUsers] = useState([]);
  const availableRoles = assignableRoles(currentUser?.role);
  const [form, setForm] = useState({ email: "", full_name: "", password: "", role: "staff" });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loyaltyRules, setLoyaltyRules] = useState([]);
  const [loyaltyAccounts, setLoyaltyAccounts] = useState([]);
  const [loyaltyLedger, setLoyaltyLedger] = useState(null);
  const [ruleForm, setRuleForm] = useState({ scope_type: "default", scope_id: "", coins_per_100: "1", is_active: true });
  const load = useCallback(async () => {
    setLoading(true); setError("");
    try { const result = await apiRequest("/auth/users"); setUsers(result.items || []); }
    catch (e) { setError(e.message || "Unable to load user accounts."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    apiRequest("/loyalty/admin/rules").then(result => setLoyaltyRules(result.items || [])).catch(e => setError(e.message || "Unable to load loyalty rules."));
    apiRequest("/loyalty/admin/accounts").then(result => setLoyaltyAccounts(result.items || [])).catch(e => setError(e.message || "Unable to load loyalty accounts."));
  }, []);

  async function create(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      await apiRequest("/auth/users", { method: "POST", body: JSON.stringify(form) });
      setForm({ email: "", full_name: "", password: "", role: "staff" });
      setNotice("User account created."); await load();
    } catch (e) { setError(e.message || "Unable to create account."); }
    finally { setSaving(false); }
  }
  async function update(id, payload) {
    setSaving(true); setError(""); setNotice("");
    try { await apiRequest("/auth/users/" + id, { method: "PATCH", body: JSON.stringify(payload) }); setNotice("User access updated."); await load(); }
    catch (e) { setError(e.message || "Unable to update user access."); }
    finally { setSaving(false); }
  }
  async function loadLoyaltyLedger(accountId) {
    setError(""); setLoyaltyLedger(null);
    try { setLoyaltyLedger(await apiRequest("/loyalty/admin/accounts/" + accountId + "/transactions")); }
    catch (e) { setError(e.message || "Unable to load loyalty ledger."); }
  }
  async function saveLoyaltyRule(event) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    const payload = { scope_type: ruleForm.scope_type, scope_id: ruleForm.scope_type === "default" ? null : Number(ruleForm.scope_id), coins_per_100: Number(ruleForm.coins_per_100), is_active: ruleForm.is_active };
    try {
      await apiRequest("/loyalty/rules", { method: "PUT", body: JSON.stringify(payload) });
      const result = await apiRequest("/loyalty/admin/rules");
      setLoyaltyRules(result.items || []); setNotice("Loyalty earning rule saved.");
    } catch (e) { setError(e.message || "Unable to save loyalty rule."); }
    finally { setSaving(false); }
  }
  return <section className="sb-workspace">
    <button className="sb-back" type="button" onClick={onBack}>← All workspaces</button>
    <p className="sb-eyebrow">BUSINESS MANAGEMENT · ACCESS</p><h1>Settings & Access</h1>
    <p>Manage user accounts and roles. Super Admin can assign every role, including additional Super Admin accounts. Owners can assign Owner and Admin roles; Admins can assign operational roles.</p>
    {error && <p className="sb-alert" role="alert">{error}</p>}{notice && <p className="sb-success" role="status">{notice}</p>}
    <form className="sb-form" onSubmit={create}>
      <h2>Create user account</h2><div className="sb-form-grid">
        <label>Full name<input required minLength="1" maxLength="200" value={form.full_name} onChange={e=>setForm(v=>({...v,full_name:e.target.value}))}/></label>
        <label>Email<input required type="email" maxLength="254" value={form.email} onChange={e=>setForm(v=>({...v,email:e.target.value}))}/></label>
        <label>Temporary password (minimum 12 characters)<input required type="password" minLength="12" maxLength="1024" autoComplete="new-password" value={form.password} onChange={e=>setForm(v=>({...v,password:e.target.value}))}/></label>
        <label>Role<select value={form.role} onChange={e=>setForm(v=>({...v,role:e.target.value}))}>{availableRoles.map(role=><option key={role} value={role}>{role.replace("_", " ").replace(/^\w/, letter=>letter.toUpperCase())}</option>)}</select></label>
      </div><button className="sb-primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Create account"}</button>
    </form>
    <div className="sb-data-card"><div className="sb-data-heading"><h2>Accounts ({users.length})</h2><button type="button" onClick={load} disabled={loading}>{loading ? "Loading…" : "Refresh"}</button></div>
      {loading ? <p className="sb-empty">Loading user accounts…</p> : users.length ? <div className="sb-table-wrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Actions</th></tr></thead><tbody>{users.map(u=><tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{u.role}</td><td>{u.is_active ? "Active" : "Inactive"}</td><td><div className="sb-access-actions"><select aria-label={"Role for "+u.email} value={u.role} disabled={saving || (u.role === "super_admin" && currentUser?.role !== "super_admin") || (u.role === "owner" && !["owner", "super_admin"].includes(currentUser?.role))} onChange={e=>update(u.id,{role:e.target.value})}>{[...new Set([u.role, ...availableRoles])].map(role=><option key={role} value={role} disabled={!availableRoles.includes(role)}>{role.replace("_", " ")}</option>)}</select><button type="button" disabled={saving || u.id === currentUser?.id} onClick={()=>update(u.id,{is_active:!u.is_active})}>{u.is_active ? "Deactivate" : "Activate"}</button></div></td></tr>)}</tbody></table></div> : <p className="sb-empty">No user accounts found.</p>}
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
      <h2>Loyalty customer accounts ({loyaltyAccounts.length})</h2>
      <div className="sb-table-wrap"><table><thead><tr><th>Card</th><th>Customer email</th><th>Available coins</th><th>Ledger</th></tr></thead><tbody>{loyaltyAccounts.map(account=><tr key={account.id}><td>{account.card_number}</td><td>{account.customer_email}</td><td>{account.available_coins}</td><td><button type="button" onClick={()=>loadLoyaltyLedger(account.id)}>View history</button></td></tr>)}</tbody></table></div>
      {loyaltyLedger && <div className="sb-data-card"><h3>Ledger: {loyaltyLedger.account.card_number} · {loyaltyLedger.account.customer_email}</h3><div className="sb-table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Coins</th><th>Order</th><th>Expires</th></tr></thead><tbody>{loyaltyLedger.items.map(item=><tr key={item.id}><td>{new Date(item.created_at).toLocaleString()}</td><td>{item.transaction_type}</td><td>{item.coins}</td><td>{item.order_reference || "—"}</td><td>{item.expires_at ? new Date(item.expires_at).toLocaleDateString() : "—"}</td></tr>)}</tbody></table></div></div>}
    </form>
    <p className="sb-muted">Current role: {currentUser?.role || "unknown"}. User-management APIs are protected by the backend. The database schema is unchanged; this uses the existing access-control tables.</p>
  </section>;
}
