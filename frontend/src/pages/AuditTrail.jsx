import { useEffect, useState } from "react";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function AuditTrail() {
  const [rows, setRows] = useState([]);
  const [action, setAction] = useState("");
  const [email, setEmail] = useState("");

  useEffect(() => {
    api
      .get("/audit-trail", { params: { action: action || undefined, user_email: email || undefined } })
      .then(({ data }) => setRows(data));
  }, [action, email]);

  return (
    <div className="space-y-5" data-testid="audit-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Audit Trail</h1>
        <p className="text-sm text-slate-600 mt-1">Immutable log of every data action — {rows.length} entries shown.</p>
      </div>

      <div className="flex flex-wrap gap-3">
        <Input
          className="max-w-xs bg-white"
          placeholder="Filter by action (e.g. QA_APPROVE)"
          data-testid="audit-action-filter"
          value={action}
          onChange={(e) => setAction(e.target.value.toUpperCase())}
        />
        <Input
          className="max-w-xs bg-white"
          placeholder="Filter by user email"
          data-testid="audit-user-filter"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Timestamp (UTC)</TableHead>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Action</TableHead>
              <TableHead>Entity</TableHead>
              <TableHead>Reference</TableHead>
              <TableHead>Reason</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="audit-table-body">
            {rows.map((a) => (
              <TableRow key={a.id} data-testid={`audit-row-${a.id}`}>
                <TableCell className="font-mono text-xs whitespace-nowrap">{a.timestamp?.slice(0, 19).replace("T", " ")}</TableCell>
                <TableCell className="text-xs">{a.user_email}</TableCell>
                <TableCell className="text-xs uppercase">{a.user_role}</TableCell>
                <TableCell className="font-mono text-xs font-semibold">{a.action}</TableCell>
                <TableCell className="text-xs">{a.entity}</TableCell>
                <TableCell className="font-mono text-[11px] text-slate-500">{a.entity_id?.slice(0, 12)}</TableCell>
                <TableCell className="text-xs text-slate-600">{a.reason || "–"}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-sm text-slate-500">
                  No audit entries match the filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
