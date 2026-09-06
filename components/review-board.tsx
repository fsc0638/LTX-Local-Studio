'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  acceptTake,
  disagreeOpinion,
  projectTakes,
  rejectTake,
  replaceShots,
  takeOpinion,
  type FactoryTake,
} from '@/lib/factory-client';
import type { FactoryPlan, FactoryShot } from '@/lib/production-factory';
import {
  LIGHT_KEYS,
  LINE_KEYS,
  consistencyCurve,
  consistencyLine,
  isRed,
  lights,
  resolveThresholds,
  takeScores,
  type Light,
  type LightKey,
  type LineKey,
  type Thresholds,
} from '@/lib/review';
import type { BibleThresholds } from '@/lib/calibration';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';

export type ReviewLocale = 'zh-TW' | 'en' | 'ja';

export const reviewCopy = {
  'zh-TW': {
    empty: '還沒有可審的 take。先到 03 拍攝把鏡頭生產出來。',
    loading: '讀取 take…',
    loadFailed: '讀不到 take 清單，請重新整理。',
    uncalibrated: '門檻未校準：目前是暫定值（C4 校準後會由 Bible 覆蓋）。',
    strict: '相鄰鏡嚴格模式（fpr 1%）',
    strictNote: '用較嚴的門檻看相鄰鏡是否連戲；採用時也以嚴格門檻判定是否記為推翻。',
    judges: { cj: '一致性', cj_dino: '整體（無臉）', sj: '風格', mq: '動態' },
    light: { red: '紅燈', green: '綠燈', unscored: '未判分' },
    unscoredNote: '裁判沒有給出這一項——服務未執行、沒有參照圖，或這是靜態圖。不是紅燈。',
    verdict: { pending: '待審', accepted: '已採用', rejected: '已退回', overridden: '推翻裁判採用' },
    overriddenBy: '由 {who} 於 {when} 推翻',
    accepted: '進 06 組片',
    deleted: '成品已刪除',
    accept: '採用',
    acceptRed: '裁判亮紅燈。仍要採用？會記錄為「推翻裁判」，含你的帳號與時間。',
    confirmAccept: '確認採用',
    cancel: '取消',
    reject: '退回',
    reasonPlaceholder: '退回原因（必填）——會以「避免：…」接到下一 take 的提示詞',
    confirmReject: '確認退回',
    opinion: '請 VLM 看一眼',
    opinionUnavailable: '主機未設定 OpenAI，無法產生意見。',
    disagree: '我不同意',
    disagreed: '你已標記不同意',
    details: '細節',
    drawerTitle: '這一 take 的細節',
    curve: '逐幀一致性（每秒一幀）',
    noCurve: '沒有逐幀資料。',
    method: { face_facenet: '臉', dinov2_large: '整體' },
    overrideTitle: '本鏡門檻覆寫',
    overrideNote: '留空＝沿用 Bible／預設。只影響這一鏡，會存在鏡的設定裡。',
    save: '儲存門檻',
    saved: '已儲存',
    reasonLabel: '退回原因',
    faceLineUncalibrated: '臉部線仍為暫定值：校準報告裡臉太少。',
    takeN: 'Take {n}',
  },
  en: {
    empty: 'Nothing to review yet. Generate the shots in 03 Shoot first.',
    loading: 'Loading takes…',
    loadFailed: 'Could not load the takes. Reload the page.',
    uncalibrated: 'Thresholds are uncalibrated placeholders (C4 writes measured values into the Bible).',
    strict: 'Strict mode for adjacent shots (fpr 1%)',
    strictNote: 'Judge with the stricter lines; accepting under them is what gets recorded as an override.',
    judges: { cj: 'Consistency', cj_dino: 'Whole (no face)', sj: 'Style', mq: 'Motion' },
    light: { red: 'Red', green: 'Green', unscored: 'Unscored' },
    unscoredNote: 'The judge gave nothing here - service down, no reference images, or a still. Not a red light.',
    verdict: { pending: 'Pending', accepted: 'Accepted', rejected: 'Sent back', overridden: 'Accepted over a red light' },
    overriddenBy: 'Overridden by {who} at {when}',
    accepted: 'Goes to 06 assembly',
    deleted: 'Output deleted',
    accept: 'Accept',
    acceptRed: 'A judge lit red. Accept anyway? This is recorded as an override with your account and the time.',
    confirmAccept: 'Confirm accept',
    cancel: 'Cancel',
    reject: 'Send back',
    reasonPlaceholder: 'Reason (required) - appended to the next take’s prompt as "避免：…"',
    confirmReject: 'Confirm',
    opinion: 'Ask the VLM',
    opinionUnavailable: 'No OpenAI key on this host, so no opinions.',
    disagree: 'I disagree',
    disagreed: 'You marked this as wrong',
    details: 'Details',
    drawerTitle: 'This take in detail',
    curve: 'Per-frame consistency (one frame a second)',
    noCurve: 'No per-frame data.',
    method: { face_facenet: 'face', dinov2_large: 'whole' },
    overrideTitle: 'Thresholds for this shot',
    overrideNote: 'Empty means the Bible or default applies. Stored with the shot; affects only it.',
    save: 'Save thresholds',
    saved: 'Saved',
    reasonLabel: 'Reason',
    faceLineUncalibrated: 'The face line is still a placeholder: too few faces in the calibration report.',
    takeN: 'Take {n}',
  },
  ja: {
    empty: 'まだレビューできるテイクがありません。03 撮影でショットを生成してください。',
    loading: 'テイクを読み込み中…',
    loadFailed: 'テイク一覧を取得できません。再読み込みしてください。',
    uncalibrated: 'しきい値は未校正の暫定値です（C4 で計測値が Bible に入ります）。',
    strict: '隣接ショットの厳格モード（fpr 1%）',
    strictNote: '厳しいしきい値で判定します。この下で採用すると「覆し」として記録されます。',
    judges: { cj: '一貫性', cj_dino: '全体（顔なし）', sj: 'スタイル', mq: '動き' },
    light: { red: '赤', green: '緑', unscored: '未判定' },
    unscoredNote: '判定なし：サービス停止、参照画像なし、または静止画。赤ではありません。',
    verdict: { pending: '未審査', accepted: '採用', rejected: '差し戻し', overridden: '赤を覆して採用' },
    overriddenBy: '{who} が {when} に覆しました',
    accepted: '06 組み立てへ',
    deleted: '出力は削除済み',
    accept: '採用',
    acceptRed: '判定が赤です。それでも採用しますか？アカウントと時刻とともに「覆し」として記録されます。',
    confirmAccept: '採用を確定',
    cancel: 'キャンセル',
    reject: '差し戻し',
    reasonPlaceholder: '理由（必須）。次のテイクのプロンプトに「避免：…」として追記されます',
    confirmReject: '確定',
    opinion: 'VLM に見てもらう',
    opinionUnavailable: 'ホストに OpenAI キーがないため意見は生成できません。',
    disagree: '同意しない',
    disagreed: '同意しないと記録済み',
    details: '詳細',
    drawerTitle: 'このテイクの詳細',
    curve: 'フレームごとの一貫性（毎秒1フレーム）',
    noCurve: 'フレーム単位のデータはありません。',
    method: { face_facenet: '顔', dinov2_large: '全体' },
    overrideTitle: 'このショットのしきい値',
    overrideNote: '空欄なら Bible／既定値。ショットに保存され、このショットのみに影響します。',
    save: 'しきい値を保存',
    saved: '保存しました',
    reasonLabel: '理由',
    faceLineUncalibrated: '顔のラインは暫定のまま：校正レポートに顔が少なすぎました。',
    takeN: 'テイク {n}',
  },
} as const;
type ReviewText = (typeof reviewCopy)[ReviewLocale];

const fill = (template: string, values: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
const stamp = (seconds: number | null | undefined) =>
  seconds ? new Date(seconds * 1000).toLocaleString() : '';

const LIGHT_TONE: Record<Light, string> = {
  red: 'bg-[#e85578]',
  green: 'bg-[#2f9e6d]',
  unscored: 'bg-[#c9c3ba]',
};

/** One score against its line: a bar with the threshold drawn as a tick, coloured by the light. */
function ScoreBar({
  label,
  value,
  threshold,
  light,
}: {
  label: string;
  value: number | null;
  threshold: number;
  light: Light;
}) {
  return (
    <div className="grid grid-cols-[52px_1fr_44px] items-center gap-2 text-[10px]">
      <span className="font-bold">{label}</span>
      <span className="relative block h-2 w-full overflow-hidden rounded-sm bg-[#efece7]">
        {value !== null ? (
          <span
            className={`absolute inset-y-0 left-0 ${LIGHT_TONE[light]}`}
            style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
          />
        ) : null}
        <span
          className="absolute inset-y-0 w-px bg-foreground"
          style={{ left: `${threshold * 100}%` }}
          title={String(threshold)}
        />
      </span>
      <span className="text-right font-mono tabular-nums text-muted-foreground">
        {value === null ? '—' : value.toFixed(2)}
      </span>
    </div>
  );
}

function Curve({ take, thresholds, text }: {
  take: FactoryTake;
  thresholds: Thresholds;
  text: ReviewText;
}) {
  const points = consistencyCurve(take.scores);
  // Each second is judged against the line of the path that scored it: a frame with no face
  // was scored by DINOv2 and belongs to the dino line, whatever its neighbours did.
  const lineFor = (method: string) => (method === 'dinov2_large' ? thresholds.cj_dino : thresholds.cj);
  const threshold = consistencyLine(take.scores, thresholds);
  if (!points.length) return <p className="text-[11px] text-muted-foreground">{text.noCurve}</p>;
  const width = 320;
  const height = 90;
  const step = points.length > 1 ? width / (points.length - 1) : 0;
  const y = (value: number) => height - Math.max(0, Math.min(1, value)) * height;
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${(i * step).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  return (
    <figure>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-24 w-full" role="img" aria-label={text.curve}>
        <rect x={0} y={0} width={width} height={height} fill="#faf9f7" />
        <line x1={0} x2={width} y1={y(threshold)} y2={y(threshold)} stroke="#111" strokeDasharray="3 3" strokeWidth={1} />
        <path d={path} fill="none" stroke="#e85578" strokeWidth={1.5} />
        {points.map((p, i) => (
          <circle key={p.second} cx={i * step} cy={y(p.value)} r={2} fill={p.value < lineFor(p.method) ? '#e85578' : '#2f9e6d'}>
            <title>{`${p.second}s · ${p.value.toFixed(3)} · ${text.method[p.method as keyof typeof text.method] ?? p.method}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="mt-1 text-[10px] text-muted-foreground">{text.curve}</figcaption>
    </figure>
  );
}

export function ReviewBoard({
  plan,
  locale,
  opinionsAvailable,
  onPlanChange,
}: {
  plan: FactoryPlan | null;
  locale: ReviewLocale;
  opinionsAvailable: boolean;
  onPlanChange: (plan: FactoryPlan) => void;
}) {
  const text = reviewCopy[locale];
  const [takes, setTakes] = useState<Record<string, FactoryTake[]>>({});
  const [loadState, setLoadState] = useState<'idle' | 'loading' | 'failed'>('idle');
  const [strict, setStrict] = useState(false);
  const [busy, setBusy] = useState('');
  const [confirming, setConfirming] = useState('');
  const [rejecting, setRejecting] = useState('');
  const [reason, setReason] = useState('');
  const [drawer, setDrawer] = useState<{ shot: FactoryShot; take: FactoryTake } | null>(null);
  const [notice, setNotice] = useState<Record<string, string>>({});

  const planId = plan?.id;
  const planStamp = plan?.updatedAt;
  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    setLoadState('loading');
    projectTakes(planId)
      .then((grouped) => {
        if (cancelled) return;
        setTakes(grouped);
        setLoadState('idle');
      })
      .catch(() => {
        if (!cancelled) setLoadState('failed');
      });
    return () => {
      cancelled = true;
    };
  }, [planId, planStamp]);

  const bible = (plan?.bible ?? null) as unknown as Record<string, unknown> | null;
  const anyUncalibrated = useMemo(
    () => (plan ? plan.shots.some((shot) => !resolveThresholds(bible, shot.request, strict).calibrated) : false),
    [plan, bible, strict],
  );

  if (!plan || !plan.shots.length) {
    return (
      <section className="rounded-md border border-border bg-white p-6 text-center">
        <p className="text-[13px] text-muted-foreground">{text.empty}</p>
      </section>
    );
  }

  const withPlan = async (id: string, work: () => Promise<FactoryPlan>) => {
    setBusy(id);
    try {
      const next = await work();
      onPlanChange(next);
      setNotice((current) => ({ ...current, [id]: '' }));
    } catch (error) {
      setNotice((current) => ({ ...current, [id]: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy('');
    }
  };

  const accept = (take: FactoryTake) => {
    setConfirming('');
    void withPlan(take.id, () => acceptTake(take.id, strict));
  };
  const reject = (take: FactoryTake) => {
    const trimmed = reason.trim();
    if (!trimmed) return;
    setRejecting('');
    setReason('');
    void withPlan(take.id, () => rejectTake(take.id, trimmed));
  };
  const askOpinion = async (take: FactoryTake) => {
    setBusy(take.id);
    try {
      const opinion = await takeOpinion(take.id);
      setTakes((current) => ({
        ...current,
        [take.shotId]: (current[take.shotId] ?? []).map((item) =>
          item.id === take.id ? { ...item, opinion } : item,
        ),
      }));
    } catch (error) {
      setNotice((current) => ({ ...current, [take.id]: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy('');
    }
  };
  const saveThresholds = async (shot: FactoryShot, values: Partial<Record<LineKey, number>>) => {
    const cleaned = Object.fromEntries(
      Object.entries(values).filter(([, v]) => typeof v === 'number' && Number.isFinite(v)),
    );
    const request = { ...shot.request } as Record<string, unknown>;
    if (Object.keys(cleaned).length) request.thresholds = cleaned;
    else delete request.thresholds;
    const shots = plan.shots.map((item) =>
      item.id === shot.id ? { ...item, request: request as FactoryShot['request'] } : item,
    );
    await withPlan(`thresholds-${shot.id}`, () => replaceShots(plan.id, shots));
    setNotice((current) => ({ ...current, [`thresholds-${shot.id}`]: text.saved }));
  };

  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-white px-4 py-3 text-[11px]">
        <label className="flex items-center gap-2 font-bold">
          <input type="checkbox" checked={strict} onChange={(event) => setStrict(event.target.checked)} />
          {text.strict}
        </label>
        <span className="text-muted-foreground">{text.strictNote}</span>
        {anyUncalibrated ? (
          <span className="ml-auto rounded-sm bg-[#fff4d6] px-2 py-1 font-bold text-[#7a5a00]">
            {text.uncalibrated}
          </span>
        ) : null}
        {loadState === 'loading' ? <span className="text-muted-foreground">{text.loading}</span> : null}
        {loadState === 'failed' ? <span className="text-[#e85578]">{text.loadFailed}</span> : null}
      </div>

      <ol className="flex flex-col gap-4">
        {plan.shots.map((shot, index) => {
          const thresholds = resolveThresholds(bible, shot.request, strict);
          const list = takes[shot.id] ?? [];
          return (
            <li key={shot.id} className="rounded-md border border-border bg-white">
              <div className="flex flex-wrap items-baseline gap-3 border-b border-border px-4 py-2">
                <span className="font-mono text-[12px] font-bold tabular-nums">{String(index + 1).padStart(2, '0')}</span>
                <span className="text-[12px] font-bold">{shot.title}</span>
                {shot.acceptedTakeId ? (
                  <span className="rounded-sm bg-[#e6f6ee] px-1.5 py-0.5 text-[10px] font-bold text-[#1f6b48]">{text.accepted}</span>
                ) : null}
                {thresholds.calibrated && (plan.bible.thresholds as BibleThresholds | undefined)?.report?.lines.cj === false ? (
                  <span className="text-[10px] text-[#7a5a00]">{text.faceLineUncalibrated}</span>
                ) : null}
                <span className="ml-auto font-mono text-[10px] tabular-nums text-muted-foreground">
                  cj {thresholds.cj} · dino {thresholds.cj_dino} · sj {thresholds.sj} · mq {thresholds.mq}
                </span>
              </div>
              {list.length === 0 ? (
                <p className="px-4 py-3 text-[11px] text-muted-foreground">—</p>
              ) : (
                <div className="flex gap-3 overflow-x-auto p-3">
                  {list.map((take, takeIndex) => {
                    const takeLights = lights(take.scores, thresholds);
                    const values = takeScores(take.scores);
                    const red = isRed(take.scores, thresholds);
                    const accepted = shot.acceptedTakeId === take.id;
                    const disabled = busy === take.id || Boolean(take.deletedAt);
                    return (
                      <article
                        key={take.id}
                        className={`flex w-64 shrink-0 flex-col gap-2 rounded-md border p-3 ${
                          accepted ? 'border-[#2f9e6d]' : 'border-border'
                        } ${take.deletedAt ? 'opacity-55' : ''}`}
                      >
                        <header className="flex items-center justify-between text-[10px]">
                          <span className="font-bold">{fill(text.takeN, { n: list.length - takeIndex })}</span>
                          <span
                            className={`rounded-sm px-1.5 py-0.5 font-bold ${
                              take.verdict === 'overridden'
                                ? 'bg-[#fdeef2] text-[#a8365a]'
                                : take.verdict === 'accepted'
                                  ? 'bg-[#e6f6ee] text-[#1f6b48]'
                                  : take.verdict === 'rejected'
                                    ? 'bg-[#f3f0ec] text-muted-foreground'
                                    : 'bg-[#eef2fd] text-[#4a5a8c]'
                            }`}
                          >
                            {text.verdict[take.verdict]}
                          </span>
                        </header>
                        {take.posterUrl ? (
                          <img src={take.posterUrl} alt="" className="aspect-video w-full rounded-sm bg-[#111] object-cover" />
                        ) : (
                          <div className="aspect-video w-full rounded-sm bg-[#f3f0ec]" />
                        )}
                        {take.deletedAt ? <p className="text-[10px] text-muted-foreground">{text.deleted}</p> : null}
                        {take.verdict === 'overridden' && take.overriddenBy ? (
                          <p className="text-[10px] text-[#a8365a]">
                            {fill(text.overriddenBy, { who: take.overriddenBy, when: stamp(take.overriddenAt) })}
                          </p>
                        ) : null}
                        {take.verdict === 'rejected' && take.reason ? (
                          <p className="text-[10px] text-muted-foreground">{text.reasonLabel}: {take.reason}</p>
                        ) : null}
                        <div className="flex flex-col gap-1">
                          {LIGHT_KEYS.map((key) => (
                            <ScoreBar
                              key={key}
                              label={text.judges[key]}
                              value={values[key]}
                              threshold={key === 'cj' ? consistencyLine(take.scores, thresholds) : thresholds[key]}
                              light={takeLights[key]}
                            />
                          ))}
                        </div>
                        {Object.values(takeLights).includes('unscored') ? (
                          <p className="text-[10px] text-muted-foreground">{text.unscoredNote}</p>
                        ) : null}
                        {take.opinion ? (
                          <p className={`text-[11px] leading-relaxed ${take.opinion.disagreed_by ? 'line-through text-muted-foreground' : ''}`}>
                            {take.opinion.text}
                          </p>
                        ) : null}
                        <div className="mt-auto flex flex-wrap gap-1">
                          {!take.opinion ? (
                            <button
                              type="button"
                              disabled={disabled || !opinionsAvailable}
                              title={opinionsAvailable ? undefined : text.opinionUnavailable}
                              onClick={() => void askOpinion(take)}
                              className="rounded-sm border border-border px-2 py-1 text-[10px] hover:bg-[#faf9f7] disabled:opacity-40"
                            >
                              {text.opinion}
                            </button>
                          ) : take.opinion.disagreed_by ? (
                            <span className="text-[10px] text-muted-foreground">{text.disagreed}</span>
                          ) : (
                            <button
                              type="button"
                              disabled={busy === take.id}
                              onClick={() => void withPlan(take.id, () => disagreeOpinion(take.id))}
                              className="rounded-sm border border-border px-2 py-1 text-[10px] hover:bg-[#faf9f7]"
                            >
                              {text.disagree}
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => setDrawer({ shot, take })}
                            className="rounded-sm border border-border px-2 py-1 text-[10px] hover:bg-[#faf9f7]"
                          >
                            {text.details}
                          </button>
                          {!accepted && !take.deletedAt ? (
                            confirming === take.id ? (
                              <span className="flex w-full flex-col gap-1 rounded-sm bg-[#fdeef2] p-2 text-[10px]">
                                {text.acceptRed}
                                <span className="flex gap-1">
                                  <button type="button" onClick={() => accept(take)} className="rounded-sm bg-[#e85578] px-2 py-1 font-bold text-white">{text.confirmAccept}</button>
                                  <button type="button" onClick={() => setConfirming('')} className="rounded-sm border border-border px-2 py-1">{text.cancel}</button>
                                </span>
                              </span>
                            ) : (
                              <button
                                type="button"
                                disabled={disabled}
                                onClick={() => (red ? setConfirming(take.id) : accept(take))}
                                className="rounded-sm bg-foreground px-2 py-1 text-[10px] font-bold text-white disabled:opacity-40"
                              >
                                {text.accept}
                              </button>
                            )
                          ) : null}
                          {take.verdict !== 'rejected' && !take.deletedAt ? (
                            rejecting === take.id ? (
                              <span className="flex w-full flex-col gap-1">
                                <textarea
                                  value={reason}
                                  onChange={(event) => setReason(event.target.value)}
                                  placeholder={text.reasonPlaceholder}
                                  rows={2}
                                  className="w-full rounded-sm border border-border px-2 py-1 text-[11px]"
                                />
                                <span className="flex gap-1">
                                  <button type="button" disabled={!reason.trim()} onClick={() => reject(take)} className="rounded-sm border border-border px-2 py-1 text-[10px] font-bold disabled:opacity-40">{text.confirmReject}</button>
                                  <button type="button" onClick={() => { setRejecting(''); setReason(''); }} className="rounded-sm border border-border px-2 py-1 text-[10px]">{text.cancel}</button>
                                </span>
                              </span>
                            ) : (
                              <button
                                type="button"
                                disabled={disabled}
                                onClick={() => { setRejecting(take.id); setReason(''); }}
                                className="rounded-sm border border-border px-2 py-1 text-[10px] hover:bg-[#faf9f7] disabled:opacity-40"
                              >
                                {text.reject}
                              </button>
                            )
                          ) : null}
                        </div>
                        {notice[take.id] ? <p className="text-[10px] text-[#e85578]">{notice[take.id]}</p> : null}
                      </article>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ol>

      <Sheet open={drawer !== null} onOpenChange={(open) => { if (!open) setDrawer(null); }}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-md">
          {drawer ? (
            <ThresholdDrawer
              key={drawer.take.id}
              shot={drawer.shot}
              take={drawer.take}
              bible={bible}
              strict={strict}
              text={text}
              notice={notice[`thresholds-${drawer.shot.id}`] ?? ''}
              onSave={(values) => void saveThresholds(drawer.shot, values)}
            />
          ) : null}
        </SheetContent>
      </Sheet>
    </section>
  );
}

function ThresholdDrawer({
  shot,
  take,
  bible,
  strict,
  text,
  notice,
  onSave,
}: {
  shot: FactoryShot;
  take: FactoryTake;
  bible: Record<string, unknown> | null;
  strict: boolean;
  text: ReviewText;
  notice: string;
  onSave: (values: Partial<Record<LineKey, number>>) => void;
}) {
  const thresholds: Thresholds = resolveThresholds(bible, shot.request, strict);
  const own = ((shot.request as Record<string, unknown>).thresholds ?? {}) as Partial<Record<LineKey, number>>;
  const [draft, setDraft] = useState<Record<LineKey, string>>({
    cj: own.cj !== undefined ? String(own.cj) : '',
    cj_dino: own.cj_dino !== undefined ? String(own.cj_dino) : '',
    sj: own.sj !== undefined ? String(own.sj) : '',
    mq: own.mq !== undefined ? String(own.mq) : '',
  });
  return (
    <>
      <SheetHeader>
        <SheetTitle>{text.drawerTitle}</SheetTitle>
        <SheetDescription>{shot.title}</SheetDescription>
      </SheetHeader>
      <div className="flex flex-col gap-5 py-4">
        <Curve take={take} thresholds={thresholds} text={text} />
        <div>
          <p className="text-[11px] font-bold">{text.overrideTitle}</p>
          <p className="mt-1 text-[10px] text-muted-foreground">{text.overrideNote}</p>
          <div className="mt-3 flex flex-col gap-2">
            {LINE_KEYS.map((key) => (
              <label key={key} className="grid grid-cols-[80px_1fr_60px] items-center gap-2 text-[11px]">
                <span className="font-bold">{text.judges[key]}</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={draft[key]}
                  placeholder={String(thresholds[key])}
                  onChange={(event) => setDraft((current) => ({ ...current, [key]: event.target.value }))}
                  className="rounded-sm border border-border px-2 py-1 font-mono text-[11px]"
                />
                <span className="font-mono text-[10px] tabular-nums text-muted-foreground">{thresholds[key]}</span>
              </label>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() =>
                onSave(
                  Object.fromEntries(
                    LINE_KEYS.map((key) => [key, draft[key] === '' ? undefined : Number(draft[key])]),
                  ) as Partial<Record<LineKey, number>>,
                )
              }
              className="rounded-sm bg-foreground px-3 py-1.5 text-[11px] font-bold text-white"
            >
              {text.save}
            </button>
            <span className="text-[10px] text-muted-foreground">{notice}</span>
          </div>
        </div>
      </div>
    </>
  );
}
