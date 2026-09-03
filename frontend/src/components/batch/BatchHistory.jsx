export const BatchHistory = ({ history }) => (
  <div className="bg-white border border-slate-200 rounded-md p-5">
    <div className="label-caps mb-3">Batch history</div>
    <div className="space-y-2 max-h-96 overflow-y-auto" data-testid="batch-history-list">
      {[...(history || [])].reverse().map((h) => (
        <div key={h.id} className="text-xs border-l-2 border-slate-200 pl-3 py-1">
          <div className="font-mono font-semibold">{h.action}</div>
          <div className="text-slate-500">
            {new Date(h.timestamp).toLocaleString()} · {h.user_email} ({h.user_role})
          </div>
          {h.reason && <div className="italic text-slate-600">“{h.reason}”</div>}
          <div className="text-slate-500 font-mono break-all">{JSON.stringify(h.detail)}</div>
        </div>
      ))}
    </div>
  </div>
);
