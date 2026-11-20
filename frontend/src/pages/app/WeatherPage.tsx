import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { ago } from "../../lib/format";
import type { MyPlant, Weather } from "../../lib/types";
import { Badge, Button, Card, CardHeader, EmptyState, ErrorState, Input, Notice, PageHeader, Skeleton } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";

export default function WeatherPage() {
  const { user } = useAuth();
  const [place, setPlace] = useState(user?.location ?? "");
  const [query, setQuery] = useState(user?.location ?? "");
  const [coords, setCoords] = useState<{ lat: number; lon: number } | null>(null);
  const plants = useQuery({ queryKey: ["plants"], queryFn: () => api<{ items: MyPlant[] }>("/plants") });
  const myCrops = [...new Set((plants.data?.items ?? []).map((p) => p.crop_key).filter(Boolean))].join(",");
  const params = new URLSearchParams(coords ? { lat: String(coords.lat), lon: String(coords.lon) } : query ? { q: query } : {});
  if (myCrops) params.set("crops", myCrops);
  const wx = useQuery({ queryKey: ["weather", params.toString()], queryFn: () => api<Weather>(`/weather?${params}`), retry: 0 });
  const submit = (e: FormEvent) => { e.preventDefault(); setCoords(null); setQuery(place); };
  const locate = () => navigator.geolocation?.getCurrentPosition((p) => setCoords({ lat: p.coords.latitude, lon: p.coords.longitude }));
  const d = wx.data;
  return (
    <div>
      <PageHeader title="Weather & disease risk" sub={myCrops ? "Risk is shown for the crops in My plants." : "Add plants under My plants to focus risk alerts on your crops."} />
      <Card className="mb-5 p-4">
        <form onSubmit={submit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Input className="flex-1" label="Location" placeholder="City or district, e.g. Multan" value={place} onChange={(e) => setPlace(e.target.value)} />
          <Button type="submit" icon="search">Show forecast</Button>
          <Button variant="secondary" icon="home" onClick={locate}>Use my location</Button>
        </form>
      </Card>
      {wx.isLoading ? <Skeleton className="h-72" /> : wx.error ? <ErrorState error={wx.error} onRetry={() => wx.refetch()} /> : d && <>
        <div className="grid gap-5 lg:grid-cols-3">
          <Card className="p-5">
            <p className="text-sm text-ink-3">{d.place.name}{d.place.admin1 ? `, ${d.place.admin1}` : ""}</p>
            <p className="mt-2 text-5xl font-semibold tabular-nums">{Math.round(Number(d.current?.temperature_2m))}°C</p>
            <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-ink-2">
              <p className="flex items-center gap-1.5"><Icon name="droplet" size={16} className="text-info-600" />Humidity {d.current?.relative_humidity_2m}%</p>
              <p className="flex items-center gap-1.5"><Icon name="cloud" size={16} />Rain {d.current?.precipitation} mm</p>
            </div>
            {d.irrigation && <div className="mt-4"><Notice tone="info" title="Irrigation">{d.irrigation}</Notice></div>}
            <p className="mt-4 text-2xs text-ink-4">{d.source} · updated {ago(d.fetched_at)}{d.stale && " (cached copy — live service unavailable)"}</p>
          </Card>
          <Card className="lg:col-span-2">
            <CardHeader title="7-day forecast" />
            <div className="grid grid-cols-4 gap-2 p-5 sm:grid-cols-7">
              {(d.daily.time as string[] | undefined)?.map((t, i) => (
                <div key={t} className="rounded-xl bg-paper-2 p-3 text-center">
                  <p className="text-xs text-ink-3">{new Date(t).toLocaleDateString(undefined, { weekday: "short" })}</p>
                  <p className="mt-1 font-semibold tabular-nums">{Math.round(Number(d.daily.temperature_2m_max[i]))}°</p>
                  <p className="text-xs tabular-nums text-ink-3">{Math.round(Number(d.daily.temperature_2m_min[i]))}°</p>
                  <p className="mt-1 text-2xs text-info-600">{d.daily.precipitation_sum[i]} mm</p>
                </div>))}
            </div>
          </Card>
        </div>
        <Card className="mt-5">
          <CardHeader title="Disease risk — next 72 hours" sub={d.risk_method} />
          <div className="p-5">
            {!d.risks.length ? <EmptyState icon="check" title="No elevated risk">The forecast doesn't match the infection conditions of diseases in our library{myCrops ? " for your crops" : ""}.</EmptyState> :
              <ul className="grid gap-3 md:grid-cols-2">{d.risks.slice(0, 12).map((r) => (
                <li key={r.label} className="rounded-xl border border-line p-4">
                  <div className="flex items-center justify-between gap-2"><p className="font-medium">{r.disease} <span className="text-ink-3">· {r.crop}</span></p><Badge tone={r.level === "High" ? "bad" : "warn"}>{r.level}</Badge></div>
                  <p className="mt-1 text-xs text-ink-3">{r.favourable_hours} favourable hours (threshold {r.needed_hours}) · {r.conditions}</p>
                  <ul className="mt-2 space-y-1 text-sm text-ink-2">{r.advice.map((a) => <li key={a}>• {a}</li>)}</ul>
                </li>))}</ul>}
          </div>
        </Card>
      </>}
    </div>
  );
}
