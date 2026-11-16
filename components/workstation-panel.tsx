'use client';

import { useEffect, useState } from 'react';
import {
  projectBudget,
  updateProject,
  workstation,
  type BudgetView,
  type Station,
  type WorkstationView,
} from '@/lib/factory-client';
import type { FactoryPlan } from '@/lib/production-factory';

export type WorkstationLocale = 'zh-TW' | 'en' | 'ja';

export const workstationCopy = {
  'zh-TW': {
    title: '工站',
    gpu: 'GPU 現在給誰',
    station: { ltx: 'LTX 拍攝', imagegen: '影像模型（關鍵格）', none: '無（後製／閒置）' },
    idle: '閒置，沒有模型常駐',
    resident: '常駐：{models}',
    queue: '佇列（依工站）',
    current: '正在跑',
    nothing: '沒有 job 在跑。',
    switchCost: '切到影像模型要付一次載入約 {s} 秒；排程器會先把同工站的排完再交棒。',
    drain: '目前工站排完還要約 {s} 秒，之後才可能切換。',
    budgetTitle: 'LP 預算（這個專案）',
    estimate: '剩餘 {n}／{total} 鏡預估 {s} 秒（生成 {g} s ＋ 切換 {sw} 次 × 載入 {ss} s）',
    actual: '已花：GPU {s} 秒、OpenAI {t} tokens',
    assumed: '以下模型還沒有實測平均，用的是文件裡的預設值：{models}',
    measured: '滾動平均（最近 20 個 job）：{models}',
    budgetGpu: 'GPU 秒數上限',
    budgetTokens: 'OpenAI tokens 上限',
    save: '儲存預算',
    saved: '已儲存',
    over: '超過預算（{kind}）：預估 {estimate}，上限 {limit}。只是警告，不會擋。',
    noPlan: '選一個專案後這裡會顯示它的預算。',
    loadFailed: '讀不到工站狀態。',
  },
  en: {
    title: 'Workstation',
    gpu: 'Who has the GPU',
    station: { ltx: 'LTX shoot', imagegen: 'Image model (keyframes)', none: 'None (post / idle)' },
    idle: 'Idle, no model resident',
    resident: 'Resident: {models}',
    queue: 'Queue by station',
    current: 'Running now',
    nothing: 'No job is running.',
    switchCost: 'Switching to the image model costs one load of about {s} s; the scheduler drains the current station before handing over.',
    drain: 'About {s} s of work remain for the current station before a switch can happen.',
    budgetTitle: 'Line-producer budget (this project)',
    estimate: '{n} of {total} shots remaining, about {s} s ({g} s generating + {sw} switches \u00d7 {ss} s load)',
    actual: 'Spent so far: GPU {s} s, OpenAI {t} tokens',
    assumed: 'No measured average yet for: {models} - documented defaults used',
    measured: 'Rolling averages (last 20 jobs): {models}',
    budgetGpu: 'GPU seconds ceiling',
    budgetTokens: 'OpenAI tokens ceiling',
    save: 'Save budget',
    saved: 'Saved',
    over: 'Over budget ({kind}): estimate {estimate}, ceiling {limit}. A warning, not a stop.',
    noPlan: 'Pick a project and its budget appears here.',
    loadFailed: 'Could not read the workstation state.',
  },
  ja: {
    title: 'ワークステーション',
    gpu: 'GPU を使っているのは',
    station: { ltx: 'LTX 撮影', imagegen: '画像モデル（キーフレーム）', none: 'なし（ポスト／アイドル）' },
    idle: 'アイドル。常駐モデルなし',
    resident: '常駐：{models}',
    queue: 'ステーション別キュー',
    current: '実行中',
    nothing: '実行中のジョブはありません。',
    switchCost: '画像モデルへの切替はロード約 {s} 秒。スケジューラは同じステーションを消化してから引き継ぎます。',
    drain: '現在のステーションの残り作業は約 {s} 秒。その後に切替が起こり得ます。',
    budgetTitle: 'LP 予算（このプロジェクト）',
    estimate: '残り {n}／{total} ショット、約 {s} 秒（生成 {g} s ＋ 切替 {sw} 回 × ロード {ss} s）',
    actual: '使用済み：GPU {s} 秒、OpenAI {t} tokens',
    assumed: '実測平均のないモデル（文書の既定値を使用）：{models}',
    measured: '移動平均（直近 20 ジョブ）：{models}',
    budgetGpu: 'GPU 秒数の上限',
    budgetTokens: 'OpenAI tokens の上限',
    save: '予算を保存',
    saved: '保存しました',
    over: '予算超過（{kind}）：見積 {estimate}、上限 {limit}。警告のみで停止しません。',
    noPlan: 'プロジェクトを選ぶと予算がここに表示されます。',
    loadFailed: 'ワークステーション状態を取得できません。',
  },
} as const;
type Text = (typeof workstationCopy)[WorkstationLocale];

const fill = (template: string, values: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));

export function WorkstationPanel({ plan, locale, onPlanChange }: {
  plan: FactoryPlan | null;
  locale: WorkstationLocale;
  onPlanChange: (plan: FactoryPlan) => void;
}) {
  const text = workstationCopy[locale];
  const [view, setView] = useState<WorkstationView | null>(null);
  const [budget, setBudget] = useState<BudgetView | null>(null);
  const [failed, setFailed] = useState(false);
  const [gpuLimit, setGpuLimit] = useState('');
  const [tokenLimit, setTokenLimit] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      workstation()
        .then((next) => { if (!cancelled) { setView(next); setFailed(false); } })
        .catch(() => { if (!cancelled) setFailed(true); });
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, []);

  const planId = plan?.id;
  useEffect(() => {
    if (!planId) { setBudget(null); return; }
    let cancelled = false;
    projectBudget(planId).then((next) => { if (!cancelled) setBudget(next); }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [planId, plan?.updatedAt]);
  useEffect(() => {
    setGpuLimit(plan?.bible.budget?.gpu_seconds ? String(plan.bible.budget.gpu_seconds) : '');
    setTokenLimit(plan?.bible.budget?.openai_tokens ? String(plan.bible.budget.openai_tokens) : '');
  }, [plan?.id, plan?.bible.budget?.gpu_seconds, plan?.bible.budget?.openai_tokens]);

  const saveBudget = async () => {
    if (!plan) return;
    const next = {
      ...(Number(gpuLimit) > 0 ? { gpu_seconds: Number(gpuLimit) } : {}),
      ...(Number(tokenLimit) > 0 ? { openai_tokens: Number(tokenLimit) } : {}),
    };
    try {
      onPlanChange(await updateProject(plan.id, { bible: { ...plan.bible, budget: next } }));
      setNotice(text.saved);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const stations: Station[] = ['ltx', 'imagegen', 'none'];
  return (
    <section className="mb-6 grid gap-4 lg:grid-cols-2">
      <div className="rounded-md border border-border bg-white p-4 text-[11px]">
        <p className="text-[10px] font-bold tracking-[0.12em]">{text.gpu}</p>
        {failed ? <p className="mt-2 text-[#e85578]">{text.loadFailed}</p> : null}
        {view ? (
          <>
            <p className="mt-2 text-[13px] font-bold">
              {view.gpu.station ? text.station[view.gpu.station] : text.idle}
            </p>
            {view.gpu.imagegen_loaded.length ? (
              <p className="text-muted-foreground">{fill(text.resident, { models: view.gpu.imagegen_loaded.join(', ') })}</p>
            ) : null}
            <p className="mt-3 text-[10px] font-bold tracking-[0.12em]">{text.queue}</p>
            <ul className="mt-1 grid grid-cols-3 gap-2">
              {stations.map((station) => (
                <li key={station} className={`rounded-sm border px-2 py-1 ${view.gpu.station === station ? 'border-[#e85578] bg-[#fdeef2]' : 'border-border'}`}>
                  <span className="block text-[9px] text-muted-foreground">{text.station[station]}</span>
                  <span className="font-mono text-[14px] font-bold tabular-nums">{view.queue[station]}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[10px] font-bold tracking-[0.12em]">{text.current}</p>
            {view.current ? (
              <p className="mt-1">
                <span className="font-bold">{view.current.project_title}</span> \u00b7 {view.current.shot_title}
                <span className="ml-2 font-mono text-[10px] text-muted-foreground">{view.current.model} \u00b7 {view.current.phase ?? ''} {view.current.progress ?? 0}%</span>
              </p>
            ) : <p className="mt-1 text-muted-foreground">{text.nothing}</p>}
            <p className="mt-3 text-muted-foreground">{fill(text.switchCost, { s: view.switch.imagegen_load_seconds })}</p>
            {view.gpu.station && view.switch.drain_seconds > 0 ? (
              <p className="text-muted-foreground">{fill(text.drain, { s: view.switch.drain_seconds })}</p>
            ) : null}
          </>
        ) : null}
      </div>

      <div className="rounded-md border border-border bg-white p-4 text-[11px]">
        <p className="text-[10px] font-bold tracking-[0.12em]">{text.budgetTitle}</p>
        {!plan ? <p className="mt-2 text-muted-foreground">{text.noPlan}</p> : null}
        {plan && budget ? (
          <>
            <p className="mt-2 font-mono tabular-nums">
              {fill(text.estimate, {
                n: budget.remaining_shots, total: budget.total_shots, s: budget.estimate.total_seconds,
                g: budget.estimate.generate_seconds, sw: budget.estimate.switches,
                ss: view?.switch.imagegen_load_seconds ?? 336,
              })}
            </p>
            <p className="font-mono tabular-nums text-muted-foreground">
              {fill(text.actual, { s: budget.actual.gpu_seconds, t: budget.actual.openai_tokens })}
            </p>
            {budget.estimate.assumed_models.length ? (
              <p className="mt-1 text-[#7a5a00]">{fill(text.assumed, { models: budget.estimate.assumed_models.join(', ') })}</p>
            ) : null}
            {budget.estimate.measured_models.length ? (
              <p className="mt-1 text-muted-foreground">
                {fill(text.measured, { models: budget.estimate.measured_models.map((m) => `${m} ${view?.averages[m] ?? ''}s`).join(', ') })}
              </p>
            ) : null}
            {budget.warnings.map((warning) => (
              <p key={warning.kind} className="mt-1 rounded-sm bg-[#fff4d6] px-2 py-1 font-bold text-[#7a5a00]">
                {fill(text.over, { kind: warning.kind, estimate: warning.estimate, limit: warning.limit })}
              </p>
            ))}
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <label className="flex flex-col text-[10px]">{text.budgetGpu}
                <input type="number" min={0} value={gpuLimit} onChange={(e) => setGpuLimit(e.target.value)} className="w-28 rounded-sm border border-border px-2 py-1 font-mono" />
              </label>
              <label className="flex flex-col text-[10px]">{text.budgetTokens}
                <input type="number" min={0} value={tokenLimit} onChange={(e) => setTokenLimit(e.target.value)} className="w-28 rounded-sm border border-border px-2 py-1 font-mono" />
              </label>
              <button type="button" onClick={() => void saveBudget()} className="rounded-sm bg-foreground px-3 py-1.5 text-[11px] font-bold text-white">{text.save}</button>
              <span className="text-[10px] text-muted-foreground">{notice}</span>
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
