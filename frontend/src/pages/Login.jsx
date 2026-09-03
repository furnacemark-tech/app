import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { LoginForm, DemoAccounts } from "@/components/auth/LoginForm";

const HERO_IMAGE =
  "https://images.unsplash.com/photo-1781708166347-898b7f09cd1b?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA1Mjh8MHwxfHNlYXJjaHwxfHxhYnN0cmFjdCUyMHNjaWVuY2UlMjBsYWJvcmF0b3J5JTIwYmFja2dyb3VuZCUyMGNsZWFufGVufDB8fHx8MTc4NjQ1MzUzOXww&ixlib=rb-4.1.0&q=85";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    const res = await login(email, password);
    setBusy(false);
    if (res.ok) navigate("/");
    else setError(res.error);
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="flex items-center px-6 sm:px-16 py-16 bg-white">
        <div className="w-full max-w-sm">
          <div className="flex items-center gap-2 mb-10">
            <div className="w-9 h-9 bg-[#002FA7] flex items-center justify-center rounded-sm">
              <FlaskConical className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="font-semibold tracking-tight">SYNTH LIMS</div>
              <div className="label-caps">Controlled Environment</div>
            </div>
          </div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight leading-none mb-2">Sign in</h1>
          <p className="text-sm text-slate-600 mb-8">
            Access is role controlled. All actions are recorded in the audit trail.
          </p>
          <LoginForm
            email={email}
            password={password}
            error={error}
            busy={busy}
            onEmailChange={setEmail}
            onPasswordChange={setPassword}
            onSubmit={submit}
          />
          <DemoAccounts />
        </div>
      </div>
      <div className="hidden lg:block relative bg-[#001A5C]">
        <img src={HERO_IMAGE} alt="Laboratory" className="absolute inset-0 w-full h-full object-cover opacity-80" />
        <div className="absolute bottom-10 left-10 right-10 text-white">
          <div className="text-xs uppercase tracking-[0.2em] mb-3 opacity-80">Sample to sign-off</div>
          <div className="text-2xl font-semibold leading-snug max-w-md">
            Specification-driven result evaluation with QA sign-off and a tamper-evident audit trail.
          </div>
        </div>
      </div>
    </div>
  );
}
