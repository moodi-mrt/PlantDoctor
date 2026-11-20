import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import { api, ApiError } from "../../lib/api";
import type { ChatReply, Citation, DiagnosisResult } from "../../lib/types";
import { Badge, Button, Card, Notice, PageHeader, Spinner } from "../../components/ui/ui";
import { Icon } from "../../components/ui/icons";

type Msg = { role: "user" | "assistant"; content: string; citations?: Citation[]; mode?: string; label?: string; needs_expert?: boolean; reason?: string };

/** Minimal, safe markdown: **bold**, bullet / numbered lists, paragraphs, [doc-id] citations. Text only — no HTML injection. */
function Md({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  const inline = (s: string) => s.split(/(\*\*[^*]+\*\*|\[[A-Za-z_:,() .-]+___[^\]]+\]|\[plant:[a-z_]+\])/g).map((p, i) =>
    p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> :
    p.startsWith("[") && p.endsWith("]") ? <sup key={i} className="text-forest-700">[ref]</sup> : <span key={i}>{p}</span>);
  return <div className="prose-answer text-[15px] leading-relaxed">{blocks.map((b, i) => {
    const lines = b.split("\n");
    if (lines.every((l) => /^\s*[-*•]\s/.test(l))) return <ul key={i}>{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*[-*•]\s/, ""))}</li>)}</ul>;
    if (lines.every((l) => /^\s*\d+[.)]\s/.test(l))) return <ol key={i}>{lines.map((l, j) => <li key={j}>{inline(l.replace(/^\s*\d+[.)]\s/, ""))}</li>)}</ol>;
    return <p key={i}>{lines.map((l, j) => <span key={j}>{inline(l)}{j < lines.length - 1 && <br />}</span>)}</p>;
  })}</div>;
}

const SUGGEST = ["How do I stop late blight spreading to my other tomatoes?", "What are the first signs of yellow rust in wheat?", "How should I water citrus trees in summer?", "گندم کی کنگی سے کیسے بچا جائے؟"];

export default function Assistant() {
  const [sp] = useSearchParams();
  const diagnosisId = sp.get("diagnosis");
  const qc = useQueryClient();
  const [conv, setConv] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [lang, setLang] = useState<"en" | "ur">("en");
  const end = useRef<HTMLDivElement>(null);
  const diag = useQuery({ queryKey: ["prediction", diagnosisId], queryFn: () => api<DiagnosisResult>(`/predictions/${diagnosisId}`), enabled: !!diagnosisId });
  const convs = useQuery({ queryKey: ["conversations"], queryFn: () => api<{ items: { id: number; title: string; created_at: string }[] }>("/assistant/conversations") });
  const send = useMutation({
    mutationFn: (message: string) => api<ChatReply>("/assistant/chat", { body: { message, conversation_id: conv, diagnosis_id: conv ? undefined : diagnosisId ? Number(diagnosisId) : undefined, language: lang } }),
    onSuccess: (r) => { setConv(r.conversation_id); setMsgs((m) => [...m, { role: "assistant", content: r.answer, citations: r.citations, mode: r.mode, label: r.label, needs_expert: r.needs_expert, reason: r.reason }]); qc.invalidateQueries({ queryKey: ["conversations"] }); },
  });
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs, send.isPending]);
  const submit = (e?: FormEvent, t?: string) => {
    e?.preventDefault();
    const m = (t ?? text).trim(); if (!m || send.isPending) return;
    setMsgs((x) => [...x, { role: "user", content: m }]); setText(""); send.mutate(m);
  };
  const open = async (id: number) => {
    const c = await api<{ messages: Msg[] }>(`/assistant/conversations/${id}`); setConv(id); setMsgs(c.messages);
  };
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_260px]">
      <div className="flex min-h-[70vh] flex-col">
        <PageHeader title="Agricultural assistant" sub="Answers come from the PlantDoctor knowledge base and cite it. No pesticide doses — always follow the product label." />
        {diag.data?.diagnosis && !conv && <div className="mb-4"><Notice tone="info" title={`Discussing: ${diag.data.diagnosis.name} on ${diag.data.plant?.info?.name ?? "your plant"}`}>Model confidence {Math.round(diag.data.diagnosis.confidence * 100)}% ({diag.data.status}).</Notice></div>}
        <Card className="flex flex-1 flex-col">
          <div className="flex-1 space-y-5 overflow-y-auto p-5" aria-live="polite">
            {!msgs.length && <div className="py-6 text-center">
              <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-forest-50 text-forest-700"><Icon name="chat" size={24} /></div>
              <p className="font-medium">Ask about symptoms, prevention or treatment</p>
              <div className="mx-auto mt-4 flex max-w-xl flex-wrap justify-center gap-2">{SUGGEST.map((s) => <button key={s} onClick={() => submit(undefined, s)} className="rounded-full border border-line-strong bg-white px-3 py-1.5 text-sm text-ink-2 hover:bg-paper-2 focus-ring">{s}</button>)}</div>
            </div>}
            {msgs.map((m, i) => (
              <div key={i} className={clsx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
                <div className={clsx("max-w-[85%] rounded-2xl px-4 py-3", m.role === "user" ? "bg-forest-800 text-white" : "border border-line bg-paper")} dir="auto">
                  {m.role === "user" ? <p className="whitespace-pre-wrap text-[15px]">{m.content}</p> : <>
                    {m.label && <Badge tone={m.mode === "ai" ? "info" : "neutral"} className="mb-2">{m.label}</Badge>}
                    <Md text={m.content} />
                    {m.reason && m.mode !== "ai" && <p className="mt-2 text-xs text-ink-4">{m.reason}</p>}
                    {m.needs_expert && <p className="mt-2 flex items-center gap-1.5 text-sm text-warn-700"><Icon name="users" size={15} />Consider confirming with your Agriculture Extension office.</p>}
                    {!!m.citations?.length && <div className="mt-3 border-t border-line pt-2">
                      <p className="text-2xs font-semibold uppercase tracking-wider text-ink-4">Sources</p>
                      <ul className="mt-1 space-y-1 text-sm">{m.citations.map((c) => <li key={c.doc_id}>
                        {c.link ? <Link to={c.link} className="text-forest-700 hover:underline">{c.title}</Link> : c.title}
                        {c.references[0] && <> · <a href={c.references[0].url} target="_blank" rel="noopener noreferrer" className="text-ink-3 hover:underline">{c.references[0].publisher}</a></>}
                      </li>)}</ul></div>}
                  </>}
                </div>
              </div>))}
            {send.isPending && <div className="flex items-center gap-2 text-sm text-ink-3" role="status"><Spinner size={16} />Looking it up…</div>}
            {send.error && <Notice tone="bad">{(send.error as ApiError).message}</Notice>}
            <div ref={end} />
          </div>
          <form onSubmit={submit} className="flex items-end gap-2 border-t border-line p-3">
            <label htmlFor="msg" className="sr-only">Your question</label>
            <textarea id="msg" rows={1} dir="auto" value={text} onChange={(e) => setText(e.target.value)} maxLength={2000}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }}
              placeholder="Ask a question…" className="max-h-40 min-h-[44px] flex-1 resize-none rounded-xl border border-line-strong px-3.5 py-2.5 text-[15px] focus-ring" />
            <select aria-label="Answer language" value={lang} onChange={(e) => setLang(e.target.value as "en" | "ur")} className="h-11 rounded-xl border border-line-strong bg-white px-2 text-sm"><option value="en">EN</option><option value="ur">اردو</option></select>
            <Button type="submit" icon="send" disabled={!text.trim()} loading={send.isPending} aria-label="Send">Send</Button>
          </form>
        </Card>
      </div>
      <aside className="hidden lg:block">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Conversations</h2><Button size="sm" variant="ghost" icon="plus" onClick={() => { setConv(null); setMsgs([]); }}>New</Button></div>
        <ul className="space-y-1">{convs.data?.items.map((c) => <li key={c.id}><button onClick={() => open(c.id)} className={clsx("w-full truncate rounded-lg px-3 py-2 text-left text-sm focus-ring", conv === c.id ? "bg-forest-50 text-forest-800" : "text-ink-2 hover:bg-paper-2")}>{c.title}</button></li>)}</ul>
      </aside>
    </div>
  );
}
