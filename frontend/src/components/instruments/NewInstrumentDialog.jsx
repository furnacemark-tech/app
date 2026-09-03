import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

export const NewInstrumentDialog = ({ open, onOpenChange, form, onFormChange, onSubmit }) => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogTrigger asChild>
      <Button data-testid="add-instrument-btn" className="bg-[#002FA7] hover:bg-[#00248a] text-white">
        Add instrument
      </Button>
    </DialogTrigger>
    <DialogContent className="bg-white" aria-describedby="inst-desc">
      <DialogHeader>
        <DialogTitle>Register instrument</DialogTitle>
        <p id="inst-desc" className="text-sm text-slate-600">
          Overdue instruments block batch release.
        </p>
      </DialogHeader>
      <form onSubmit={onSubmit} className="space-y-3" data-testid="create-instrument-form">
        <div>
          <Label className="label-caps">Name</Label>
          <Input data-testid="instrument-name-input" required value={form.name} onChange={(e) => onFormChange({ ...form, name: e.target.value })} />
        </div>
        <div>
          <Label className="label-caps">Code</Label>
          <Input
            data-testid="instrument-code-input"
            value={form.instrument_code}
            onChange={(e) => onFormChange({ ...form, instrument_code: e.target.value })}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label className="label-caps">Calibration due</Label>
            <Input
              type="date"
              data-testid="instrument-calibration-input"
              required
              value={form.calibration_due}
              onChange={(e) => onFormChange({ ...form, calibration_due: e.target.value })}
            />
          </div>
          <div>
            <Label className="label-caps">Service due</Label>
            <Input
              type="date"
              data-testid="instrument-service-input"
              required
              value={form.service_due}
              onChange={(e) => onFormChange({ ...form, service_due: e.target.value })}
            />
          </div>
        </div>
        <Button type="submit" data-testid="submit-instrument-btn" className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white">
          Register
        </Button>
      </form>
    </DialogContent>
  </Dialog>
);
