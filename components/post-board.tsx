'use client';

import { useEffect, useRef, useState } from 'react';
import { serviceFetch } from '@/lib/service-session';
import { postTake, projectPost, projectTakes, type FactoryTake, type PostListing } from '@/lib/factory-client';
import type { FactoryPlan, FactoryShot } from '@/lib/production-factory';

export type PostLocale = 'zh-TW' | 'en' | 'ja';

export const postCopy = {
  'zh-TW': {
    empty: '還沒有核准的 take。先到 04 審片採用每一鏡的 take。',
    serviceDown: '後製服務未執行，三個開關都不可用。',
    rifeMissing: 'RIFE 權重未安裝，補幀不可用；放大與清理不受影響。',
    upscale: '放大',
    clean: '清理',
    interpolate: '補幀',
    scale: '倍率',
    targetFps: '目標 fps',
    paintMask: '在圖上塗要清掉的地方（白色），然後送出。',
    brush: '筆刷',
    clear: '清除',
    submitClean: '送出清理',
    cancel: '取消',
    submitted: '已送出，處理完成後會出現新版本。',
    versions: '後製版本',
    noVersions: '尚無後製版本。',
    failed: '失敗',
    processing: '處理中…',
    scored: '已判分',
    op: { upscale: '放大 ×{scale}', clean: '清理', interpolate: '補幀 → {fps} fps' },
    noAccepted: '這一鏡還沒有採用的 take。',
    mqNote: '完成後自動經過動態裁判（MQ）；分數在 04 審片頁可見。',
  },
  en: {
    empty: 'No accepted takes yet. Accept each shot\u2019s take in 04 Review first.',
    serviceDown: 'The post service is not running; all three tools are unavailable.',
    rifeMissing: 'RIFE weights are not installed, so interpolation is unavailable; upscale and clean still work.',
    upscale: 'Upscale',
    clean: 'Clean',
    interpolate: 'Interpolate',
    scale: 'Scale',
    targetFps: 'Target fps',
    paintMask: 'Paint what to remove (white) on the frame, then submit.',
    brush: 'Brush',
    clear: 'Clear',
    submitClean: 'Submit clean-up',
    cancel: 'Cancel',
    submitted: 'Submitted; the new version appears when processing finishes.',
    versions: 'Post versions',
    noVersions: 'No post versions yet.',
    failed: 'Failed',
    processing: 'Processing\u2026',
    scored: 'Scored',
    op: { upscale: 'Upscale \u00d7{scale}', clean: 'Clean', interpolate: 'Interpolate \u2192 {fps} fps' },
    noAccepted: 'This shot has no accepted take yet.',
    mqNote: 'Finished versions go through the motion judge (MQ) automatically; scores show in 04 Review.',
  },
  ja: {
    empty: '採用済みテイクがありません。まず 04 レビューで各ショットのテイクを採用してください。',
    serviceDown: 'ポストサービスが動いていないため、3つのツールは使えません。',
    rifeMissing: 'RIFE の重みが未インストールのため補間は使えません。拡大とクリーンは使えます。',
    upscale: '拡大',
    clean: 'クリーン',
    interpolate: '補間',
    scale: '倍率',
    targetFps: '目標 fps',
    paintMask: '消したい部分をフレーム上に白で塗ってから送信してください。',
    brush: 'ブラシ',
    clear: 'クリア',
    submitClean: 'クリーンを送信',
    cancel: 'キャンセル',
    submitted: '送信しました。処理が終わると新しいバージョンが表示されます。',
    versions: 'ポストバージョン',
    noVersions: 'まだポストバージョンはありません。',
    failed: '失敗',
    processing: '処理中…',
    scored: '判定済み',
    op: { upscale: '拡大 ×{scale}', clean: 'クリーン', interpolate: '補間 → {fps} fps' },
    noAccepted: 'このショットには採用済みテイクがありません。',
    mqNote: '完了したバージョンは自動で動き判定（MQ）を通ります。スコアは 04 レビューに表示されます。',
  },
} as const;
type Text = (typeof postCopy)[PostLocale];

const fill = (template: string, values: Record<string, string | number>) =>
  template.replace(/\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));

/**
 * A mask painted over the poster frame. Exported as a PNG the size of the frame, white where the
 * user painted, and uploaded as an ordinary asset so the post job can name it by id.
 */
function MaskPainter({ poster, text, onSubmit, onCancel }: {
  poster: string;
  text: Text;
  onSubmit: (blob: Blob) => void;
  onCancel: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [brush, setBrush] = useState(24);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);
  const painting = useRef(false);

  useEffect(() => {
    const image = new Image();
    image.onload = () => {
      setSize({ w: image.naturalWidth, h: image.naturalHeight });
    };
    image.src = poster;
  }, [poster]);

  const draw = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const element = canvas.current;
    if (!element || !painting.current) return;
    const rect = element.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * element.width;
    const y = ((event.clientY - rect.top) / rect.height) * element.height;
    const context = element.getContext('2d');
    if (!context) return;
    context.fillStyle = '#ffffff';
    context.beginPath();
    context.arc(x, y, brush, 0, Math.PI * 2);
    context.fill();
  };
  const clear = () => {
    const element = canvas.current;
    const context = element?.getContext('2d');
    if (element && context) {
      context.fillStyle = '#000000';
      context.fillRect(0, 0, element.width, element.height);
    }
  };
  useEffect(() => {
    if (size) clear();
  }, [size]);

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[10px] text-muted-foreground">{text.paintMask}</p>
      <div className="relative w-full overflow-hidden rounded-sm bg-[#111]">
        <img src={poster} alt="" className="block w-full" />
        {size ? (
          <canvas
            ref={canvas}
            width={size.w}
            height={size.h}
            className="absolute inset-0 h-full w-full cursor-crosshair opacity-50 mix-blend-screen"
            onPointerDown={(event) => { painting.current = true; draw(event); }}
            onPointerMove={draw}
            onPointerUp={() => { painting.current = false; }}
            onPointerLeave={() => { painting.current = false; }}
          />
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[10px]">
        <label className="flex items-center gap-1">{text.brush}
          <input type="range" min={4} max={80} value={brush} onChange={(event) => setBrush(Number(event.target.value))} />
        </label>
        <button type="button" onClick={clear} className="rounded-sm border border-border px-2 py-1">{text.clear}</button>
        <button
          type="button"
          onClick={() => canvas.current?.toBlob((blob) => { if (blob) onSubmit(blob); }, 'image/png')}
          className="rounded-sm bg-foreground px-2 py-1 font-bold text-white"
        >
          {text.submitClean}
        </button>
        <button type="button" onClick={onCancel} className="rounded-sm border border-border px-2 py-1">{text.cancel}</button>
      </div>
    </div>
  );
}

export function PostBoard({ plan, locale }: { plan: FactoryPlan | null; locale: PostLocale }) {
  const text = postCopy[locale];
  const [listing, setListing] = useState<PostListing | null>(null);
  const [accepted, setAccepted] = useState<Record<string, FactoryTake>>({});
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<Record<string, string>>({});
  const [painting, setPainting] = useState('');
  const [scale, setScale] = useState<Record<string, 2 | 4>>({});
  const [fps, setFps] = useState<Record<string, number>>({});
  // Polling runs while a submitted job has not yet appeared as a version: the count of versions
  // at submission time is remembered, and the poll stops once the listing shows more than that.
  const [pending, setPending] = useState(0);
  const expected = useRef(0);

  const planId = plan?.id;
  useEffect(() => {
    if (!planId) return;
    let cancelled = false;
    const load = async () => {
      try {
        const [post, takes] = await Promise.all([projectPost(planId), projectTakes(planId)]);
        if (cancelled) return;
        setListing(post);
        const chosen: Record<string, FactoryTake> = {};
        for (const shot of plan?.shots ?? []) {
          const take = (takes[shot.id] ?? []).find((item) => item.id === shot.acceptedTakeId);
          if (take) chosen[shot.id] = take;
        }
        setAccepted(chosen);
      } catch (error) {
        if (!cancelled) setNotice((current) => ({ ...current, page: error instanceof Error ? error.message : String(error) }));
      }
    };
    void load();
    // While a submitted job has not yet appeared as a version, keep looking.
    const timer = pending > 0 ? window.setInterval(() => void load(), 4000) : undefined;
    return () => {
      cancelled = true;
      if (timer) window.clearInterval(timer);
    };
  }, [planId, plan?.updatedAt, plan?.shots, pending]);

  useEffect(() => {
    if (!listing || pending === 0) return;
    const total = Object.values(listing.versions).reduce((n, list) => n + list.length, 0);
    if (total >= expected.current) setPending(0);
  }, [listing, pending]);

  if (!plan || !plan.shots.length || !Object.keys(accepted).length) {
    return (
      <section className="rounded-md border border-border bg-white p-6 text-center">
        <p className="text-[13px] text-muted-foreground">{text.empty}</p>
      </section>
    );
  }
  const service = listing?.service ?? { available: false, rife_available: false, ops: [] };

  const submit = async (shot: FactoryShot, take: FactoryTake, body: Parameters<typeof postTake>[1]) => {
    setBusy(take.id);
    setNotice((current) => ({ ...current, [shot.id]: '' }));
    try {
      await postTake(take.id, body);
      const total = Object.values(listing?.versions ?? {}).reduce((n, list) => n + list.length, 0);
      expected.current = Math.max(expected.current, total) + 1;
      setPending((current) => current + 1);
      setNotice((current) => ({ ...current, [shot.id]: text.submitted }));
    } catch (error) {
      setNotice((current) => ({ ...current, [shot.id]: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy('');
    }
  };
  const submitClean = async (shot: FactoryShot, take: FactoryTake, blob: Blob) => {
    setBusy(take.id);
    try {
      const response = await serviceFetch(`/api/assets?name=mask-${take.id.slice(0, 8)}.png`, {
        method: 'POST',
        headers: { 'Content-Type': 'image/png' },
        body: blob,
      });
      if (!response.ok) throw new Error(`mask upload failed: HTTP ${response.status}`);
      const asset = (await response.json()) as { id: string };
      setPainting('');
      await submit(shot, take, { op: 'clean', mask_image_id: asset.id });
    } catch (error) {
      setNotice((current) => ({ ...current, [shot.id]: error instanceof Error ? error.message : String(error) }));
      setBusy('');
    }
  };

  return (
    <section className="flex flex-col gap-4">
      <div className="rounded-md border border-border bg-white px-4 py-3 text-[11px]">
        {!service.available ? <p className="text-[#a8365a]">{text.serviceDown}</p> : null}
        {service.available && !service.rife_available ? <p className="text-[#7a5a00]">{text.rifeMissing}</p> : null}
        <p className="text-muted-foreground">{text.mqNote}</p>
        {notice.page ? <p className="text-[#e85578]">{notice.page}</p> : null}
      </div>
      <ol className="flex flex-col gap-3">
        {plan.shots.map((shot, index) => {
          const take = accepted[shot.id];
          const versions = listing?.versions[shot.id] ?? [];
          return (
            <li key={shot.id} className="rounded-md border border-border bg-white">
              <div className="flex flex-wrap items-baseline gap-3 border-b border-border px-4 py-2">
                <span className="font-mono text-[12px] font-bold tabular-nums">{String(index + 1).padStart(2, '0')}</span>
                <span className="text-[12px] font-bold">{shot.title}</span>
                {!take ? <span className="text-[10px] text-muted-foreground">{text.noAccepted}</span> : null}
              </div>
              {take ? (
                <div className="grid gap-3 p-3 md:grid-cols-[240px_1fr]">
                  <div className="flex flex-col gap-2">
                    {take.posterUrl ? <img src={take.posterUrl} alt="" className="aspect-video w-full rounded-sm bg-[#111] object-cover" /> : <div className="aspect-video w-full rounded-sm bg-[#f3f0ec]" />}
                    {painting === take.id && take.posterUrl ? (
                      <MaskPainter poster={take.posterUrl} text={text} onCancel={() => setPainting('')} onSubmit={(blob) => void submitClean(shot, take, blob)} />
                    ) : (
                      <div className="flex flex-wrap items-center gap-2 text-[10px]">
                        <select value={scale[shot.id] ?? 2} onChange={(event) => setScale((c) => ({ ...c, [shot.id]: Number(event.target.value) as 2 | 4 }))} className="rounded-sm border border-border px-1 py-1">
                          <option value={2}>{text.scale} \u00d72</option>
                          <option value={4}>{text.scale} \u00d74</option>
                        </select>
                        <button type="button" disabled={!service.available || busy === take.id} onClick={() => void submit(shot, take, { op: 'upscale', scale: scale[shot.id] ?? 2 })} className="rounded-sm bg-foreground px-2 py-1 font-bold text-white disabled:opacity-40">{text.upscale}</button>
                        <button type="button" disabled={!service.available || busy === take.id || !take.posterUrl} onClick={() => setPainting(take.id)} className="rounded-sm border border-border px-2 py-1 hover:bg-[#faf9f7] disabled:opacity-40">{text.clean}</button>
                        <input type="number" min={2} max={120} value={fps[shot.id] ?? 48} onChange={(event) => setFps((c) => ({ ...c, [shot.id]: Number(event.target.value) }))} className="w-16 rounded-sm border border-border px-1 py-1 font-mono" title={text.targetFps} />
                        <button type="button" disabled={!service.rife_available || busy === take.id} title={service.rife_available ? undefined : text.rifeMissing} onClick={() => void submit(shot, take, { op: 'interpolate', target_fps: fps[shot.id] ?? 48 })} className="rounded-sm border border-border px-2 py-1 hover:bg-[#faf9f7] disabled:opacity-40">{text.interpolate}</button>
                      </div>
                    )}
                    {notice[shot.id] ? <p className="text-[10px] text-[#a8365a]">{notice[shot.id]}</p> : null}
                  </div>
                  <div>
                    <p className="text-[10px] font-bold">{text.versions}</p>
                    {versions.length === 0 ? <p className="text-[10px] text-muted-foreground">{text.noVersions}</p> : (
                      <ul className="mt-1 flex flex-col gap-1 text-[10px]">
                        {versions.map((version) => {
                          const post = version.post!;
                          const label = post.op === 'upscale'
                            ? fill(text.op.upscale, { scale: String(post.parameters?.scale ?? '') })
                            : post.op === 'interpolate'
                              ? fill(text.op.interpolate, { fps: String(post.parameters?.fps ?? '') })
                              : text.op.clean;
                          return (
                            <li key={version.id} className="flex flex-wrap items-center gap-2 rounded-sm border border-border px-2 py-1">
                              <span className="font-bold">{label}</span>
                              {post.failed ? <span className="text-[#a8365a]">{text.failed}{version.reason ? ` \u00b7 ${version.reason}` : ''}</span>
                                : version.scores ? <span className="text-[#1f6b48]">{text.scored}</span>
                                  : <span className="text-muted-foreground">{text.processing}</span>}
                              {version.outputUrl && !post.failed ? <a href={version.outputUrl} target="_blank" rel="noreferrer" className="underline">mp4</a> : null}
                            </li>
                          );
                        })}
                      </ul>
                    )}
                  </div>
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
