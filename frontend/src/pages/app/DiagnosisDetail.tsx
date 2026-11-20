import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import type { DiagnosisResult, MyPlant } from "../../lib/types";
import { Button, Card, ErrorState, Loading, Select, Textarea } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";
import ResultView from "../../components/diagnosis/ResultView";

export default function DiagnosisDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["prediction", id], queryFn: () => api<DiagnosisResult>(`/predictions/${id}`) });
  const plants = useQuery({ queryKey: ["plants"], queryFn: () => api<{ items: MyPlant[] }>("/plants") });
  const [notes, setNotes] = useState("");
  useEffect(() => { setNotes(q.data?.notes ?? ""); }, [q.data?.notes]);
  const save = useMutation({ mutationFn: (body: object) => api<DiagnosisResult>(`/predictions/${id}`, { method: "PATCH", body }),
    onSuccess: (d) => { qc.setQueryData(["prediction", id], d); qc.invalidateQueries({ queryKey: ["predictions"] }); } });
  const del = useMutation({ mutationFn: () => api(`/predictions/${id}`, { method: "DELETE" }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["predictions"] }); qc.invalidateQueries({ queryKey: ["analytics"] }); nav("/app/diagnoses"); } });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <ErrorState error={q.error} title="Diagnosis not found" />;
  const r = q.data;
  return (
    <div>
      <Link to="/app/diagnoses" className="mb-4 inline-flex items-center gap-1.5 text-sm text-ink-3 hover:text-ink"><Icon name="arrowLeft" size={16} />All diagnoses</Link>
      <ResultView r={r} />
      <Card className="mt-5 grid gap-4 p-5 md:grid-cols-[1fr_260px]">
        <div>
          <Textarea label="Notes" rows={3} maxLength={2000} placeholder="What did you do? e.g. removed infected leaves, sprayed on 12 March…" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Button className="mt-2" size="sm" variant="secondary" onClick={() => save.mutate({ notes })} loading={save.isPending} disabled={notes === (r.notes ?? "")}>Save notes</Button>
        </div>
        <div>
          <Select label="Plant" value={r.plant_id ?? ""} onChange={(e) => save.mutate({ plant_id: e.target.value ? Number(e.target.value) : null })}>
            <option value="">— not linked —</option>{plants.data?.items.map((p) => <option key={p.id} value={p.id}>{p.nickname}</option>)}
          </Select>
          <Button className="mt-4" variant="danger" size="sm" icon="trash" loading={del.isPending}
            onClick={() => { if (window.confirm("Delete this diagnosis and its photo permanently?")) del.mutate(); }}>Delete diagnosis</Button>
        </div>
      </Card>
    </div>
  );
}
