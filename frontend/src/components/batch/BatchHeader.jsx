import { StatusBadge } from "@/components/StatusBadge";
import { ShieldAlert } from "lucide-react";

const Field = ({ label, value, testId }) => (
  <div>
    <div className="label-caps">{label}</div>
    <div className="text-sm tabnum" data-testid={testId}>
      {value ?? "–"}
    </div>
  </div>
);

const customerLabel = (batch) => {
  if (batch.customer_name) return batch.customer_name;
  return batch.sales_mode === "multi" ? "Multi-customer" : "–";
};

export const BatchHeader = ({ batch }) => (
  <div className="bg-white border border-slate-200 rounded-md p-5">
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <div className="label-caps">Batch</div>
        <h1 className="text-3xl font-bold tracking-tight font-mono" data-testid="batch-number">
          {batch.batch_number}
        </h1>
        <div className="text-sm text-slate-600 mt-1">{batch.product_name}</div>
      </div>
      <StatusBadge value={batch.status} testId="batch-status-badge" />
    </div>

    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-5">
      <Field label="Production date" value={batch.production_date} testId="batch-production-date" />
      {batch.shelf_life_required && (
        <>
          <Field label="Shelf life (days)" value={batch.shelf_life_days} testId="batch-shelf-life" />
          <Field label="Expiry date (calculated)" value={batch.expiry_date} testId="batch-expiry-date" />
        </>
      )}
      <Field label="Specification version" value={`v${batch.spec_version}`} testId="batch-spec-version" />
      <Field label="Overall result" value={batch.overall_result} testId="batch-overall-result" />
      <Field label="Release basis" value={batch.release_basis} testId="batch-release-basis" />
      <Field label="Customer" value={customerLabel(batch)} testId="batch-customer" />
      <Field label="Instrument" value={batch.instrument_snapshot?.name} testId="batch-instrument" />
    </div>

    {batch.hold_reasons?.length > 0 && (
      <div className="mt-4 bg-red-50 border border-red-200 rounded p-3 text-sm text-red-800" data-testid="hold-reasons">
        <div className="label-caps text-red-700 flex items-center gap-1.5 mb-1">
          <ShieldAlert className="w-3.5 h-3.5" /> On hold for QA investigation
        </div>
        <ul className="list-disc pl-5">
          {batch.hold_reasons.map((r, i) => (
            <li key={`${i}-${r}`}>{r}</li>
          ))}
        </ul>
      </div>
    )}

    {batch.required_actions?.length > 0 && batch.status === "RETURNED" && (
      <div className="mt-4 bg-amber-50 border border-amber-200 rounded p-3 text-sm text-amber-900" data-testid="required-actions">
        <div className="label-caps text-amber-800 mb-1">QA required investigation actions</div>
        <ul className="list-disc pl-5">
          {batch.required_actions.map((r, i) => (
            <li key={`${i}-${r}`}>{r}</li>
          ))}
        </ul>
      </div>
    )}

    {batch.active_disposition && (
      <div className="mt-4 bg-amber-50 border border-amber-300 rounded p-3 text-sm text-amber-900" data-testid="disposition-notice">
        <div className="label-caps text-amber-800 mb-1">
          Released after investigation · {batch.active_disposition.reference}
        </div>
        <div className="text-xs space-y-0.5">
          <div>
            Out of specification result retained as FAIL against specification v
            {batch.active_disposition.spec_version}:{" "}
            {batch.active_disposition.accepted_oos_results
              .map((a) => `${a.parameter_name} = ${a.original_value} ${a.units}`)
              .join(", ")}
          </div>
          <div>Conclusion: {batch.active_disposition.investigation_conclusion}</div>
          <div>Impact: {batch.active_disposition.impact_assessment}</div>
          <div>Justification: {batch.active_disposition.release_justification}</div>
          <div>
            Evidence: {batch.active_disposition.evidence_references.join(", ")} · QA{" "}
            {batch.active_disposition.qa_user} · {new Date(batch.active_disposition.recorded_at).toLocaleString()}
          </div>
        </div>
      </div>
    )}

    {batch.cancelled && (
      <div className="mt-4 bg-slate-100 border border-slate-300 rounded p-3 text-sm" data-testid="cancelled-notice">
        Cancelled by {batch.cancelled.cancelled_by} on {batch.cancelled.cancelled_at?.slice(0, 19).replace("T", " ")} — “
        {batch.cancelled.reason}”. Release and C of A delivery are blocked.
      </div>
    )}
  </div>
);
