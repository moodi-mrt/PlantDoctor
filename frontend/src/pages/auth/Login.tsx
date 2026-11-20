import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { Button, Input, Notice } from "../../components/ui/ui";
import AuthShell from "./AuthShell";

export default function Login() {
  const [sp] = useSearchParams();
  const nav = useNavigate();
  const { refresh } = useAuth();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [err, setErr] = useState<ApiError | null>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await api("/auth/login", { body: { email, password } }); await refresh(); nav(sp.get("next")?.startsWith("/") ? sp.get("next")! : "/app", { replace: true }); }
    catch (x) { setErr(x as ApiError); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Sign in" sub="Welcome back to PlantDoctor." footer={<>New here? <Link to="/register" className="font-medium text-forest-700 hover:underline">Create a free account</Link></>}>
      <form onSubmit={submit} className="space-y-4" noValidate>
        {err && <Notice tone="bad">{err.message}</Notice>}
        <Input label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} error={err?.fieldError("email")} />
        <Input label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
        <div className="flex justify-end"><Link to="/forgot" className="text-sm text-forest-700 hover:underline">Forgot password?</Link></div>
        <Button type="submit" full size="lg" loading={busy}>Sign in</Button>
      </form>
    </AuthShell>
  );
}
