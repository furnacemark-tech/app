import { Button } from "@/components/ui/button";

export const CustomerCard = ({ customer, admin, onAddContact, onToggle }) => (
  <div className="bg-white border border-slate-200 rounded-md p-4" data-testid={`customer-card-${customer.name}`}>
    <div className="flex items-start justify-between gap-2">
      <div>
        <div className="font-semibold">{customer.name}</div>
        <div className="label-caps">
          {customer.account_code} · {customer.active ? "Active" : "Inactive"}
        </div>
      </div>
      {admin && (
        <div className="flex gap-2">
          <Button size="sm" variant="outline" data-testid={`add-contact-btn-${customer.name}`} onClick={() => onAddContact(customer)}>
            Add contact
          </Button>
          <Button size="sm" variant="outline" data-testid={`toggle-customer-${customer.name}`} onClick={() => onToggle(customer)}>
            {customer.active ? "Deactivate" : "Activate"}
          </Button>
        </div>
      )}
    </div>
    <div className="mt-3 space-y-1">
      {(customer.contacts || []).map((ct) => (
        <div key={ct.id} className="text-xs flex justify-between border-b border-slate-100 pb-1">
          <span>{ct.name}</span>
          <span className="font-mono text-slate-500">{ct.email}</span>
        </div>
      ))}
      {(customer.contacts || []).length === 0 && <div className="text-xs text-slate-500">No saved contacts.</div>}
    </div>
  </div>
);
