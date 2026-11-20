import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { Button, Input, Notice } from "../../components/ui/ui";
import AuthShell from "./AuthShell";

export default function Forgot() {
  const [email, setEmail] = useState(""); const [sent, setSent] = useState(false);
  const [err, setErr] = useState<ApiError | null>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await api("/auth/forgot", { body: { email } }); setSent(true); } catch (x) { setErr(x as ApiError); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Reset your password" sub="We'll email you a link to choose a new password." footer={<Link to="/login" className="text-forest-700 hover:underline">Back to sign in</Link>}>
      {sent ? <Notice tone="ok" title="Check your inbox">If an account exists for {email}, a reset link is on its way. It's valid for 1 hour.</Notice> :
        <form onSubmit={submit} className="space-y-4" noValidate>
          {err && <Notice tone="bad">{err.message}</Notice>}
          <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} error={err?.fieldError("email")} />
          <Button type="submit" full size="lg" loading={busy}>Send reset link</Button>
        </form>}
    </AuthShell>
  );
}
