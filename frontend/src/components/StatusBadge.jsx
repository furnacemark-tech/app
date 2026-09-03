const MAP = {
  PASS: "bg-emerald-50 text-emerald-700 border-emerald-200",
  FAIL: "bg-red-50 text-red-700 border-red-200",
  WARN: "bg-amber-50 text-amber-700 border-amber-200",
  PENDING: "bg-slate-50 text-slate-600 border-slate-200",
  NO_SPEC: "bg-slate-50 text-slate-500 border-slate-200",
  OPEN: "bg-sky-50 text-sky-700 border-sky-200",
  IN_PROGRESS: "bg-indigo-50 text-indigo-700 border-indigo-200",
  COMPLETE: "bg-emerald-50 text-emerald-700 border-emerald-200",
  CLOSED: "bg-slate-100 text-slate-700 border-slate-300",
  Approved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  "Pending Review": "bg-amber-50 text-amber-700 border-amber-200",
  "Requires Investigation": "bg-red-50 text-red-700 border-red-200",
  "Not Submitted": "bg-slate-50 text-slate-600 border-slate-200",
};

export const StatusBadge = ({ value, testId }) => (
  <span
    data-testid={testId}
    className={`inline-flex items-center border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide rounded ${
      MAP[value] || "bg-slate-50 text-slate-600 border-slate-200"
    }`}
  >
    {String(value || "-").replace(/_/g, " ")}
  </span>
);
