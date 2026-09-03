import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const deliveryLabel = (status) => (status === "READY_FOR_QA_TO_SEND" ? "Ready for QA to send" : status);

const shelfLifeLine = (snapshot) =>
  snapshot?.shelf_life_required ? ` · Expiry ${snapshot?.expiry_date}` : " · shelf life not applicable";

const CoaActions = ({ coa, isQa, onDownload, onSend, onReissue }) => (
  <div className="flex flex-wrap items-center gap-2">
    <StatusBadge value={coa.status === "ACTIVE" ? "PASS" : "CLOSED"} />
    <span className="text-[11px] uppercase tracking-wide text-slate-600" data-testid={`coa-delivery-status-${coa.certificate_number}`}>
      {deliveryLabel(coa.delivery_status)}
    </span>
    <Button size="sm" variant="outline" data-testid={`download-coa-pdf-btn-${coa.certificate_number}`} onClick={() => onDownload(coa)}>
      PDF
    </Button>
    {isQa && coa.status === "ACTIVE" && (
      <>
        <Button size="sm" variant="outline" data-testid={`send-coa-btn-${coa.certificate_number}`} onClick={() => onSend(coa)}>
          Record send
        </Button>
        <Button size="sm" variant="outline" data-testid={`reissue-coa-btn-${coa.certificate_number}`} onClick={() => onReissue(coa)}>
          Authorise replacement
        </Button>
      </>
    )}
  </div>
);

const CoaCard = ({ coa, supersededCert, isQa, onDownload, onSend, onReissue }) => (
  <div className="border border-slate-200 rounded p-3 text-sm" data-testid={`coa-${coa.certificate_number}`}>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div>
        <div className="font-mono font-semibold">{coa.certificate_number}</div>
        <div className="text-xs text-slate-600">
          Revision {coa.revision} · issued {coa.issue_date?.slice(0, 19).replace("T", " ")} ·{" "}
          {coa.customer_name || "All customers"} · authorised by {coa.authorised_by}
        </div>
        {coa.supersedes_coa_id && (
          <div className="text-xs text-slate-500">
            Replaces {supersededCert} — “{coa.reason}”
          </div>
        )}
        <div className="text-xs text-slate-600">
          Production {coa.snapshot?.production_date}
          {shelfLifeLine(coa.snapshot)}
        </div>
      </div>
      <CoaActions coa={coa} isQa={isQa} onDownload={onDownload} onSend={onSend} onReissue={onReissue} />
    </div>
  </div>
);

const DeliveryTable = ({ deliveries }) => (
  <div className="mt-5">
    <div className="label-caps mb-2">Delivery records</div>
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          <TableHead>Certificate</TableHead>
          <TableHead>Rev</TableHead>
          <TableHead>Customer</TableHead>
          <TableHead>Recipient</TableHead>
          <TableHead>Email</TableHead>
          <TableHead>Sent by</TableHead>
          <TableHead>Sent at</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody data-testid="deliveries-body">
        {deliveries.map((d) => (
          <TableRow key={d.id} data-testid={`delivery-row-${d.recipient_email}`}>
            <TableCell className="font-mono text-xs">{d.certificate_number}</TableCell>
            <TableCell className="tabnum">{d.coa_revision}</TableCell>
            <TableCell className="text-xs">{d.customer_name || "–"}</TableCell>
            <TableCell className="text-xs">{d.recipient_name}</TableCell>
            <TableCell className="font-mono text-xs">{d.recipient_email}</TableCell>
            <TableCell className="text-xs">{d.sent_by}</TableCell>
            <TableCell className="font-mono text-xs">{d.sent_at?.slice(0, 19).replace("T", " ")}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </div>
);

export const CoaSection = ({ batch, isQa, onDownload, onSend, onReissue }) => {
  const coas = batch.coas || [];
  const deliveries = batch.deliveries || [];
  const certNumberById = Object.fromEntries(coas.map((c) => [c.id, c.certificate_number]));

  return (
    <div className="bg-white border border-slate-200 rounded-md p-5" data-testid="coa-section">
      <div className="label-caps mb-3">Certificates of Analysis</div>
      <div className="space-y-2">
        {coas.map((c) => (
          <CoaCard
            key={c.id}
            coa={c}
            supersededCert={certNumberById[c.supersedes_coa_id]}
            isQa={isQa}
            onDownload={onDownload}
            onSend={onSend}
            onReissue={onReissue}
          />
        ))}
        {coas.length === 0 && <div className="text-sm text-slate-500">No certificate generated yet.</div>}
      </div>
      {deliveries.length > 0 && <DeliveryTable deliveries={deliveries} />}
    </div>
  );
};
