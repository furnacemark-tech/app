import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Download } from "lucide-react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { downloadBlob } from "@/hooks/useBatch";
import { NewBatchDialog } from "@/components/batch/NewBatchDialog";
import { BatchTable } from "@/components/batch/BatchTable";
import { Button } from "@/components/ui/button";

export default function Batches() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const [batches, setBatches] = useState([]);
  const [products, setProducts] = useState([]);
  const [customers, setCustomers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    product_id: "",
    batch_number: "",
    production_date: new Date().toISOString().slice(0, 10),
    customer_id: "",
  });

  const load = useCallback(() => api.get("/batches").then(({ data }) => setBatches(data)), []);

  useEffect(() => {
    load();
    api.get("/products").then(({ data }) => {
      setProducts(data);
      setForm((f) => ({ ...f, product_id: f.product_id || data[0]?.id || "" }));
    });
    api.get("/customers").then(({ data }) => setCustomers(data));
  }, [load]);

  const selected = products.find((p) => p.id === form.product_id);
  const exclusive = selected?.active_version?.sales_mode === "exclusive";

  const create = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.post("/batches", {
        product_id: form.product_id,
        batch_number: form.batch_number,
        production_date: form.production_date,
        customer_id: exclusive ? form.customer_id || selected?.active_version?.exclusive_customer_id : null,
      });
      toast.success(`Batch ${data.batch_number} created`);
      setOpen(false);
      navigate(`/batches/${data.id}`);
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const exportReport = async () => {
    const { data } = await api.get("/reports/batches.csv", { responseType: "blob" });
    downloadBlob(data, `batch-report-${new Date().toISOString().slice(0, 10)}.csv`);
    toast.success("Batch report exported");
  };

  return (
    <div className="space-y-5" data-testid="batches-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Batch Release</h1>
          <p className="text-sm text-slate-600 mt-1">{batches.length} batches · Draft to Released lifecycle</p>
        </div>
        <div className="flex flex-wrap gap-2 items-center">
          <Button variant="outline" data-testid="export-batches-btn" onClick={exportReport}>
            <Download className="w-4 h-4 mr-1.5" /> Export report
          </Button>
          {can("admin", "qc") && (
            <NewBatchDialog
              open={open}
              onOpenChange={setOpen}
              form={form}
              onFormChange={setForm}
              products={products}
              customers={customers}
              exclusive={exclusive}
              selected={selected}
              onSubmit={create}
            />
          )}
        </div>
      </div>

      <BatchTable batches={batches} onSelect={(b) => navigate(`/batches/${b.id}`)} />
    </div>
  );
}
