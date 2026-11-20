import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { KIND_LABEL } from "../../lib/format";
import type { PlantInfo } from "../../lib/types";
import { Badge, Card, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from "../../components/ui/ui";

interface D { label: string; name: string; crop: string; crop_key: string; kind: string; pathogen: string; symptoms: string; in_model: boolean }

export default function Knowledge() {
  const base = useLocation().pathname.startsWith("/app") ? "/app/knowledge" : "/knowledge";
  const [q, setQ] = useState(""); const [dq, setDq] = useState(""); const [crop, setCrop] = useState(""); const [kind, setKind] = useState("");
  useEffect(() => { const t = setTimeout(() => setDq(q), 200); return () => clearTimeout(t); }, [q]);
  const crops = useQuery({ queryKey: ["crops"], queryFn: () => api<{ items: PlantInfo[] }>("/crops") });
  const params = new URLSearchParams({ ...(dq && { q: dq }), ...(crop && { crop }), ...(kind && { kind }) });
  const list = useQuery({ queryKey: ["diseases", params.toString()], queryFn: () => api<{ items: D[]; total: number; kinds: string[] }>(`/diseases?${params}`) });
  return (
    <div className={base === "/knowledge" ? "mx-auto max-w-page px-5 py-10" : ""}>
      <PageHeader eyebrow="Knowledge Center" title="Plant disease library" sub="Curated from university extension services and international research centres. Every entry lists its references." />
      <Card className="mb-5 grid gap-3 p-4 sm:grid-cols-[1fr_200px_220px]">
        <Input label="Search" placeholder="Symptom, disease or pathogen — e.g. yellow stripes" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Crop" value={crop} onChange={(e) => setCrop(e.target.value)}><option value="">All crops</option>{crops.data?.items.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}</Select>
        <Select label="Type" value={kind} onChange={(e) => setKind(e.target.value)}><option value="">All types</option>{list.data?.kinds.map((k) => <option key={k} value={k}>{KIND_LABEL[k] ?? k}</option>)}</Select>
      </Card>
      {list.isLoading ? <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 9 }).map((_, i) => <Skeleton key={i} className="h-36" />)}</div> :
        list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> :
        !list.data?.items.length ? <Card><EmptyState icon="search" title="Nothing found">Try a different word or clear the filters.</EmptyState></Card> :
        <>
          <p className="mb-2 text-sm text-ink-3">{list.data.total} entries</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {list.data.items.map((d) => (
              <Link key={d.label} to={`${base}/${encodeURIComponent(d.label)}`} className="group rounded-2xl focus-ring">
                <Card className="h-full p-4 transition-shadow group-hover:shadow-lift">
                  <div className="flex items-start justify-between gap-2"><p className="font-semibold group-hover:text-forest-700">{d.name}</p><Badge>{d.crop}</Badge></div>
                  <p className="mt-0.5 truncate text-xs italic text-ink-3">{d.pathogen}</p>
                  <p className="mt-2 line-clamp-3 text-sm text-ink-2">{d.symptoms}</p>
                  <div className="mt-3 flex gap-1.5"><Badge tone="brand">{KIND_LABEL[d.kind] ?? d.kind}</Badge>{d.in_model && <Badge tone="ok">Detectable from photo</Badge>}</div>
                </Card>
              </Link>))}
          </div>
        </>}
    </div>
  );
}
