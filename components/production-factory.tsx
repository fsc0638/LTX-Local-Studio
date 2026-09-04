'use client';
/* eslint-disable jsx-a11y/media-has-caption -- Generated local videos do not have caption tracks. */

import { useEffect, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  CirclePause,
  CirclePlay,
  Download,
  Factory,
  FileJson,
  Plus,
  RotateCcw,
  Trash2,
  Upload,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DeleteMediaButton } from '@/components/delete-media-button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Textarea } from '@/components/ui/textarea';
import { serviceFetch } from '@/lib/service-session';
import {
  MAX_FACTORY_SHOTS,
  activeFactoryShot,
  clearFactoryShotOutput,
  createFactoryPlan,
  createFactoryShot,
  nextQueuedShot,
  parseFactoryImport,
  reopenFactoryShot,
  restoreFactoryPlan,
  serializeFactoryPlan,
  summarizeFactory,
  type FactoryPlan,
  type FactoryRequest,
  type FactoryShot,
  type FactoryShotState,
} from '@/lib/production-factory';

type Locale = 'zh-TW' | 'en' | 'ja';
export type FactoryIncoming = {
  token: string;
  request: FactoryRequest;
};

type WorkerJob = {
  id: string;
  status: string;
  status_url?: string;
  output_url?: string;
  poster_url?: string;
  progress?: number;
  message?: string;
  error?: string | { message?: string };
  artifacts?: { kind: string; url: string }[];
};

const copy = {
  'zh-TW': {
    eyebrow: '02 / 製片工廠',
    title: '批次鏡頭生產線',
    note: '把已設定完成的鏡頭排入同一條生產線，依序使用本機唯一 GPU。每鏡先驗證、再生成，失敗即暫停，避免後續鏡頭盲目消耗資源。',
    localNote:
      'V1 計畫保存在目前瀏覽器的帳號空間。關閉頁面時，已送出的鏡頭會繼續；重新開啟後才會接續送出下一鏡。可隨時匯出 JSON 交接。',
    project: '製片名稱',
    total: '總鏡數',
    waiting: '待製作',
    active: '製作中',
    completed: '已完成',
    failed: '需處理',
    addBlank: '新增空白鏡頭',
    import: '匯入製片 JSON',
    export: '匯出製片 JSON',
    start: '啟動生產線',
    resume: '繼續生產',
    pause: '完成目前鏡頭後暫停',
    queueEmpty: '先從「生成」頁把設定加入製片工廠，或新增空白鏡頭。',
    shot: '鏡頭',
    prompt: '鏡頭提示詞',
    defaultPrompt: '電影感鏡頭，清楚描述場景、主體、動作、運鏡與光線。',
    remove: '移除鏡頭',
    retry: '修正後重試',
    rework: '修改／重做',
    reworkNote: '保留目前成品作為前次版本，重新開放此鏡頭修改與生產。',
    result: '成品／前次版本',
    download: '下載',
    noResult: '完成的鏡頭會顯示在這裡',
    workerBusy: 'GPU 正在處理其他任務，保留順位等待。',
    validating: '正在驗證鏡頭設定',
    submitting: '正在送入本機 GPU',
    invalid: '鏡頭設定未通過驗證',
    requestFailed: '無法連接影片服務，生產線已暫停。',
    imported: '已匯入新的製片計畫。',
    importFailed: '無法匯入製片 JSON。',
    offline: '影片服務離線；計畫仍可編輯，但不能啟動生產。',
    activePause: '已停止送出新鏡頭；目前 GPU 任務仍會安全完成。',
    deleteNote: '移除只刪除製片計畫列，不會刪除已生成成品。',
    outputDeleted: '成品已移到本機私有回收區；鏡頭設定仍保留，可修改後重做。',
  },
  en: {
    eyebrow: '02 / PRODUCTION FACTORY',
    title: 'Batch shot production line',
    note: 'Queue configured shots on one production line and use the host GPU in order. Every shot is validated before generation; a failure pauses the line to prevent blind GPU spend.',
    localNote:
      'V1 plans are stored per account in this browser. A submitted shot keeps running if the page closes; reopen the page to dispatch the next shot. Export JSON at any time for handoff.',
    project: 'Production title',
    total: 'Total shots',
    waiting: 'Waiting',
    active: 'In production',
    completed: 'Completed',
    failed: 'Needs action',
    addBlank: 'Add blank shot',
    import: 'Import factory JSON',
    export: 'Export factory JSON',
    start: 'Start production line',
    resume: 'Resume production',
    pause: 'Pause after current shot',
    queueEmpty:
      'Add the current setup from Create, or start with a blank shot.',
    shot: 'Shot',
    prompt: 'Shot prompt',
    defaultPrompt:
      'A cinematic shot describing the scene, subject, action, camera and light.',
    remove: 'Remove shot',
    retry: 'Fix and retry',
    rework: 'Edit / remake',
    reworkNote:
      'Keep the current output as the previous take and reopen this shot for editing and production.',
    result: 'Outputs / previous takes',
    download: 'Download',
    noResult: 'Completed shots will appear here',
    workerBusy: 'The GPU is handling another job. This shot keeps its place.',
    validating: 'Validating shot settings',
    submitting: 'Sending shot to the local GPU',
    invalid: 'Shot settings did not pass validation',
    requestFailed: 'The video service is unavailable. The line is paused.',
    imported: 'A new production plan was imported.',
    importFailed: 'Could not import the production JSON.',
    offline:
      'The video service is offline. You can edit the plan but cannot start production.',
    activePause:
      'New dispatches are paused; the current GPU job will finish safely.',
    deleteNote: 'Removing a row does not delete an already generated output.',
    outputDeleted:
      'The output was moved to private local trash. The shot settings remain available for another take.',
  },
  ja: {
    eyebrow: '02 / 制作ファクトリー',
    title: 'ショット一括制作ライン',
    note: '設定済みショットを一つのラインに並べ、ホストGPUへ順番に送ります。各ショットは生成前に検証され、失敗時は停止して不要なGPU消費を防ぎます。',
    localNote:
      'V1計画はこのブラウザのアカウント領域に保存されます。送信済みショットはページを閉じても継続し、再度開くと次のショットを送信します。JSONで引き継げます。',
    project: '制作タイトル',
    total: '総ショット',
    waiting: '待機',
    active: '制作中',
    completed: '完了',
    failed: '要対応',
    addBlank: '空のショットを追加',
    import: '制作JSONを読み込む',
    export: '制作JSONを書き出す',
    start: '制作ラインを開始',
    resume: '制作を再開',
    pause: '現在のショット後に停止',
    queueEmpty:
      '「生成」から現在の設定を追加するか、空のショットを作成してください。',
    shot: 'ショット',
    prompt: 'ショットプロンプト',
    defaultPrompt: '場面、被写体、動作、カメラ、光を明確にした映画的ショット。',
    remove: 'ショットを削除',
    retry: '修正して再試行',
    rework: '修正／再制作',
    reworkNote:
      '現在の成果を前回版として残し、このショットを編集・再制作できる状態に戻します。',
    result: '成果／前回版',
    download: 'ダウンロード',
    noResult: '完成したショットはここに表示されます',
    workerBusy: 'GPUは別のタスクを処理中です。順番を保持して待機します。',
    validating: 'ショット設定を検証中',
    submitting: 'ローカルGPUへ送信中',
    invalid: 'ショット設定の検証に失敗しました',
    requestFailed: '動画サービスに接続できません。制作ラインを停止しました。',
    imported: '新しい制作計画を読み込みました。',
    importFailed: '制作JSONを読み込めませんでした。',
    offline:
      '動画サービスはオフラインです。計画編集はできますが制作は開始できません。',
    activePause: '新規送信を停止しました。現在のGPUタスクは安全に完了します。',
    deleteNote: '行を削除しても生成済み成果は削除されません。',
    outputDeleted:
      '成果を本機の非公開ごみ箱へ移動しました。ショット設定は残っているため、修正して再制作できます。',
  },
} as const;

const terminal = new Set(['succeeded', 'failed', 'cancelled', 'interrupted']);

function errorMessage(value: WorkerJob, fallback: string): string {
  if (typeof value.error === 'string') return value.error;
  return value.error?.message || value.message || fallback;
}

function statusTone(status: FactoryShotState): string {
  if (status === 'succeeded') return 'bg-[#e9f8f5] text-[#11786f]';
  if (status === 'failed') return 'bg-red-50 text-red-700';
  if (['validating', 'submitting', 'running'].includes(status))
    return 'bg-[#fff0f3] text-[#c53d60]';
  return 'bg-[#f2f2ef] text-muted-foreground';
}

function requestMeta(request: FactoryRequest): string {
  const duration = Number(request.duration_seconds || 0);
  const model =
    typeof request.model === 'string' ? request.model : 'ltx23-distilled';
  const mode = typeof request.mode === 'string' ? request.mode : 't2v';
  const aspectRatio =
    typeof request.aspect_ratio === 'string' ? request.aspect_ratio : undefined;
  const fps = Number(request.fps || 0);
  return [
    model,
    mode,
    aspectRatio,
    duration > 0 ? `${duration}s` : undefined,
    fps > 0 ? `${fps} FPS` : undefined,
  ]
    .filter(Boolean)
    .join(' · ');
}

export function ProductionFactory({
  locale,
  online,
  incoming,
  onIncomingConsumed,
}: {
  locale: Locale;
  online: boolean;
  incoming: FactoryIncoming | null;
  onIncomingConsumed: () => void;
}) {
  const text = copy[locale];
  const [plan, setPlan] = useState<FactoryPlan>(() =>
    createFactoryPlan('pending', new Date(0)),
  );
  const [hydrated, setHydrated] = useState(false);
  const [storageKey, setStorageKey] = useState('');
  const [notice, setNotice] = useState('');
  const importInput = useRef<HTMLInputElement>(null);
  const planRef = useRef(plan);
  const consumed = useRef(new Set<string>());

  const mutate = (change: (current: FactoryPlan) => FactoryPlan) =>
    setPlan((current) => ({
      ...change(current),
      updatedAt: new Date().toISOString(),
    }));

  const patchShot = (
    id: string,
    change: (shot: FactoryShot) => FactoryShot,
    runStatus?: FactoryPlan['status'],
  ) =>
    mutate((current) => ({
      ...current,
      status: runStatus || current.status,
      shots: current.shots.map((shot) =>
        shot.id === id ? change(shot) : shot,
      ),
    }));

  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  useEffect(() => {
    const abort = new AbortController();
    void serviceFetch('/api/auth/session', { signal: abort.signal })
      .then(async (response) =>
        response.ok
          ? (response.json() as Promise<{ user?: { id?: string } }>)
          : Promise.reject(),
      )
      .catch(() => ({}))
      .then((session: { user?: { id?: string } }) => {
        if (abort.signal.aborted) return;
        const key = `ltx-production-factory-v1:${session.user?.id || 'local'}`;
        let restored: FactoryPlan | undefined;
        try {
          const saved = window.localStorage.getItem(key);
          if (saved) restored = restoreFactoryPlan(JSON.parse(saved));
        } catch {
          window.localStorage.removeItem(key);
        }
        setStorageKey(key);
        setPlan(restored || createFactoryPlan(crypto.randomUUID()));
        setHydrated(true);
      });
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (!hydrated || !storageKey) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(plan));
    } catch {
      // The current in-memory queue stays usable when browser storage is denied.
    }
  }, [hydrated, plan, storageKey]);

  useEffect(() => {
    if (!hydrated || !incoming || consumed.current.has(incoming.token)) return;
    consumed.current.add(incoming.token);
    // eslint-disable-next-line react/react-compiler -- This external parent event is intentionally consumed into persisted factory state.
    mutate((current) => {
      if (current.shots.length >= MAX_FACTORY_SHOTS) return current;
      const shot = createFactoryShot(
        incoming.request,
        crypto.randomUUID(),
        current.shots.length,
      );
      if (current.status === 'running') shot.status = 'queued';
      return {
        ...current,
        status: current.status === 'completed' ? 'paused' : current.status,
        shots: [...current.shots, shot],
      };
    });
    onIncomingConsumed();
  }, [hydrated, incoming, onIncomingConsumed]);

  useEffect(() => {
    if (!hydrated) return;
    let disposed = false;
    let pending = false;

    const tick = async () => {
      if (disposed || pending) return;
      const current = planRef.current;
      const active = activeFactoryShot(current);
      if (!active && current.status !== 'running') return;
      pending = true;
      try {
        if (active?.status === 'running' && active.statusUrl) {
          const response = await serviceFetch(active.statusUrl);
          const job = (await response.json()) as WorkerJob;
          if (!response.ok)
            throw new Error(errorMessage(job, text.requestFailed));
          if (!terminal.has(job.status)) {
            patchShot(active.id, (shot) => ({
              ...shot,
              progress: job.progress || 0,
              message: job.message,
            }));
            return;
          }
          if (job.status === 'succeeded') {
            const artifact = job.artifacts?.find(
              (item) => item.kind === 'video',
            );
            patchShot(active.id, (shot) => ({
              ...shot,
              status: 'succeeded',
              progress: 100,
              message: job.message,
              outputUrl: job.output_url || artifact?.url,
              posterUrl: job.poster_url,
              error: undefined,
            }));
          } else {
            patchShot(
              active.id,
              (shot) => ({
                ...shot,
                status: 'failed',
                progress: job.progress || shot.progress,
                error: errorMessage(job, text.requestFailed),
              }),
              'paused',
            );
          }
          return;
        }

        const queued = nextQueuedShot(current);
        if (!queued) {
          mutate((value) => ({
            ...value,
            status:
              value.shots.length > 0 &&
              value.shots.every((shot) => shot.status === 'succeeded')
                ? 'completed'
                : 'paused',
          }));
          return;
        }

        patchShot(queued.id, (shot) => ({
          ...shot,
          status: 'validating',
          message: text.validating,
          error: undefined,
        }));
        const validation = await serviceFetch('/api/v1/validate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(queued.request),
        });
        const validationBody = (await validation.json()) as WorkerJob;
        if (!validation.ok) {
          patchShot(
            queued.id,
            (shot) => ({
              ...shot,
              status: 'failed',
              error: errorMessage(validationBody, text.invalid),
              message: undefined,
            }),
            'paused',
          );
          return;
        }

        patchShot(queued.id, (shot) => ({
          ...shot,
          status: 'submitting',
          message: text.submitting,
        }));
        const response = await serviceFetch('/api/v1/jobs', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Idempotency-Key': queued.idempotencyKey,
          },
          body: JSON.stringify(queued.request),
        });
        const job = (await response.json()) as WorkerJob & { code?: string };
        if (response.status === 409 && job.code === 'worker_busy') {
          patchShot(queued.id, (shot) => ({
            ...shot,
            status: 'queued',
            message: text.workerBusy,
          }));
          return;
        }
        if (!response.ok) {
          patchShot(
            queued.id,
            (shot) => ({
              ...shot,
              status: 'failed',
              error: errorMessage(job, text.requestFailed),
              message: undefined,
            }),
            'paused',
          );
          return;
        }
        patchShot(queued.id, (shot) => ({
          ...shot,
          status: job.status === 'succeeded' ? 'succeeded' : 'running',
          jobId: job.id,
          statusUrl: job.status_url || `/api/v1/jobs/${job.id}`,
          outputUrl: job.output_url,
          posterUrl: job.poster_url,
          progress: job.progress || 0,
          message: job.message,
        }));
      } catch (error) {
        const activeNow = activeFactoryShot(planRef.current);
        if (activeNow) {
          patchShot(
            activeNow.id,
            (shot) => ({
              ...shot,
              status: shot.jobId ? 'running' : 'queued',
              error:
                error instanceof Error ? error.message : text.requestFailed,
            }),
            'paused',
          );
        } else {
          mutate((value) => ({ ...value, status: 'paused' }));
        }
        setNotice(text.requestFailed);
      } finally {
        pending = false;
      }
    };

    void tick();
    const timer = window.setInterval(tick, 3000);
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [
    hydrated,
    text.invalid,
    text.requestFailed,
    text.submitting,
    text.validating,
    text.workerBusy,
  ]);

  const summary = summarizeFactory(plan);
  const active = activeFactoryShot(plan);
  const editable = !active && plan.status !== 'running';
  const completedShots = plan.shots.filter((shot) => shot.outputUrl);

  const freshIdempotencyKey = (shot: FactoryShot) =>
    `factory-${shot.id}-${crypto.randomUUID().slice(0, 8)}`;

  const reopen = (id: string) =>
    patchShot(
      id,
      (shot) => reopenFactoryShot(shot, freshIdempotencyKey(shot)),
      'paused',
    );

  const addBlank = () => {
    if (plan.shots.length >= MAX_FACTORY_SHOTS) return;
    mutate((current) => ({
      ...current,
      status: current.status === 'completed' ? 'paused' : current.status,
      shots: [
        ...current.shots,
        createFactoryShot(
          {
            prompt: text.defaultPrompt,
            model: 'ltx23-distilled',
            mode: 't2v',
            aspect_ratio: '16:9',
            duration_seconds: 4,
            fps: 24,
            seed: 42 + current.shots.length,
            audio: true,
          },
          crypto.randomUUID(),
          current.shots.length,
        ),
      ],
    }));
  };

  const start = () => {
    setNotice('');
    mutate((current) => ({
      ...current,
      status: 'running',
      shots: current.shots.map((shot) =>
        shot.status === 'draft' ? { ...shot, status: 'queued' } : shot,
      ),
    }));
  };

  const retry = (id: string) =>
    patchShot(id, (shot) => ({
      ...shot,
      status: 'queued',
      idempotencyKey: `factory-${shot.id}-${crypto.randomUUID().slice(0, 8)}`,
      jobId: undefined,
      statusUrl: undefined,
      outputUrl: undefined,
      posterUrl: undefined,
      progress: 0,
      error: undefined,
      message: undefined,
    }));

  const move = (index: number, direction: -1 | 1) =>
    mutate((current) => {
      const target = index + direction;
      if (target < 0 || target >= current.shots.length) return current;
      const shots = [...current.shots];
      [shots[index], shots[target]] = [shots[target], shots[index]];
      return { ...current, shots };
    });

  const exportPlan = () => {
    const blob = new Blob([serializeFactoryPlan(plan)], {
      type: 'application/json',
    });
    const href = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = href;
    link.download = `ltx-production-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(href);
  };

  const importPlan = async (file?: File) => {
    if (!file) return;
    try {
      if (file.size > 1_000_000) throw new Error();
      const imported = parseFactoryImport(await file.text(), () =>
        crypto.randomUUID(),
      );
      setPlan(imported);
      setNotice(text.imported);
    } catch {
      setNotice(text.importFailed);
    } finally {
      if (importInput.current) importInput.current.value = '';
    }
  };

  return (
    <section>
      <div className="mb-8 flex flex-col justify-between gap-5 border-b border-border pb-6 lg:flex-row lg:items-end">
        <div className="max-w-3xl">
          <p className="mb-2 text-[10px] font-bold tracking-[0.18em] text-[#e85578]">
            {text.eyebrow}
          </p>
          <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
            {text.title}
          </h1>
          <p className="mt-3 text-xs leading-6 text-muted-foreground">
            {text.note}
          </p>
        </div>
        <div className="flex items-center gap-2 border border-[#bfe8e3] bg-[#f0fbf9] px-4 py-3 text-[10px] font-bold text-[#11786f]">
          <Factory className="size-4" />
          {plan.status.toUpperCase()}
        </div>
      </div>

      <div className="mb-6 grid gap-px bg-border sm:grid-cols-5">
        {[
          [text.total, summary.total],
          [text.waiting, summary.waiting],
          [text.active, summary.active],
          [text.completed, summary.completed],
          [text.failed, summary.failed],
        ].map(([label, value]) => (
          <div key={label} className="bg-white p-4">
            <p className="text-[9px] font-bold tracking-[0.16em] text-muted-foreground">
              {label}
            </p>
            <p className="mt-2 text-2xl font-black">{value}</p>
          </div>
        ))}
      </div>

      {!online && (
        <p
          role="alert"
          className="mb-5 border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"
        >
          {text.offline}
        </p>
      )}
      {notice && (
        <p className="mb-5 border border-border bg-white p-4 text-xs">
          {notice}
        </p>
      )}

      <div className="grid gap-6 xl:grid-cols-[1.45fr_.75fr]">
        <div className="space-y-5">
          <section className="border border-border bg-white p-5">
            <label className="block text-[10px] font-bold tracking-[0.12em]">
              {text.project}
              <Input
                value={plan.title}
                maxLength={120}
                disabled={!editable}
                onChange={(event) =>
                  mutate((current) => ({
                    ...current,
                    title: event.target.value,
                  }))
                }
                className="mt-2 h-12 rounded-none text-sm font-extrabold"
              />
            </label>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                className="rounded-none"
                disabled={!editable || plan.shots.length >= MAX_FACTORY_SHOTS}
                onClick={addBlank}
              >
                <Plus /> {text.addBlank}
              </Button>
              <input
                ref={importInput}
                type="file"
                accept="application/json,.json"
                className="hidden"
                onChange={(event) => void importPlan(event.target.files?.[0])}
              />
              <Button
                type="button"
                variant="outline"
                className="rounded-none"
                disabled={!editable}
                onClick={() => importInput.current?.click()}
              >
                <Upload /> {text.import}
              </Button>
              <Button
                type="button"
                variant="outline"
                className="rounded-none"
                disabled={!plan.shots.length}
                onClick={exportPlan}
              >
                <FileJson /> {text.export}
              </Button>
            </div>
          </section>

          {!plan.shots.length ? (
            <div className="grid min-h-72 place-items-center border border-dashed border-border bg-[#fafaf8] p-8 text-center text-sm text-muted-foreground">
              {text.queueEmpty}
            </div>
          ) : (
            <div className="space-y-3">
              {plan.shots.map((shot, index) => {
                const shotEditable = editable;
                return (
                  <article
                    key={shot.id}
                    className="border border-border bg-white"
                  >
                    <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
                      <span className="grid size-8 place-items-center bg-foreground text-[10px] font-black text-background">
                        {String(index + 1).padStart(2, '0')}
                      </span>
                      <Input
                        aria-label={`${text.shot} ${index + 1}`}
                        value={shot.title}
                        maxLength={120}
                        disabled={!shotEditable}
                        onChange={(event) =>
                          patchShot(shot.id, (current) => ({
                            ...current,
                            title: event.target.value,
                          }))
                        }
                        className="h-9 min-w-48 flex-1 rounded-none border-0 bg-transparent px-0 text-xs font-extrabold shadow-none focus-visible:ring-0"
                      />
                      <span
                        className={`px-2 py-1 text-[9px] font-black tracking-[0.12em] ${statusTone(shot.status)}`}
                      >
                        {shot.status.toUpperCase()}
                      </span>
                      <div className="flex gap-1">
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          disabled={!shotEditable || index === 0}
                          aria-label="Move up"
                          onClick={() => move(index, -1)}
                        >
                          <ArrowUp />
                        </Button>
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          disabled={
                            !shotEditable || index === plan.shots.length - 1
                          }
                          aria-label="Move down"
                          onClick={() => move(index, 1)}
                        >
                          <ArrowDown />
                        </Button>
                        <Button
                          type="button"
                          size="icon-sm"
                          variant="ghost"
                          disabled={!shotEditable}
                          aria-label={text.remove}
                          title={text.deleteNote}
                          onClick={() =>
                            mutate((current) => ({
                              ...current,
                              shots: current.shots.filter(
                                (item) => item.id !== shot.id,
                              ),
                            }))
                          }
                        >
                          <Trash2 />
                        </Button>
                      </div>
                    </div>
                    <div className="grid gap-4 p-4 lg:grid-cols-[1fr_auto]">
                      <label className="text-[10px] font-bold">
                        {text.prompt}
                        <Textarea
                          value={shot.request.prompt}
                          maxLength={4000}
                          disabled={!shotEditable}
                          onChange={(event) =>
                            patchShot(
                              shot.id,
                              (current) => ({
                                ...reopenFactoryShot(
                                  current,
                                  current.status === 'draft'
                                    ? current.idempotencyKey
                                    : freshIdempotencyKey(current),
                                ),
                                request: {
                                  ...current.request,
                                  prompt: event.target.value,
                                },
                              }),
                              plan.status === 'completed'
                                ? 'paused'
                                : undefined,
                            )
                          }
                          className="mt-2 min-h-24 rounded-none bg-[#fafaf8] text-xs"
                        />
                      </label>
                      <div className="min-w-44 text-[10px] leading-5 text-muted-foreground lg:text-right">
                        {requestMeta(shot.request)}
                      </div>
                    </div>
                    {['validating', 'submitting', 'running'].includes(
                      shot.status,
                    ) && (
                      <div className="space-y-2 border-t border-border p-4">
                        <Progress
                          value={shot.progress}
                          className="h-1.5 rounded-none [&>div]:bg-[#25b6a6]"
                        />
                        <p className="text-[10px] text-muted-foreground">
                          {shot.message}
                        </p>
                      </div>
                    )}
                    {shot.error && (
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-red-100 bg-red-50 p-4 text-[10px] text-red-700">
                        <span>{shot.error}</span>
                        <Button
                          type="button"
                          variant="outline"
                          className="rounded-none bg-white"
                          onClick={() => retry(shot.id)}
                        >
                          <RotateCcw /> {text.retry}
                        </Button>
                      </div>
                    )}
                    {shot.outputUrl && editable && (
                      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border bg-[#fafaf8] p-4">
                        <p className="text-[10px] leading-5 text-muted-foreground">
                          {text.reworkNote}
                        </p>
                        <Button
                          type="button"
                          variant="outline"
                          className="rounded-none bg-white"
                          onClick={() => reopen(shot.id)}
                        >
                          <RotateCcw /> {text.rework}
                        </Button>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          )}
        </div>

        <aside className="space-y-5 self-start xl:sticky xl:top-28">
          <section className="border border-border bg-[#171918] p-5 text-white">
            <div className="flex items-center gap-2 text-xs font-extrabold tracking-[0.14em]">
              <Factory className="size-4 text-[#25b6a6]" />
              {text.title}
            </div>
            <p className="mt-4 text-[10px] leading-5 text-white/60">
              {text.localNote}
            </p>
            <div className="mt-5 space-y-2">
              {plan.status === 'running' ? (
                <Button
                  type="button"
                  variant="outline"
                  className="h-12 w-full rounded-none border-white/25 bg-transparent text-white hover:bg-white hover:text-black"
                  onClick={() => {
                    mutate((current) => ({ ...current, status: 'paused' }));
                    setNotice(text.activePause);
                  }}
                >
                  <CirclePause /> {text.pause}
                </Button>
              ) : (
                <Button
                  type="button"
                  className="h-12 w-full rounded-none bg-[#e85578] text-white hover:bg-[#d8486b]"
                  disabled={
                    !online ||
                    !plan.shots.some((shot) =>
                      ['draft', 'queued'].includes(shot.status),
                    ) ||
                    Boolean(active)
                  }
                  onClick={start}
                >
                  <CirclePlay />{' '}
                  {plan.status === 'draft' ? text.start : text.resume}
                </Button>
              )}
            </div>
          </section>

          <section className="border border-border bg-white">
            <div className="border-b border-border px-5 py-4 text-xs font-extrabold tracking-[0.12em]">
              {text.result} · {completedShots.length}
            </div>
            {!completedShots.length ? (
              <div className="grid min-h-48 place-items-center p-6 text-center text-xs text-muted-foreground">
                {text.noResult}
              </div>
            ) : (
              <div className="max-h-[620px] divide-y divide-border overflow-auto">
                {completedShots.map((shot) => (
                  <article key={shot.id} className="p-4">
                    <video
                      controls
                      preload="metadata"
                      poster={shot.posterUrl}
                      src={shot.outputUrl?.replace('?download=1', '')}
                      className="aspect-video w-full bg-black object-contain"
                    />
                    <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                      <p className="truncate text-xs font-bold">{shot.title}</p>
                      <div className="flex items-center gap-2">
                        <a
                          href={`${shot.outputUrl}${shot.outputUrl?.includes('?') ? '&' : '?'}download=1`}
                          className="flex shrink-0 items-center gap-1 text-[10px] font-bold text-[#e85578]"
                        >
                          <Download className="size-3" /> {text.download}
                        </a>
                        {shot.jobId && (
                          <DeleteMediaButton
                            locale={locale}
                            kind="jobs"
                            id={shot.jobId}
                            name={shot.title}
                            disabled={!editable}
                            onDeleted={() => {
                              patchShot(
                                shot.id,
                                (current) =>
                                  clearFactoryShotOutput(
                                    current,
                                    freshIdempotencyKey(current),
                                  ),
                                'paused',
                              );
                              setNotice(text.outputDeleted);
                            }}
                          />
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </section>
  );
}
