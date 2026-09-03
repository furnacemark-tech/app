import { useCallback, useMemo, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useBatch, buildResultPayload, downloadBlob } from "@/hooks/useBatch";
import { BatchHeader } from "@/components/batch/BatchHeader";
import { BatchResultsTable } from "@/components/batch/BatchResultsTable";
import { QcActionsPanel } from "@/components/batch/QcActionsPanel";
import { QaActionsPanel } from "@/components/batch/QaActionsPanel";
import { CoaSection } from "@/components/batch/CoaSection";
import { BatchHistory } from "@/components/batch/BatchHistory";
import { SendCoaDialog, ReissueCoaDialog } from "@/components/batch/CoaDialogs";

const QC_EDITABLE_STATUSES = ["DRAFT", "RETURNED", "ON_HOLD"];
const EMPTY_INVESTIGATION = { issue: "", root_cause: "", impact: "", corrective_action: "", required_actions: "" };
const EMPTY_DISPOSITION = {
  investigation_conclusion: "",
  impact_assessment: "",
  release_justification: "",
  corrective_action: "",
  corrective_action_not_applicable: false,
  evidence_references: "",
  oos_reviewed_accepted_without_change: false,
};

export default function BatchDetail() {
  const { id } = useParams();
  const { can, user } = useAuth();
  const {
    batch, paramById, resultsById, instruments, customers,
    entries, setEntries, instrumentId, setInstrumentId, productionDate, setProductionDate, call,
  } = useBatch(id);

  const [releaseCustomers, setReleaseCustomers] = useState([]);
  const [inv, setInv] = useState(EMPTY_INVESTIGATION);
  const [prodReason, setProdReason] = useState("");
  const [cancel, setCancel] = useState({ reason: "", replacement_batch_id: "" });
  const [sendFor, setSendFor] = useState(null);
  const [recipients, setRecipients] = useState([]);
  const [manual, setManual] = useState({ name: "", email: "" });
  const [reissue, setReissue] = useState(null);
  const [reissueReason, setReissueReason] = useState("");
  const [disposition, setDisposition] = useState(EMPTY_DISPOSITION);

  const selectableContacts = useMemo(
    () =>
      customers
        .filter((c) => !sendFor?.customer_id || c.id === sendFor.customer_id)
        .flatMap((c) => (c.contacts || []).map((ct) => ({ ...ct, customer: c.name }))),
    [customers, sendFor]
  );

  const downloadCoaPdf = useCallback(
    async (coa) => {
      const { data } = await api.get(`/batches/${id}/coa/${coa.id}/pdf`, { responseType: "blob" });
      downloadBlob(data, `${coa.certificate_number}.pdf`);
      toast.success("C of A PDF downloaded");
    },
    [id]
  );

  if (!batch) return <div className="text-sm text-slate-500">Loading batch…</div>;

  const qcEditable = can("admin", "qc") && QC_EDITABLE_STATUSES.includes(batch.status);

  const saveResults = () =>
    call(
      () =>
        api.post(`/batches/${id}/results`, {
          results: buildResultPayload(batch, paramById, resultsById, entries),
          instrument_id: instrumentId || null,
        }),
      "Results saved"
    );

  const decision = (d) =>
    call(
      () =>
        api.post(`/batches/${id}/qa-decision/${d}`, {
          ...inv,
          required_actions: inv.required_actions.split("\n").map((s) => s.trim()).filter(Boolean),
        }),
      `QA decision recorded: ${d}`
    );

  const sendCoa = async () => {
    const ok = await call(() => api.post(`/batches/${id}/coa/${sendFor.id}/send`, { recipients }), "Delivery recorded");
    if (ok) {
      setSendFor(null);
      setRecipients([]);
    }
  };

  const authoriseReissue = async () => {
    const ok = await call(
      () => api.post(`/batches/${id}/coa/${reissue.id}/authorise-replacement`, { reason: reissueReason }),
      "Replacement C of A authorised"
    );
    if (ok) setReissue(null);
  };

  return (
    <div className="space-y-5" data-testid="batch-detail-page">
      <Link to="/batches" className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 no-print">
        <ArrowLeft className="w-4 h-4" /> Batches
      </Link>

      <BatchHeader batch={batch} />

      <BatchResultsTable
        batch={batch}
        paramById={paramById}
        resultsById={resultsById}
        entries={entries}
        editable={qcEditable}
        instruments={instruments}
        instrumentId={instrumentId}
        onInstrumentChange={setInstrumentId}
        onEntryChange={(parameterId, entry) => setEntries({ ...entries, [parameterId]: entry })}
        onSave={saveResults}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 no-print">
        {can("admin", "qc") && (
          <QcActionsPanel
            batch={batch}
            customers={customers}
            releaseCustomers={releaseCustomers}
            onToggleCustomer={(customerId, checked) =>
              setReleaseCustomers(
                checked ? [...releaseCustomers, customerId] : releaseCustomers.filter((x) => x !== customerId)
              )
            }
            onSubmit={() => call(() => api.post(`/batches/${id}/submit`, { comment: inv.issue }), "Submitted to QA")}
            onRelease={() =>
              call(
                () => api.post(`/batches/${id}/release`, { customer_ids: releaseCustomers }),
                "Batch released and C of A generated"
              )
            }
          />
        )}

        {can("qa") && (
          <QaActionsPanel
            batch={batch}
            inv={inv}
            onInvChange={setInv}
            onDecision={decision}
            prod={{ production_date: productionDate, reason: prodReason }}
            onProdChange={(next) => {
              setProductionDate(next.production_date);
              setProdReason(next.reason);
            }}
            onAmendProductionDate={() =>
              call(
                () =>
                  api.post(`/batches/${id}/production-date`, {
                    production_date: productionDate,
                    reason: prodReason,
                  }),
                "Production date amended and expiry recalculated"
              )
            }
            cancel={cancel}
            onCancelChange={setCancel}
            disposition={disposition}
            onDispositionChange={setDisposition}
            onReleaseAfterInvestigation={() =>
              call(
                () =>
                  api.post(`/batches/${id}/disposition/release-after-investigation`, {
                    ...disposition,
                    issue: inv.issue || disposition.investigation_conclusion,
                    evidence_references: disposition.evidence_references
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  }),
                "Batch released after documented investigation — original FAIL result retained"
              )
            }
            onCancel={() =>
              call(
                () =>
                  api.post(`/batches/${id}/cancel`, {
                    reason: cancel.reason,
                    replacement_batch_id: cancel.replacement_batch_id || null,
                  }),
                "Batch cancelled"
              )
            }
          />
        )}
      </div>

      <CoaSection
        batch={batch}
        isQa={can("qa")}
        onDownload={downloadCoaPdf}
        onSend={(c) => {
          setSendFor(c);
          setRecipients([]);
        }}
        onReissue={(c) => {
          setReissue(c);
          setReissueReason("");
        }}
      />

      <BatchHistory history={batch.history} />

      <SendCoaDialog
        open={!!sendFor}
        onOpenChange={(o) => !o && setSendFor(null)}
        contacts={selectableContacts}
        recipients={recipients}
        onRecipientsChange={setRecipients}
        manual={manual}
        onManualChange={setManual}
        onSend={sendCoa}
      />

      <ReissueCoaDialog
        open={!!reissue}
        onOpenChange={(o) => !o && setReissue(null)}
        reason={reissueReason}
        onReasonChange={setReissueReason}
        onConfirm={authoriseReissue}
      />

      <div className="text-xs text-slate-500">
        Signed in as {user.email} ({user.role.toUpperCase()})
      </div>
    </div>
  );
}
