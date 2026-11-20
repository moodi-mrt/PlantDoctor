import { useState } from "react";
import { Link } from "react-router-dom";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { dateTime, pct } from "../../lib/format";
import type { DiagnosisSummary, Page, PlantInfo, Status } from "../../lib/types";
import { Badge, Button, ButtonLink, Card, EmptyState, ErrorState, Input, PageHeader, Select, Skeleton } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";

export function StatusBadge({ s, healthy }: { s: Status; healthy?: boolean }) {
  if (s === "confident") return healthy ? <Badge tone="ok">Healthy</Badge> : <Badge tone="brand">Confident</Badge>;
  if (s === "tentative") return <Badge tone="warn">Verify</Badge>;
  return <Badge tone="neutral">{{ uncertain: "Inconclusive", needs_input: "Plant unclear", unknown: "Not recognised", no_leaf: "No plant", unsupported_crop: "Unsupported" }[s] ?? s}</Badge>;
}

export default function History() {
  const [q, setQ] = useState(""); const [crop, setCrop] = useState(""); const [status, setStatus] = useState("");
  const params = new URLSearchParams({ limit: "20", ...(q && { q }), ...(crop && { crop }), ...(status && { status }) });
  const crops = useQuery({ queryKey: ["crops"], queryFn: () => api<{ items: PlantInfo[] }>("/crops") });
  const list = useInfiniteQuery({
    queryKey: ["predictions", "list", params.toString()],
    queryFn: ({ pageParam }) => api<Page<DiagnosisSummary>>(`/predictions?${params}${pageParam ? `&cursor=${pageParam}` : ""}`),
    initialPageParam: 0 as number, getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];
  const total = list.data?.pages[0]?.total;
  return (
    <div>
      <PageHeader title="History & reports" sub="Every saved diagnosis, with its photo, result and model version."
        action={<a href={`/api/v1/predictions/export.csv?${params}`} className="inline-flex h-10 items-center gap-2 rounded-xl border border-line-strong bg-white px-4 text-sm font-medium shadow-card hover:bg-paper-2 focus-ring"><Icon name="download" size={18} />Export CSV</a>} />
      <Card className="mb-5 grid gap-3 p-4 sm:grid-cols-[1fr_200px_200px]">
        <Input label="Search" placeholder="Disease, crop or note" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select label="Crop" value={crop} onChange={(e) => setCrop(e.target.value)}>
          <option value="">All crops</option>{crops.data?.items.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
        </Select>
        <Select label="Result" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All results</option><option value="confident">Confident</option><option value="tentative">Needs verification</option>
          <option value="uncertain,needs_input,unknown,no_leaf,unsupported_crop">Unclear / no result</option>
        </Select>
      </Card>
      {list.isLoading ? <div className="space-y-2">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div> :
        list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> :
        !items.length ? <Card><EmptyState icon="history" title={q || crop || status ? "No matching diagnoses" : "No diagnoses yet"}
          action={!(q || crop || status) && <ButtonLink to="/app/diagnose" icon="camera">Diagnose a plant</ButtonLink>}>
          {q || crop || status ? "Try different filters." : "Saved results will appear here."}</EmptyState></Card> :
        <>
          <p className="mb-2 text-sm text-ink-3">{total} diagnos{total === 1 ? "is" : "es"}</p>
          <Card as="ul" className="divide-y divide-line">
            {items.map((d) => (
              <li key={d.id}><Link to={`/app/diagnoses/${d.id}`} className="flex items-center gap-4 px-4 py-3 hover:bg-paper-2 focus-ring">
                {d.thumbnail_url ? <img src={d.thumbnail_url} alt="" className="h-14 w-14 rounded-xl object-cover" loading="lazy" /> : <span className="h-14 w-14 rounded-xl bg-paper-3" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{d.name ?? "No diagnosis"}</p>
                  <p className="text-sm text-ink-3">{d.crop ?? "Unknown plant"} · {dateTime(d.created_at)}</p>
                </div>
                <div className="hidden text-right sm:block"><p className="text-sm tabular-nums">{d.name ? pct(d.confidence) : "—"}</p><p className="text-2xs text-ink-4">{d.model_version}</p></div>
                <StatusBadge s={d.status} healthy={d.healthy} />
              </Link></li>))}
          </Card>
          {list.hasNextPage && <div className="mt-4 text-center"><Button variant="secondary" onClick={() => list.fetchNextPage()} loading={list.isFetchingNextPage}>Load more</Button></div>}
        </>}
    </div>
  );
}
