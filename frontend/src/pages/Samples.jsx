import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Search } from "lucide-react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function Samples() {
  const { can, user } = useAuth();
  const navigate = useNavigate();
  const [samples, setSamples] = useState([]);
  const [points, setPoints] = useState([]);
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    sample_point_id: "",
    sample_date: new Date().toISOString().slice(0, 10),
    sample_time: new Date().toTimeString().slice(0, 5),
    analyst_initials: "",
    notes: "",
  });

  const load = useCallback(
    () => api.get("/samples", { params: { search: search || undefined } }).then(({ data }) => setSamples(data)),
    [search]
  );

  useEffect(() => {
    api.get("/sample-points").then(({ data }) => {
      setPoints(data);
      setForm((f) => ({ ...f, sample_point_id: f.sample_point_id || data[0]?.id || "" }));
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/samples", { ...form, analyst_initials: form.analyst_initials || user.initials });
      toast.success(`Sample ${data.record_id} registered`);
      setOpen(false);
      navigate(`/samples/${data.id}`);
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-5" data-testid="samples-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Sample Browser</h1>
          <p className="text-sm text-slate-600 mt-1">{samples.length} records</p>
        </div>
        {can("admin", "qc", "qa") && (
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button data-testid="register-sample-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
                <Plus className="w-4 h-4 mr-1.5" /> Register sample
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-white" aria-describedby="register-sample-desc">
              <DialogHeader>
                <DialogTitle>Register new sample</DialogTitle>
                <p id="register-sample-desc" className="text-sm text-slate-600">
                  Creates an auditable sample record for result entry.
                </p>
              </DialogHeader>
              <form onSubmit={create} className="space-y-3" data-testid="register-sample-form">
                <div>
                  <Label className="label-caps">Sample point</Label>
                  <select
                    data-testid="sample-point-select"
                    className="mt-1.5 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
                    value={form.sample_point_id}
                    onChange={(e) => setForm({ ...form, sample_point_id: e.target.value })}
                    required
                  >
                    {points.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="label-caps">Date</Label>
                    <Input
                      type="date"
                      data-testid="sample-date-input"
                      value={form.sample_date}
                      onChange={(e) => setForm({ ...form, sample_date: e.target.value })}
                      required
                    />
                  </div>
                  <div>
                    <Label className="label-caps">Time</Label>
                    <Input
                      type="time"
                      data-testid="sample-time-input"
                      value={form.sample_time}
                      onChange={(e) => setForm({ ...form, sample_time: e.target.value })}
                    />
                  </div>
                </div>
                <div>
                  <Label className="label-caps">Analyst initials</Label>
                  <Input
                    data-testid="sample-analyst-input"
                    placeholder={user.initials}
                    value={form.analyst_initials}
                    onChange={(e) => setForm({ ...form, analyst_initials: e.target.value })}
                  />
                </div>
                <Button type="submit" data-testid="submit-sample-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
                  Create record
                </Button>
              </form>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <div className="relative max-w-sm">
        <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
        <Input
          data-testid="sample-search-input"
          placeholder="Search record ID…"
          className="pl-9 bg-white"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Record ID</TableHead>
              <TableHead>Sample point</TableHead>
              <TableHead>Date</TableHead>
              <TableHead>Analyst</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Result</TableHead>
              <TableHead>QA status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="samples-table-body">
            {samples.map((s) => (
              <TableRow
                key={s.id}
                data-testid={`sample-row-${s.record_id}`}
                className="cursor-pointer hover:bg-slate-50 transition-colors duration-200"
                onClick={() => navigate(`/samples/${s.id}`)}
              >
                <TableCell className="font-mono text-xs">{s.record_id}</TableCell>
                <TableCell>{s.sample_point_name}</TableCell>
                <TableCell className="tabnum">{s.sample_date}</TableCell>
                <TableCell>{s.analyst_initials}</TableCell>
                <TableCell><StatusBadge value={s.status} /></TableCell>
                <TableCell><StatusBadge value={s.overall_result} /></TableCell>
                <TableCell><StatusBadge value={s.qa_status} /></TableCell>
              </TableRow>
            ))}
            {samples.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="text-slate-500 text-sm">
                  No samples found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
