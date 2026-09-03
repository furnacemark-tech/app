import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle } from "lucide-react";
import api from "@/lib/api";

const TONE = {
  EXPIRED: "bg-red-50 border-red-200 text-red-800",
  CRITICAL: "bg-red-50 border-red-200 text-red-800",
  WARNING: "bg-amber-50 border-amber-200 text-amber-900",
};

export const StabilityAlerts = ({ days = 90 }) => {
  const [alerts, setAlerts] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/alerts/expiring", { params: { days } }).then(({ data }) => setAlerts(data));
  }, [days]);

  return (
    <div className="bg-white border border-slate-200 rounded-md p-4" data-testid="stability-alerts">
      <div className="label-caps flex items-center gap-1.5 mb-3">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-600" /> Shelf-life alerts · next {days} days
      </div>
      <div className="space-y-2 max-h-56 overflow-y-auto">
        {alerts.length === 0 && (
          <div className="text-sm text-slate-500" data-testid="stability-alerts-empty">
            No released batch expires within {days} days.
          </div>
        )}
        {alerts.map((a) => (
          <button
            key={a.batch_id}
            data-testid={`stability-alert-${a.batch_number}`}
            onClick={() => navigate(`/batches/${a.batch_id}`)}
            className={`w-full text-left border rounded px-3 py-2 text-sm transition-colors duration-200 ${TONE[a.severity]}`}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-xs">{a.batch_number}</span>
              <span className="text-xs tabnum">
                {a.days_remaining < 0 ? `expired ${Math.abs(a.days_remaining)}d ago` : `${a.days_remaining}d left`}
              </span>
            </div>
            <div className="text-xs opacity-90">
              {a.product_name} · expires {a.expiry_date}
              {a.customer_name ? ` · ${a.customer_name}` : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
};
