import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago, pct } from "../../lib/format";
import type { DiagnosisSummary, Page, Weather } from "../../lib/types";
import { Badge, Button, ButtonLink, Card, CardHeader, EmptyState, ErrorState, Notice, Skeleton } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";
import { StatusBadge } from "./History";

interface Overview {
  total_diagnoses: number; in_period: number; plants: number; healthy: number; diseased: number; unclear: number;
  top_conditions: { name: string; count: number }[]; crops: { crop: string; total: number; healthy: number; diseased: number; unclear: number }[];
  weekly: { week: string; healthy: number; diseased: number; unclear: number }[]; avg_confidence: number | null;
}
const C = { healthy: "#059669", diseased: "#B45309", unclear: "#98A29B" };

function Stat({ label, value, sub, icon }: { label: string; value: React.ReactNode; sub?: string; icon: any }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between"><p className="text-sm text-ink-3">{label}</p><Icon name={icon} size={18} className="text-forest-600" /></div>
      <p className="mt-2 text-3xl font-semibold tabular-nums tracking-tight">{value}</p>
      {sub && <p className="mt-1 text-xs text-ink-4">{sub}</p>}
    </Card>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [sp] = useSearchParams();
  const ov = useQuery({ queryKey: ["analytics"], queryFn: () => api<Overview>("/analytics/overview") });
  const recent = useQuery({ queryKey: ["predictions", "recent"], queryFn: () => api<Page<DiagnosisSummary>>("/predictions?limit=5") });
  const wx = useQuery({ queryKey: ["weather", user?.location ?? "default"], queryFn: () => api<Weather>(`/weather${user?.location ? `?q=${encodeURIComponent(user.location)}` : ""}`), retry: 0 });
  const resend = useMutation({ mutationFn: () => api("/auth/resend-verification", { method: "POST" }) });
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const o = ov.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm text-ink-3">{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}</p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-[28px]">{greet}, {user?.name.split(" ")[0]}</h1>
        </div>
        <ButtonLink to="/app/diagnose" icon="camera" size="lg">Diagnose a plant</ButtonLink>
      </div>

      {sp.get("welcome") && <Notice tone="ok" title="Welcome to PlantDoctor">Start by diagnosing a plant, or add the plants and fields you want to track under “My plants”.</Notice>}
      {user && !user.email_verified && (
        <Notice tone="info" title="Please confirm your email">
          We sent a link to {user.email}. {resend.isSuccess ? "A new link has been sent." :
            <Button variant="link" onClick={() => resend.mutate()} loading={resend.isPending}>Resend link</Button>}
        </Notice>)}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {ov.isLoading ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-28" />) : o && <>
          <Stat label="Total diagnoses" value={o.total_diagnoses} icon="history" sub={`${o.in_period} in the last 6 months`} />
          <Stat label="Healthy results" value={o.healthy} icon="check" sub={o.healthy + o.diseased ? `${pct(o.healthy / (o.healthy + o.diseased))} of clear results` : "—"} />
          <Stat label="Problems found" value={o.diseased} icon="alert" sub={`${o.unclear} unclear photos`} />
          <Stat label="My plants" value={o.plants} icon="sprout" sub={o.avg_confidence ? `avg. confidence ${pct(o.avg_confidence)}` : undefined} />
        </>}
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Crop health over time" sub="Results per week" />
          <div className="h-64 px-2 pb-4 pt-2">
            {ov.isLoading ? <Skeleton className="m-4 h-52" /> : !o?.weekly.length ? <EmptyState icon="chart" title="No data yet">Your weekly results will appear here after your first diagnosis.</EmptyState> :
              <ResponsiveContainer>
                <BarChart data={o.weekly} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
                  <CartesianGrid vertical={false} stroke="#E4E6E0" />
                  <XAxis dataKey="week" tickFormatter={(w) => new Date(w).toLocaleDateString(undefined, { day: "numeric", month: "short" })} fontSize={11} tickLine={false} axisLine={false} />
                  <YAxis allowDecimals={false} fontSize={11} tickLine={false} axisLine={false} />
                  <Tooltip cursor={{ fill: "#F4F3EE" }} contentStyle={{ borderRadius: 12, border: "1px solid #E4E6E0", fontSize: 12 }} />
                  {(["healthy", "diseased", "unclear"] as const).map((k) => <Bar key={k} dataKey={k} stackId="a" fill={C[k]} radius={k === "unclear" ? [4, 4, 0, 0] : 0} name={k[0].toUpperCase() + k.slice(1)} />)}
                </BarChart>
              </ResponsiveContainer>}
          </div>
        </Card>
        <Card>
          <CardHeader title="Most found problems" />
          <div className="p-5 pt-3">
            {ov.isLoading ? <Skeleton className="h-40" /> : !o?.top_conditions.length ? <p className="py-8 text-center text-sm text-ink-3">No diseases found yet.</p> :
              <ul className="space-y-3">{o.top_conditions.map((c) => {
                const max = o.top_conditions[0].count;
                return <li key={c.name} className="text-sm"><div className="flex justify-between gap-2"><span className="truncate">{c.name}</span><span className="tabular-nums text-ink-3">{c.count}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-paper-3"><div className="h-full rounded-full bg-warn-600" style={{ width: `${(c.count / max) * 100}%` }} /></div></li>;
              })}</ul>}
          </div>
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Recent scans" action={<Link to="/app/diagnoses" className="text-sm font-medium text-forest-700 hover:underline">View all</Link>} />
          {recent.isLoading ? <div className="space-y-2 p-5"><Skeleton className="h-14" /><Skeleton className="h-14" /></div> :
            recent.error ? <ErrorState error={recent.error} onRetry={() => recent.refetch()} /> :
            !recent.data?.items.length ? <EmptyState icon="scan" title="No diagnoses yet" action={<ButtonLink to="/app/diagnose" icon="camera">Diagnose your first plant</ButtonLink>}>Take a photo of a leaf with symptoms to get started.</EmptyState> :
            <ul className="divide-y divide-line px-2 pb-2 pt-1">{recent.data.items.map((d) => (
              <li key={d.id}><Link to={`/app/diagnoses/${d.id}`} className="flex items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-paper-2 focus-ring">
                {d.thumbnail_url ? <img src={d.thumbnail_url} alt="" className="h-11 w-11 rounded-lg object-cover" loading="lazy" /> : <span className="h-11 w-11 rounded-lg bg-paper-3" />}
                <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium">{d.name ?? "No diagnosis"}</p><p className="text-xs text-ink-3">{d.crop ?? "Unknown plant"} · {ago(d.created_at)}</p></div>
                <StatusBadge s={d.status} healthy={d.healthy} />
              </Link></li>))}</ul>}
        </Card>
        <Card>
          <CardHeader title="Weather & disease risk" sub={wx.data ? `${wx.data.place.name} · next 3 days` : undefined} action={<Link to="/app/weather" className="text-sm font-medium text-forest-700 hover:underline">Details</Link>} />
          <div className="p-5 pt-3">
            {wx.isLoading ? <Skeleton className="h-32" /> : wx.error ? <p className="text-sm text-ink-3">Weather is unavailable right now.</p> : wx.data && <>
              <div className="flex items-center gap-4">
                <p className="text-4xl font-semibold tabular-nums">{Math.round(Number(wx.data.current?.temperature_2m))}°</p>
                <div className="text-sm text-ink-3"><p>Humidity {wx.data.current?.relative_humidity_2m}%</p><p>Rain today {wx.data.daily.precipitation_sum?.[0]} mm</p></div>
              </div>
              <div className="mt-4 space-y-2">
                {wx.data.risks.length ? wx.data.risks.slice(0, 3).map((r) => (
                  <div key={r.label} className="flex items-center justify-between gap-2 text-sm"><span className="truncate">{r.disease} <span className="text-ink-4">· {r.crop}</span></span><Badge tone={r.level === "High" ? "bad" : "warn"}>{r.level}</Badge></div>))
                  : <p className="text-sm text-ink-3">No elevated disease risk in the forecast.</p>}
              </div>
              <p className="mt-3 text-2xs text-ink-4">Source: Open-Meteo · updated {ago(wx.data.fetched_at)}</p>
            </>}
          </div>
        </Card>
      </div>
    </div>
  );
}
