import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export const NewCustomerDialog = ({ open, onOpenChange, form, onFormChange, onSubmit }) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogTrigger asChild>
      <Button data-testid="add-customer-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
        Add customer
      </Button>
    </DialogTrigger>
    <DialogContent className="bg-white" aria-describedby="cust-desc">
      <DialogHeader>
        <DialogTitle>New customer</DialogTitle>
        <p id="cust-desc" className="text-sm text-slate-600">
          Used for C of A delivery records.
        </p>
      </DialogHeader>
      <form onSubmit={onSubmit} className="space-y-3" data-testid="create-customer-form">
        <div>
          <Label className="label-caps">Name</Label>
          <Input
            data-testid="customer-name-input"
            required
            value={form.name}
            onChange={(e) => onFormChange({ ...form, name: e.target.value })}
          />
        </div>
        <div>
          <Label className="label-caps">Account code</Label>
          <Input
            data-testid="customer-code-input"
            value={form.account_code}
            onChange={(e) => onFormChange({ ...form, account_code: e.target.value })}
          />
        </div>
        <Button type="submit" data-testid="submit-customer-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
          Create
        </Button>
      </form>
    </DialogContent>
  </Dialog>
);

export const NewContactDialog = ({ customer, onOpenChange, contact, onContactChange, onSubmit }) => (
  <Dialog open={!!customer} onOpenChange={onOpenChange}>
    <DialogContent className="bg-white" aria-describedby="contact-desc">
      <DialogHeader>
        <DialogTitle>Add contact · {customer?.name}</DialogTitle>
        <p id="contact-desc" className="text-sm text-slate-600">
          Saved contacts can be selected by QA when sending a C of A.
        </p>
      </DialogHeader>
      <form onSubmit={onSubmit} className="space-y-3" data-testid="create-contact-form">
        <div>
          <Label className="label-caps">Contact name</Label>
          <Input
            data-testid="contact-name-input"
            required
            value={contact.name}
            onChange={(e) => onContactChange({ ...contact, name: e.target.value })}
          />
        </div>
        <div>
          <Label className="label-caps">Email</Label>
          <Input
            type="email"
            data-testid="contact-email-input"
            required
            value={contact.email}
            onChange={(e) => onContactChange({ ...contact, email: e.target.value })}
          />
        </div>
        <Button type="submit" data-testid="submit-contact-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
          Save contact
        </Button>
      </form>
    </DialogContent>
  </Dialog>
);
