'use client';
/* eslint-disable jsx-a11y/media-has-caption -- Generated local videos do not have caption tracks. */

import { useEffect, useRef, useState } from 'react';
import {
  ArrowDown,
  ArrowUp,
  Braces,
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
import {
  CharacterLock,
  type CharacterDraft,
} from '@/components/character-lock';
import { DeleteMediaButton } from '@/components/delete-media-button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import type { Asset } from '@/components/media-library';
import { serviceFetch } from '@/lib/service-session';
import * as factory from '@/lib/factory-client';
import {
  MAX_FACTORY_SHOTS,
  activeFactoryShot,
  bibleFromRequest,
  clearFactoryShotOutput,
  countPinnedShots,
  createFactoryPlan,
  createFactoryShot,
  hasFactoryBible,
  normalizeFactoryRequest,
  parseFactoryImport,
  pinFactoryField,
  projectBible,
  reprojectShots,
  reopenFactoryShot,
  serializeFactoryPlan,
  summarizeFactory,
  unpinFactoryField,
  type FactoryPlan,
  type FactoryBible,
  type FactoryRequest,
  type FactoryShot,
  type FactoryShotState,
} from '@/lib/production-factory';

type Locale = 'zh-TW' | 'en' | 'ja';
export type FactoryIncoming = {
  token: string;
  request: FactoryRequest;
  bible?: FactoryBible;
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
    addBlank: '新增鏡頭',
    bible: '00 / 專案 Bible',
    bibleHint: '先固定角色、音樂與輸出規格；新增鏡頭會繼承這些設定。',
    bibleRequired: '請先設定專案 Bible，再新增鏡頭。',
    legacyFound: '這個瀏覽器還留著一份舊版計畫（{count} 鏡）。要上傳到主機嗎？上傳後即可關掉分頁繼續生產。',
    legacyUpload: '上傳到主機',
    legacyDiscard: '不用了',
    legacyDone: '已上傳到主機；瀏覽器裡的舊副本已清除。',
    music: '音樂母帶',
    noMusic: '不使用音樂',
    output: '輸出規格',
    inherited: '繼承',
    overridden: '此鏡覆寫',
    restore: '還原繼承',
    allSettings: '全部設定',
    outgoingJson: '即將送出的 JSON',
    valid: '設定驗證通過',
    reprojected: 'Bible 已套用；{count} 鏡保留覆寫欄位。',
    import: '匯入製片 JSON',
    export: '匯出製片 JSON',
    start: '啟動生產線',
    resume: '繼續生產',
    pause: '完成目前鏡頭後暫停',
    queueEmpty: '先從「生成」頁把設定加入製片工廠，或新增空白鏡頭。',
    shot: '鏡頭',
    prompt: '鏡頭提示詞',
    draft: '起草',
    drafting: '起草中…',
    draftUnavailable: '主機未設定 OpenAI，無法起草。',
    draftFailed: '起草失敗，請稍後再試。',
    draftBudget: '本專案的起草額度已用完。',
    draftSuggestion: '草稿（不會覆蓋你改過的提示詞）',
    draftApply: '採用',
    draftDismiss: '不用',
    primaryAction: '主要動作',
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
    addBlank: 'Add shot',
    bible: '00 / PROJECT BIBLE',
    bibleHint:
      'Lock character, music and output defaults before adding inherited shots.',
    bibleRequired: 'Set the project Bible before adding a shot.',
    legacyFound: 'This browser still holds an older plan ({count} shots). Upload it to the host? Once uploaded you can close the tab and it keeps running.',
    legacyUpload: 'Upload to the host',
    legacyDiscard: 'No thanks',
    legacyDone: 'Uploaded. The browser copy has been cleared.',
    music: 'Music master',
    noMusic: 'No music',
    output: 'Output defaults',
    inherited: 'Inherited',
    overridden: 'Shot override',
    restore: 'Restore inheritance',
    allSettings: 'All settings',
    outgoingJson: 'Outgoing JSON',
    valid: 'Validation passed',
    reprojected: 'Bible applied; {count} shots keep overrides.',
    import: 'Import factory JSON',
    export: 'Export factory JSON',
    start: 'Start production line',
    resume: 'Resume production',
    pause: 'Pause after current shot',
    queueEmpty:
      'Add the current setup from Create, or start with a blank shot.',
    shot: 'Shot',
    prompt: 'Shot prompt',
    draft: 'Draft',
    drafting: 'Drafting\u2026',
    draftUnavailable: 'This host has no OpenAI key, so drafting is off.',
    draftFailed: 'Drafting failed. Try again in a moment.',
    draftBudget: 'This project has spent its drafting budget.',
    draftSuggestion: 'Draft (your own prompt is left alone)',
    draftApply: 'Use it',
    draftDismiss: 'Discard',
    primaryAction: 'Primary action',
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
    addBlank: 'ショットを追加',
    bible: '00 / プロジェクト Bible',
    bibleHint: '人物、音楽、出力設定を固定してから継承ショットを追加します。',
    bibleRequired: '先にプロジェクト Bible を設定してください。',
    legacyFound: 'このブラウザに旧版の計画（{count} ショット）が残っています。ホストへアップロードしますか？アップロード後はタブを閉じても生成が続きます。',
    legacyUpload: 'ホストへアップロード',
    legacyDiscard: '不要',
    legacyDone: 'アップロードしました。ブラウザ側の複製は削除済みです。',
    music: '音楽マスター',
    noMusic: '音楽なし',
    output: '出力設定',
    inherited: '継承',
    overridden: 'ショット上書き',
    restore: '継承に戻す',
    allSettings: '全設定',
    outgoingJson: '送信予定 JSON',
    valid: '検証済み',
    reprojected: 'Bibleを反映しました。{count}ショットは上書きを保持します。',
    import: '制作JSONを読み込む',
    export: '制作JSONを書き出す',
    start: '制作ラインを開始',
    resume: '制作を再開',
    pause: '現在のショット後に停止',
    queueEmpty:
      '「生成」から現在の設定を追加するか、空のショットを作成してください。',
    shot: 'ショット',
    prompt: 'ショットプロンプト',
    draft: '下書き',
    drafting: '作成中…',
    draftUnavailable: 'ホストに OpenAI キーがないため下書きは使えません。',
    draftFailed: '下書きに失敗しました。しばらくしてからお試しください。',
    draftBudget: 'このプロジェクトの下書き上限に達しました。',
    draftSuggestion: '下書き（編集済みのプロンプトは上書きしません）',
    draftApply: '採用',
    draftDismiss: '破棄',
    primaryAction: '主なアクション',
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


/** Surfaces the host's `code` when it has one; a bare "request failed" hides why. */
function factoryMessage(error: unknown, fallback: string): string {
  if (error instanceof factory.FactoryRequestError) {
    return `${error.message} (${error.code})`;
  }
  return error instanceof Error && error.message ? error.message : fallback;
}

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

function ShotSettings({
  shot,
  disabled,
  labels,
  onChange,
  onRestore,
}: {
  shot: FactoryShot;
  disabled: boolean;
  labels: {
    inherited: string;
    overridden: string;
    restore: string;
    allSettings: string;
    outgoingJson: string;
    valid: string;
    invalid: string;
  };
  onChange: (shot: FactoryShot) => void;
  onRestore: (field: string) => void;
}) {
  const [source, setSource] = useState(() =>
    JSON.stringify(shot.request, null, 2),
  );
  const [validation, setValidation] = useState('');
  const validate = async (request: FactoryRequest) => {
    try {
      const response = await serviceFetch('/api/v1/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
      });
      const result = (await response.json()) as WorkerJob;
      setValidation(
        response.ok ? labels.valid : errorMessage(result, labels.invalid),
      );
    } catch {
      setValidation(labels.invalid);
    }
  };
  return (
    <details className="border-t border-border bg-[#fafaf8] p-4">
      <summary className="flex cursor-pointer items-center gap-2 text-[10px] font-bold">
        <Braces className="size-3.5" /> {labels.allSettings}
      </summary>
      <div className="mt-4 flex flex-wrap gap-2">
        {Object.keys(shot.request)
          .sort()
          .map((field) => {
            const pinned = shot.pinned.includes(field);
            return (
              <Button
                key={field}
                type="button"
                size="sm"
                variant="outline"
                disabled={disabled}
                title={pinned ? labels.restore : labels.inherited}
                className="h-7 rounded-none px-2 text-[9px]"
                onClick={() =>
                  pinned
                    ? onRestore(field)
                    : onChange(pinFactoryField(shot, field))
                }
              >
                {field} · {pinned ? labels.overridden : labels.inherited}
              </Button>
            );
          })}
      </div>
      <label className="mt-4 block text-[10px] font-bold">
        {labels.outgoingJson}
        <Textarea
          value={source}
          disabled={disabled}
          spellCheck={false}
          className="mt-2 min-h-64 rounded-none bg-white font-mono text-[10px]"
          onChange={(event) => {
            const nextSource = event.target.value;
            setSource(nextSource);
            try {
              const request = normalizeFactoryRequest(JSON.parse(nextSource));
              let next = { ...shot, request };
              const fields = new Set([
                ...Object.keys(shot.request),
                ...Object.keys(request),
              ]);
              for (const field of fields) {
                if (
                  JSON.stringify(shot.request[field]) !==
                  JSON.stringify(request[field])
                ) {
                  next = pinFactoryField(next, field);
                }
              }
              onChange(next);
              void validate(request);
            } catch {
              setValidation(labels.invalid);
            }
          }}
        />
      </label>
      {validation && (
        <p className="mt-2 text-[10px] text-muted-foreground">{validation}</p>
      )}
    </details>
  );
}

export function ProductionFactory({
  locale,
  online,
  incoming,
  onIncomingConsumed,
  onPlanChange,
  section = 'all',
  draftAvailable = false,
}: {
  locale: Locale;
  online: boolean;
  /** Whether the host has an OpenAI key. False disables the draft button and says why. */
  draftAvailable?: boolean;
  incoming: FactoryIncoming | null;
  onIncomingConsumed: () => void;
  /** Lets the page derive stage status and the board from the same plan this component owns. */
  onPlanChange?: (plan: FactoryPlan) => void;
  /**
   * Which half of the factory to show. Stage 00 (Bible) and stage 03 (queue) render the *same*
   * mounted instance with different values, so the plan stays one piece of state; mounting the
   * component twice would give each stage its own plan.
   */
  section?: 'all' | 'bible' | 'queue';
}) {
  const showBible = section !== 'queue';
  const showQueue = section !== 'bible';
  const text = copy[locale];
  const [plan, setPlan] = useState<FactoryPlan>(() =>
    createFactoryPlan('pending', new Date(0)),
  );
  const [hydrated, setHydrated] = useState(false);
  // Set by every local edit and cleared once the host has the change.
  const [dirty, setDirty] = useState(false);
  const [legacy, setLegacy] = useState<FactoryPlan | null>(null);
  const [legacyOwner, setLegacyOwner] = useState('');
  const [notice, setNotice] = useState('');
  const [assets, setAssets] = useState<Asset[]>([]);
  // Drafts the user has not accepted yet, kept per shot. A draft only lands here when the prompt
  // is pinned - that is, when the user has already written something the draft must not replace.
  const [drafts, setDrafts] = useState<
    Record<string, { prompt: string; primary_action: string }>
  >({});
  const [drafting, setDrafting] = useState('');
  const [draftNotice, setDraftNotice] = useState<Record<string, string>>({});
  const importInput = useRef<HTMLInputElement>(null);
  const planRef = useRef(plan);
  const consumed = useRef(new Set<string>());

  const mutate = (change: (current: FactoryPlan) => FactoryPlan) => {
    setDirty(true);
    return setPlan((current) => ({
      ...change(current),
      updatedAt: new Date().toISOString(),
    }));
  };

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

  /**
   * Ask the host to draft this shot. The key stays there; this only ever sees two strings.
   *
   * A prompt the user has pinned - by writing it themselves, or by accepting an earlier draft -
   * is never replaced. The draft is offered beside it instead, and applying it takes a click.
   */
  const draftShot = async (shot: FactoryShot) => {
    if (!draftAvailable || drafting) return;
    setDrafting(shot.id);
    setDraftNotice((current) => ({ ...current, [shot.id]: '' }));
    try {
      const response = await serviceFetch(`/api/v1/factory/shots/${shot.id}/draft`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: '{}',
      });
      if (!response.ok) {
        setDraftNotice((current) => ({
          ...current,
          [shot.id]: response.status === 429 ? text.draftBudget
            : response.status === 503 ? text.draftUnavailable
              : text.draftFailed,
        }));
        return;
      }
      const draft = (await response.json()) as { prompt?: string; primary_action?: string };
      const written = { prompt: String(draft.prompt ?? ''),
                        primary_action: String(draft.primary_action ?? '') };
      if (!written.prompt) {
        setDraftNotice((current) => ({ ...current, [shot.id]: text.draftFailed }));
        return;
      }
      if (shot.pinned.includes('prompt')) {
        setDrafts((current) => ({ ...current, [shot.id]: written }));
        return;
      }
      applyDraft(shot.id, written);
    } catch {
      setDraftNotice((current) => ({ ...current, [shot.id]: text.draftFailed }));
    } finally {
      setDrafting('');
    }
  };

  /**
   * Write a draft into the shot and pin the prompt. Pinning is what makes it a decision: an
   * unpinned prompt is reprojected away the next time the Bible changes.
   */
  const applyDraft = (
    id: string,
    draft: { prompt: string; primary_action: string },
  ) => {
    patchShot(id, (current) => ({
      ...pinFactoryField(
        reopenFactoryShot(
          current,
          current.status === 'draft' ? current.idempotencyKey : freshIdempotencyKey(current),
        ),
        'prompt',
      ),
      request: {
        ...current.request,
        prompt: draft.prompt,
        primary_action: draft.primary_action,
      },
    }));
    setDrafts((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  };

  useEffect(() => {
    planRef.current = plan;
  }, [plan]);

  // The plan lives on the host. This loads it; a plan left here by the pre-B1 build is offered
  // for upload rather than pushed silently, since it may be one the user abandoned.
  useEffect(() => {
    const abort = new AbortController();
    void (async () => {
      let userId = '';
      try {
        const response = await serviceFetch('/api/auth/session', { signal: abort.signal });
        if (response.ok) {
          const session = (await response.json()) as { user?: { id?: string } };
          userId = session.user?.id || '';
        }
      } catch {
        // Not signed in, or the endpoint is unavailable; the factory endpoints will say so.
      }
      if (abort.signal.aborted) return;
      try {
        const projects = await factory.listProjects();
        const loaded = projects.length
          ? await factory.getProject(projects[0].id)
          : await factory.createProject({ title: 'UNTITLED PRODUCTION' });
        if (abort.signal.aborted) return;
        setPlan(loaded);
        setLegacy(factory.localPlan(userId));
        setLegacyOwner(userId);
      } catch (error) {
        if (!abort.signal.aborted) setNotice(factoryMessage(error, text.requestFailed));
      } finally {
        if (!abort.signal.aborted) setHydrated(true);
      }
    })();
    return () => abort.abort();
  }, [text.requestFailed]);

  useEffect(() => {
    const abort = new AbortController();
    void serviceFetch('/api/v1/assets', { signal: abort.signal })
      .then(async (response) =>
        response.ok
          ? (response.json() as Promise<{ assets?: Asset[] }>)
          : Promise.reject(),
      )
      .then((result) => setAssets(result.assets || []))
      .catch(() => undefined);
    return () => abort.abort();
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    onPlanChange?.(plan);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the callback is a stable page setter.
  }, [hydrated, plan]);

  // Edits are optimistic locally and pushed to the host shortly after, so typing stays smooth
  // without a request per keystroke. While the line runs the host owns the plan; pushing then
  // would overwrite the progress it is writing.
  useEffect(() => {
    if (!hydrated || !plan.id || plan.status === 'running' || !dirty) return;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          await factory.updateProject(plan.id, { title: plan.title, bible: plan.bible });
          await factory.replaceShots(plan.id, plan.shots);
          setDirty(false);
        } catch (error) {
          setNotice(factoryMessage(error, text.requestFailed));
        }
      })();
    }, 600);
    return () => window.clearTimeout(timer);
  }, [hydrated, dirty, plan, text.requestFailed]);

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
        bible: hasFactoryBible(current.bible)
          ? current.bible
          : incoming.bible || bibleFromRequest(incoming.request),
        status: current.status === 'completed' ? 'paused' : current.status,
        shots: [...current.shots, shot],
      };
    });
    onIncomingConsumed();
  }, [hydrated, incoming, onIncomingConsumed]);

  // The host schedules and submits; the browser only watches. Closing this tab no longer stops
  // the line, which is the whole point of moving the queue off the client.
  useEffect(() => {
    if (!hydrated || !plan.id || plan.status !== 'running') return;
    let disposed = false;
    const poll = async () => {
      try {
        const fresh = await factory.getProject(plan.id);
        if (!disposed) setPlan(fresh);
      } catch {
        // A transient read failure just means the next tick shows the change instead.
      }
    };
    const timer = window.setInterval(() => void poll(), 2000);
    void poll();
    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [hydrated, plan.id, plan.status]);

  const summary = summarizeFactory(plan);
  const active = activeFactoryShot(plan);
  const editable = !active && plan.status !== 'running';
  const completedShots = plan.shots.filter((shot) => shot.outputUrl);
  const characterValue: CharacterDraft = {
    enabled: Boolean(plan.bible.character),
    name: plan.bible.character?.name || '',
    description: plan.bible.character?.description || '',
    references: (plan.bible.character?.references || []).flatMap(
      (reference) => {
        const asset = assets.find((item) => item.id === reference.image_id);
        return asset
          ? [
              {
                asset,
                view: reference.view as CharacterDraft['references'][number]['view'],
              },
            ]
          : [];
      },
    ),
  };
  const audioAssets = assets.filter((asset) => asset.kind === 'audio');

  const updateBible = (change: (bible: FactoryBible) => FactoryBible) => {
    const overrideCount = countPinnedShots(plan);
    mutate((current) => {
      const bible = change(current.bible);
      return reprojectShots({ ...current, bible }, bible);
    });
    setNotice(text.reprojected.replace('{count}', String(overrideCount)));
  };

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
    if (!hasFactoryBible(plan.bible)) {
      setNotice(text.bibleRequired);
      return;
    }
    mutate((current) => ({
      ...current,
      status: current.status === 'completed' ? 'paused' : current.status,
      shots: [
        ...current.shots,
        createFactoryShot(
          projectBible(current.bible, {
            prompt: text.defaultPrompt,
            mode: 't2v',
            duration_seconds: 4,
            seed: 42 + current.shots.length,
          }),
          crypto.randomUUID(),
          current.shots.length,
        ),
      ],
    }));
  };

  const runOnHost = (action: (id: string) => Promise<FactoryPlan>) => {
    setNotice('');
    void (async () => {
      try {
        // Flush pending edits first: starting a line the host has not seen would run stale shots.
        if (dirty) {
          await factory.updateProject(plan.id, { title: plan.title, bible: plan.bible });
          await factory.replaceShots(plan.id, plan.shots);
          setDirty(false);
        }
        setPlan(await action(plan.id));
      } catch (error) {
        setNotice(factoryMessage(error, text.requestFailed));
      }
    })();
  };

  const start = () => runOnHost(factory.runProject);

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
      {section === 'all' && (
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
      )}

      {showQueue && (
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
      )}

      {!online && (
        <p
          role="alert"
          className="mb-5 border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900"
        >
          {text.offline}
        </p>
      )}
      {legacy && (
        <div className="mb-5 flex flex-wrap items-center gap-3 border border-amber-200 bg-amber-50 p-4 text-xs text-amber-900">
          <p className="flex-1">
            {text.legacyFound.replace('{count}', String(legacy.shots.length))}
          </p>
          <Button
            type="button"
            className="rounded-none"
            onClick={() => {
              const pending = legacy;
              setLegacy(null);
              void (async () => {
                try {
                  setPlan(await factory.uploadLocalPlan(pending));
                  factory.forgetLocalPlan(legacyOwner);
                  setNotice(text.legacyDone);
                } catch (error) {
                  setNotice(factoryMessage(error, text.requestFailed));
                }
              })();
            }}
          >
            {text.legacyUpload}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="rounded-none bg-white"
            onClick={() => {
              factory.forgetLocalPlan(legacyOwner);
              setLegacy(null);
            }}
          >
            {text.legacyDiscard}
          </Button>
        </div>
      )}
      {notice && (
        <p className="mb-5 border border-border bg-white p-4 text-xs">
          {notice}
        </p>
      )}

      <div
        className={`grid gap-6 ${showQueue ? 'xl:grid-cols-[1.45fr_.75fr]' : ''}`}
      >
        <div className="space-y-5">
          {showBible && (
          <section className="space-y-5 border border-border bg-white p-5">
            <div>
              <h2 className="text-xs font-extrabold tracking-[0.13em]">
                {text.bible}
              </h2>
              <p className="mt-2 text-[10px] leading-5 text-muted-foreground">
                {text.bibleHint}
              </p>
            </div>
            <fieldset disabled={!editable}>
              <CharacterLock
                locale={locale}
                value={characterValue}
                current={null}
                onPrimary={(asset) =>
                  updateBible((bible) => ({
                    ...bible,
                    character: bible.character
                      ? {
                          ...bible.character,
                          references: [
                            ...bible.character.references.filter(
                              (reference) => reference.image_id === asset.id,
                            ),
                            ...bible.character.references.filter(
                              (reference) => reference.image_id !== asset.id,
                            ),
                          ],
                        }
                      : undefined,
                  }))
                }
                onChange={(character) =>
                  updateBible((bible) => ({
                    ...bible,
                    character: character.enabled
                      ? {
                          name: character.name.trim(),
                          description: character.description.trim(),
                          references: character.references.map((reference) => ({
                            image_id: reference.asset.id,
                            view: reference.view,
                          })),
                        }
                      : undefined,
                  }))
                }
              />
            </fieldset>
            <div className="grid gap-4 lg:grid-cols-2">
              <label className="text-[10px] font-bold">
                {text.music}
                <Select
                  value={plan.bible.music?.audio_id || 'none'}
                  disabled={!editable}
                  onValueChange={(id) =>
                    updateBible((bible) => ({
                      ...bible,
                      music:
                        !id || id === 'none'
                          ? undefined
                          : {
                              audio_id: id,
                              audio_start_seconds: 0,
                              audio_mode: 'soundtrack',
                              lrc: '',
                              lrc_timebase: 'output',
                            },
                    }))
                  }
                >
                  <SelectTrigger className="mt-2 w-full rounded-none bg-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">{text.noMusic}</SelectItem>
                    {audioAssets.map((asset) => (
                      <SelectItem key={asset.id} value={asset.id}>
                        {asset.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <label className="text-[10px] font-bold">
                lyric_offset_seconds
                <Input
                  type="number"
                  step="0.1"
                  disabled={!editable}
                  value={plan.bible.lyric_offset_seconds}
                  onChange={(event) =>
                    updateBible((bible) => ({
                      ...bible,
                      lyric_offset_seconds: Number(event.target.value),
                    }))
                  }
                  className="mt-2 rounded-none"
                />
              </label>
            </div>
            {plan.bible.music && (
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="text-[10px] font-bold">
                  audio_start_seconds
                  <Input
                    type="number"
                    min={0}
                    step="0.1"
                    disabled={!editable}
                    value={plan.bible.music.audio_start_seconds}
                    onChange={(event) =>
                      updateBible((bible) => ({
                        ...bible,
                        music: bible.music
                          ? {
                              ...bible.music,
                              audio_start_seconds: Number(event.target.value),
                            }
                          : undefined,
                      }))
                    }
                    className="mt-2 rounded-none"
                  />
                </label>
                <label className="text-[10px] font-bold">
                  audio_mode
                  <Select
                    disabled={!editable}
                    value={plan.bible.music.audio_mode}
                    onValueChange={(audioMode) =>
                      updateBible((bible) => ({
                        ...bible,
                        music:
                          bible.music && audioMode
                            ? { ...bible.music, audio_mode: audioMode }
                            : bible.music,
                      }))
                    }
                  >
                    <SelectTrigger className="mt-2 w-full rounded-none">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="soundtrack">soundtrack</SelectItem>
                      <SelectItem value="condition">condition</SelectItem>
                    </SelectContent>
                  </Select>
                </label>
                <label className="text-[10px] font-bold lg:col-span-2">
                  LRC
                  <Textarea
                    disabled={!editable}
                    value={plan.bible.music.lrc}
                    onChange={(event) =>
                      updateBible((bible) => ({
                        ...bible,
                        music: bible.music
                          ? { ...bible.music, lrc: event.target.value }
                          : undefined,
                      }))
                    }
                    className="mt-2 min-h-24 rounded-none font-mono text-[10px]"
                  />
                </label>
              </div>
            )}
            <div>
              <h3 className="text-[10px] font-bold tracking-[0.12em]">
                {text.output}
              </h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {(['model', 'aspect_ratio', 'profile'] as const).map(
                  (field) => (
                    <label key={field} className="text-[10px] font-bold">
                      {field}
                      <Input
                        disabled={!editable}
                        value={String(plan.bible.output[field] || '')}
                        onChange={(event) =>
                          updateBible((bible) => ({
                            ...bible,
                            output: {
                              ...bible.output,
                              [field]: event.target.value || undefined,
                            },
                          }))
                        }
                        className="mt-2 rounded-none"
                      />
                    </label>
                  ),
                )}
                <label className="text-[10px] font-bold">
                  fps
                  <Input
                    type="number"
                    min={8}
                    max={60}
                    disabled={!editable}
                    value={plan.bible.output.fps || ''}
                    onChange={(event) =>
                      updateBible((bible) => ({
                        ...bible,
                        output: {
                          ...bible.output,
                          fps: event.target.value
                            ? Number(event.target.value)
                            : undefined,
                        },
                      }))
                    }
                    className="mt-2 rounded-none"
                  />
                </label>
              </div>
              <label className="mt-4 flex items-center gap-3 text-[10px] font-bold">
                <Switch
                  disabled={!editable}
                  checked={Boolean(plan.bible.output.audio)}
                  onCheckedChange={(audio) =>
                    updateBible((bible) => ({
                      ...bible,
                      output: { ...bible.output, audio },
                    }))
                  }
                />
                audio
              </label>
            </div>
            <div>
              <h3 className="text-[10px] font-bold tracking-[0.12em]">
                directing
              </h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                {(
                  [
                    'shot_size',
                    'angle',
                    'camera',
                    'emotion',
                    'performance',
                  ] as const
                ).map((field) => (
                  <label key={field} className="text-[10px] font-bold">
                    {field}
                    <Input
                      disabled={!editable}
                      value={plan.bible.directing?.[field] || ''}
                      onChange={(event) =>
                        updateBible((bible) => ({
                          ...bible,
                          directing: {
                            ...bible.directing,
                            [field]: event.target.value,
                          },
                        }))
                      }
                      className="mt-2 rounded-none"
                    />
                  </label>
                ))}
              </div>
            </div>
          </section>
          )}
          {showQueue && (
          <>
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
                      <div>
                        {/* The button sits beside the label, not inside it: clicking a <label>
                            activates the control it names, which would fight the button. */}
                        <div className="flex flex-wrap items-center gap-2 text-[10px] font-bold">
                          <label htmlFor={`prompt-${shot.id}`}>{text.prompt}</label>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={
                              !shotEditable || !draftAvailable || drafting === shot.id
                            }
                            title={draftAvailable ? undefined : text.draftUnavailable}
                            onClick={() => void draftShot(shot)}
                            className="h-6 rounded-none px-2 text-[10px]"
                          >
                            {drafting === shot.id ? text.drafting : text.draft}
                          </Button>
                          <span className="font-normal text-muted-foreground">
                            {draftNotice[shot.id] ||
                              (draftAvailable ? '' : text.draftUnavailable)}
                          </span>
                        </div>
                        <Textarea
                          id={`prompt-${shot.id}`}
                          value={shot.request.prompt}
                          maxLength={4000}
                          disabled={!shotEditable}
                          onChange={(event) =>
                            patchShot(
                              shot.id,
                              (current) => ({
                                ...pinFactoryField(
                                  reopenFactoryShot(
                                    current,
                                    current.status === 'draft'
                                      ? current.idempotencyKey
                                      : freshIdempotencyKey(current),
                                  ),
                                  'prompt',
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
                      </div>
                      <div className="min-w-44 text-[10px] leading-5 text-muted-foreground lg:text-right">
                        {requestMeta(shot.request)}
                      </div>
                      {drafts[shot.id] ? (
                        <div className="border border-dashed border-border bg-[#fafaf8] p-3 lg:col-span-2">
                          <p className="text-[10px] font-bold">{text.draftSuggestion}</p>
                          <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">
                            {drafts[shot.id].prompt}
                          </p>
                          {drafts[shot.id].primary_action ? (
                            <p className="mt-2 text-[11px] text-muted-foreground">
                              {text.primaryAction}: {drafts[shot.id].primary_action}
                            </p>
                          ) : null}
                          <div className="mt-3 flex gap-2">
                            <Button
                              type="button"
                              size="sm"
                              disabled={!shotEditable}
                              onClick={() => applyDraft(shot.id, drafts[shot.id])}
                              className="h-7 rounded-none px-3 text-[10px]"
                            >
                              {text.draftApply}
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={() =>
                                setDrafts((current) => {
                                  const next = { ...current };
                                  delete next[shot.id];
                                  return next;
                                })
                              }
                              className="h-7 rounded-none px-3 text-[10px]"
                            >
                              {text.draftDismiss}
                            </Button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                    <ShotSettings
                      shot={shot}
                      disabled={!shotEditable}
                      labels={text}
                      onChange={(next) =>
                        patchShot(
                          shot.id,
                          () =>
                            reopenFactoryShot(
                              next,
                              next.status === 'draft'
                                ? next.idempotencyKey
                                : freshIdempotencyKey(next),
                            ),
                          plan.status === 'completed' ? 'paused' : undefined,
                        )
                      }
                      onRestore={(field) =>
                        patchShot(shot.id, (current) => {
                          const unpinned = unpinFactoryField(current, field);
                          return reprojectShots({
                            ...planRef.current,
                            shots: [unpinned],
                          }).shots[0];
                        })
                      }
                    />
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
          </>
          )}
        </div>

        {showQueue && (
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
        )}
      </div>
    </section>
  );
}
