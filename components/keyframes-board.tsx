'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  approveKeyframe,
  projectKeyframes,
  rejectKeyframe,
  runKeyframes,
  stopKeyframes,
  type FactoryKeyframe,
  type KeyframeListing,
} from '@/lib/factory-client';
import {
  batchEstimateSeconds,
  leadKeyframe,
  needsAttention,
  type KeyframeRecord,
} from '@/lib/keyframes';
import type { FactoryPlan } from '@/lib/production-factory';

export type KeyframesLocale = 'zh-TW' | 'en' | 'ja';

export const keyframesCopy = {
  'zh-TW': {
    empty: '還沒有鏡頭。先到 01 分鏡建立鏡頭清單。',
    noCharacter: 'Bible 沒有角色參照圖，關鍵格無從生成。先到 00 企劃 Bible 加參照。',
    phaseKeyframes: '現在是關鍵格階段：影像模型常駐 GPU',
    phaseShoot: '現在是拍攝階段：影像模型未載入',
    switchCost: '切換到關鍵格要付一次模型載入（約 {s} 秒），之後每鏡約 {p} 秒；切回拍攝時再付一次。',
    estimate: '整批預估 {s} 秒（{n} 鏡）',
    generateAll: '產生全部關鍵格',
    stop: '停止',
    running: '生成中 {done}／{total}',
    stopped: '已停止',
    failed: '批次失敗：{error}',
    done: '整批完成',
    light: { green: '綠燈', yellow: '黃燈', red: '紅燈', unscored: '未判分', failed: '失敗' },
    lightNote: { yellow: '略低於門檻，看一眼再決定。', red: '重生一次仍偏低——請人決定。', unscored: '裁判沒給分數，不是紅燈。' },
    attempt: '第 {n} 次',
    approve: '核准',
    approved: '已核准',
    fromKeyframe: '來自關鍵格',
    reject: '退回',
    reasonPlaceholder: '退回原因（必填）',
    confirm: '確認',
    cancel: '取消',
    noOutput: '尚未生成',
    reasonLabel: '原因',
  },
  en: {
    empty: 'No shots yet. Build the shot list in 01 Breakdown first.',
    noCharacter: 'The Bible has no character references, so there is nothing to generate from. Add them in 00 Bible.',
    phaseKeyframes: 'Keyframe phase: the image model is resident on the GPU',
    phaseShoot: 'Shoot phase: the image model is not loaded',
    switchCost: 'Switching to keyframes costs one model load (about {s} s), then about {p} s per shot; switching back to shooting costs another.',
    estimate: 'Batch estimate {s} s for {n} shots',
    generateAll: 'Generate all keyframes',
    stop: 'Stop',
    running: 'Generating {done} of {total}',
    stopped: 'Stopped',
    failed: 'Batch failed: {error}',
    done: 'Batch finished',
    light: { green: 'Green', yellow: 'Yellow', red: 'Red', unscored: 'Unscored', failed: 'Failed' },
    lightNote: { yellow: 'A little under the line - look before deciding.', red: 'Still low after one regeneration - a person decides.', unscored: 'The judge gave no number. Not a red light.' },
    attempt: 'Attempt {n}',
    approve: 'Approve',
    approved: 'Approved',
    fromKeyframe: 'From keyframe',
    reject: 'Reject',
    reasonPlaceholder: 'Reason (required)',
    confirm: 'Confirm',
    cancel: 'Cancel',
    noOutput: 'Not generated',
    reasonLabel: 'Reason',
  },
  ja: {
    empty: 'ショットがありません。まず 01 絵コンテでショットを作ってください。',
    noCharacter: 'Bible にキャラクター参照画像がないため生成できません。00 企画で追加してください。',
    phaseKeyframes: 'キーフレーム段階：画像モデルが GPU に常駐中',
    phaseShoot: '撮影段階：画像モデルは未ロード',
    switchCost: 'キーフレームへの切替にはモデルロード1回（約 {s} 秒）、その後1ショット約 {p} 秒。撮影へ戻す際にもう1回。',
    estimate: '一括見積 {s} 秒（{n} ショット）',
    generateAll: 'すべてのキーフレームを生成',
    stop: '停止',
    running: '生成中 {done}／{total}',
    stopped: '停止しました',
    failed: '一括失敗：{error}',
    done: '一括完了',
    light: { green: '緑', yellow: '黄', red: '赤', unscored: '未判定', failed: '失敗' },
    lightNote: { yellow: 'しきい値をわずかに下回っています。確認してから決めてください。', red: '再生成しても低いままです。人が判断してください。', unscored: '判定なし。赤ではありません。' },
    attempt: '{n} 回目',
    approve: '承認',
    approved: '承認済み',
    fromKeyframe: 'キーフレーム由来',
    reject: '差し戻し',
    reasonPlaceholder: '理由（必須）',
    confirm: '確定',
    cancel: 'キャンセル',
    noOutput: '未生成',
    reasonLabel: '理由',
  },
} as const;
type Text = (typeof keyframesCopy)[KeyframesLocale];

const fill = (template: string, values: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));

const LIGHT_TONE: Record<string, string> = {
  green: 'bg-[#e6f6ee] text-[#1f6b48]',
  yellow: 'bg-[#fff4d6] text-[#7a5a00]',
  red: 'bg-[#fdeef2] text-[#a8365a]',
  unscored: 'bg-[#f3f0ec] text-muted-foreground',
  failed: 'bg-[#f3f0ec] text-muted-foreground',
};

const toRecord = (k: FactoryKeyframe): KeyframeRecord => ({ ...k });

export function KeyframesBoard({
  plan,
  locale,
  onPlanChange,
  onAttention,
}: {
  plan: FactoryPlan | null;
  locale: KeyframesLocale;
  onPlanChange: (plan: FactoryPlan) => void;
  onAttention?: (count: number) => void;
}) {
  const text = keyframesCopy[locale];
  const [listing, setListing] = useState<KeyframeListing | null>(null);
  const [busy, setBusy] = useState('');
  const [rejecting, setRejecting] = useState('');
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState('');

  const planId = plan?.id;
  const running = listing?.run.status === 'running' || listing?.run.status === 'stopping';
  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    const load = () =>
      projectKeyframes(planId)
        .then((next) => {
          if (!cancelled) setListing(next);
        })
        .catch((error) => {
          if (!cancelled) setNotice(error instanceof Error ? error.message : String(error));
        });
    void load();
    // While the host is generating, the listing is the only place progress appears.
    const timer = running ? window.setInterval(() => void load(), 3000) : undefined;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [planId, running, plan?.updatedAt]);

  const attention = useMemo(() => {
    if (!plan || !listing) return 0;
    return plan.shots.filter((shot) => needsAttention((listing.keyframes[shot.id] ?? []).map(toRecord))).length;
  }, [plan, listing]);
  useEffect(() => {
    onAttention?.(attention);
  }, [attention, onAttention]);

  if (!plan || !plan.shots.length) {
    return (
      <section className="rounded-md border border-border bg-white p-6 text-center">
        <p className="text-[13px] text-muted-foreground">{text.empty}</p>
      </section>
    );
  }
  const hasReferences = Boolean(plan.bible.character?.references.length);
  const loaded = Boolean(listing?.gpu.imagegen_loaded.length);
  const costs = listing?.costs ?? { switch_seconds: 336, per_keyframe_seconds: 26 };
  const estimate = batchEstimateSeconds(plan.shots.length, loaded);

  const withPlan = async (id: string, work: () => Promise<FactoryPlan>) => {
    setBusy(id);
    setNotice('');
    try {
      onPlanChange(await work());
      setListing(await projectKeyframes(plan.id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy('');
    }
  };
  const start = async () => {
    setBusy('run');
    setNotice('');
    try {
      await runKeyframes(plan.id);
      setListing(await projectKeyframes(plan.id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy('');
    }
  };

  const run = listing?.run ?? {};
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 rounded-md border border-border bg-white px-4 py-3 text-[11px]">
        <div className="flex flex-wrap items-center gap-3">
          <span className={`rounded-sm px-2 py-1 font-bold ${loaded ? 'bg-[#fdeef2] text-[#a8365a]' : 'bg-[#eef2fd] text-[#4a5a8c]'}`}>
            {loaded ? text.phaseKeyframes : text.phaseShoot}
          </span>
          <span className="text-muted-foreground">
            {fill(text.switchCost, { s: costs.switch_seconds, p: costs.per_keyframe_seconds })}
          </span>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {running ? (
            <>
              <span className="font-bold">{fill(text.running, { done: run.done ?? 0, total: run.total ?? plan.shots.length })}</span>
              <button type="button" onClick={() => void stopKeyframes(plan.id)} className="rounded-sm border border-border px-3 py-1 font-bold hover:bg-[#faf9f7]">
                {text.stop}
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={!hasReferences || busy === 'run'}
              title={hasReferences ? undefined : text.noCharacter}
              onClick={() => void start()}
              className="rounded-sm bg-foreground px-3 py-1.5 font-bold text-white disabled:opacity-40"
            >
              {text.generateAll}
            </button>
          )}
          <span className="font-mono tabular-nums text-muted-foreground">{fill(text.estimate, { s: estimate, n: plan.shots.length })}</span>
          {run.status === 'done' ? <span className="text-[#1f6b48]">{text.done}</span> : null}
          {run.status === 'stopped' ? <span>{text.stopped}</span> : null}
          {run.status === 'failed' ? <span className="text-[#e85578]">{fill(text.failed, { error: run.error ?? '' })}</span> : null}
        </div>
        {!hasReferences ? <p className="text-[#7a5a00]">{text.noCharacter}</p> : null}
        {notice ? <p className="text-[#e85578]">{notice}</p> : null}
      </div>

      <ol className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-4">
        {plan.shots.map((shot, index) => {
          const records = (listing?.keyframes[shot.id] ?? []).map(toRecord);
          const lead = leadKeyframe(records);
          const lightKey = lead ? (lead.verdict === 'failed' ? 'failed' : lead.light ?? 'unscored') : 'unscored';
          const fromKeyframe = Boolean(shot.request.keyframe_id);
          const current = run.current === shot.id;
          return (
            <li key={shot.id} className={`flex flex-col gap-2 rounded-md border bg-white p-2 ${current ? 'border-[#e85578]' : 'border-border'}`}>
              {lead?.outputUrl ? (
                <img src={lead.outputUrl} alt="" className="aspect-video w-full rounded-sm bg-[#111] object-cover" />
              ) : (
                <div className="grid aspect-video w-full place-items-center rounded-sm bg-[#f3f0ec] text-[10px] text-muted-foreground">
                  {current ? '…' : text.noOutput}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-1 text-[10px]">
                <span className="font-mono font-bold tabular-nums">{String(index + 1).padStart(2, '0')}</span>
                <span className="truncate font-bold">{shot.title}</span>
                {fromKeyframe ? <span className="rounded-sm bg-[#e6f6ee] px-1.5 py-0.5 font-bold text-[#1f6b48]">{text.fromKeyframe}</span> : null}
              </div>
              {lead ? (
                <div className="flex flex-wrap items-center gap-1 text-[10px]">
                  <span className={`rounded-sm px-1.5 py-0.5 font-bold ${LIGHT_TONE[lightKey]}`}>{text.light[lightKey as keyof typeof text.light]}</span>
                  <span className="text-muted-foreground">{fill(text.attempt, { n: lead.attempt })}</span>
                  {lead.verdict === 'approved' ? <span className="text-[#1f6b48]">{text.approved}</span> : null}
                </div>
              ) : null}
              {lead && lightKey in text.lightNote && lead.verdict === 'pending' ? (
                <p className="text-[10px] text-muted-foreground">{text.lightNote[lightKey as keyof typeof text.lightNote]}</p>
              ) : null}
              {lead?.verdict === 'failed' && lead.reason ? <p className="text-[10px] text-[#a8365a]">{text.reasonLabel}: {lead.reason}</p> : null}
              {lead && lead.verdict === 'pending' && lead.outputUrl ? (
                rejecting === lead.id ? (
                  <div className="flex flex-col gap-1">
                    <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder={text.reasonPlaceholder} rows={2} className="w-full rounded-sm border border-border px-2 py-1 text-[11px]" />
                    <div className="flex gap-1">
                      <button type="button" disabled={!reason.trim()} onClick={() => { const r = reason.trim(); setRejecting(''); setReason(''); void withPlan(lead.id, () => rejectKeyframe(lead.id, r)); }} className="rounded-sm border border-border px-2 py-1 text-[10px] font-bold disabled:opacity-40">{text.confirm}</button>
                      <button type="button" onClick={() => { setRejecting(''); setReason(''); }} className="rounded-sm border border-border px-2 py-1 text-[10px]">{text.cancel}</button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-auto flex gap-1">
                    <button type="button" disabled={busy === lead.id} onClick={() => void withPlan(lead.id, () => approveKeyframe(lead.id))} className="rounded-sm bg-foreground px-2 py-1 text-[10px] font-bold text-white disabled:opacity-40">{text.approve}</button>
                    <button type="button" disabled={busy === lead.id} onClick={() => { setRejecting(lead.id); setReason(''); }} className="rounded-sm border border-border px-2 py-1 text-[10px] hover:bg-[#faf9f7]">{text.reject}</button>
                  </div>
                )
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
