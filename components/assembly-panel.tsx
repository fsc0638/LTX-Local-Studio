'use client';

import { useEffect, useState } from 'react';
import { assembleProject, projectAssembly, type AssemblyView } from '@/lib/factory-client';
import { assemblyFileName, assemblyReadiness } from '@/lib/assembly';
import type { FactoryPlan } from '@/lib/production-factory';

export type AssemblyLocale = 'zh-TW' | 'en' | 'ja';

export const assemblyCopy = {
  'zh-TW': {
    title: '組片',
    note: '只取每鏡在 04 審片採用的 take，依鏡頭順序接成一支，原曲從 Bible 設定的起點連續鋪底。',
    empty: '還沒有鏡頭。',
    missing: '還有 {n} 鏡沒有採用的 take，組片先停用：',
    ready: '{n} 鏡全部有採用的 take。',
    cut: '組片',
    cutting: '組片中…',
    done: '完成：{frames} 幀、{seconds} 秒',
    failed: '組片失敗：{error}',
    downloadMp4: '下載 MP4',
    downloadManifest: '下載 shot manifest／EDL（JSON）',
    manifestNote: 'manifest 可從 00 企劃匯入還原每鏡完整 request；edl 記每鏡的 take、seed、參照指紋、模型版本、裁決。',
    goReview: '到 04 審片採用 take',
  },
  en: {
    title: 'Assembly',
    note: 'Takes exactly the take accepted in 04 Review for each shot, joins them in shot order, and lays the song underneath from the start set in the Bible.',
    empty: 'No shots yet.',
    missing: '{n} shots have no accepted take, so the cut is disabled:',
    ready: 'All {n} shots have an accepted take.',
    cut: 'Assemble',
    cutting: 'Assembling\u2026',
    done: 'Done: {frames} frames, {seconds} s',
    failed: 'Assembly failed: {error}',
    downloadMp4: 'Download MP4',
    downloadManifest: 'Download shot manifest / EDL (JSON)',
    manifestNote: 'The manifest imports in 00 Bible and restores every shot\u2019s full request; edl records each shot\u2019s take, seed, reference fingerprints, model version and verdict.',
    goReview: 'Accept takes in 04 Review',
  },
  ja: {
    title: '組み立て',
    note: '各ショットで 04 レビューが採用したテイクだけを、ショット順につなぎ、Bible の開始位置から原曲を連続で敷きます。',
    empty: 'ショットがありません。',
    missing: '採用テイクのないショットが {n} あるため、組み立ては無効です：',
    ready: '{n} ショットすべてに採用テイクがあります。',
    cut: '組み立て',
    cutting: '組み立て中…',
    done: '完了：{frames} フレーム、{seconds} 秒',
    failed: '組み立て失敗：{error}',
    downloadMp4: 'MP4 をダウンロード',
    downloadManifest: 'ショットマニフェスト／EDL（JSON）をダウンロード',
    manifestNote: 'マニフェストは 00 企画で取り込んで各ショットの完全なリクエストを復元できます。edl には各ショットのテイク、seed、参照フィンガープリント、モデル版、判定が記録されます。',
    goReview: '04 レビューでテイクを採用',
  },
} as const;
type Text = (typeof assemblyCopy)[AssemblyLocale];

const fill = (template: string, values: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));

export function AssemblyPanel({ plan, locale, onGoReview }: {
  plan: FactoryPlan | null;
  locale: AssemblyLocale;
  onGoReview?: () => void;
}) {
  const text: Text = assemblyCopy[locale];
  const [view, setView] = useState<AssemblyView | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const readiness = assemblyReadiness(plan);
  const running = view?.assembly.status === 'running';

  const planId = plan?.id;
  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    const load = () => projectAssembly(planId).then((next) => { if (!cancelled) setView(next); }).catch(() => undefined);
    void load();
    const timer = running ? window.setInterval(() => void load(), 3000) : undefined;
    return () => { cancelled = true; if (timer) window.clearInterval(timer); };
  }, [planId, plan?.updatedAt, running]);

  if (!plan || !plan.shots.length) {
    return <section className="mb-6 rounded-md border border-border bg-white p-4 text-[12px] text-muted-foreground">{text.empty}</section>;
  }

  const cut = async () => {
    setBusy(true);
    setNotice('');
    try {
      await assembleProject(plan.id);
      setView(await projectAssembly(plan.id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  };
  const downloadManifest = () => {
    if (!view?.manifest) return;
    const blob = new Blob([JSON.stringify(view.manifest, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = assemblyFileName(plan.title, 'json');
    link.click();
    URL.revokeObjectURL(url);
  };
  const state = view?.assembly ?? {};
  return (
    <section className="mb-6 flex flex-col gap-3 rounded-md border border-border bg-white p-4 text-[12px]">
      <div>
        <h2 className="text-[13px] font-bold">{text.title}</h2>
        <p className="mt-1 text-[11px] text-muted-foreground">{text.note}</p>
      </div>
      {readiness.ready ? (
        <p className="text-[11px] text-[#1f6b48]">{fill(text.ready, { n: readiness.total })}</p>
      ) : (
        <div className="text-[11px] text-[#a8365a]">
          <p>{fill(text.missing, { n: readiness.missing.length })}</p>
          <ul className="mt-1 list-disc pl-5">
            {readiness.missing.map((m) => <li key={m.id}>{String(m.index + 1).padStart(2, '0')} {m.title}</li>)}
          </ul>
          {onGoReview ? <button type="button" onClick={onGoReview} className="mt-2 rounded-sm border border-border px-2 py-1 text-[11px] hover:bg-[#faf9f7]">{text.goReview}</button> : null}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" disabled={!readiness.ready || busy || running} onClick={() => void cut()} className="rounded-sm bg-foreground px-3 py-1.5 text-[11px] font-bold text-white disabled:opacity-40">
          {running ? text.cutting : text.cut}
        </button>
        {state.status === 'done' ? <span className="font-mono text-[11px] tabular-nums text-[#1f6b48]">{fill(text.done, { frames: state.frames ?? 0, seconds: state.seconds ?? 0 })}</span> : null}
        {state.status === 'failed' ? <span className="text-[11px] text-[#e85578]">{fill(text.failed, { error: state.error ?? '' })}</span> : null}
        {notice ? <span className="text-[11px] text-[#e85578]">{notice}</span> : null}
      </div>
      {state.status === 'done' && state.output_url ? (
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_260px]">
          <video className="aspect-video w-full rounded-sm bg-black" controls preload="metadata" poster={state.poster_url} src={state.output_url} />
          <div className="flex flex-col gap-2">
            <a href={`${state.output_url}?download=1`} download={assemblyFileName(plan.title, 'mp4')} className="rounded-sm border border-border px-3 py-1.5 text-center text-[11px] font-bold hover:bg-[#faf9f7]">{text.downloadMp4}</a>
            <button type="button" disabled={!view?.manifest} onClick={downloadManifest} className="rounded-sm border border-border px-3 py-1.5 text-[11px] font-bold hover:bg-[#faf9f7] disabled:opacity-40">{text.downloadManifest}</button>
            <p className="text-[10px] text-muted-foreground">{text.manifestNote}</p>
          </div>
        </div>
      ) : null}
    </section>
  );
}
