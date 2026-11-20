import { Link, useLocation, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { KIND_LABEL } from "../../lib/format";
import type { KBEntry } from "../../lib/types";
import { Badge, ButtonLink, Card, ErrorState, Loading } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";
import { ProductsPanel, References, TreatmentPlan } from "../../components/diagnosis/ResultView";

export default function DiseasePage() {
  const { label = "" } = useParams();
  const { user } = useAuth();
  const inApp = useLocation().pathname.startsWith("/app");
  const q = useQuery({ queryKey: ["disease", label], queryFn: () => api<KBEntry>(`/diseases/${encodeURIComponent(label)}`) });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorState error={q.error} title="Entry not found" />;
  const k = q.data;
  return (
    <div className={inApp ? "" : "mx-auto max-w-4xl px-5 py-10"}>
      <Link to={inApp ? "/app/knowledge" : "/knowledge"} className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink"><Icon name="arrowLeft" size={16} />Disease library</Link>
      <div className="flex flex-wrap items-center gap-2"><Badge>{k.crop}</Badge><Badge tone="brand">{KIND_LABEL[k.kind] ?? k.kind}</Badge>{k.in_model && <Badge tone="ok">Detectable from photo</Badge>}</div>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight">{k.name}</h1>
      <p className="mt-1 italic text-ink-3">{k.pathogen}</p>
      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        <Card className="p-5 lg:col-span-2">
          <h2 className="font-semibold">Symptoms</h2><p className="mt-1.5 text-[15px] text-ink-2">{k.symptoms}</p>
          {k.affected_parts.length > 0 && <p className="mt-3 text-sm"><span className="text-ink-3">Affected parts: </span>{k.affected_parts.join(", ")}</p>}
          <h2 className="mt-5 font-semibold">Causes</h2><p className="mt-1.5 text-[15px] text-ink-2">{k.causes}</p>
          <h2 className="mt-5 font-semibold">Favourable conditions</h2><p className="mt-1.5 text-[15px] text-ink-2">{k.conditions}</p>
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold">Seeing this?</h2>
          <p className="mt-1.5 text-sm text-ink-3">Confirm with a photo diagnosis before treating — several diseases look alike.</p>
          <ButtonLink to={user ? "/app/diagnose" : "/try"} icon="camera" className="mt-4 w-full">Diagnose a photo</ButtonLink>
        </Card>
      </div>
      <Card className="mt-5 p-5"><h2 className="mb-3 text-lg font-semibold">Treatment and prevention</h2><TreatmentPlan k={k} /></Card>
      {k.treatment.chemical.length > 0 && <Card className="mt-5 p-5"><h2 className="mb-3 text-lg font-semibold">Products in Pakistan</h2><ProductsPanel label={k.label} /></Card>}
      <Card className="mt-5 p-5"><h2 className="mb-3 text-lg font-semibold">References</h2><References k={k} /></Card>
    </div>
  );
}
