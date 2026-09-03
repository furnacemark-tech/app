import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function OOSLog() {
  const [rows, setRows] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/oos-log").then(({ data }) => setRows(data));
  }, []);

  return (
    <div className="space-y-5" data-testid="oos-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Out of Specification Log</h1>
        <p className="text-sm text-slate-600 mt-1">Failures and rejected records raised for investigation.</p>
      </div>
      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Record ID</TableHead>
              <TableHead>Sample point</TableHead>
              <TableHead>Raised</TableHead>
              <TableHead>Raised by</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="oos-table-body">
            {rows.map((o) => (
              <TableRow
                key={o.id}
                className="cursor-pointer hover:bg-slate-50 transition-colors duration-200"
                data-testid={`oos-row-${o.record_id}`}
                onClick={() => navigate(`/samples/${o.sample_id}`)}
              >
                <TableCell className="font-mono text-xs">{o.record_id}</TableCell>
                <TableCell>{o.sample_point_name}</TableCell>
                <TableCell className="font-mono text-xs">{o.raised_at?.slice(0, 19).replace("T", " ")}</TableCell>
                <TableCell className="text-xs">{o.raised_by}</TableCell>
                <TableCell className="text-xs">{o.reason}</TableCell>
                <TableCell><StatusBadge value={o.status} /></TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-sm text-slate-500">
                  No OOS events logged.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
