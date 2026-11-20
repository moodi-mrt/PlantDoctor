import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "../../lib/api";
import { ago } from "../../lib/format";
import type { MyPlant, PlantInfo } from "../../lib/types";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Notice, PageHeader, Select, Skeleton } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";

export default function Plants() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["plants"], queryFn: () => api<{ items: MyPlant[] }>("/plants") });
  const crops = useQuery({ queryKey: ["crops"], queryFn: () => api<{ items: PlantInfo[] }>("/crops") });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ nickname: "", crop_key: "", location: "" });
  const create = useMutation({
    mutationFn: () => api("/plants", { body: { ...f, crop_key: f.crop_key || null, location: f.location || null } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["plants"] }); setOpen(false); setF({ nickname: "", crop_key: "", location: "" }); },
  });
  const del = useMutation({ mutationFn: (id: number) => api(`/plants/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["plants"] }) });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  return (
    <div>
      <PageHeader title="My plants" sub="Track individual plants, fields or orchard blocks and see their health over time." action={<Button icon="plus" onClick={() => setOpen(true)}>Add plant</Button>} />
      {open && (
        <Card className="mb-5 p-5">
          <form onSubmit={submit} className="grid gap-4 sm:grid-cols-3">
            <Input label="Name" placeholder="e.g. North field wheat" required value={f.nickname} onChange={(e) => setF({ ...f, nickname: e.target.value })} />
            <Select label="Crop" value={f.crop_key} onChange={(e) => setF({ ...f, crop_key: e.target.value })}>
              <option value="">Choose…</option>{crops.data?.items.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
            </Select>
            <Input label="Location (optional)" placeholder="e.g. Sargodha" value={f.location} onChange={(e) => setF({ ...f, location: e.target.value })} />
            {create.error && <div className="sm:col-span-3"><Notice tone="bad">{(create.error as ApiError).message}</Notice></div>}
            <div className="flex gap-2 sm:col-span-3"><Button type="submit" loading={create.isPending}>Save</Button><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
          </form>
        </Card>)}
      {list.isLoading ? <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40" />)}</div> :
        list.error ? <ErrorState error={list.error} onRetry={() => list.refetch()} /> :
        !list.data?.items.length ? <Card><EmptyState icon="sprout" title="No plants yet" action={<Button icon="plus" onClick={() => setOpen(true)}>Add your first plant</Button>}>Add the plants or fields you look after, then link diagnoses to them to see trends.</EmptyState></Card> :
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {list.data.items.map((p) => (
            <Card key={p.id} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0"><h3 className="truncate font-semibold">{p.nickname}</h3><p className="text-sm text-ink-3">{p.crop ?? "Crop not set"}{p.scientific && <span className="italic"> · {p.scientific}</span>}</p></div>
                {p.last_status ? (p.last_healthy ? <Badge tone="ok">Healthy</Badge> : p.last_condition ? <Badge tone="warn">{p.last_condition}</Badge> : <Badge>Unclear</Badge>) : <Badge>Not checked</Badge>}
              </div>
              {p.location && <p className="mt-2 flex items-center gap-1 text-sm text-ink-3"><Icon name="home" size={14} />{p.location}</p>}
              <p className="mt-3 text-sm text-ink-2">{p.diagnosis_count} diagnos{p.diagnosis_count === 1 ? "is" : "es"}{p.last_checked && ` · last ${ago(p.last_checked)}`}</p>
              <div className="mt-auto flex gap-2 pt-4">
                <Link to={`/app/diagnoses?plant=${p.id}`} className="text-sm font-medium text-forest-700 hover:underline">History</Link>
                <button className="ml-auto text-sm text-ink-3 hover:text-bad-700" onClick={() => { if (confirm(`Remove “${p.nickname}”? Its diagnoses are kept.`)) del.mutate(p.id); }}>Remove</button>
              </div>
            </Card>))}
        </div>}
    </div>
  );
}
