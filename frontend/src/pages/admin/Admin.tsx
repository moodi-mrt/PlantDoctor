import { useState } from "react";
import { Route, Routes } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../lib/api";
import { ago, pct } from "../../lib/format";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Input, Loading, PageHeader, Select } from "../../components/ui/ui";

const j = <T,>(p: string) => () => api<T>(p);

function Overview() {
  const q = useQuery({ queryKey: ["admin", "overview"], queryFn: j<any>("/admin/overview") });
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const o = q.data;
  const tiles: [string, any, string?][] = [
    ["Users", o.users.total, `${o.users.verified} verified · ${o.users.new_7d} new this week`],
    ["Diagnoses", o.diagnoses.total, `${o.diagnoses.last_24h} in 24 h · ${o.diagnoses.last_7d} in 7 days`],
    ["Low-confidence rate", pct(o.diagnoses.low_confidence_rate), "not 'confident'"],
    ["Avg. inference", `${o.diagnoses.avg_latency_ms} ms`, `${o.inference.device ?? "—"} · ${o.inference.version ?? "no model"}`],
  ];
  return (
    <div className="space-y-5">
      <PageHeader title="Admin overview" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{tiles.map(([k, v, s]) => (
        <Card key={k} className="p-5"><p className="text-sm text-ink-3">{k}</p><p className="mt-2 text-3xl font-semibold tabular-nums">{v}</p><p className="mt-1 text-xs text-ink-4">{s}</p></Card>))}</div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2"><CardHeader title="Diagnoses per day" />
          <div className="h-60 p-3"><ResponsiveContainer><BarChart data={o.diagnoses.per_day} margin={{ left: -20 }}>
            <CartesianGrid vertical={false} stroke="#E4E6E0" /><XAxis dataKey="day" fontSize={11} tickFormatter={(d) => d.slice(5)} tickLine={false} axisLine={false} />
            <YAxis allowDecimals={false} fontSize={11} tickLine={false} axisLine={false} /><Tooltip /><Bar dataKey="count" fill="#14532D" radius={[4, 4, 0, 0]} />
          </BarChart></ResponsiveContainer></div></Card>
        <Card><CardHeader title="Result status" />
          <ul className="space-y-2 p-5 text-sm">{Object.entries(o.diagnoses.by_status).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span className="tabular-nums">{v as number}</span></li>)}</ul>
          <CardHeader title="User feedback" />
          <ul className="space-y-2 p-5 text-sm">{Object.entries(o.diagnoses.user_feedback).map(([k, v]) => <li key={k} className="flex justify-between"><span>{k}</span><span>{v as number}</span></li>)}</ul>
        </Card>
      </div>
    </div>
  );
}

function Users() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["admin", "users", q], queryFn: j<any>(`/admin/users?q=${encodeURIComponent(q)}`) });
  const patch = useMutation({ mutationFn: ({ id, body }: any) => api(`/admin/users/${id}`, { method: "PATCH", body }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "users"] }) });
  return (
    <div>
      <PageHeader title="Users" />
      <Card className="mb-4 p-4"><Input label="Search" placeholder="Name or email" value={q} onChange={(e) => setQ(e.target.value)} /></Card>
      {patch.error && <p className="mb-3 text-sm text-bad-700">{(patch.error as Error).message}</p>}
      <Card className="overflow-x-auto">
        <table className="w-full text-sm"><thead className="text-left text-xs text-ink-3"><tr className="border-b border-line">{["User", "Role", "Diagnoses", "Last login", "Status"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
          <tbody>{list.data?.items.map((u: any) => (
            <tr key={u.id} className="border-b border-line last:border-0">
              <td className="px-4 py-3"><p className="font-medium">{u.name}</p><p className="text-xs text-ink-3">{u.email}{u.email_verified ? "" : " · unverified"}</p></td>
              <td className="px-4 py-3"><select aria-label={`Role of ${u.email}`} value={u.role} onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })} className="rounded-lg border border-line-strong px-2 py-1">{["farmer", "consultant", "admin"].map((r) => <option key={r}>{r}</option>)}</select></td>
              <td className="px-4 py-3 tabular-nums">{u.diagnoses}</td>
              <td className="px-4 py-3 text-ink-3">{u.last_login_at ? ago(u.last_login_at) : "—"}</td>
              <td className="px-4 py-3"><Button size="sm" variant={u.is_active ? "secondary" : "primary"} onClick={() => patch.mutate({ id: u.id, body: { is_active: !u.is_active } })}>{u.is_active ? "Deactivate" : "Activate"}</Button></td>
            </tr>))}</tbody></table>
      </Card>
    </div>
  );
}

function Models() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "models"], queryFn: j<any>("/admin/models") });
  const act = useMutation({ mutationFn: (id: number) => api(`/admin/models/${id}/activate`, { method: "POST" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin"] }) });
  if (q.isLoading) return <Loading />;
  return (
    <div>
      <PageHeader title="Model versions" sub="Every prediction stores the model version that produced it." />
      <div className="space-y-4">{q.data?.items.map((m: any) => (
        <Card key={m.id} className="p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div><p className="font-semibold">{m.version} <span className="font-normal text-ink-3">· {m.task} · {m.arch} · {m.n_classes} classes</span></p><p className="text-xs text-ink-4">sha256 {m.sha256}… · registered {ago(m.created_at)}</p></div>
            {m.is_active ? <Badge tone="ok">Active</Badge> : <Button size="sm" variant="secondary" disabled={!m.artifact_exists} loading={act.isPending} onClick={() => act.mutate(m.id)}>Activate</Button>}
          </div>
          {Object.keys(m.metrics ?? {}).length > 0 && <dl className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">{Object.entries(m.metrics).filter(([, v]) => typeof v === "number").map(([k, v]) => <div key={k}><dt className="text-xs text-ink-3">{k}</dt><dd className="tabular-nums">{(v as number) <= 1 ? pct(v as number, 1) : String(v)}</dd></div>)}</dl>}
        </Card>))}</div>
      {q.data?.v2_reports && <Card className="mt-5 p-5"><h3 className="font-semibold">v2 evaluation reports</h3><pre className="mt-2 overflow-x-auto text-xs text-ink-2">{JSON.stringify(q.data.v2_reports, null, 1)}</pre></Card>}
    </div>
  );
}

function Review() {
  const qc = useQueryClient();
  const [kind, setKind] = useState("low_confidence");
  const q = useQuery({ queryKey: ["admin", "review", kind], queryFn: j<any>(`/admin/predictions/review?kind=${kind}`) });
  const set = useMutation({ mutationFn: ({ id, review }: any) => api(`/admin/predictions/${id}/review`, { method: "PATCH", body: { review } }), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "review"] }) });
  return (
    <div>
      <PageHeader title="Review queue" sub="Uncertain and user-reported predictions. Photos appear only when the user opted in to sharing." />
      <Card className="mb-4 max-w-xs p-4"><Select label="Show" value={kind} onChange={(e) => setKind(e.target.value)}><option value="low_confidence">Low confidence / failed</option><option value="feedback_incorrect">Reported incorrect by user</option><option value="all">All</option></Select></Card>
      {q.isLoading ? <Loading /> : !q.data?.items.length ? <Card><EmptyState icon="check" title="Nothing to review" /></Card> :
        <div className="space-y-3">{q.data.items.map((d: any) => (
          <Card key={d.id} className="flex flex-col gap-4 p-4 sm:flex-row">
            {d.image_url ? <img src={d.image_url} alt="" className="h-24 w-24 rounded-xl object-cover" /> : <div className="grid h-24 w-24 place-items-center rounded-xl bg-paper-3 text-center text-2xs text-ink-4">photo not shared</div>}
            <div className="flex-1 text-sm">
              <p className="font-medium">#{d.id} · {d.name ?? d.status} {d.crop && <span className="text-ink-3">· {d.crop}</span>}</p>
              <p className="text-ink-3">status {d.status} · conf {pct(d.confidence)} · plant conf {pct(d.plant_confidence)} · crop by {d.crop_source} · {d.model_version}</p>
              {d.alternatives?.length > 0 && <p className="text-xs text-ink-4">alt: {d.alternatives.map((a: any) => `${a.label} ${pct(a.prob)}`).join(", ")}</p>}
              {d.feedback && <Badge tone="warn" className="mt-1">user: {d.feedback}</Badge>}
            </div>
            <div className="flex flex-wrap items-start gap-1.5">{["confirmed", "mislabeled", "ood", "bad_photo"].map((r) => <Button key={r} size="sm" variant={d.review === r ? "primary" : "secondary"} onClick={() => set.mutate({ id: d.id, review: r })}>{r.replace("_", " ")}</Button>)}</div>
          </Card>))}</div>}
    </div>
  );
}

function Datasets() {
  const q = useQuery({ queryKey: ["admin", "datasets"], queryFn: j<any>("/admin/datasets") });
  if (q.isLoading) return <Loading />;
  return (
    <div>
      <PageHeader title="Datasets" sub="Sources, licences and image counts used for training." />
      <Card className="overflow-x-auto"><table className="w-full text-sm"><thead className="text-left text-xs text-ink-3"><tr className="border-b border-line">{["Dataset", "Licence", "Images kept", "Duplicates removed"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr></thead>
        <tbody>{q.data?.items.map((d: any) => <tr key={d.key} className="border-b border-line last:border-0"><td className="px-4 py-3"><p className="font-medium">{d.name}</p><a href={d.mirror ?? d.origin} className="text-xs text-forest-700 hover:underline" target="_blank" rel="noopener noreferrer">{d.key}</a></td>
          <td className="px-4 py-3 text-ink-2">{d.license ?? "not stated — check origin"}</td>
          <td className="px-4 py-3 tabular-nums">{d.images_kept ? Object.values(d.images_kept as Record<string, number>).reduce((a, b) => a + b, 0) : d.images ? Object.values(d.images as Record<string, number>).reduce((a, b) => a + b, 0) : "—"}</td>
          <td className="px-4 py-3 tabular-nums">{d.duplicates_skipped ?? "—"}</td></tr>)}</tbody></table></Card>
    </div>
  );
}

function System() {
  const s = useQuery({ queryKey: ["admin", "system"], queryFn: j<any>("/admin/system") });
  const a = useQuery({ queryKey: ["admin", "audit"], queryFn: j<any>("/admin/audit?limit=50") });
  return (
    <div className="space-y-5">
      <PageHeader title="System & audit" />
      {s.data && <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{[["Database", s.data.database], ["Disk free", `${s.data.disk.free_gb} / ${s.data.disk.total_gb} GB`], ["GPU", s.data.gpu?.name ?? "CPU only"], ["Claude API", s.data.llm_available ? "configured" : "not configured"]].map(([k, v]) => <Card key={k} className="p-4"><p className="text-xs text-ink-3">{k}</p><p className="mt-1 font-medium">{v}</p></Card>)}</div>}
      <Card className="overflow-x-auto"><CardHeader title="Audit log" />
        <table className="mt-3 w-full text-sm"><tbody>{a.data?.items.map((e: any) => <tr key={e.id} className="border-t border-line"><td className="px-4 py-2 text-ink-3">{ago(e.created_at)}</td><td className="px-4 py-2 font-medium">{e.action}</td><td className="px-4 py-2 text-ink-3">actor {e.actor_id ?? "—"} · {e.target}</td><td className="px-4 py-2 text-xs text-ink-4">{e.ip}</td></tr>)}</tbody></table>
      </Card>
    </div>
  );
}

export default function Admin() {
  return (
    <Routes>
      <Route index element={<Overview />} />
      <Route path="users" element={<Users />} />
      <Route path="models" element={<Models />} />
      <Route path="review" element={<Review />} />
      <Route path="datasets" element={<Datasets />} />
      <Route path="system" element={<System />} />
    </Routes>
  );
}
