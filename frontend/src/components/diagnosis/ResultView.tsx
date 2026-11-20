import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "../../lib/api";
import { KIND_LABEL, dateTime, pct, rupees } from "../../lib/format";
import type { DiagnosisResult, KBEntry, Products, Status } from "../../lib/types";
import { Badge, Button, ButtonLink, Card, ConfidenceMeter, Loading, Notice, Skeleton } from "../ui/ui";
import { Icon, type IconName } from "../ui/icons";

const STATUS: Record<Status, { tone: "ok" | "warn" | "bad" | "info"; label: string; icon: IconName }> = {
  confident: { tone: "ok", label: "Confident result", icon: "check" },
  tentative: { tone: "warn", label: "Possible match — verify", icon: "alert" },
  uncertain: { tone: "bad", label: "Inconclusive", icon: "alert" },
  needs_input: { tone: "info", label: "Tell us the plant", icon: "info" },
  unknown: { tone: "bad", label: "Not recognised", icon: "alert" },
  no_leaf: { tone: "bad", label: "No plant found", icon: "alert" },
  unsupported_crop: { tone: "info", label: "Plant not supported yet", icon: "info" },
};

function Section({ title, children, icon }: { title: string; children: ReactNode; icon?: IconName }) {
  return (
    <section className="py-4 first:pt-0">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">{icon && <Icon name={icon} size={16} className="text-forest-600" />}{title}</h3>
      <div className="text-[15px] leading-relaxed text-ink-2">{children}</div>
    </section>
  );
}
function List({ items }: { items: string[] }) {
  if (!items?.length) return <p className="text-ink-4">—</p>;
  return <ul className="space-y-1.5">{items.map((t) => <li key={t} className="flex gap-2"><span className="mt-2.5 h-1 w-1 shrink-0 rounded-full bg-forest-500" />{t}</li>)}</ul>;
}

export function TreatmentPlan({ k }: { k: KBEntry }) {
  const t = k.treatment;
  if (k.kind === "healthy" || k.kind === "none") return <List items={[...t.immediate, ...t.preventive]} />;
  return (
    <div className="divide-y divide-line">
      <Section title="Do this now" icon="flag"><List items={t.immediate} /></Section>
      <Section title="Organic and cultural control" icon="leaf"><List items={t.organic} /></Section>
      <Section title="Chemical options — active ingredients" icon="shield">
        {t.chemical.length ? <>
          <ul className="space-y-1.5">{t.chemical.map((c) => (
            <li key={c.ai} className="flex flex-wrap items-center gap-2"><span className="font-medium text-ink">{c.ai}</span>
              {c.group && <Badge tone="brand">{c.group}</Badge>}{c.note && <span className="text-sm text-ink-3">({c.note})</span>}</li>))}
          </ul>
          {k.chemical_notice && <div className="mt-3"><Notice tone="warn" title="Read before spraying">{k.chemical_notice}</Notice></div>}
        </> : <p className="text-ink-3">No chemical cure — rely on the actions above.</p>}
      </Section>
      <Section title="Prevention" icon="shield"><List items={t.preventive} /></Section>
      <Section title="Watering" icon="droplet"><p>{t.watering}</p></Section>
      <Section title="Soil" icon="sprout"><p>{t.soil}</p></Section>
      <Section title="Fertilizer" icon="leaf"><p>{t.fertilizer}</p></Section>
      <Section title="Long-term care" icon="history"><List items={t.long_term} /></Section>
    </div>
  );
}

export function ProductsPanel({ label }: { label: string }) {
  const q = useQuery({ queryKey: ["products", label], queryFn: () => api<Products>(`/products?label=${encodeURIComponent(label)}`) });
  if (q.isLoading) return <Loading label="Finding products…" />;
  if (q.error || !q.data) return <Notice tone="bad">Products couldn't be loaded.</Notice>;
  const groups = q.data.groups;
  if (!groups.length) return <p className="text-ink-3">No chemical products are recommended for this problem — follow the cultural and preventive steps.</p>;
  return (
    <div className="space-y-6">
      <Notice tone="info">{q.data.disclaimer}</Notice>
      {groups.map((g) => (
        <div key={g.active_ingredient}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h4 className="font-semibold capitalize">{g.active_ingredient}</h4>{g.resistance_group && <Badge tone="brand">{g.resistance_group}</Badge>}
          </div>
          {g.verified.length ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {g.verified.map((p) => (
                <Card key={p.id} className="flex flex-col p-4">
                  <div className="mb-2 flex flex-wrap gap-1.5"><Badge tone="ok" icon="check">Verified listing</Badge>
                    {p.combination && <Badge tone="warn">Mixture: also {p.also_contains.join(", ")}</Badge>}
                    {p.seed_treatment && <Badge tone="info">Seed treatment</Badge>}</div>
                  <p className="line-clamp-2 text-sm font-medium text-ink">{p.title}</p>
                  <dl className="mt-2 grid grid-cols-[auto,1fr] gap-x-3 gap-y-0.5 text-xs text-ink-3">
                    <dt>Company</dt><dd className="text-ink-2">{p.company ?? "—"}</dd>
                    <dt>Active</dt><dd className="text-ink-2">{p.active_ingredient}</dd>
                    <dt>Pack</dt><dd className="text-ink-2">{p.pack_size ?? "—"}</dd>
                    <dt>Price</dt><dd className="font-medium text-ink">{rupees(p.price_pkr)}</dd>
                  </dl>
                  <div className="mt-auto flex items-center justify-between pt-3">
                    <span className="text-2xs text-ink-4">{p.store} · checked {p.verified_on}</span>
                    <a href={p.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-forest-700 hover:underline">View <Icon name="external" size={14} /></a>
                  </div>
                </Card>))}
            </div>
          ) : <p className="text-sm text-ink-3">No verified listing found for this ingredient.</p>}
          <div className="mt-2 flex flex-wrap gap-3 text-sm">
            {g.search.map((s) => <a key={s.url} href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-ink-3 hover:text-forest-700">
              <Icon name="search" size={14} />{s.label}<span className="text-2xs">(search suggestion)</span></a>)}
          </div>
        </div>))}
    </div>
  );
}

export function References({ k }: { k: KBEntry }) {
  return (
    <ul className="space-y-2.5">
      {k.references.map((r) => (
        <li key={r.id} className="text-sm">
          <a href={r.url} target="_blank" rel="noopener noreferrer" className="font-medium text-forest-700 hover:underline">{r.title}</a>
          <span className="text-ink-3"> — {r.publisher}{r.checked && ` · link checked ${r.checked}`}</span>
        </li>))}
    </ul>
  );
}

function Explanation({ id }: { id: number }) {
  const [lang, setLang] = useState<"en" | "ur">("en");
  const q = useQuery({ queryKey: ["explain", id, lang], queryFn: () => api<any>(`/predictions/${id}/explanation?lang=${lang}`), staleTime: Infinity });
  if (q.isLoading) return <div className="space-y-2"><Skeleton className="h-4 w-3/4" /><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-2/3" /></div>;
  const d = q.data;
  if (!d?.available) return <p className="text-sm text-ink-3">AI explanations are not enabled on this server. The full plan below comes from the curated knowledge base.</p>;
  if (!d.text) return <p className="text-sm text-ink-3">The AI explanation was withheld because it didn't pass our safety check — please use the verified plan below.</p>;
  const t = d.text;
  return (
    <div dir={lang === "ur" ? "rtl" : "ltr"}>
      <div className="mb-3 flex items-center justify-between gap-2" dir="ltr">
        <Badge tone="info" icon="info">AI-generated · grounded in the knowledge base</Badge>
        <div className="flex gap-1 text-xs">{(["en", "ur"] as const).map((l) => (
          <button key={l} onClick={() => setLang(l)} className={clsx("rounded-lg px-2 py-1", lang === l ? "bg-forest-800 text-white" : "text-ink-3 hover:bg-paper-2")}>{l === "en" ? "English" : "اردو"}</button>))}</div>
      </div>
      <p className="text-[15px] leading-relaxed text-ink">{t.summary}</p>
      <h4 className="mt-3 text-sm font-semibold">What to do now</h4>
      <ol className="mt-1 list-decimal space-y-1 pl-5 text-[15px] text-ink-2">{t.what_to_do_now.map((s: string) => <li key={s}>{s}</li>)}</ol>
      <h4 className="mt-3 text-sm font-semibold">Why it happened</h4><p className="text-[15px] text-ink-2">{t.why_it_happened}</p>
      <p className="mt-3 text-sm text-warn-700">{t.caution}</p>
    </div>
  );
}

export default function ResultView({ r, onRetry, onTypePlant, guest }: {
  r: DiagnosisResult; onRetry?: () => void; onTypePlant?: (crop: string) => void; guest?: boolean;
}) {
  const s = STATUS[r.status];
  const d = r.diagnosis;
  const k = d?.knowledge;
  const [tab, setTab] = useState<"overview" | "plan" | "products" | "refs">("overview");
  const [view, setView] = useState<"photo" | "heat">("photo");
  const qc = useQueryClient();
  const fb = useMutation({
    mutationFn: (feedback: string) => api(`/predictions/${r.id}`, { method: "PATCH", body: { feedback } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["prediction", String(r.id)] }),
  });
  const [feedback, setFeedback] = useState(r.feedback);
  const plant = r.plant?.info;
  const photo = r.image_url;
  const tabs = [["overview", "Overview"], ["plan", "Treatment plan"], ["products", "Products"], ["refs", "References"]] as const;

  return (
    <div className="space-y-5">
      {/* Status banner */}
      <div className={clsx("flex flex-col gap-3 rounded-2xl border p-4 sm:flex-row sm:items-center sm:justify-between",
        { ok: "border-emerald-600/20 bg-emerald-50", warn: "border-warn-600/25 bg-warn-50", bad: "border-bad-600/20 bg-bad-50", info: "border-info-600/20 bg-info-50" }[s.tone])}
        role={s.tone === "ok" ? "status" : "alert"}>
        <div className="flex gap-3">
          <Icon name={s.icon} className={clsx("mt-0.5 shrink-0", { ok: "text-emerald-700", warn: "text-warn-700", bad: "text-bad-700", info: "text-info-600" }[s.tone])} />
          <div>
            <p className="font-semibold text-ink">{s.label}</p>
            <p className="text-sm text-ink-2">{r.message ?? (d?.healthy ? "No disease symptoms recognised." : "The model is confident about this result. Still check the symptoms below match what you see.")}</p>
          </div>
        </div>
        {onRetry && r.status !== "confident" && <Button variant="secondary" size="sm" icon="camera" onClick={onRetry}>Retake photo</Button>}
      </div>

      {r.quality?.warnings?.length > 0 && (
        <Notice tone="warn" title="Photo quality">{r.quality.warnings.map((w) => <p key={w.code}>{w.message}</p>)}</Notice>
      )}

      {r.status === "needs_input" && r.plant && onTypePlant && (
        <Card className="p-5">
          <h3 className="font-semibold">Which plant is this?</h3>
          <p className="mt-1 text-sm text-ink-3">The closest matches were — pick one to re-analyse this photo for that crop:</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {r.plant.candidates.map((c) => (
              <Button key={c.crop} variant="secondary" size="sm" onClick={() => onTypePlant(c.info?.key ?? c.crop)}>{c.info?.name ?? c.crop} <span className="text-ink-4">{pct(c.probability)}</span></Button>))}
          </div>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        {/* Image */}
        <Card className="overflow-hidden">
          <div className="relative aspect-square bg-paper-2">
            {(view === "photo" ? photo ?? r.heatmap_url : r.heatmap_url) ?
              <img src={(view === "photo" ? photo ?? r.heatmap_url : r.heatmap_url)!} alt={view === "photo" ? "Uploaded plant photo" : "Grad-CAM heatmap: warmer areas influenced the prediction most"} className="h-full w-full object-contain" />
              : <div className="grid h-full place-items-center text-sm text-ink-4">No image</div>}
          </div>
          {r.heatmap_url && (
            <div className="flex items-center justify-between gap-3 border-t border-line p-3">
              <div className="inline-flex rounded-lg bg-paper-2 p-0.5 text-sm" role="group" aria-label="Image view">
                {(["photo", "heat"] as const).map((v) => (
                  <button key={v} aria-pressed={view === v} onClick={() => setView(v)} disabled={v === "photo" && !photo}
                    className={clsx("rounded-md px-3 py-1.5 font-medium", view === v ? "bg-white shadow-card" : "text-ink-3 disabled:opacity-40")}>{v === "photo" ? "Photo" : "Model focus"}</button>))}
              </div>
              <span className="text-2xs text-ink-4">{view === "heat" ? "Check it focuses on the symptoms" : `${r.model_version ?? ""}`}</span>
            </div>
          )}
        </Card>

        {/* Summary */}
        <div className="space-y-5">
          <Card className="p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-4">Plant</p>
            {plant ? <>
              <p className="mt-1 text-lg font-semibold">{plant.name} <span className="text-sm font-normal italic text-ink-3">{plant.scientific}</span></p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <Badge>{plant.type}</Badge><Badge>{plant.family}</Badge>
                {r.plant?.source === "user" ? <Badge tone="brand">Named by you</Badge> : r.plant?.confidence != null && <Badge tone="brand">Identified from photo · {pct(r.plant.confidence)}</Badge>}
              </div>
              {r.plant?.source === "user" && r.plant.agrees_with_user === false && (
                <div className="mt-3"><Notice tone="warn">The photo looks more like <b>{r.plant.candidates[0]?.info?.name ?? r.plant.candidates[0]?.crop}</b> to the model. Double-check the plant name.</Notice></div>)}
            </> : <p className="mt-1 text-ink-3">{r.plant?.typed ? `${r.plant.typed} (not identified)` : "Not identified"}</p>}
          </Card>

          <Card className="p-5">
            <p className="text-xs font-semibold uppercase tracking-wider text-ink-4">Diagnosis</p>
            {d && k ? <>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <h2 className="text-2xl font-semibold tracking-tight">{r.status === "uncertain" ? `Closest match: ${d.name}` : d.name}</h2>
                <Badge tone={d.healthy ? "ok" : "neutral"}>{KIND_LABEL[d.kind] ?? d.kind}</Badge>
              </div>
              {k.pathogen && k.pathogen !== "—" && <p className="mt-1 text-sm italic text-ink-3">{k.pathogen}</p>}
              <div className="mt-4"><ConfidenceMeter value={d.confidence} calibrated={d.calibrated} /></div>
              {k.affected_parts.length > 0 && <p className="mt-4 text-sm text-ink-2"><span className="text-ink-3">Affected parts: </span>{k.affected_parts.join(", ")}</p>}
              {r.findings.length > 0 && <div className="mt-4"><Notice tone="info" title="Possible co-occurring problems">{r.findings.map((f) => `${f.name} (${pct(f.probability)})`).join(" · ")}</Notice></div>}
            </> : <p className="mt-1 text-ink-3">No diagnosis — see the message above.</p>}
          </Card>
        </div>
      </div>

      {d && k && (
        <Card>
          <div className="flex gap-1 overflow-x-auto border-b border-line px-3" role="tablist" aria-label="Diagnosis details">
            {tabs.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} aria-controls={`panel-${id}`} id={`tab-${id}`} onClick={() => setTab(id)}
                className={clsx("whitespace-nowrap border-b-2 px-3 py-3.5 text-sm font-medium focus-ring", tab === id ? "border-forest-800 text-ink" : "border-transparent text-ink-3 hover:text-ink")}>{label}</button>))}
          </div>
          <div className="p-5" role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
            {tab === "overview" && <div className="divide-y divide-line">
              {r.id && !d.healthy && <Section title="Explanation" icon="chat"><Explanation id={r.id} /></Section>}
              <Section title="Symptoms" icon="search"><p>{k.symptoms}</p></Section>
              {k.causes && k.causes !== "—" && <Section title="Possible causes" icon="info"><p>{k.causes}</p></Section>}
              {k.conditions && k.conditions !== "—" && <Section title="Conditions that favour it" icon="cloud"><p>{k.conditions}</p></Section>}
              {r.alternatives.length > 0 && <Section title="Other possibilities the model considered" icon="layers">
                <ul className="space-y-2">{r.alternatives.map((a) => (
                  <li key={a.label} className="flex items-center gap-3 text-sm">
                    <Link to={`/knowledge/${encodeURIComponent(a.label)}`} className="min-w-0 flex-1 truncate hover:text-forest-700">{a.name} <span className="text-ink-4">· {a.crop}</span></Link>
                    <div className="h-1.5 w-28 overflow-hidden rounded-full bg-paper-3"><div className="h-full rounded-full bg-forest-400" style={{ width: `${Math.max(2, a.probability * 100)}%` }} /></div>
                    <span className="w-12 text-right tabular-nums text-ink-3">{pct(a.probability, 1)}</span>
                  </li>))}</ul>
              </Section>}
            </div>}
            {tab === "plan" && <TreatmentPlan k={k} />}
            {tab === "products" && <ProductsPanel label={d.label} />}
            {tab === "refs" && <References k={k} />}
          </div>
        </Card>
      )}

      {r.expert_help.length > 0 && (
        <Card className="p-5">
          <h3 className="flex items-center gap-2 font-semibold"><Icon name="users" size={18} className="text-forest-600" />When to ask an expert</h3>
          <p className="mt-1 text-sm text-ink-3">Confirm before spraying if the result is uncertain, the problem is spreading fast, or it could be a notifiable disease.</p>
          <ul className="mt-3 space-y-2 text-sm">{r.expert_help.map((e) => <li key={e.name}>
            {e.url ? <a href={e.url} target="_blank" rel="noopener noreferrer" className="font-medium text-forest-700 hover:underline">{e.name}</a> : <span className="font-medium">{e.name}</span>}
            {e.note && <span className="text-ink-3"> — {e.note}</span>}</li>)}</ul>
        </Card>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2">
        {r.id ? <>
          <ButtonLink to={`/app/assistant?diagnosis=${r.id}`} icon="chat" variant="secondary">Ask the assistant</ButtonLink>
          <a href={`/api/v1/predictions/${r.id}/report.pdf`} className="inline-flex h-10 items-center gap-2 rounded-xl border border-line-strong bg-white px-4 text-sm font-medium shadow-card hover:bg-paper-2 focus-ring"><Icon name="download" size={18} />Download PDF report</a>
          {d && <div className="ml-auto flex items-center gap-2 text-sm text-ink-3">
            <span>Was this right?</span>
            {(["correct", "incorrect", "unsure"] as const).map((f) => (
              <button key={f} onClick={() => { setFeedback(f); fb.mutate(f); }} aria-pressed={feedback === f}
                className={clsx("rounded-lg border px-2.5 py-1 text-xs font-medium focus-ring", feedback === f ? "border-forest-800 bg-forest-800 text-white" : "border-line-strong bg-white hover:bg-paper-2")}>
                {f === "correct" ? "Yes" : f === "incorrect" ? "No" : "Not sure"}</button>))}
          </div>}
        </> : guest && <Notice tone="info" title="This result wasn't saved">Create a free account to keep your diagnoses, download PDF reports and ask the assistant. <Link to="/register" className="font-medium text-forest-700 underline">Create account</Link></Notice>}
      </div>
      <p className="text-xs text-ink-4">{dateTime(r.created_at)} · model {r.model_version ?? "—"} · analysed in {r.latency_ms} ms · decision support only, not a laboratory diagnosis.</p>
    </div>
  );
}
