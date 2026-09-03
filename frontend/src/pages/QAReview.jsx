import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const TABS = [
  { key: "Pending Review", label: "Review queue" },
  { key: "Approved", label: "Approved records" },
  { key: "Requires Investigation", label: "Correction queue" },
];

export default function QAReview() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("Pending Review");
  const [rows, setRows] = useState([]);

  useEffect(() => {
    api.get("/samples", { params: { qa_status: tab } }).then(({ data }) => setRows(data));
  }, [tab]);

  return (
    <div className="space-y-5" data-testid="qa-review-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">QA Review</h1>
        <p className="text-sm text-slate-600 mt-1">Sign off, reject and track corrective records.</p>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-white border border-slate-200">
          {TABS.map((t) => (
            <TabsTrigger key={t.key} value={t.key} data-testid={`qa-tab-${t.key.replace(/\s+/g, "-").toLowerCase()}`}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Record ID</TableHead>
              <TableHead>Sample point</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Analyst</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>Reviewer</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="qa-queue-body">
            {rows.map((s) => (
              <TableRow
                key={s.id}
                data-testid={`qa-row-${s.record_id}`}
                className="cursor-pointer hover:bg-slate-50 transition-colors duration-200"
                onClick={() => navigate(`/samples/${s.id}`)}
              >
                <TableCell className="font-mono text-xs">{s.record_id}</TableCell>
                <TableCell>{s.sample_point_name}</TableCell>
                <TableCell className="tabnum">{s.sample_date}</TableCell>
                <TableCell>{s.analyst_initials}</TableCell>
                <TableCell><StatusBadge value={s.overall_result} /></TableCell>
                <TableCell className="text-xs text-slate-500">{s.qa_reviewer || "–"}</TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-sm text-slate-500">
                  Queue is empty.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
