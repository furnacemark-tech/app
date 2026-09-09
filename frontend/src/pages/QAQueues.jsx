import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  SAMPLE_QUEUE_FILTERS,
  sampleQueueCount,
  sampleQueueRows,
  totalSampleAttentionRecords,
} from "@/lib/qaQueue";

const Panel = ({ title, count, children, testId }) => (
  <div className="bg-white border border-slate-200 rounded-md" data-testid={testId}>
    <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
      <div className="label-caps">{title}</div>
      <div className="text-sm font-bold tabnum">{count}</div>
    </div>
    <div className="overflow-x-auto">{children}</div>
  </div>
);

export default function QAQueues() {
  const [q, setQ] = useState(null);
  const [sampleFilter, setSampleFilter] = useState("ready_for_review");
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/qa/queues").then(({ data }) => setQ(data));
  }, []);

  if (!q) return <div className="text-sm text-slate-500">Loading queues…</div>;

  const sampleRows = sampleQueueRows(q, sampleFilter);
  const sampleAttentionCount = totalSampleAttentionRecords(q);

  const batchTable = (rows, prefix) => (
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          <TableHead>Batch</TableHead>
          <TableHead>Product</TableHead>
          <TableHead>Production</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((b) => (
          <TableRow
            key={b.id}
            data-testid={`${prefix}-row-${b.batch_number}`}
            className="cursor-pointer hover:bg-slate-50 transition-colors duration-200"
            onClick={() => navigate(`/batches/${b.id}`)}
          >
            <TableCell className="font-mono text-xs">{b.batch_number}</TableCell>
            <TableCell>{b.product_name}</TableCell>
            <TableCell className="tabnum">{b.production_date}</TableCell>
            <TableCell><StatusBadge value={b.status} /></TableCell>
          </TableRow>
        ))}
        {rows.length === 0 && (
          <TableRow>
            <TableCell colSpan={4} className="text-sm text-slate-500">Queue is empty.</TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );

  const sampleTable = (rows) => (
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          <TableHead>Record</TableHead>
          <TableHead>Sample point</TableHead>
          <TableHead>Date</TableHead>
          <TableHead>Result</TableHead>
          <TableHead>QA status</TableHead>
          <TableHead>Attention reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody data-testid="sample-qa-queue-body">
        {rows.map((sample) => (
          <TableRow
            key={sample.id}
            data-testid={`sample-qa-queue-row-${sample.record_id}`}
            className="hover:bg-slate-50 transition-colors duration-200"
          >
            <TableCell className="font-mono text-xs">
              <Link
                to={`/samples/${sample.id}`}
                data-testid={`sample-qa-queue-link-${sample.record_id}`}
                className="underline underline-offset-2"
              >
                {sample.record_id}
              </Link>
            </TableCell>
            <TableCell>{sample.sample_point_name}</TableCell>
            <TableCell className="tabnum">{sample.sample_date}</TableCell>
            <TableCell><StatusBadge value={sample.overall_result} /></TableCell>
            <TableCell><StatusBadge value={sample.qa_status} /></TableCell>
            <TableCell
              className="max-w-md text-xs text-slate-700"
              data-testid={`sample-qa-attention-${sample.record_id}`}
            >
              {sample.attention_reasons.length > 0
                ? sample.attention_reasons.join(" · ")
                : "Awaiting QA decision."}
            </TableCell>
          </TableRow>
        ))}
        {rows.length === 0 && (
          <TableRow>
            <TableCell
              colSpan={6}
              className="text-sm text-slate-500"
              data-testid="sample-qa-empty-state"
            >
              No records match this QA classification.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  );

  return (
    <div className="space-y-5" data-testid="qa-queues-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">QA Work Queues</h1>
        <p className="text-sm text-slate-600 mt-1">
          Awaiting review, held for investigation, and certificates ready to send.
          {q.samples_pending_review > 0 && ` · ${q.samples_pending_review} sample record(s) also pending review.`}
        </p>
      </div>

      <Panel
        title="Sample QA attention"
        count={sampleAttentionCount}
        testId="sample-qa-queue-panel"
      >
        <div className="flex flex-wrap gap-2 border-b border-slate-200 p-3">
          {SAMPLE_QUEUE_FILTERS.map((filter) => (
            <Button
              key={filter.key}
              variant={sampleFilter === filter.key ? "default" : "outline"}
              size="sm"
              data-testid={`sample-qa-filter-${filter.key}`}
              onClick={() => setSampleFilter(filter.key)}
            >
              {filter.label} ({sampleQueueCount(q, filter.key)})
            </Button>
          ))}
        </div>
        {sampleTable(sampleRows)}
      </Panel>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Panel title="Batches awaiting review" count={q.awaiting_review.length} testId="queue-awaiting-review">
          {batchTable(q.awaiting_review, "awaiting")}
        </Panel>
        <Panel title="On hold / returned" count={q.on_hold.length} testId="queue-on-hold">
          {batchTable(q.on_hold, "hold")}
        </Panel>
      </div>

      <Panel title="Certificates ready for QA to send" count={q.certificates_to_send.length} testId="queue-to-send">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Certificate</TableHead>
              <TableHead>Rev</TableHead>
              <TableHead>Batch</TableHead>
              <TableHead>Product</TableHead>
              <TableHead>Customer</TableHead>
              <TableHead>Issued</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {q.certificates_to_send.map((c) => (
              <TableRow
                key={c.certificate_number}
                data-testid={`to-send-row-${c.certificate_number}`}
                className="cursor-pointer hover:bg-slate-50 transition-colors duration-200"
                onClick={() => navigate(`/batches/${c.batch_id}`)}
              >
                <TableCell className="font-mono text-xs">{c.certificate_number}</TableCell>
                <TableCell className="tabnum">{c.revision}</TableCell>
                <TableCell className="font-mono text-xs">{c.batch_number}</TableCell>
                <TableCell>{c.product_name}</TableCell>
                <TableCell>{c.customer_name || "All customers"}</TableCell>
                <TableCell className="font-mono text-xs">{c.issue_date?.slice(0, 10)}</TableCell>
              </TableRow>
            ))}
            {q.certificates_to_send.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-sm text-slate-500">Nothing waiting to be sent.</TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Panel>

      {q.reissue_required.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-md p-4" data-testid="queue-reissue-required">
          <div className="label-caps text-amber-800 mb-1">Replacement C of A to authorise</div>
          <div className="text-sm text-amber-900 space-y-1">
            {q.reissue_required.map((b) => (
              <button
                key={b.batch_id}
                data-testid={`reissue-required-${b.batch_number}`}
                className="block underline"
                onClick={() => navigate(`/batches/${b.batch_id}`)}
              >
                {b.batch_number} · {b.product_name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
