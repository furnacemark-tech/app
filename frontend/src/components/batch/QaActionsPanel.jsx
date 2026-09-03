import { Ban, FileCheck2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const DECISIONS = [
  { key: "return", label: "Return to QC", testId: "qa-return-btn", variant: "outline", className: "" },
  { key: "approve", label: "Approve", testId: "qa-approve-batch-btn", variant: "outline", className: "" },
  { key: "release", label: "Release", testId: "qa-release-batch-btn", className: "bg-emerald-600 hover:bg-emerald-700 text-white" },
  { key: "reject", label: "Reject", testId: "qa-reject-batch-btn", className: "bg-red-600 hover:bg-red-700 text-white" },
];

const InvestigationFields = ({ inv, onChange }) => (
  <>
    <Textarea
      placeholder="Issue / comment (required)"
      data-testid="inv-issue-input"
      value={inv.issue}
      onChange={(e) => onChange({ ...inv, issue: e.target.value })}
    />
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
      <Input placeholder="Root cause" data-testid="inv-root-cause-input" value={inv.root_cause} onChange={(e) => onChange({ ...inv, root_cause: e.target.value })} />
      <Input placeholder="Impact" data-testid="inv-impact-input" value={inv.impact} onChange={(e) => onChange({ ...inv, impact: e.target.value })} />
      <Input placeholder="Corrective action" data-testid="inv-corrective-input" value={inv.corrective_action} onChange={(e) => onChange({ ...inv, corrective_action: e.target.value })} />
    </div>
    <Textarea
      placeholder="Required actions for QC (one per line)"
      data-testid="inv-actions-input"
      value={inv.required_actions}
      onChange={(e) => onChange({ ...inv, required_actions: e.target.value })}
    />
  </>
);

const ProductionDateBlock = ({ batch, prod, onProdChange, onAmend }) => (
  <div className="border-t border-slate-200 pt-3 space-y-2">
    <div className="label-caps">Amend production date (QA only)</div>
    <div className="flex flex-wrap gap-2">
      <Input
        type="date"
        className="w-40"
        data-testid="qa-production-date-input"
        value={prod.production_date}
        onChange={(e) => onProdChange({ ...prod, production_date: e.target.value })}
      />
      <Input
        className="flex-1 min-w-[12rem]"
        placeholder="Reason (required)"
        data-testid="qa-production-reason-input"
        value={prod.reason}
        onChange={(e) => onProdChange({ ...prod, reason: e.target.value })}
      />
      <Button variant="outline" data-testid="qa-amend-production-date-btn" onClick={onAmend}>
        Amend
      </Button>
    </div>
    {batch.coa_reissue_required && (
      <p className="text-xs text-amber-700" data-testid="reissue-required-notice">
        Corrected data requires QA to authorise a replacement C of A below.
      </p>
    )}
  </div>
);

const CancelBlock = ({ cancel, onCancelChange, onCancel }) => (
  <div className="border-t border-slate-200 pt-3 space-y-2">
    <div className="label-caps">Cancel batch (QA only)</div>
    <div className="flex flex-wrap gap-2">
      <Input
        className="flex-1 min-w-[10rem]"
        placeholder="Cancellation reason"
        data-testid="cancel-reason-input"
        value={cancel.reason}
        onChange={(e) => onCancelChange({ ...cancel, reason: e.target.value })}
      />
      <Input
        className="w-56"
        placeholder="Replacement batch id (optional)"
        data-testid="cancel-replacement-input"
        value={cancel.replacement_batch_id}
        onChange={(e) => onCancelChange({ ...cancel, replacement_batch_id: e.target.value })}
      />
      <Button variant="outline" data-testid="cancel-batch-btn" onClick={onCancel}>
        <Ban className="w-4 h-4 mr-1.5" /> Cancel batch
      </Button>
    </div>
  </div>
);

const DISPOSITION_FIELDS = [
  { key: "investigation_conclusion", label: "Investigation conclusion", testId: "disp-conclusion-input" },
  { key: "impact_assessment", label: "Scientific / technical impact assessment", testId: "disp-impact-input" },
  { key: "release_justification", label: "Justification for release", testId: "disp-justification-input" },
];

const DispositionBlock = ({ batch, disposition, onChange, onRelease }) => {
  if (batch.status !== "ON_HOLD" && !batch.investigation_required) return null;
  const failing = (batch.results || []).filter((r) => r.status === "FAIL");
  return (
    <div className="border-t border-slate-200 pt-3 space-y-2" data-testid="disposition-block">
      <div className="label-caps">Release after investigation (OOS disposition)</div>
      {failing.length > 0 ? (
        <p className="text-xs text-slate-600" data-testid="disposition-oos-list">
          Out of specification: {failing.map((r) => `${r.parameter_name} = ${r.value_numeric ?? r.value_text} ${r.units}`).join(", ")}.
          The original result and its FAIL classification are never changed by this disposition.
        </p>
      ) : (
        <p className="text-xs text-slate-600">No out of specification result is recorded on this batch.</p>
      )}
      {DISPOSITION_FIELDS.map((f) => (
        <div key={f.key}>
          <Label className="label-caps">{f.label}</Label>
          <Textarea
            data-testid={f.testId}
            value={disposition[f.key]}
            onChange={(e) => onChange({ ...disposition, [f.key]: e.target.value })}
          />
        </div>
      ))}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <Input
          placeholder="Corrective / preventive action"
          data-testid="disp-corrective-input"
          value={disposition.corrective_action}
          onChange={(e) => onChange({ ...disposition, corrective_action: e.target.value })}
        />
        <Input
          placeholder="Evidence / specialist assessment references (comma separated)"
          data-testid="disp-evidence-input"
          value={disposition.evidence_references}
          onChange={(e) => onChange({ ...disposition, evidence_references: e.target.value })}
        />
      </div>
      <label className="flex items-start gap-2 text-xs text-slate-700">
        <input
          type="checkbox"
          data-testid="disp-corrective-na-checkbox"
          checked={disposition.corrective_action_not_applicable}
          onChange={(e) => onChange({ ...disposition, corrective_action_not_applicable: e.target.checked })}
        />
        Corrective / preventive action is not applicable
      </label>
      <label className="flex items-start gap-2 text-xs text-slate-700">
        <input
          type="checkbox"
          data-testid="disp-accept-oos-checkbox"
          checked={disposition.oos_reviewed_accepted_without_change}
          onChange={(e) => onChange({ ...disposition, oos_reviewed_accepted_without_change: e.target.checked })}
        />
        I confirm the OOS result has been reviewed and is accepted for disposition without changing its original FAIL
        classification
      </label>
      <Button
        data-testid="qa-release-after-investigation-btn"
        className="bg-amber-600 hover:bg-amber-700 text-white"
        onClick={onRelease}
      >
        <FileCheck2 className="w-4 h-4 mr-1.5" /> Release after investigation
      </Button>
    </div>
  );
};

export const QaActionsPanel = ({
  batch,
  inv,
  onInvChange,
  onDecision,
  prod,
  onProdChange,
  onAmendProductionDate,
  cancel,
  onCancelChange,
  onCancel,
  disposition,
  onDispositionChange,
  onReleaseAfterInvestigation,
}) => (
  <div className="bg-white border border-slate-200 rounded-md p-5 space-y-3" data-testid="qa-actions">
    <div className="label-caps">QA review &amp; investigation</div>
    <InvestigationFields inv={inv} onChange={onInvChange} />
    <div className="flex flex-wrap gap-2">
      {DECISIONS.map((d) => (
        <Button
          key={d.key}
          variant={d.variant}
          className={d.className}
          data-testid={d.testId}
          onClick={() => onDecision(d.key)}
        >
          {d.label}
        </Button>
      ))}
    </div>
    <DispositionBlock
      batch={batch}
      disposition={disposition}
      onChange={onDispositionChange}
      onRelease={onReleaseAfterInvestigation}
    />
    <ProductionDateBlock batch={batch} prod={prod} onProdChange={onProdChange} onAmend={onAmendProductionDate} />
    <CancelBlock cancel={cancel} onCancelChange={onCancelChange} onCancel={onCancel} />
  </div>
);
