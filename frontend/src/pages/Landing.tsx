import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "../lib/api";
import { pct } from "../lib/format";
import type { DiagnosisResult, Meta, PlantInfo } from "../lib/types";
import { Badge, ButtonLink, Card, ConfidenceMeter, Skeleton, Spinner } from "../components/ui/ui";
import { Icon, type IconName } from "../components/ui/icons";

type Sample = { file: string; crop: string; disease: string; source: string };

function Demo() {
  const samples = useQuery({ queryKey: ["demo-samples"], queryFn: () => api<{ items: Sample[] }>("/demo/samples") });
  const [picked, setPicked] = useState<string | null>(null);
  const [view, setView] = useState<"photo" | "heat">("photo");
  const run = useMutation({ mutationFn: (f: string) => api<DiagnosisResult>(`/demo/${f}`, { method: "POST" }) });
  const r = run.data;
  const choose = (f: string) => { setPicked(f); setView("photo"); run.mutate(f); };
  return (
    <Card className="overflow-hidden shadow-lift">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <p className="text-sm font-medium">Live demo — pick a sample photo</p>
        <Badge tone="brand">Real model, nothing stored</Badge>
      </div>
      <div className="grid gap-2 border-b border-line p-3 grid-cols-6">
        {samples.isLoading && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)}
        {samples.data?.items.map((s) => (
          <button key={s.file} onClick={() => choose(s.file)} aria-pressed={picked === s.file} aria-label={`Analyse sample: ${s.crop}, ${s.disease}`}
            className={clsx("relative aspect-square overflow-hidden rounded-lg ring-offset-2 focus-ring", picked === s.file ? "ring-2 ring-forest-800" : "opacity-80 hover:opacity-100")}>
            <img src={`/samples/${s.file}`} alt="" className="h-full w-full object-cover" loading="lazy" />
            {s.source === "field" && <span className="absolute bottom-0.5 left-0.5 rounded bg-ink/70 px-1 text-[9px] text-white">field</span>}
          </button>))}
      </div>
      <div className="grid min-h-[270px] gap-4 p-5 sm:grid-cols-2">
        {!picked && <div className="col-span-full grid place-items-center text-center text-sm text-ink-3"><div><Icon name="scan" size={28} className="mx-auto mb-2 text-forest-600" />Choose a photo above to see a real diagnosis.</div></div>}
        {picked && run.isPending && <div className="col-span-full grid place-items-center text-sm text-ink-3" role="status"><div className="flex items-center gap-2"><Spinner /> Analysing…</div></div>}
        {picked && run.isError && <p className="col-span-full text-sm text-bad-700">{(run.error as Error).message}</p>}
        {r && !run.isPending && <>
          <div>
            <div className="relative aspect-square overflow-hidden rounded-xl bg-paper-2">
              <img src={view === "photo" ? `/samples/${picked}` : r.heatmap_url!} alt={view === "photo" ? "Sample photo" : "Model attention heatmap"} className="h-full w-full object-cover" />
            </div>
            <div className="mt-2 inline-flex rounded-lg bg-paper-2 p-0.5 text-xs">
              {(["photo", "heat"] as const).map((v) => <button key={v} aria-pressed={view === v} onClick={() => setView(v)} className={clsx("rounded-md px-2.5 py-1 font-medium", view === v ? "bg-white shadow-card" : "text-ink-3")}>{v === "photo" ? "Photo" : "Model focus"}</button>)}
            </div>
          </div>
          <div className="flex flex-col">
            <p className="text-xs uppercase tracking-wider text-ink-4">Plant</p>
            <p className="font-semibold">{r.plant?.info?.name} <span className="text-sm font-normal italic text-ink-3">{r.plant?.info?.scientific}</span></p>
            <p className="text-xs text-ink-3">identified from the photo · {pct(r.plant?.confidence)}</p>
            <p className="mt-4 text-xs uppercase tracking-wider text-ink-4">Diagnosis</p>
            <p className="text-xl font-semibold tracking-tight">{r.diagnosis?.name ?? "—"}</p>
            <p className="text-xs italic text-ink-3">{r.diagnosis?.knowledge.pathogen}</p>
            {r.diagnosis && <div className="mt-4"><ConfidenceMeter value={r.diagnosis.confidence} /></div>}
            <p className="mt-auto pt-4 text-xs text-ink-4">{r.latency_ms} ms · {r.model_version}</p>
          </div>
        </>}
      </div>
    </Card>
  );
}

const STEPS: [IconName, string, string][] = [
  ["sprout", "Tell us the plant — or don't", "Type its name in English or Urdu, or let the model identify it from the photo."],
  ["camera", "Photograph the symptoms", "One leaf or fruit, in daylight, filling the frame. Crop it right in the app."],
  ["shield", "Get a cautious, cited answer", "Diagnosis with calibrated confidence, the model's focus area, a treatment plan with sources, and products sold in Pakistan."],
];
const FEATURES: [IconName, string, string][] = [
  ["layers", "Two-stage identification", "Plant first, disease second — each with its own confidence. If the plant isn't clear, we ask instead of guessing."],
  ["search", "Explainable results", "A Grad-CAM heatmap shows which part of the photo drove the prediction, so you can check it looked at the symptoms."],
  ["book", "Source-cited treatment plans", "Immediate steps, organic and chemical options (active ingredients + resistance groups), prevention, watering, soil and fertilizer — every plan links to its references."],
  ["store", "Products available in Pakistan", "Verified store listings with the date we checked them, kept separate from plain search suggestions. No invented prices or links."],
  ["cloud", "Weather-based disease risk", "Forecast temperature and humidity are checked against each disease's infection conditions for your crops."],
  ["chat", "Assistant that stays grounded", "Ask follow-up questions in English or Urdu. Answers cite the knowledge base and never include pesticide doses."],
];
const FAQ: [string, string][] = [
  ["How accurate is it?", "On clear, single-leaf photos similar to the training data the model is very accurate; on cluttered real-field photos it is much less reliable. We publish both numbers in the Reliability section and the app flags uncertain results instead of hiding them."],
  ["Which crops are supported?", "The crops marked “Supported” below can be diagnosed from a photo. The disease library also covers crops the image model doesn't know yet, as reference information."],
  ["Will it tell me how much pesticide to use?", "No. We name active ingredients and their resistance groups, link to registered products, and tell you to follow the product label. Doses depend on the product, crop and local registration."],
  ["Is my photo private?", "Guest scans are not stored. With an account, photos are stored privately, location metadata (EXIF/GPS) is removed, and you can delete any diagnosis or your whole account at any time."],
  ["Does it work in Urdu?", "You can type plant names in Urdu or Roman Urdu, and the assistant and explanations can answer in Urdu. A full Urdu interface is planned."],
  ["Does it replace an agronomist?", "No. It is decision support. For uncertain results, fast-spreading problems or notifiable diseases such as citrus greening, contact your district Agriculture Extension office."],
];

export default function Landing() {
  const meta = useQuery({ queryKey: ["meta"], queryFn: () => api<Meta>("/meta") });
  const crops = useQuery({ queryKey: ["crops"], queryFn: () => api<{ items: (PlantInfo & { supported: boolean; disease_count: number })[]; supported_count: number }>("/crops") });
  const m = meta.data?.metrics;
  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 -z-10 h-[520px] bg-gradient-to-b from-forest-50 to-paper" />
        <div className="mx-auto grid max-w-page gap-10 px-5 pb-16 pt-12 lg:grid-cols-[1.05fr_1fr] lg:items-center lg:pt-20">
          <div>
            <Badge tone="brand" icon="leaf">Plant health from a single photo</Badge>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.08] tracking-tight text-ink sm:text-5xl">
              Know what's wrong with your crop — and what to do next.
            </h1>
            <p className="mt-5 max-w-xl text-lg text-ink-2">
              PlantDoctor identifies the plant, detects likely diseases and pests, and gives a treatment plan built from
              extension-service sources — with honest confidence, not guesses.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <ButtonLink to="/try" size="lg" icon="scan">Try disease detection</ButtonLink>
              <ButtonLink to="/register" size="lg" variant="secondary">Create free account</ButtonLink>
            </div>
            <dl className="mt-10 grid max-w-md grid-cols-3 gap-4">
              {[["Crops", meta.data?.crops], ["Conditions", meta.data?.classes], ["Library entries", crops.data ? crops.data.items.reduce((n, c) => n + c.disease_count, 0) : undefined]].map(([k, v]) => (
                <div key={k as string}><dt className="text-xs text-ink-3">{k}</dt><dd className="text-2xl font-semibold tabular-nums">{v ?? "—"}</dd></div>))}
            </dl>
          </div>
          <Demo />
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="mx-auto max-w-page scroll-mt-20 px-5 py-16">
        <p className="text-xs font-semibold uppercase tracking-wider text-forest-600">How it works</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight">Three steps, under a minute</h2>
        <ol className="mt-8 grid gap-5 md:grid-cols-3">
          {STEPS.map(([icon, t, d], i) => (
            <li key={t}><Card className="h-full p-6">
              <div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-forest-800 text-white"><Icon name={icon} /></span><span className="text-sm font-semibold text-ink-4">0{i + 1}</span></div>
              <h3 className="mt-4 font-semibold">{t}</h3><p className="mt-1.5 text-[15px] text-ink-3">{d}</p>
            </Card></li>))}
        </ol>
      </section>

      {/* Crops */}
      <section id="crops" className="scroll-mt-20 border-y border-line bg-white">
        <div className="mx-auto max-w-page px-5 py-16">
          <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-forest-600">Coverage</p>
              <h2 className="mt-2 text-3xl font-semibold tracking-tight">Supported crops</h2>
              <p className="mt-2 max-w-xl text-ink-3">“Supported” crops can be diagnosed from a photo by the current model. Others have disease-library information only.</p>
            </div>
            <ButtonLink to="/knowledge" variant="secondary" icon="book">Browse disease library</ButtonLink>
          </div>
          <div className="mt-8 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {crops.isLoading && Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
            {crops.data?.items.map((c) => (
              <div key={c.key} className={clsx("rounded-xl border p-3.5", c.supported ? "border-line bg-paper" : "border-dashed border-line-strong bg-white")}>
                <div className="flex items-start justify-between gap-2"><p className="font-medium">{c.name}</p>{c.supported && <Icon name="check" size={16} className="mt-0.5 text-emerald-600" />}</div>
                <p className="truncate text-xs italic text-ink-3">{c.scientific}</p>
                <p className="mt-1.5 text-xs text-ink-4">{c.disease_count ? `${c.disease_count} condition${c.disease_count === 1 ? "" : "s"}` : "healthy reference"} · {c.supported ? "photo diagnosis" : "library only"}</p>
              </div>))}
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="mx-auto max-w-page px-5 py-16">
        <p className="text-xs font-semibold uppercase tracking-wider text-forest-600">Platform</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight">Built for decisions in the field</h2>
        <div className="mt-8 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(([icon, t, d]) => (
            <div key={t}><span className="grid h-10 w-10 place-items-center rounded-xl bg-forest-50 text-forest-700"><Icon name={icon} /></span>
              <h3 className="mt-4 font-semibold">{t}</h3><p className="mt-1.5 text-[15px] text-ink-3">{d}</p></div>))}
        </div>
      </section>

      {/* Reliability */}
      <section id="reliability" className="scroll-mt-20 bg-forest-900 text-white">
        <div className="mx-auto grid max-w-page gap-10 px-5 py-16 lg:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-forest-300">Scientific transparency</p>
            <h2 className="mt-2 text-3xl font-semibold tracking-tight">How reliable is it? We show you.</h2>
            <p className="mt-4 text-forest-100">Accuracy on tidy lab photos says little about a muddy field. We report both, and the app is designed around the weaker number: it flags uncertainty, asks for the plant name when unsure, and refuses to diagnose photos unlike its training data.</p>
            <ul className="mt-6 space-y-2 text-sm text-forest-100">
              {["Held-out test images never used in training", "Separate external test on real field photos (PlantDoc)",
                meta.data?.calibrated ? "Confidence calibrated with temperature scaling" : "Confidence thresholds tuned on a validation set",
                meta.data?.ood_detection ? "Out-of-distribution detector rejects unfamiliar images" : "Unfamiliar images are routed to “tell us the plant” instead of guessed",
                "Every saved prediction records the model version"].map((t) => <li key={t} className="flex gap-2"><Icon name="check" size={16} className="mt-0.5 text-emerald-500" />{t}</li>)}
            </ul>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            {meta.isLoading ? <Skeleton className="h-40 sm:col-span-2" /> : <>
              <div className="rounded-2xl bg-white/5 p-5 ring-1 ring-white/10">
                <p className="text-sm text-forest-200">Held-out test set</p>
                <p className="mt-2 text-4xl font-semibold tabular-nums">{pct(m?.test?.accuracy ?? m?.accuracy, 1)}</p>
                <p className="mt-1 text-sm text-forest-200">accuracy · macro-F1 {pct(m?.test?.macro_f1 ?? m?.macro_f1, 1)}</p>
                <p className="mt-3 text-xs text-forest-300">{(m?.test?.n ?? m?.n)?.toLocaleString()} images, mostly lab-style photos{m?.test?.split ? ` (${m.test.split} split)` : ""}.</p>
              </div>
              <div className="rounded-2xl bg-white/5 p-5 ring-1 ring-white/10">
                <p className="text-sm text-forest-200">Real field photos (external)</p>
                <p className="mt-2 text-4xl font-semibold tabular-nums text-warn-100">{pct(m?.field?.top1 ?? m?.field_top1, 1)}</p>
                <p className="mt-1 text-sm text-forest-200">exact match · {pct(m?.field?.top5, 0)} within top 5 · crop {pct(m?.field?.crop, 0)}</p>
                <p className="mt-3 text-xs text-forest-300">{m?.field?.n} images from a different dataset — the honest real-world number.</p>
              </div>
              <p className="text-xs text-forest-300 sm:col-span-2">Model {meta.data?.model_version} · {meta.data?.classes} classes. Full methodology in the <a href="/report" className="underline">technical report</a>.</p>
            </>}
          </div>
        </div>
      </section>

      {/* Audiences */}
      <section className="mx-auto max-w-page px-5 py-16">
        <div className="grid gap-5 md:grid-cols-2">
          <Card className="p-7"><Icon name="sprout" className="text-forest-700" />
            <h3 className="mt-3 text-lg font-semibold">For farmers and growers</h3>
            <ul className="mt-3 space-y-2 text-[15px] text-ink-2">{["Works on a phone camera, type plant names in Urdu", "Clear next steps before you spend on chemicals", "Weather warnings for your crops", "History of every field and plant you check"].map((t) => <li key={t} className="flex gap-2"><Icon name="check" size={16} className="mt-1 text-emerald-600" />{t}</li>)}</ul>
          </Card>
          <Card className="p-7"><Icon name="users" className="text-forest-700" />
            <h3 className="mt-3 text-lg font-semibold">For agronomists and consultants</h3>
            <ul className="mt-3 space-y-2 text-[15px] text-ink-2">{["Differential list with probabilities, not one answer", "Explainability heatmaps and model version on every report", "PDF reports and CSV export for your records", "Resistance-group aware chemical options"].map((t) => <li key={t} className="flex gap-2"><Icon name="check" size={16} className="mt-1 text-emerald-600" />{t}</li>)}</ul>
          </Card>
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="scroll-mt-20 border-t border-line bg-white">
        <div className="mx-auto max-w-3xl px-5 py-16">
          <h2 className="text-3xl font-semibold tracking-tight">Frequently asked questions</h2>
          <div className="mt-8 divide-y divide-line">
            {FAQ.map(([q, a]) => (
              <details key={q} className="group py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-medium focus-ring rounded-lg">{q}<Icon name="plus" size={18} className="shrink-0 text-ink-3 transition-transform group-open:rotate-45" /></summary>
                <p className="mt-2 text-[15px] text-ink-3">{a}</p>
              </details>))}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-page px-5 py-16">
        <Card className="flex flex-col items-start justify-between gap-6 bg-forest-50 p-8 sm:flex-row sm:items-center">
          <div><h2 className="text-2xl font-semibold tracking-tight">Check your first plant now</h2><p className="mt-1 text-ink-3">No account needed for a quick check.</p></div>
          <ButtonLink to="/try" size="lg" icon="scan">Try disease detection</ButtonLink>
        </Card>
      </section>
    </>
  );
}
