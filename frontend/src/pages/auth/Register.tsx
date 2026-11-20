import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Button, Input, Notice } from "../../components/ui/ui";
import AuthShell from "./AuthShell";

export default function Register() {
  const nav = useNavigate();
  const { refresh } = useAuth();
  const [f, setF] = useState({ name: "", email: "", password: "" });
  const [err, setErr] = useState<ApiError | null>(null); const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await api("/auth/register", { body: f }); await refresh(); nav("/app?welcome=1", { replace: true }); }
    catch (x) { setErr(x as ApiError); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Create your account" sub="Free. Keep your diagnoses, download reports and ask the assistant."
      footer={<>Already have an account? <Link to="/login" className="font-medium text-forest-700 hover:underline">Sign in</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {err && !err.details && <Notice tone="bad">{err.message}</Notice>}
        <Input label="Your name" autoComplete="name" required value={f.name} onChange={set("name")} error={err?.fieldError("name")} />
        <Input label="Email" type="email" autoComplete="email" required value={f.email} onChange={set("email")} error={err?.fieldError("email")} />
        <Input label="Password" type="password" autoComplete="new-password" required minLength={10} value={f.password} onChange={set("password")}
          hint="At least 10 characters. A short phrase is easy to remember." error={err?.fieldError("password") ?? (err?.code === "weak_password" ? err.message : undefined)} />
        <Button type="submit" full size="lg" loading={busy}>Create account</Button>
        <p className="text-xs text-ink-3">We'll send a link to confirm your email. Your photos stay private and you can delete them at any time.</p>
      </form>
    </AuthShell>
  );
}
