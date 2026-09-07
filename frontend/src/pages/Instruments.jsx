import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { StatusBadge } from "@/components/StatusBadge";
import { NewInstrumentDialog } from "@/components/instruments/NewInstrumentDialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const EMPTY_FORM = {
  name: "",
  instrument_code: "",
  calibration_due: "",
  service_due: "",
  category: "",
  availability_status: "AVAILABLE",
};

export default function Instruments() {
  const { can } = useAuth();
  const editable = can("admin", "qa");
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);

  const load = useCallback(() => api.get("/instruments").then(({ data }) => setItems(data)), []);

  useEffect(() => {
    load();
  }, [load]);

  const create = async (e) => {
    e.preventDefault();
    try {
      await api.post("/instruments", { ...form, active: true });
      toast.success("Instrument registered");
      setOpen(false);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-5" data-testid="instruments-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Instrument Register</h1>
          <p className="text-sm text-slate-600 mt-1">Calibration and service state gate batch release.</p>
        </div>
        {editable && (
          <NewInstrumentDialog open={open} onOpenChange={setOpen} form={form} onFormChange={setForm} onSubmit={create} />
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Instrument</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Availability</TableHead>
              <TableHead>Calibration due</TableHead>
              <TableHead>Service due</TableHead>
              <TableHead>State</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="instruments-table-body">
            {items.map((i) => (
              <TableRow key={i.id} data-testid={`instrument-row-${i.instrument_code || i.name}`}>
                <TableCell className="font-medium">{i.name}</TableCell>
                <TableCell className="font-mono text-xs">{i.instrument_code}</TableCell>
                <TableCell className="text-xs">{i.category || "Not configured"}</TableCell>
                <TableCell className="text-xs">{i.availability_status}</TableCell>
                <TableCell className="tabnum">{i.calibration_due}</TableCell>
                <TableCell className="tabnum">{i.service_due}</TableCell>
                <TableCell>
                  <StatusBadge value={i.eligible ? "PASS" : "FAIL"} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
