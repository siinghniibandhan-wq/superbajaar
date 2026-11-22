import { useState, useEffect } from "react";
import "./ReplenishmentWorkspace.css";
import { apiRequest } from "../../services/api.js";
import { toLocalDateInputValue } from "./dateInput.js";

const money = v => new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(Number(v || 0));
const label = v => String(v || "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());

export default function ReplenishmentWorkspace({ onBack, variants }) {
  const [activeTab, setActiveTab] = useState("report");
  const [replenishmentReport, setReplenishmentReport] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [stats, setStats] = useState(null);
  const [showGenerateModal, setShowGenerateModal] = useState(false);
  const [limit, setLimit] = useState(1000);

  const load = async (generate = false) => {
    setLoading(true);
    setError("");
    setNotice("");
    try {
      if (activeTab === "report") {
        const response = await apiRequest(`/purchasing/replenishment/report?limit=${limit}`);
        setReplenishmentReport(response.items || []);

        const statsResponse = await apiRequest("/purchasing/replenishment/stats");
        setStats(statsResponse);
      }

      if (generate) {
        const response = await apiRequest("/purchasing/replenish?generate=true&limit=" + limit, {
          method: "POST",
        });
        setNotice(response.message);
        setReplenishmentReport(response.items || []);
        load(false);
      }
    } catch (e) {
      setError(e.message || "Unable to load replenishment data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(false);
  }, [activeTab, limit]);

  const generatePOs = async () => {
    await load(true);
    setShowGenerateModal(false);
  };

  const clearAlert = async (variantId) => {
    try {
      await apiRequest(`/purchasing/replenishment/${variantId}/clear-alert`, {
        method: "POST",
      });
      setNotice("Reorder alert cleared successfully.");
      load(false);
    } catch (e) {
      setError(e.message || "Unable to clear reorder alert.");
    }
  };

  const getStockStatus = (currentStock, reorderPoint) => {
    if (currentStock === null || currentStock === 0) return "out_of_stock";
    if (currentStock <= reorderPoint) return "out_of_stock";
    if (currentStock <= reorderPoint * 1.5) return "reorder_needed";
    return "in_stock";
  };

  const stockStatusBadge = (currentStock, reorderPoint) => {
    const status = getStockStatus(currentStock, reorderPoint);
    const styles = {
      out_of_stock: { bg: "#fee2e2", text: "#dc2626", label: "Out of Stock" },
      reorder_needed: { bg: "#fef3c7", text: "#d97706", label: "Reorder Needed" },
      in_stock: { bg: "#d1fae5", text: "#059669", label: "In Stock" },
    };
    const style = styles[status];
    return (
      <span
        className="sb-replenishment-status"
        style={{ backgroundColor: style.bg, color: style.text }}
      >
        {style.label}
      </span>
    );
  };

  return (
    <div className="sb-replenishment-workspace">
      <div className="sb-workspace-header">
        <div>
          <h2>Automated Replenishment</h2>
          <p>Generate draft purchase orders based on reorder points.</p>
        </div>
        <div className="sb-workspace-actions">
          <button
            className="sb-primary"
            type="button"
            onClick={() => setShowGenerateModal(true)}
            disabled={loading}
          >
            Generate Purchase Orders
          </button>
          <button className="sb-secondary" type="button" onClick={onBack}>
            Back
          </button>
        </div>
      </div>

      {notice && (
        <div className="sb-notice sb-notice-success">{notice}</div>
      )}

      {error && (
        <div className="sb-notice sb-notice-error">{error}</div>
      )}

      {stats && (
        <div className="sb-replenishment-stats">
          <div className="sb-stat-card">
            <div className="sb-stat-value">{stats.total_configured_variants}</div>
            <div className="sb-stat-label">Configured Variants</div>
          </div>
          <div className="sb-stat-card">
            <div className="sb-stat-value">{stats.stock_below_reorder}</div>
            <div className="sb-stat-label">Stock Below Reorder Point</div>
          </div>
          <div className="sb-stat-card">
            <div className="sb-stat-value">{stats.out_of_stock}</div>
            <div className="sb-stat-label">Out of Stock</div>
          </div>
          <div className="sb-stat-card">
            <div className="sb-stat-value">
              {money(stats.avg_reorder_point)}
            </div>
            <div className="sb-stat-label">Avg Reorder Point</div>
          </div>
          <div className="sb-stat-card">
            <div className="sb-stat-value">
              {money(stats.avg_reorder_qty)}
            </div>
            <div className="sb-stat-label">Avg Reorder Qty</div>
          </div>
        </div>
      )}

      <div className="sb-replenishment-tabs">
        <button
          type="button"
          className={activeTab === "report" ? "is-active" : ""}
          onClick={() => setActiveTab("report")}
        >
          Replenishment Report
        </button>
      </div>

      {loading ? (
        <div className="sb-loading">Loading...</div>
      ) : replenishmentReport.length === 0 ? (
        <div className="sb-empty">
          <p>No variants need replenishment at this time.</p>
        </div>
      ) : (
        <div className="sb-replenishment-list">
          <div className="sb-replenishment-table-header">
            <div className="sb-th">Product</div>
            <div className="sb-th">Variant</div>
            <div className="sb-th">SKU</div>
            <div className="sb-th">Selling Price</div>
            <div className="sb-th">Reorder Point</div>
            <div className="sb-th">Reorder Qty</div>
            <div className="sb-th">Current Stock</div>
            <div className="sb-th">Min Stock Date</div>
            <div className="sb-th">Status</div>
            <div className="sb-th">Action</div>
          </div>

          {replenishmentReport.map((item) => (
            <div key={item.variant_id} className="sb-replenishment-row">
              <div className="sb-td">
                <strong>{item.product_name}</strong>
              </div>
              <div className="sb-td">{item.variant_name || "-"}</div>
              <div className="sb-td">{item.sku || "-"}</div>
              <div className="sb-td">{money(item.selling_price)}</div>
              <div className="sb-td">{item.reorder_point || "-"}</div>
              <div className="sb-td">{item.reorder_qty || "-"}</div>
              <div className="sb-td">{item.current_stock !== null ? item.current_stock : "-"}</div>
              <div className="sb-td">
                {item.min_stock_date
                  ? new Date(item.min_stock_date).toLocaleDateString("en-IN")
                  : "-"}
              </div>
              <div className="sb-td">
                {stockStatusBadge(item.current_stock, item.reorder_point)}
              </div>
              <div className="sb-td">
                {item.current_stock <= item.reorder_point && (
                  <button
                    className="sb-button-small sb-button-success"
                    type="button"
                    onClick={() => clearAlert(item.variant_id)}
                  >
                    Clear Alert
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {showGenerateModal && (
        <div className="sb-modal-overlay" onClick={() => setShowGenerateModal(false)}>
          <div className="sb-modal" onClick={(e) => e.stopPropagation()}>
            <div className="sb-modal-header">
              <h3>Generate Purchase Orders</h3>
            </div>
            <div className="sb-modal-body">
              <p>Generate draft purchase orders for all items with stock below reorder point.</p>
              <p>
                <strong>Limit:</strong> {limit} items
              </p>
              <p>
                <strong>Total items needing replenishment:</strong> {replenishmentReport.length}
              </p>
              <p>
                This will create draft requisitions that must be reviewed and approved before they
                are submitted.
              </p>
            </div>
            <div className="sb-modal-footer">
              <button
                className="sb-secondary"
                type="button"
                onClick={() => setShowGenerateModal(false)}
              >
                Cancel
              </button>
              <button
                className="sb-primary"
                type="button"
                onClick={generatePOs}
                disabled={loading}
              >
                {loading ? "Generating..." : "Generate Purchase Orders"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
