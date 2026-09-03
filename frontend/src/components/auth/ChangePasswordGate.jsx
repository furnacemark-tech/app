import { useState } from "react";
import { toast } from "sonner";
import api, { apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

export const ChangePasswordGate = () => {
  const { user, logout } = useAuth();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  if (!user || !user.must_change_password) return null;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Password updated. Please sign in with your new password.");
      await logout();
    } catch (err) {
      toast.error(apiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open>
      <DialogContent className="bg-white" aria-describedby="change-pw-desc">
        <DialogHeader>
          <DialogTitle>Set a new password</DialogTitle>
          <p id="change-pw-desc" className="text-sm text-slate-600">
            Your account uses a temporary password. Choose a new one before continuing.
          </p>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3" data-testid="change-password-form">
          <div>
            <Label className="label-caps">Temporary password</Label>
            <Input
              type="password"
              required
              data-testid="current-password-input"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div>
            <Label className="label-caps">New password (min 8 characters)</Label>
            <Input
              type="password"
              required
              data-testid="new-password-input"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </div>
          <Button
            type="submit"
            disabled={busy}
            data-testid="submit-change-password-btn"
            className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white"
          >
            {busy ? "Updating…" : "Update password"}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
};
