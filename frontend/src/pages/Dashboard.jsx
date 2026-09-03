import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import api from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { StabilityAlerts } from "@/components/StabilityAlerts";
import { useAuth } from "@/context/AuthContext";

const ROLE_TITLE = { qa: "QA Dashboard", admin: "Administration", qc: "QC Dashboard" };
const AXIS_TICK = { fontSize: 11 };

const Kpi = ({ label, value, testId, accent }) => (
  <div className="bg-white border border-slate-200 rounded-md p-4" data-testid={testId}>
    <div className="label-caps">{label}</div>
    <div className={`text-3xl font-bold tabnum mt-1 ${accent || "text-slate-900"}`}>{value}</div>
  </div>
);

export default function Dashboard() {
  const { user } = useAuth();
  const [d, setD] = useState(null);

  useEffect(() => {
    api.get("/dashboard").then(({ data }) => setD(data));
  }, []);

  if (!d) return <div className="text-sm text-slate-500">Loading dashboard…</div>;

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">
          {ROLE_TITLE[user.role] || "Dashboard"}
        </h1>
        <p className="text-sm text-slate-600 mt-1">Live status of laboratory records and sign-off queues.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Kpi label="Total Records" value={d.total_samples} testId="kpi-total" />
        <Kpi label="Pending Review" value={d.pending_review} testId="kpi-pending" accent="text-amber-600" />
        <Kpi label="Approved" value={d.approved} testId="kpi-approved" accent="text-emerald-600" />
        <Kpi label="Failures" value={d.failures} testId="kpi-failures" accent="text-red-600" />
        <Kpi label="Open OOS" value={d.open_oos} testId="kpi-oos" accent="text-red-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StabilityAlerts days={365} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-md p-4">
          <div className="label-caps mb-4">Result outcome by sample date</div>
          <div className="h-64 min-h-[256px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
                <XAxis dataKey="date" tick={AXIS_TICK} />
                <YAxis tick={AXIS_TICK} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="pass" stackId="a" fill="#22C55E" />
                <Bar dataKey="warn" stackId="a" fill="#F59E0B" />
                <Bar dataKey="fail" stackId="a" fill="#EF4444" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="bg-white border border-slate-200 rounded-md p-4">
          <div className="label-caps mb-3">Recent records</div>
          <div className="divide-y divide-slate-100" data-testid="recent-samples-list">
            {d.recent_samples.length === 0 && (
              <div className="text-sm text-slate-500 py-2">No samples registered yet.</div>
            )}
            {d.recent_samples.map((s) => (
              <Link
                key={s.id}
                to={`/samples/${s.id}`}
                className="flex items-center justify-between py-2 hover:bg-slate-50 transition-colors duration-200 px-1"
              >
                <div>
                  <div className="font-mono text-xs text-slate-900">{s.record_id}</div>
                  <div className="text-xs text-slate-500">{s.sample_point_name}</div>
                </div>
                <StatusBadge value={s.overall_result} />
              </Link>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
