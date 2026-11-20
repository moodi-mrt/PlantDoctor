import { useCallback, useEffect, useRef, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";
import clsx from "clsx";
import { Button, Notice } from "../ui/ui";
import { Icon } from "../ui/icons";

const TYPES = ["image/jpeg", "image/png", "image/webp"];
const MAX_MB = 15;

async function load(src: string): Promise<HTMLImageElement> {
  return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });
}

/** Render the crop + rotation to a JPEG blob (also strips EXIF before upload). */
async function render(src: string, area: Area | null, rotation: number): Promise<Blob> {
  const img = await load(src);
  const rad = (rotation * Math.PI) / 180;
  const sw = Math.abs(Math.cos(rad)) * img.width + Math.abs(Math.sin(rad)) * img.height;
  const sh = Math.abs(Math.sin(rad)) * img.width + Math.abs(Math.cos(rad)) * img.height;
  const full = document.createElement("canvas");
  full.width = sw; full.height = sh;
  const fc = full.getContext("2d")!;
  fc.translate(sw / 2, sh / 2); fc.rotate(rad); fc.drawImage(img, -img.width / 2, -img.height / 2);
  const a = area ?? { x: 0, y: 0, width: sw, height: sh };
  const scale = Math.min(1, 2048 / Math.max(a.width, a.height));
  const out = document.createElement("canvas");
  out.width = Math.round(a.width * scale); out.height = Math.round(a.height * scale);
  out.getContext("2d")!.drawImage(full, a.x, a.y, a.width, a.height, 0, 0, out.width, out.height);
  return new Promise((res) => out.toBlob((b) => res(b!), "image/jpeg", 0.92));
}

export interface Picked { blob: Blob; url: string; width: number; height: number; name: string }

export default function ImageInput({ onReady, disabled }: { onReady: (p: Picked | null) => void; disabled?: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const camRef = useRef<HTMLInputElement>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [name, setName] = useState("photo.jpg");
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);
  const [editing, setEditing] = useState(false);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(1);
  const [rotation, setRotation] = useState(0);
  const [area, setArea] = useState<Area | null>(null);
  const [preview, setPreview] = useState<Picked | null>(null);

  const accept = useCallback(async (f: File | undefined) => {
    setError(null);
    if (!f) return;
    if (!TYPES.includes(f.type)) return setError(`“${f.name}” isn't a JPG, PNG or WebP image.`);
    if (f.size > MAX_MB * 1024 * 1024) return setError(`That photo is larger than ${MAX_MB} MB. Choose a smaller one.`);
    const url = URL.createObjectURL(f);
    try {
      const img = await load(url);
      if (Math.min(img.width, img.height) < 128) { URL.revokeObjectURL(url); return setError("That image is too small. Use a photo at least 128 px on the shorter side."); }
      setSrc(url); setName(f.name); setRotation(0); setZoom(1); setArea(null);
      const blob = await render(url, null, 0);
      const p = { blob, url: URL.createObjectURL(blob), width: img.width, height: img.height, name: f.name };
      setPreview(p); onReady(p);
    } catch { setError("We couldn't read that image. Try another photo."); }
  }, [onReady]);

  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => { const f = [...(e.clipboardData?.files ?? [])].find((x) => x.type.startsWith("image/")); if (f) accept(f); };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [accept]);

  const applyEdit = async () => {
    if (!src) return;
    const blob = await render(src, area, rotation);
    const p = { blob, url: URL.createObjectURL(blob), width: area?.width ?? 0, height: area?.height ?? 0, name };
    setPreview(p); onReady(p); setEditing(false);
  };
  const clear = () => { setSrc(null); setPreview(null); onReady(null); };

  if (preview && !editing) return (
    <div>
      <div className="relative overflow-hidden rounded-2xl border border-line bg-paper-2">
        <img src={preview.url} alt="Selected plant photo" className="mx-auto max-h-[420px] w-full object-contain" />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" size="sm" icon="crop" onClick={() => setEditing(true)} disabled={disabled}>Crop / rotate</Button>
        <Button variant="secondary" size="sm" icon="rotate" onClick={() => fileRef.current?.click()} disabled={disabled}>Replace photo</Button>
        <Button variant="ghost" size="sm" icon="x" onClick={clear} disabled={disabled}>Remove</Button>
      </div>
      <input ref={fileRef} type="file" accept={TYPES.join(",")} className="sr-only" tabIndex={-1} onChange={(e) => { accept(e.target.files?.[0]); e.target.value = ""; }} />
    </div>
  );

  if (editing && src) return (
    <div>
      <div className="relative h-[360px] overflow-hidden rounded-2xl bg-ink">
        <Cropper image={src} crop={crop} zoom={zoom} rotation={rotation} aspect={1} onCropChange={setCrop} onZoomChange={setZoom}
          onRotationChange={setRotation} onCropComplete={(_, px) => setArea(px)} objectFit="contain" />
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-ink-2">Zoom<input type="range" min={1} max={4} step={0.05} value={zoom} onChange={(e) => setZoom(+e.target.value)} className="mt-1 w-full accent-forest-800" /></label>
        <label className="text-sm text-ink-2">Rotate<input type="range" min={-180} max={180} step={1} value={rotation} onChange={(e) => setRotation(+e.target.value)} className="mt-1 w-full accent-forest-800" /></label>
      </div>
      <p className="mt-2 text-xs text-ink-3">Frame the affected leaf so it fills most of the square.</p>
      <div className="mt-3 flex gap-2"><Button onClick={applyEdit} icon="check">Apply</Button><Button variant="ghost" onClick={() => setEditing(false)}>Cancel</Button></div>
    </div>
  );

  return (
    <div>
      <div onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); accept(e.dataTransfer.files[0]); }}
        className={clsx("flex flex-col items-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition-colors",
          drag ? "border-emerald-600 bg-emerald-50" : "border-line-strong bg-white")}>
        <div className="mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-forest-50 text-forest-700"><Icon name="upload" size={24} /></div>
        <p className="font-medium">Drop a leaf or fruit photo here</p>
        <p className="mt-1 text-sm text-ink-3">JPG, PNG or WebP · up to {MAX_MB} MB · or paste with Ctrl + V</p>
        <div className="mt-5 flex flex-col gap-2 sm:flex-row">
          <Button icon="camera" onClick={() => camRef.current?.click()} disabled={disabled}>Take photo</Button>
          <Button variant="secondary" icon="upload" onClick={() => fileRef.current?.click()} disabled={disabled}>Choose file</Button>
        </div>
        <input ref={fileRef} type="file" accept={TYPES.join(",")} className="sr-only" tabIndex={-1} aria-label="Choose photo" onChange={(e) => { accept(e.target.files?.[0]); e.target.value = ""; }} />
        <input ref={camRef} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-label="Take photo with camera" onChange={(e) => { accept(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      {error && <div className="mt-3"><Notice tone="bad">{error}</Notice></div>}
      <ul className="mt-4 grid gap-2 text-sm text-ink-3 sm:grid-cols-2">
        {["One leaf or fruit filling most of the frame", "Daylight, no harsh shadow or flash", "Symptoms in sharp focus", "Plain background if possible"].map((t) => (
          <li key={t} className="flex items-center gap-2"><Icon name="check" size={16} className="text-emerald-600" />{t}</li>))}
      </ul>
    </div>
  );
}
