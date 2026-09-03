import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const LoginForm = ({ email, password, error, busy, onEmailChange, onPasswordChange, onSubmit }) => (
  <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
    <div>
      <Label className="label-caps">Email</Label>
      <Input
        type="email"
        required
        value={email}
        data-testid="login-email-input"
        onChange={(e) => onEmailChange(e.target.value)}
        className="mt-1.5"
        placeholder="you@lims.local"
      />
    </div>
    <div>
      <Label className="label-caps">Password</Label>
      <Input
        type="password"
        required
        value={password}
        data-testid="login-password-input"
        onChange={(e) => onPasswordChange(e.target.value)}
        className="mt-1.5"
        placeholder="••••••••"
      />
    </div>
    {error && (
      <div data-testid="login-error" className="text-sm text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded">
        {error}
      </div>
    )}
    <Button
      type="submit"
      disabled={busy}
      data-testid="login-submit-button"
      className="w-full bg-[#002FA7] hover:bg-[#00248a] text-white transition-colors duration-200"
    >
      {busy ? "Signing in..." : "Sign in"}
    </Button>
  </form>
);

export const DemoAccounts = () => null;
