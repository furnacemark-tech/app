import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export const NewBatchDialog = ({ open, onOpenChange, form, onFormChange, products, customers, exclusive, selected, onSubmit }) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogTrigger asChild>
      <Button data-testid="create-batch-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
        <Plus className="w-4 h-4 mr-1.5" /> New batch
      </Button>
    </DialogTrigger>
    <DialogContent className="bg-white" aria-describedby="new-batch-desc">
      <DialogHeader>
        <DialogTitle>Create batch</DialogTitle>
        <p id="new-batch-desc" className="text-sm text-slate-600">
          The production date sets the applicable specification version and expiry date.
        </p>
      </DialogHeader>
      <form onSubmit={onSubmit} className="space-y-3" data-testid="create-batch-form">
        <div>
          <Label className="label-caps">Product</Label>
          <select
            data-testid="batch-product-select"
            className="mt-1.5 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
            value={form.product_id}
            onChange={(e) => onFormChange({ ...form, product_id: e.target.value })}
          >
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.active_version?.sales_mode === "exclusive" ? "(customer exclusive)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label className="label-caps">Batch number</Label>
          <Input
            data-testid="batch-number-input"
            required
            value={form.batch_number}
            onChange={(e) => onFormChange({ ...form, batch_number: e.target.value })}
          />
        </div>
        <div>
          <Label className="label-caps">Production date</Label>
          <Input
            type="date"
            data-testid="batch-production-date-input"
            required
            value={form.production_date}
            onChange={(e) => onFormChange({ ...form, production_date: e.target.value })}
          />
        </div>
        {exclusive ? (
          <div>
            <Label className="label-caps">Customer (locked after creation)</Label>
            <select
              data-testid="batch-customer-select"
              className="mt-1.5 w-full border border-slate-300 rounded px-3 py-2 text-sm bg-white"
              value={form.customer_id || selected?.active_version?.exclusive_customer_id || ""}
              onChange={(e) => onFormChange({ ...form, customer_id: e.target.value })}
            >
              {customers.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ) : (
          <p className="text-xs text-slate-500">
            Multi-customer product — certificates are generated per customer at release.
          </p>
        )}
        <Button type="submit" data-testid="submit-batch-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
          Create batch
        </Button>
      </form>
    </DialogContent>
  </Dialog>
);
