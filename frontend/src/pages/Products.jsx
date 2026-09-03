import { useEffect, useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export default function Products() {
  const { can } = useAuth();
  const [products, setProducts] = useState([]);
  const [versions, setVersions] = useState([]);
  const [active, setActive] = useState(null);
  const [amend, setAmend] = useState({ shelf_life_days: "", shelf_life_required: true, reason: "" });

  const load = () => api.get("/products").then(({ data }) => setProducts(data));
  useEffect(() => {
    load();
  }, []);

  const openHistory = async (p) => {
    const { data } = await api.get(`/products/${p.id}/versions`);
    setVersions(data);
    setActive(p);
    setAmend({
      shelf_life_days: String(p.active_version?.shelf_life_days ?? ""),
      shelf_life_required: !!p.active_version?.shelf_life_required,
      reason: "",
    });
  };

  const submitAmend = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/products/${active.id}/amend`, {
        shelf_life_days: parseInt(amend.shelf_life_days, 10),
        shelf_life_required: amend.shelf_life_required,
        reason: amend.reason,
      });
      toast.success("Specification amended — effective immediately for new batches");
      setActive(null);
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  return (
    <div className="space-y-5" data-testid="products-page">
      <div>
        <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Product Specifications</h1>
        <p className="text-sm text-slate-600 mt-1">
          Fixed shelf-life periods per product. {can("admin", "qa") ? "Amendments are effective immediately and fully logged." : "Read-only for QC."}
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>Batch type</TableHead>
              <TableHead>Shelf life required</TableHead>
              <TableHead>Shelf life (days)</TableHead>
              <TableHead>Sales mode</TableHead>
              <TableHead>Active version</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody data-testid="products-table-body">
            {products.map((p) => (
              <TableRow key={p.id} data-testid={`product-row-${p.code || p.name}`}>
                <TableCell className="font-medium">{p.name}</TableCell>
                <TableCell className="text-xs">{p.batch_type}</TableCell>
                <TableCell className="text-xs">{p.active_version?.shelf_life_required ? "Yes" : "No"}</TableCell>
                <TableCell className="tabnum">{p.active_version?.shelf_life_required ? p.active_version?.shelf_life_days : "–"}</TableCell>
                <TableCell className="text-xs">{p.active_version?.sales_mode}</TableCell>
                <TableCell className="tabnum text-xs">v{p.active_version?.version}</TableCell>
                <TableCell>
                  <Button size="sm" variant="outline" data-testid={`product-history-btn-${p.code || p.name}`} onClick={() => openHistory(p)}>
                    {can("admin", "qa") ? "Amend / history" : "History"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <Dialog open={!!active} onOpenChange={(o) => !o && setActive(null)}>
        <DialogContent className="bg-white max-w-2xl" aria-describedby="spec-desc">
          <DialogHeader>
            <DialogTitle>{active?.name}</DialogTitle>
            <p id="spec-desc" className="text-sm text-slate-600">
              Specification version history. Existing batches keep the version applied at creation.
            </p>
          </DialogHeader>
          {can("admin", "qa") && (
            <form onSubmit={submitAmend} className="space-y-3 border-b border-slate-200 pb-4" data-testid="amend-spec-form">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="label-caps">Shelf life (days)</Label>
                  <Input
                    type="number"
                    data-testid="amend-shelf-life-input"
                    value={amend.shelf_life_days}
                    onChange={(e) => setAmend({ ...amend, shelf_life_days: e.target.value })}
                  />
                </div>
                <div>
                  <Label className="label-caps">Shelf life required</Label>
                  <select
                    data-testid="amend-shelf-required-select"
                    className="w-full h-9 border border-slate-300 rounded px-2 text-sm bg-white"
                    value={amend.shelf_life_required ? "yes" : "no"}
                    onChange={(e) => setAmend({ ...amend, shelf_life_required: e.target.value === "yes" })}
                  >
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
              </div>
              <div>
                <Label className="label-caps">Reason for amendment</Label>
                <Textarea
                  data-testid="amend-reason-input"
                  required
                  value={amend.reason}
                  onChange={(e) => setAmend({ ...amend, reason: e.target.value })}
                />
              </div>
              <Button type="submit" data-testid="submit-amend-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
                Amend specification
              </Button>
            </form>
          )}
          <div className="max-h-64 overflow-y-auto space-y-2" data-testid="spec-version-list">
            {versions.map((v) => (
              <div key={v.id} className="text-xs border border-slate-200 rounded p-2">
                <div className="font-mono font-semibold">
                  v{v.version} · effective {v.effective_from}
                </div>
                <div className="text-slate-600">
                  Shelf life {v.shelf_life_required ? `${v.shelf_life_days} days` : "not required"} · {v.created_by} ·{" "}
                  {new Date(v.created_at).toLocaleString()}
                </div>
                {v.original_values && (
                  <div className="text-slate-500">
                    Original shelf life: {String(v.original_values.shelf_life_days)} → new: {String(v.new_values?.shelf_life_days)}
                  </div>
                )}
                <div className="italic text-slate-600">“{v.reason}”</div>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
