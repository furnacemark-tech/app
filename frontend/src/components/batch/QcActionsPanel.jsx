import { Send, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

const SUBMITTABLE = ["DRAFT", "RETURNED"];
const RELEASABLE = ["DRAFT", "RETURNED", "APPROVED"];

export const QcActionsPanel = ({ batch, customers, releaseCustomers, onToggleCustomer, onSubmit, onRelease }) => (
  <div className="bg-white border border-slate-200 rounded-md p-5 space-y-3" data-testid="qc-actions">
    <div className="label-caps">QC actions</div>

    {batch.sales_mode === "multi" && !batch.customer_id && (
      <div>
        <Label className="label-caps">Customers for C of A at release</Label>
        <div className="mt-1.5 space-y-1">
          {customers.map((c) => (
            <label key={c.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                data-testid={`release-customer-${c.name}`}
                checked={releaseCustomers.includes(c.id)}
                onChange={(e) => onToggleCustomer(c.id, e.target.checked)}
              />
              {c.name}
            </label>
          ))}
        </div>
      </div>
    )}

    <div className="flex flex-wrap gap-2">
      {SUBMITTABLE.includes(batch.status) && (
        <Button variant="outline" data-testid="submit-batch-to-qa-btn" onClick={onSubmit}>
          <Send className="w-4 h-4 mr-1.5" /> Submit to QA
        </Button>
      )}
      {RELEASABLE.includes(batch.status) && (
        <Button onClick={onRelease} data-testid="qc-release-btn" className="bg-emerald-600 hover:bg-emerald-700 text-white">
          <FileText className="w-4 h-4 mr-1.5" /> Generate C of A &amp; release
        </Button>
      )}
    </div>

    <p className="text-xs text-slate-500">
      Release requires every result within specification and an instrument inside calibration and service dates.
    </p>
  </div>
);
