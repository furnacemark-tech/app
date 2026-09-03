import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const SendCoaDialog = ({
  open,
  onOpenChange,
  contacts,
  recipients,
  onRecipientsChange,
  manual,
  onManualChange,
  onSend,
}) => {
  const addManual = () => {
    if (!manual.name || !manual.email) {
      toast.error("Recipient name and email are required");
      return;
    }
    onRecipientsChange([...recipients, { ...manual, contact_id: null }]);
    onManualChange({ name: "", email: "" });
  };

  const toggleContact = (contact, checked) =>
    onRecipientsChange(
      checked
        ? [...recipients, { contact_id: contact.id, name: contact.name, email: contact.email }]
        : recipients.filter((r) => r.contact_id !== contact.id)
    );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white" aria-describedby="send-desc">
        <DialogHeader>
          <DialogTitle>Record C of A delivery</DialogTitle>
          <p id="send-desc" className="text-sm text-slate-600">
            Select saved contacts or add a recipient. One record is stored per recipient.
          </p>
        </DialogHeader>
        <div className="space-y-3">
          <div className="max-h-40 overflow-y-auto space-y-1" data-testid="contact-picker">
            {contacts.map((ct) => (
              <label key={ct.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  data-testid={`recipient-checkbox-${ct.email}`}
                  checked={recipients.some((r) => r.contact_id === ct.id)}
                  onChange={(e) => toggleContact(ct, e.target.checked)}
                />
                {ct.name} · <span className="font-mono text-xs">{ct.email}</span>
                <span className="text-xs text-slate-500">({ct.customer})</span>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              placeholder="Name"
              data-testid="manual-recipient-name"
              value={manual.name}
              onChange={(e) => onManualChange({ ...manual, name: e.target.value })}
            />
            <Input
              placeholder="Email"
              data-testid="manual-recipient-email"
              value={manual.email}
              onChange={(e) => onManualChange({ ...manual, email: e.target.value })}
            />
            <Button variant="outline" data-testid="add-manual-recipient-btn" onClick={addManual}>
              Add
            </Button>
          </div>
          <div className="text-xs text-slate-600" data-testid="selected-recipients">
            {recipients.length} recipient(s): {recipients.map((r) => r.email).join(", ")}
          </div>
          <Button onClick={onSend} data-testid="confirm-send-coa-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
            Record as sent
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export const ReissueCoaDialog = ({ open, onOpenChange, reason, onReasonChange, onConfirm }) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="bg-white" aria-describedby="reissue-desc">
      <DialogHeader>
        <DialogTitle>Authorise replacement C of A</DialogTitle>
        <p id="reissue-desc" className="text-sm text-slate-600">
          The current certificate becomes Superseded and the new revision becomes active.
        </p>
      </DialogHeader>
      <Textarea
        placeholder="Reason for reissue"
        data-testid="reissue-reason-input"
        value={reason}
        onChange={(e) => onReasonChange(e.target.value)}
      />
      <Button data-testid="confirm-reissue-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white" onClick={onConfirm}>
        Authorise
      </Button>
    </DialogContent>
  </Dialog>
);
