import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { api } from "../../lib/api";
import type { PlantInfo } from "../../lib/types";
import { Badge } from "../ui/ui";
import { Icon } from "../ui/icons";

export interface PickedPlant { key: string; name: string; scientific: string; supported: boolean }

/** Accessible combobox: type a plant name in English, Urdu or Roman Urdu ("tamatar", "کینو"). */
export default function PlantPicker({ value, onChange, autoFocus }: { value: PickedPlant | null; onChange: (p: PickedPlant | null) => void; autoFocus?: boolean }) {
  const [text, setText] = useState(value?.name ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [debounced, setDebounced] = useState(text);
  const id = useId();
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { const t = setTimeout(() => setDebounced(text.trim()), 180); return () => clearTimeout(t); }, [text]);
  const q = useQuery({
    queryKey: ["resolve", debounced],
    queryFn: () => api<{ items: (PlantInfo & { supported: boolean })[] }>(`/crops/resolve?q=${encodeURIComponent(debounced)}`),
    enabled: debounced.length >= 2 && debounced !== value?.name,
  });
  const items = q.data?.items ?? [];
  const pick = (p: PlantInfo & { supported: boolean }) => {
    onChange({ key: p.key, name: p.name, scientific: p.scientific, supported: p.supported });
    setText(p.name); setOpen(false);
  };
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink-2">Plant name</label>
      <div className="relative">
        <Icon name="search" size={18} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-4" />
        <input ref={ref} id={id} role="combobox" aria-expanded={open && items.length > 0} aria-controls={`${id}-list`} aria-autocomplete="list"
          aria-activedescendant={open && items[active] ? `${id}-o${active}` : undefined} autoFocus={autoFocus} autoComplete="off"
          placeholder="e.g. tomato, gandum, kinnow, آلو" value={text}
          onChange={(e) => { setText(e.target.value); setOpen(true); setActive(0); if (value) onChange(null); }}
          onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, items.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter" && items[active]) { e.preventDefault(); pick(items[active]); }
            if (e.key === "Escape") setOpen(false);
          }}
          className="h-12 w-full rounded-xl border border-line-strong bg-white pl-10 pr-10 text-[15px] focus-ring" />
        {value && <Icon name="check" size={18} className="absolute right-3.5 top-1/2 -translate-y-1/2 text-emerald-600" />}
      </div>
      {open && items.length > 0 && (
        <ul id={`${id}-list`} role="listbox" className="absolute z-20 mt-1.5 w-full overflow-hidden rounded-xl border border-line bg-white py-1 shadow-lift">
          {items.map((p, i) => (
            <li key={p.key} id={`${id}-o${i}`} role="option" aria-selected={i === active}
              onMouseDown={(e) => { e.preventDefault(); pick(p); }} onMouseEnter={() => setActive(i)}
              className={clsx("flex cursor-pointer items-center justify-between gap-3 px-3.5 py-2.5", i === active && "bg-paper-2")}>
              <div className="min-w-0">
                <p className="text-sm font-medium">{p.name}</p>
                <p className="truncate text-xs italic text-ink-3">{p.scientific}</p>
              </div>
              {p.supported ? <Badge tone="ok">Supported</Badge> : <Badge>Info only</Badge>}
            </li>
          ))}
        </ul>
      )}
      {open && debounced.length >= 2 && !q.isFetching && q.isSuccess && !items.length && (
        <p className="mt-2 text-sm text-ink-3">No match for “{debounced}”. You can still upload a photo and let the model identify the plant.</p>
      )}
      {value && !value.supported && (
        <p className="mt-2 text-sm text-warn-700">{value.name} is in the library but the image model can't diagnose it yet.</p>
      )}
    </div>
  );
}
