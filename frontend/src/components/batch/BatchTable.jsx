import { StatusBadge } from "@/components/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

const customerLabel = (batch) => {
  if (batch.customer_name) return batch.customer_name;
  return batch.sales_mode === "multi" ? "Multi-customer" : "–";
};

export const BatchTable = ({ batches, onSelect }) => (
  <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
    <Table className="data-table">
      <TableHeader>
        <TableRow>
          <TableHead>Batch</TableHead>
          <TableHead>Product</TableHead>
          <TableHead>Production</TableHead>
          <TableHead>Expiry</TableHead>
          <TableHead>Customer</TableHead>
          <TableHead>Spec</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody data-testid="batches-table-body">
        {batches.map((b) => (
          <TableRow
            key={b.id}
            data-testid={`batch-row-${b.batch_number}`}
            className="cursor-pointer hover:bg-slate-50 transition-colors duration-200"
            onClick={() => onSelect(b)}
          >
            <TableCell className="font-mono text-xs">{b.batch_number}</TableCell>
            <TableCell>{b.product_name}</TableCell>
            <TableCell className="tabnum">{b.production_date}</TableCell>
            <TableCell className="tabnum">{b.shelf_life_required ? b.expiry_date : "n/a"}</TableCell>
            <TableCell>{customerLabel(b)}</TableCell>
            <TableCell className="tabnum text-xs">v{b.spec_version}</TableCell>
            <TableCell>
              <StatusBadge value={b.status} />
            </TableCell>
          </TableRow>
        ))}
        {batches.length === 0 && (
          <TableRow>
            <TableCell colSpan={7} className="text-sm text-slate-500">
              No batches yet.
            </TableCell>
          </TableRow>
        )}
      </TableBody>
    </Table>
  </div>
);
