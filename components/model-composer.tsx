"use client";
/* eslint-disable next/no-img-element, jsx-a11y/media-has-caption -- Authenticated local artifacts have no caption tracks. */
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Progress } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { MediaLibrary, type Asset } from "@/components/media-library";
import { serviceFetch } from "@/lib/service-session";
import { DeleteMediaButton } from "@/components/delete-media-button";

type Value = string | number | boolean;
type Rule = { type: "string" | "number" | "integer" | "boolean"; title?: string; description?: string; default?: Value; enum?: Value[]; minimum?: number; maximum?: number; maxLength?: number; required?: boolean };
export type InstalledModel = { id: string; label: string; media_type: "video" | "image" | "text"; available: boolean; description: string; accepts_image: boolean; modes: string[]; parameters: Record<string, Rule> };
type Job = { id: string; status: string; status_url: string; progress: number; message?: string; media_type: InstalledModel["media_type"]; resolved_parameters: { model: string }; artifacts: { url: string; kind: string }[]; quality_control?: { passed: boolean; warnings?: string[] }; error?: { message?: string } };
const copy = {
  "zh-TW": { prompt: "提示詞", mode: "生成模式", submit: "開始生成", cancel: "取消任務", history: "此模型的產出與任務", empty: "尚無任務", download: "下載成品", review: "通過技術驗證；內容品質仍需人工檢查。", error: "操作失敗，請檢查連線後重試。", reference: "參照圖片", clear: "取消參照", pending: "處理中", retry: "重試相同請求", unavailable: "此模型目前未就緒", details: "參數由主機已安裝的模型提供；不會自動下載或更換模型。" },
  en: { prompt: "Prompt", mode: "Generation mode", submit: "Generate", cancel: "Cancel job", history: "This model’s outputs and jobs", empty: "No jobs yet", download: "Download output", review: "Technical checks passed; content still needs human review.", error: "Request failed. Check your connection and retry.", reference: "Reference image", clear: "Clear reference", pending: "Processing", retry: "Retry same request", unavailable: "Model is not ready", details: "Parameters come from an installed host adapter. Models are never downloaded or replaced automatically." },
  ja: { prompt: "プロンプト", mode: "生成モード", submit: "生成する", cancel: "タスクをキャンセル", history: "このモデルの作品とタスク", empty: "タスクはありません", download: "作品をダウンロード", review: "技術検証に合格。内容の品質は人による確認が必要です。", error: "操作に失敗しました。接続を確認して再試行してください。", reference: "参照画像", clear: "参照を解除", pending: "処理中", retry: "同じリクエストを再試行", unavailable: "モデルは未準備です", details: "設定項目はホストに導入済みのモデルが提供します。モデルの自動ダウンロードや置換は行いません。" },
};
const active = (job: Job) => ["queued", "running"].includes(job.status);

function TextArtifact({ url }: { url: string }) {
  const [text, setText] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    serviceFetch(url, { signal: abort.signal }).then(async (r) => { if (!r.ok) throw new Error(); return r.text(); })
      .then(setText).catch(() => { if (!abort.signal.aborted) setText("Preview unavailable / 無法載入預覽 / 読込失敗"); });
    return () => abort.abort();
  }, [url]);
  // Render as text, never HTML or executable model output.
  return <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words bg-[#fafaf8] p-5 text-sm">{text}</pre>;
}

export function ModelComposer({ model, locale }: { model: InstalledModel; locale: keyof typeof copy }) {
  const t = copy[locale];
  const [prompt, setPrompt] = useState("");
  const [mode, setMode] = useState(model.modes[0]);
  const [values, setValues] = useState<Record<string, Value>>(() => Object.fromEntries(Object.entries(model.parameters).filter(([, r]) => r.default !== undefined).map(([name, r]) => [name, r.default!])));
  const [reference, setReference] = useState<Asset | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const attempt = useRef<{ body: string; key: string } | null>(null);
  const deleted = useRef(new Set<string>());
  const chosen = jobs.find((job) => job.id === selected) || jobs[0];
  const busy = jobs.some(active);
  const artifact = chosen?.artifacts?.[0];

  useEffect(() => {
    const abort = new AbortController();
    let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const response = await serviceFetch("/api/v1/jobs?limit=100", { signal: abort.signal });
        if (!response.ok) throw new Error();
        const result = await response.json() as { jobs: Job[] };
        if (!abort.signal.aborted) setJobs(result.jobs.filter((job) => job.resolved_parameters.model === model.id && !deleted.current.has(job.id)));
      } catch { if (!abort.signal.aborted) setError(t.error); }
      finally { pending = false; }
    };
    void refresh();
    const timer = window.setInterval(refresh, 3000);
    return () => { abort.abort(); window.clearInterval(timer); };
  }, [model.id, t.error]);

  const submit = async () => {
    const body = JSON.stringify({ model: model.id, prompt, mode, parameters: values, ...(reference ? { image_id: reference.id } : {}) });
    if (attempt.current?.body !== body) attempt.current = { body, key: crypto.randomUUID() };
    setSending(true); setError("");
    try {
      const response = await serviceFetch("/api/v1/jobs", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": attempt.current!.key }, body });
      const result = await response.json() as Job & { error?: string };
      if (!response.ok) throw new Error(typeof result.error === "string" ? result.error : t.error);
      setJobs((current) => [result, ...current.filter((job) => job.id !== result.id)]);
      setSelected(result.id); attempt.current = null;
    } catch (issue) { setError(issue instanceof Error ? issue.message : t.error); }
    finally { setSending(false); }
  };
  const cancel = async (job: Job) => {
    try {
      const r = await serviceFetch(`${job.status_url}/cancel`, { method: "POST" });
      if (!r.ok) throw new Error();
      const result = await r.json() as Job;
      setJobs((current) => current.map((item) => item.id === result.id ? result : item));
    } catch { setError(t.error); }
  };
  const update = (name: string, value?: Value) => setValues((current) => {
    const next = { ...current }; if (value === undefined) delete next[name]; else next[name] = value; return next;
  });

  return <section className="grid gap-6 xl:grid-cols-[1.3fr_1fr]">
    <div className="space-y-6">
      <section className="border border-border bg-white p-5">
        <h2 className="mb-4 text-sm font-extrabold tracking-wider">{t.history}</h2>
        {artifact ? <div>{artifact.kind === "video" ? <video controls src={artifact.url.replace("?download=1", "")} className="max-h-[600px] w-full bg-black" /> : artifact.kind === "image" ? <img src={artifact.url.replace("?download=1", "")} alt={model.label} className="max-h-[600px] w-full object-contain" /> : <TextArtifact url={artifact.url} />}
          <p className="mt-3 text-xs text-[#11786f]">{t.review}</p>
          {chosen.quality_control?.warnings?.map((warning) => <p key={warning} className="mt-1 text-xs text-amber-800">{warning}</p>)}
          <a href={artifact.url} className="mt-4 inline-block border border-border px-4 py-2 text-xs font-bold">{t.download}</a></div>
          : <div className="grid min-h-64 place-items-center bg-[#fafaf8] text-sm text-muted-foreground">{chosen ? `${chosen.status} · ${chosen.progress}%` : t.empty}</div>}
        {chosen && active(chosen) && <div className="mt-4 space-y-3"><Progress value={chosen.progress} /><p className="text-xs">{chosen.message || t.pending}</p><Button variant="outline" onClick={() => void cancel(chosen)}>{t.cancel}</Button></div>}
        {chosen?.error?.message && <p role="alert" className="mt-3 text-xs text-red-700">{chosen.error.message}</p>}
        <div className="mt-5 max-h-56 space-y-2 overflow-auto">{jobs.map((job) => <button key={job.id} onClick={() => setSelected(job.id)} className={`block w-full border p-3 text-left text-xs ${chosen?.id === job.id ? "border-[#e85578]" : "border-border"}`}>{job.id} · {job.status}</button>)}</div>
      </section>
      {chosen && !active(chosen) && <DeleteMediaButton locale={locale} kind="jobs" id={chosen.id} name={chosen.id} onDeleted={() => { deleted.current.add(chosen.id); setJobs(current => current.filter(job => job.id !== chosen.id)); setSelected(null); attempt.current = null; }} />}
      {model.accepts_image && <MediaLibrary locale={locale} onSelect={setReference} onDelete={(id) => setReference(current => current?.id === id ? null : current)} />}
    </div>
    <form onSubmit={(event) => { event.preventDefault(); void submit(); }} className="space-y-5 self-start border border-border bg-white p-6">
      <h2 className="text-lg font-extrabold">{model.label}</h2><p className="text-xs leading-5 text-muted-foreground">{t.details}</p>
      <label className="block text-xs font-bold">{t.prompt}<Textarea required maxLength={4000} value={prompt} onChange={(e) => setPrompt(e.target.value)} className="mt-2 min-h-40 rounded-none" /></label>
      <label className="block text-xs font-bold">{t.mode}<Select value={mode} onValueChange={(value) => value && setMode(value)}><SelectTrigger className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{model.modes.map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}</SelectContent></Select></label>
      <div className="grid gap-4 sm:grid-cols-2">{Object.entries(model.parameters).map(([name, rule]) => <label key={name} className="block text-xs font-bold">{rule.title || name}{rule.required ? " *" : ""}
        {rule.type === "boolean" ? <Switch className="ml-3" checked={Boolean(values[name])} onCheckedChange={(value) => update(name, value)} /> : rule.enum ? <Select value={values[name] === undefined ? null : String(values[name])} onValueChange={(value) => update(name, rule.enum!.find((item) => String(item) === value))}><SelectTrigger className="mt-2 w-full"><SelectValue /></SelectTrigger><SelectContent>{rule.enum.map((item) => <SelectItem key={String(item)} value={String(item)}>{String(item)}</SelectItem>)}</SelectContent></Select> : <Input className="mt-2 rounded-none" required={rule.required} type={rule.type === "string" ? "text" : "number"} step={rule.type === "integer" ? 1 : "any"} min={rule.minimum} max={rule.maximum} maxLength={rule.maxLength} value={String(values[name] ?? "")} onChange={(e) => update(name, e.target.value === "" ? undefined : rule.type === "string" ? e.target.value : Number(e.target.value))} />}
        {rule.description && <span className="mt-1 block text-[10px] font-normal text-muted-foreground">{rule.description}</span>}</label>)}</div>
      {reference && <p className="text-xs">{t.reference}: {reference.name} <button type="button" className="text-[#e85578] underline" onClick={() => setReference(null)}>{t.clear}</button></p>}
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
      <Button type="submit" disabled={sending || busy || !model.available || !prompt.trim() || (mode === "i2v" && !reference)} className="h-12 w-full rounded-none">{!model.available ? t.unavailable : sending || busy ? t.pending : error ? t.retry : t.submit}</Button>
    </form>
  </section>;
}
