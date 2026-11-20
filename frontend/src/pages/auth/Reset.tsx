import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { Button, ButtonLink, Input, Notice } from "../../components/ui/ui";
import AuthShell from "./AuthShell";

export default function Reset() {
  const [sp] = useSearchParams();
  const [pw, setPw] = useState(""); const [pw2, setPw2] = useState(""); const [done, setDone] = useState(false);
  const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(null);
    if (pw !== pw2) return setErr("The two passwords don't match.");
    setBusy(true);
    try { await api("/auth/reset", { body: { token: sp.get("token") ?? "", password: pw } }); setDone(true); }
    catch (x) { setErr((x as ApiError).message); } finally { setBusy(false); }
  };
  return (
    <AuthShell title="Choose a new password">
      {done ? <div className="space-y-4"><Notice tone="ok" title="Password changed">For your security you've been signed out everywhere. Sign in with your new password.</Notice><ButtonLink to="/login">Sign in</ButtonLink></div> :
        <form onSubmit={submit} className="space-y-4" noValidate>
          {err && <Notice tone="bad">{err}</Notice>}
          <Input label="New password" type="password" autoComplete="new-password" value={pw} onChange={(e) => setPw(e.target.value)} hint="At least 10 characters." />
          <Input label="Repeat new password" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} />
          <Button type="submit" full size="lg" loading={busy}>Save password</Button>
        </form>}
    </AuthShell>
  );
}
