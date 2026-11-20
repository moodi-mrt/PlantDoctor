import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { api, ApiError, upload } from "../../lib/api";
import type { DiagnosisResult, MyPlant } from "../../lib/types";
import { Button, Card, Notice, Select, Spinner } from "../ui/ui";
import { Icon } from "../ui/icons";
import ImageInput, { type Picked } from "./ImageInput";
import PlantPicker, { type PickedPlant } from "./PlantPicker";
import ResultView from "./ResultView";

type Mode = "name" | "photo";
type Phase = "input" | "uploading" | "analysing" | "done" | "error";

/**
 * The two-path flow from the brief: "Which plant would you like to diagnose?"
 *   (a) type the plant name, then add a photo  (disease model restricted to that crop)
 *   (b) just upload / capture a photo            (the model identifies the plant first)
 * Progress is real: upload % from XHR, then an indeterminate "analysing" state until the server answers.
 */
export default function DiagnoseFlow({ guest, onSaved }: { guest?: boolean; onSaved?: (r: DiagnosisResult) => void }) {
  const [mode, setMode] = useState<Mode | null>(null);
  const [plant, setPlant] = useState<PickedPlant | null>(null);
  const [image, setImage] = useState<Picked | null>(null);
  const [phase, setPhase] = useState<Phase>("input");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<DiagnosisResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [plantId, setPlantId] = useState<string>("");
  const abort = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const plants = useQuery({ queryKey: ["plants"], queryFn: () => api<{ items: MyPlant[] }>("/plants"), enabled: !guest });

  const run = useCallback(async (cropOverride?: string) => {
    if (!image) return;
    const form = new FormData();
    form.append("file", image.blob, image.name.replace(/\.\w+$/, "") + ".jpg");
    const crop = cropOverride ?? (mode === "name" ? plant?.key : undefined);
    if (crop) form.append("crop", crop);
    if (plantId) form.append("plant_id", plantId);
    abort.current = new AbortController();
    setPhase("uploading"); setProgress(0); setError(null);
    try {
      const p = upload<DiagnosisResult>("/predictions", form, (pct) => { setProgress(pct); if (pct >= 100) setPhase("analysing"); }, abort.current.signal);
      const r = await p;
      setResult(r); setPhase("done");
      if (r.saved) { qc.invalidateQueries({ queryKey: ["predictions"] }); qc.invalidateQueries({ queryKey: ["analytics"] }); onSaved?.(r); }
    } catch (e) {
      if ((e as Error).name === "AbortError") { setPhase("input"); return; }
      setError(e as ApiError); setPhase("error");
    }
  }, [image, mode, plant, plantId, qc, onSaved]);

  useEffect(() => { if (phase === "done") resultRef.current?.focus(); }, [phase]);
  const reset = () => { setImage(null); setResult(null); setPhase("input"); setError(null); };
  const canRun = !!image && (mode === "photo" || (mode === "name" && plant));

  if (phase === "done" && result) return (
    <div ref={resultRef} tabIndex={-1} className="outline-none">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Diagnosis result</h2>
        <Button variant="secondary" icon="plus" onClick={() => { reset(); setMode(null); setPlant(null); }}>New diagnosis</Button>
      </div>
      <ResultView r={result} guest={guest} onRetry={reset}
        onTypePlant={(crop) => { setMode("name"); setPlant({ key: crop, name: crop, scientific: "", supported: true }); run(crop); }} />
    </div>
  );

  const busy = phase === "uploading" || phase === "analysing";
  return (
    <div className="space-y-5">
      {/* Step 1 */}
      <Card className="p-5 sm:p-6">
        <p className="text-xs font-semibold uppercase tracking-wider text-forest-600">Step 1</p>
        <h2 className="mt-1 text-xl font-semibold tracking-tight">Which plant would you like to diagnose?</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {([["name", "search", "I know the plant", "Type its name — the diagnosis is limited to that crop, which is more reliable."],
             ["photo", "camera", "Identify it from a photo", "Upload or take a photo; the model identifies the plant first."]] as const).map(([m, icon, title, sub]) => (
            <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m} disabled={busy}
              className={clsx("flex gap-3 rounded-2xl border p-4 text-left transition-colors focus-ring",
                mode === m ? "border-forest-800 bg-forest-50 ring-1 ring-forest-800" : "border-line-strong bg-white hover:bg-paper-2")}>
              <span className={clsx("grid h-10 w-10 shrink-0 place-items-center rounded-xl", mode === m ? "bg-forest-800 text-white" : "bg-paper-2 text-forest-700")}><Icon name={icon} /></span>
              <span><span className="block font-medium">{title}</span><span className="mt-0.5 block text-sm text-ink-3">{sub}</span></span>
            </button>))}
        </div>
        {mode === "name" && <div className="mt-5 max-w-md"><PlantPicker value={plant} onChange={setPlant} autoFocus /></div>}
      </Card>

      {/* Step 2 */}
      {mode && (
        <Card className="p-5 sm:p-6">
          <p className="text-xs font-semibold uppercase tracking-wider text-forest-600">Step 2</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight">Add a photo of the affected leaf or fruit</h2>
          <div className="mt-4"><ImageInput onReady={setImage} disabled={busy} /></div>
          {!guest && (plants.data?.items.length ?? 0) > 0 && (
            <div className="mt-4 max-w-sm">
              <Select label="Link to one of my plants (optional)" value={plantId} onChange={(e) => setPlantId(e.target.value)} disabled={busy}>
                <option value="">— none —</option>
                {plants.data!.items.map((p) => <option key={p.id} value={p.id}>{p.nickname}{p.crop ? ` (${p.crop})` : ""}</option>)}
              </Select>
            </div>)}
        </Card>
      )}

      {phase === "error" && error && (
        <Notice tone="bad" title="We couldn't analyse that image">
          <p>{error.message}</p>
          {error.code === "rate_limited" && guest && <p className="mt-1"><a href="/register" className="font-medium underline">Create a free account</a> for more scans.</p>}
        </Notice>
      )}

      {mode && (
        <div className="sticky bottom-20 z-10 lg:bottom-4">
          <Card className="flex flex-col gap-3 p-4 shadow-lift sm:flex-row sm:items-center sm:justify-between">
            {busy ? (
              <div className="flex flex-1 items-center gap-3" role="status" aria-live="polite">
                <Spinner className="text-forest-700" />
                <div className="flex-1">
                  <p className="text-sm font-medium">{phase === "uploading" ? `Uploading photo… ${progress}%` : "Analysing on the server — identifying the plant and checking for disease…"}</p>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-paper-3">
                    <div className={clsx("h-full rounded-full bg-forest-700 transition-[width]", phase === "analysing" && "w-1/3 animate-[slide_1.2s_ease-in-out_infinite]")}
                      style={phase === "uploading" ? { width: `${progress}%` } : undefined} />
                  </div>
                </div>
                <Button variant="ghost" size="sm" onClick={() => abort.current?.abort()}>Cancel</Button>
              </div>
            ) : (
              <>
                <p className="text-sm text-ink-3">{!image ? "Add a photo to continue." : mode === "name" && !plant ? "Choose the plant name from the list." : guest ? "Guest scans are not saved." : "Your photo is stored privately in your account."}</p>
                <Button size="lg" icon="scan" disabled={!canRun} onClick={() => run()}>Analyse photo</Button>
              </>
            )}
          </Card>
        </div>
      )}
      <style>{`@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(300%)}}`}</style>
    </div>
  );
}
