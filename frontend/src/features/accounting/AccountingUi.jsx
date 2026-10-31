import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Inbox, X } from "lucide-react";
import { ACCOUNT_TYPES, errorText } from "./accountingApi.js";

/** Load data with loading/error state; reloads whenever `deps` change. */
export function useLoader(fn, deps) {
  const [state, setState] = useState({ data: null, loading: true, error: "" });
  const seq = useRef(0);
  const reload = useCallback(async () => {
    const id = ++seq.current;
    setState((s) => ({ ...s, loading: true, error: "" }));
    try {
      const data = await fn();
      if (id === seq.current) setState({ data, loading: false, error: "" });
    } catch (error) {
      if (id === seq.current) setState((s) => ({ ...s, loading: false, error: errorText(error) }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => { reload(); }, [reload]);
  return { ...state, reload };
}

export function Sheet({ title, onClose, children, footer, wide = false, icon = null }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = previous; };
  }, [onClose]);
  return (
    <div className="acc-sheet-backdrop acc-no-print-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className={`acc-sheet${wide ? " wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="acc-grabber" aria-hidden="true" />
        <div className="acc-sheet-head">
          {icon}
          <h2>{title}</h2>
          <button className="acc-icon-btn" type="button" onClick={onClose} aria-label="Close"><X size={18} /></button>
        </div>
        <div className="acc-sheet-body">{children}</div>
        {footer && <div className="acc-sheet-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Empty({ title, children, icon: Icon = Inbox }) {
  return (
    <div className="acc-empty">
      <Icon size={34} aria-hidden="true" />
      <strong>{title}</strong>
      {children && <div>{children}</div>}
    </div>
  );
}

export function Loading({ rows = 4 }) {
  return <div aria-busy="true" aria-label="Loading">{Array.from({ length: rows }, (_, i) => <div key={i} className="acc-skeleton" style={{ width: `${90 - i * 12}%` }} />)}</div>;
}

export function Alert({ children, tone = "error", onRetry }) {
  if (!children) return null;
  return (
    <div className={`acc-alert ${tone === "error" ? "" : tone}`} role={tone === "error" ? "alert" : "status"}>
      {tone === "error" && <AlertTriangle size={16} style={{ flex: "none", marginTop: 1 }} aria-hidden="true" />}
      <div style={{ flex: 1 }}>{children}</div>
      {onRetry && <button className="acc-btn small" type="button" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`acc-field ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <em>{hint}</em>}
    </label>
  );
}

/** Account picker grouped by account type. `filter` narrows the list (e.g. only expense accounts). */
export function AccountSelect({ accounts, value, onChange, filter, placeholder = "Choose account", required = false, ariaLabel }) {
  const list = (accounts || []).filter((a) => a.is_active !== false && (!filter || filter(a)));
  return (
    <select value={value || ""} onChange={(event) => onChange(event.target.value ? Number(event.target.value) : "")} required={required} aria-label={ariaLabel}>
      <option value="">{placeholder}</option>
      {ACCOUNT_TYPES.map((type) => {
        const group = list.filter((a) => a.account_type === type.key);
        if (!group.length) return null;
        return (
          <optgroup key={type.key} label={type.label}>
            {group.map((a) => <option key={a.id} value={a.id}>{a.code} · {a.name}</option>)}
          </optgroup>
        );
      })}
    </select>
  );
}

export function Toast({ message, onDone }) {
  useEffect(() => {
    if (!message) return undefined;
    const timer = setTimeout(onDone, 3200);
    return () => clearTimeout(timer);
  }, [message, onDone]);
  if (!message) return null;
  return <div className="acc-toast" role="status">{message}</div>;
}
