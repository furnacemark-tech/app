import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { CustomerCard } from "@/components/customers/CustomerCard";
import { NewCustomerDialog, NewContactDialog } from "@/components/customers/CustomerDialogs";

const EMPTY_CUSTOMER = { name: "", account_code: "" };
const EMPTY_CONTACT = { name: "", email: "" };

export default function Customers() {
  const { can } = useAuth();
  const admin = can("admin");
  const [customers, setCustomers] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_CUSTOMER);
  const [contactFor, setContactFor] = useState(null);
  const [contact, setContact] = useState(EMPTY_CONTACT);

  const load = useCallback(() => api.get("/customers").then(({ data }) => setCustomers(data)), []);

  useEffect(() => {
    load();
  }, [load]);

  const run = async (request, okMsg, onDone) => {
    try {
      await request();
      toast.success(okMsg);
      if (onDone) onDone();
      load();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    }
  };

  const createCustomer = (e) => {
    e.preventDefault();
    run(() => api.post("/customers", { ...form, active: true }), "Customer created", () => {
      setOpen(false);
      setForm(EMPTY_CUSTOMER);
    });
  };

  const addContact = (e) => {
    e.preventDefault();
    run(
      () => api.post(`/customers/${contactFor.id}/contacts`, { ...contact, active: true }),
      "Contact added",
      () => {
        setContactFor(null);
        setContact(EMPTY_CONTACT);
      }
    );
  };

  const toggle = (c) =>
    run(
      () => api.patch(`/customers/${c.id}`, { name: c.name, account_code: c.account_code, active: !c.active }),
      c.active ? "Customer deactivated" : "Customer activated"
    );

  return (
    <div className="space-y-5" data-testid="customers-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none">Customers</h1>
          <p className="text-sm text-slate-600 mt-1">
            {admin ? "Admin maintained. All changes are logged." : "View only — Admin maintains customer records."}
          </p>
        </div>
        {admin && (
          <NewCustomerDialog
            open={open}
            onOpenChange={setOpen}
            form={form}
            onFormChange={setForm}
            onSubmit={createCustomer}
          />
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4" data-testid="customers-list">
        {customers.map((c) => (
          <CustomerCard key={c.id} customer={c} admin={admin} onAddContact={setContactFor} onToggle={toggle} />
        ))}
      </div>

      <NewContactDialog
        customer={contactFor}
        onOpenChange={(o) => !o && setContactFor(null)}
        contact={contact}
        onContactChange={setContact}
        onSubmit={addContact}
      />
    </div>
  );
}
