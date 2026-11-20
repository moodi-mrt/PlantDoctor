import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, ApiError } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ButtonLink, Loading, Notice } from "../../components/ui/ui";
import AuthShell from "./AuthShell";

export default function Verify() {
  const [sp] = useSearchParams();
  const { refresh, user } = useAuth();
  const [state, setState] = useState<"busy" | "ok" | "err">("busy");
  const [msg, setMsg] = useState("");
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return; done.current = true;
    const t = sp.get("token");
    if (!t) { setState("err"); setMsg("This link is missing its token."); return; }
    api("/auth/verify", { body: { token: t } }).then(() => { setState("ok"); refresh(); })
      .catch((e: ApiError) => { setState("err"); setMsg(e.message); });
  }, [sp, refresh]);
  return (
    <AuthShell title="Confirm your email">
      {state === "busy" && <Loading label="Confirming…" />}
      {state === "ok" && <div className="space-y-4"><Notice tone="ok" title="Email confirmed">Thank you — your account is fully set up.</Notice><ButtonLink to={user ? "/app" : "/login"}>Continue</ButtonLink></div>}
      {state === "err" && <div className="space-y-4"><Notice tone="bad">{msg}</Notice>{user && <p className="text-sm text-ink-3">You can request a new link from Settings.</p>}</div>}
    </AuthShell>
  );
}
