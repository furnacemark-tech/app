import { Save } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const testKey = (name) => name.replace(/\s+/g, "-").toLowerCase();

const specText = (parameter, limit) => {
  if (parameter.value_type === "numeric") {
    return `${limit.lower_limit ?? "–"} to ${limit.upper_limit ?? "–"} ${parameter.units}`;
  }
  return limit.expected_text;
};

const ResultInput = ({ parameter, entry, onChange }) => {
  const key = testKey(parameter.name);
  if (parameter.value_type === "numeric") {
    return (
      <Input
        type="number"
        step="any"
        className="h-8 w-28 tabnum"
        data-testid={`batch-result-input-${key}`}
        value={entry.value}
        onChange={(ev) => onChange({ ...entry, value: ev.target.value })}
      />
    );
  }
  return (
    <select
      className="h-8 w-44 border border-slate-300 rounded px-2 text-sm bg-white"
      data-testid={`batch-result-input-${key}`}
      value={entry.value}
      onChange={(ev) => onChange({ ...entry, value: ev.target.value })}
    >
      <option value="">Select…</option>
      {(parameter.options || []).map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
};

const ResultHistory = ({ result, testId }) => {
  if (!result) return <>–</>;
  if ((result.amendments || []).length === 0) return <>{`r${result.revision} ${result.entered_by}`}</>;
  return (
    <div data-testid={testId}>
      {result.amendments.map((a) => (
        <div key={a.timestamp}>
          {String(a.original_value)} → {String(a.new_value)} · {a.user_email} · “{a.reason}”
        </div>
      ))}
    </div>
  );
};

const ResultRow = ({ parameter, limit, result, entry, editable, onEntryChange }) => {
  const key = testKey(parameter.name);
  return (
    <TableRow>
      <TableCell className="font-medium">{parameter.name}</TableCell>
      <TableCell className="text-xs tabnum text-slate-600">{specText(parameter, limit)}</TableCell>
      <TableCell>
        {editable ? (
          <ResultInput parameter={parameter} entry={entry} onChange={onEntryChange} />
        ) : (
          <span className="tabnum">{result ? result.value_numeric ?? result.value_text : "–"}</span>
        )}
      </TableCell>
      {editable && (
        <TableCell>
          <Input
            className="h-8 w-48"
            placeholder={result ? "Required to amend" : "–"}
            data-testid={`batch-reason-input-${key}`}
            value={entry.reason}
            onChange={(ev) => onEntryChange({ ...entry, reason: ev.target.value })}
          />
        </TableCell>
      )}
      <TableCell>
        <StatusBadge value={result ? result.status : "PENDING"} testId={result ? `batch-result-status-${key}` : undefined} />
      </TableCell>
      <TableCell className="text-xs text-slate-500">
        <ResultHistory result={result} testId={`amendment-history-${key}`} />
      </TableCell>
    </TableRow>
  );
};

export const BatchResultsTable = ({
  batch,
  paramById,
  resultsById,
  entries,
  editable,
  instruments,
  instrumentId,
  onInstrumentChange,
  onEntryChange,
  onSave,
}) => (
  <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
    <div className="px-5 pt-4 label-caps">Test results vs approved specification</div>
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          <TableHead>Parameter</TableHead>
          <TableHead>Spec</TableHead>
          <TableHead>Result</TableHead>
          {editable && <TableHead>Amendment reason</TableHead>}
          <TableHead>Status</TableHead>
          <TableHead>History</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody data-testid="batch-results-body">
        {(batch.applied_limits || []).map((limit) => {
          const parameter = paramById[limit.parameter_id];
          if (!parameter) return null;
          return (
            <ResultRow
              key={limit.parameter_id}
              parameter={parameter}
              limit={limit}
              result={resultsById[limit.parameter_id]}
              entry={entries[limit.parameter_id] || { value: "", reason: "" }}
              editable={editable}
              onEntryChange={(entry) => onEntryChange(limit.parameter_id, entry)}
            />
          );
        })}
      </TableBody>
    </Table>

    {editable && (
      <div className="p-4 border-t border-slate-200 flex flex-wrap items-end gap-3 no-print">
        <div>
          <Label className="label-caps">Confirm instrument used</Label>
          <select
            data-testid="batch-instrument-select"
            className="mt-1.5 h-9 border border-slate-300 rounded px-2 text-sm bg-white"
            value={instrumentId}
            onChange={(e) => onInstrumentChange(e.target.value)}
          >
            <option value="">Select instrument…</option>
            {instruments.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name} {i.in_calibration && i.in_service ? "" : "(overdue)"}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={onSave} data-testid="save-batch-results-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
          <Save className="w-4 h-4 mr-1.5" /> Save results
        </Button>
      </div>
    )}
  </div>
);
