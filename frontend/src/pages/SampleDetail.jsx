import { useCallback, useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Save, Send, CheckCircle2, XCircle, FileText } from "lucide-react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { coaEligibility, coaErrorMessage } from "@/lib/coaEligibility";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function SampleDetail() {
  const { id } = useParams();
  const { can, user } = useAuth();
  const [sample, setSample] = useState(null);
  const [specs, setSpecs] = useState([]);
  const [params, setParams] = useState([]);
  const [entries, setEntries] = useState({});
  const [audit, setAudit] = useState([]);
  const [qaComment, setQaComment] = useState("");

  const load = useCallback(async () => {
    const { data } = await api.get(`/samples/${id}`);
    setSample(data);
    const [sp, pr, au] = await Promise.all([
      api.get("/specifications", { params: { sample_point_id: data.sample_point_id } }),
      api.get("/parameters"),
      api.get("/audit-trail", { params: { entity_id: id } }),
    ]);
    setSpecs(sp.data);
    setParams(pr.data);
    setAudit(au.data);
    const map = {};
    (data.results || []).forEach((r) => {
      map[r.parameter_id] = {
        value: r.value_numeric !== null && r.value_numeric !== undefined ? String(r.value_numeric) : r.value_text || "",
        instrument_id: r.instrument_id || "",
        comment: "",
      };
    });
    setEntries(map);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (!sample) return <div className="text-sm text-slate-500">Loading record…</div>;

  const paramById = Object.fromEntries(params.map((p) => [p.id, p]));
  const resultsById = Object.fromEntries((sample.results || []).map((r) => [r.parameter_id, r]));
  const locked = sample.qa_status === "Approved";
  const canEdit = can("admin", "qc") && !locked;
  const activeSpecs = specs.filter((s) => s.active !== false);
  const outstandingParams = activeSpecs
    .filter((s) => {
      const r = resultsById[s.parameter_id];
      return !r || !["PASS", "WARN", "FAIL"].includes(r.status);
    })
    .map((s) => paramById[s.parameter_id]?.name)
    .filter(Boolean);
  const incomplete = activeSpecs.length > 0 && outstandingParams.length > 0;
  const coa = coaEligibility(sample, incomplete, outstandingParams);

  const saveResults = async () => {
    const payload = specs
      .map((s) => {
        const p = paramById[s.parameter_id];
        const e = entries[s.parameter_id];
        if (!p || !e || e.value === "") return null;
        return {
          parameter_id: s.parameter_id,
          value_numeric: p.value_type === "numeric" ? parseFloat(e.value) : null,
          value_text: p.value_type === "numeric" ? null : e.value,
          instrument_id: e.instrument_id || "",
          comment: e.comment || "",
        };
      })
      .filter(Boolean);
    if (payload.length === 0) return toast.error("Enter at least one result value");
    try {
      await api.post(`/samples/${id}/results`, { results: payload });
      toast.success("Results saved and evaluated against specification");
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const submitForReview = async () => {
    try {
      await api.post(`/samples/${id}/submit`, { comment: qaComment });
      toast.success("Submitted for QA review");
      setQaComment("");
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const decide = async (decision) => {
    try {
      await api.post(`/samples/${id}/decision/${decision}`, { comment: qaComment });
      toast.success(decision === "approve" ? "Record approved" : "Record returned for investigation");
      setQaComment("");
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const exportCoa = async () => {
    if (!coa.eligible) {
      toast.error(coa.message);
      return;
    }
    try {
      await api.get(`/samples/${id}/coa`);
      window.print();
    } catch (err) {
      toast.error(coaErrorMessage(err.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-5" data-testid="sample-detail-page">
      <Link to="/samples" className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 no-print">
        <ArrowLeft className="w-4 h-4" /> Sample browser
      </Link>

      <div className="bg-white border border-slate-200 rounded-md p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="label-caps">Record</div>
            <h1 className="text-3xl font-bold tracking-tight font-mono" data-testid="sample-record-id">
              {sample.record_id}
            </h1>
            <div className="text-sm text-slate-600 mt-1">
              {sample.sample_point_name} · {sample.sample_date} {sample.sample_time} · Analyst {sample.analyst_initials}
            </div>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <StatusBadge value={sample.status} testId="sample-status-badge" />
            <StatusBadge value={sample.overall_result} testId="sample-result-badge" />
            <StatusBadge value={sample.qa_status} testId="sample-qa-status-badge" />
            <Button
              variant="outline"
              size="sm"
              onClick={exportCoa}
              disabled={!coa.eligible}
              title={coa.message}
              data-testid="export-coa-btn"
              className="no-print"
            >
              <FileText className="w-4 h-4 mr-1.5" /> CoA
            </Button>
          </div>
        </div>
        {sample.qa_comment && (
          <div className="mt-4 text-sm bg-slate-50 border border-slate-200 rounded p-3" data-testid="qa-comment-box">
            <span className="label-caps mr-2">QA note</span>
            {sample.qa_comment} — {sample.qa_reviewer}
          </div>
        )}
        {!coa.eligible && (
          <div
            className="mt-4 text-sm bg-amber-50 border border-amber-200 text-amber-900 rounded p-3"
            data-testid="coa-unavailable-notice"
          >
            {coa.message}
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <div className="px-5 pt-4 label-caps">Analytical results vs specification</div>
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Parameter</TableHead>
              <TableHead>Method</TableHead>
              <TableHead>Spec</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Instrument</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Entered by</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="results-table-body">
            {specs.map((s) => {
              const p = paramById[s.parameter_id];
              if (!p) return null;
              const r = resultsById[s.parameter_id];
              const e = entries[s.parameter_id] || { value: "", instrument_id: "" };
              const spec =
                p.value_type === "numeric"
                  ? `${s.lower_limit ?? "–"} to ${s.upper_limit ?? "–"} ${p.units}`
                  : s.expected_text || "–";
              return (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{p.name}</TableCell>
                  <TableCell className="font-mono text-xs text-slate-500">{p.method}</TableCell>
                  <TableCell className="tabnum text-xs text-slate-600">{spec}</TableCell>
                  <TableCell>
                    {canEdit ? (
                      p.value_type === "numeric" ? (
                        <Input
                          type="number"
                          step="any"
                          className="h-8 w-28 tabnum"
                          data-testid={`result-input-${p.name.replace(/\s+/g, "-").toLowerCase()}`}
                          value={e.value}
                          onChange={(ev) =>
                            setEntries({ ...entries, [s.parameter_id]: { ...e, value: ev.target.value } })
                          }
                        />
                      ) : (
                        <select
                          className="h-8 w-44 border border-slate-300 rounded px-2 text-sm bg-white"
                          data-testid={`result-input-${p.name.replace(/\s+/g, "-").toLowerCase()}`}
                          value={e.value}
                          onChange={(ev) =>
                            setEntries({ ...entries, [s.parameter_id]: { ...e, value: ev.target.value } })
                          }
                        >
                          <option value="">Select…</option>
                          {(p.options || []).map((o) => (
                            <option key={o} value={o}>
                              {o}
                            </option>
                          ))}
                        </select>
                      )
                    ) : (
                      <span className="tabnum">{r ? (r.value_numeric ?? r.value_text) : "–"}</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {canEdit ? (
                      <Input
                        className="h-8 w-28"
                        placeholder="ID"
                        data-testid={`instrument-input-${p.name.replace(/\s+/g, "-").toLowerCase()}`}
                        value={e.instrument_id}
                        onChange={(ev) =>
                          setEntries({ ...entries, [s.parameter_id]: { ...e, instrument_id: ev.target.value } })
                        }
                      />
                    ) : (
                      <span className="font-mono text-xs">{r?.instrument_id || "–"}</span>
                    )}
                  </TableCell>
                  <TableCell>{r ? <StatusBadge value={r.status} testId={`result-status-${p.name.replace(/\s+/g, "-").toLowerCase()}`} /> : <StatusBadge value="PENDING" />}</TableCell>
                  <TableCell className="text-xs text-slate-500">
                    {r ? `${r.entered_by} (r${r.revision})` : "–"}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        {canEdit && (
          <div className="p-4 border-t border-slate-200 no-print">
            <Button onClick={saveResults} data-testid="save-results-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
              <Save className="w-4 h-4 mr-1.5" /> Save results
            </Button>
          </div>
        )}
        {locked && (
          <div className="p-4 border-t border-slate-200 text-sm text-slate-600" data-testid="locked-notice">
            This record is QA approved and locked from further data entry.
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 no-print">
        <div className="bg-white border border-slate-200 rounded-md p-5 space-y-3">
          <div className="label-caps">Workflow · signed in as {user.role.toUpperCase()}</div>
          <Textarea
            data-testid="workflow-comment-input"
            placeholder="Comment / reason (required for rejection)"
            value={qaComment}
            onChange={(e) => setQaComment(e.target.value)}
          />
          {incomplete && (
            <div
              className="text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded p-3"
              data-testid="incomplete-warning"
            >
              <div className="font-semibold mb-1">Record is incomplete — ordinary release is blocked.</div>
              <div>Outstanding required parameters:</div>
              <ul className="list-disc pl-5 mt-1" data-testid="outstanding-parameters-list">
                {outstandingParams.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            {can("admin", "qc") && sample.qa_status !== "Approved" && (
              <Button
                variant="outline"
                onClick={submitForReview}
                disabled={incomplete}
                data-testid="submit-review-btn"
                title={incomplete ? "All required results must be entered first" : ""}
              >
                <Send className="w-4 h-4 mr-1.5" /> Submit for QA review
              </Button>
            )}
            {can("admin", "qa") && sample.qa_status === "Pending Review" && (
              <>
                <Button
                  onClick={() => decide("approve")}
                  disabled={incomplete}
                  data-testid="qa-approve-btn"
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  title={incomplete ? "Cannot approve: required results are missing" : ""}
                >
                  <CheckCircle2 className="w-4 h-4 mr-1.5" /> Approve
                </Button>
                <Button
                  onClick={() => decide("reject")}
                  data-testid="qa-reject-btn"
                  className="bg-red-600 hover:bg-red-700 text-white"
                >
                  <XCircle className="w-4 h-4 mr-1.5" /> Reject
                </Button>
              </>
            )}
          </div>
          {!can("admin", "qa") && (
            <p className="text-xs text-slate-500">QA sign-off is restricted to QA and Admin roles.</p>
          )}
        </div>

        <div className="bg-white border border-slate-200 rounded-md p-5">
          <div className="label-caps mb-3">Record audit trail</div>
          <div className="space-y-2 max-h-72 overflow-y-auto" data-testid="record-audit-list">
            {audit.map((a) => (
              <div key={a.id} className="text-xs border-l-2 border-slate-200 pl-3 py-1">
                <div className="font-mono text-slate-900">{a.action}</div>
                <div className="text-slate-500">
                  {new Date(a.timestamp).toLocaleString()} · {a.user_email} ({a.user_role})
                </div>
                {a.reason && <div className="text-slate-600 italic">“{a.reason}”</div>}
              </div>
            ))}
            {audit.length === 0 && <div className="text-sm text-slate-500">No entries yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}
