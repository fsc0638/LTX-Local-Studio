'use client';

import { Button } from '@/components/ui/button';
import {
  hasFactoryBible,
  summarizeFactory,
  type FactoryPlan,
} from '@/lib/production-factory';
import {
  planProgress,
  STAGE_KEYS,
  type PlanProgress,
  type StageKey,
} from '@/lib/stages';
import { stageCopy, type StageLocale } from '@/components/stage-rail';

const copy = {
  'zh-TW': {
    eyebrow: '狀態板',
    title: '每首歌做到哪了',
    note: '這裡不生成任何東西，只回答一個問題：這條製作線現在卡在誰身上。',
    project: '專案',
    stage: '卡在哪個階段',
    last: '上一步結論',
    next: '下一步',
    owner: { user: '你', worker: '主機', none: '—' },
    open: '前往',
    shots: '{n} 鏡',
    empty: '還沒有專案。先到「企劃 Bible」固定角色、音樂與輸出規格。',
    start: '開始設定 Bible',
    resultNone: '尚未開始。',
    resultBible: 'Bible 已設定，鏡頭還沒建立。',
    resultBreakdown: '鏡頭清單已建立，尚未生產。',
    resultShots: '已完成 {done}／{total} 鏡。',
    resultCompleted: '全部鏡頭完成，可以組片。',
    resultFailed: '{failed} 鏡失敗，生產線已暫停。',
    nextBible: '設定角色、音樂與輸出規格',
    nextShots: '新增鏡頭（會繼承 Bible）',
    nextRun: '開始生產',
    nextWait: '等待本機生產完成',
    nextFix: '修正失敗的鏡頭後重試',
    nextAssemble: '組片並下載',
    nextUnavailable: '此階段本期未啟用',
  },
  en: {
    eyebrow: 'STATUS BOARD',
    title: 'Where each song stands',
    note: 'Nothing is generated here. It answers one question: who is this production line waiting on.',
    project: 'Project',
    stage: 'Current stage',
    last: 'Last result',
    next: 'Next',
    owner: { user: 'You', worker: 'Host', none: '—' },
    open: 'Open',
    shots: '{n} shots',
    empty: 'No project yet. Start in Project Bible: fix the character, music and output format.',
    start: 'Set up the Bible',
    resultNone: 'Not started.',
    resultBible: 'Bible set; no shots yet.',
    resultBreakdown: 'Shot list built; nothing generated yet.',
    resultShots: '{done} of {total} shots finished.',
    resultCompleted: 'Every shot finished; ready to assemble.',
    resultFailed: '{failed} shots failed; the line is paused.',
    nextBible: 'Set the character, music and output format',
    nextShots: 'Add shots (they inherit the Bible)',
    nextRun: 'Start generating',
    nextWait: 'Wait for the host to finish',
    nextFix: 'Fix the failed shots, then retry',
    nextAssemble: 'Assemble and download',
    nextUnavailable: 'Not enabled this phase',
  },
  ja: {
    eyebrow: 'ステータスボード',
    title: '各曲の進捗',
    note: 'ここでは生成しません。この制作ラインが今誰待ちかだけを示します。',
    project: 'プロジェクト',
    stage: '現在の段階',
    last: '前段階の結果',
    next: '次の一手',
    owner: { user: 'あなた', worker: 'ホスト', none: '—' },
    open: '開く',
    shots: '{n} ショット',
    empty: 'プロジェクトがありません。「企画 Bible」で人物・音楽・出力設定を決めてください。',
    start: 'Bible を設定',
    resultNone: '未開始。',
    resultBible: 'Bible 設定済み。ショット未作成。',
    resultBreakdown: 'ショット一覧を作成済み。生成は未実行。',
    resultShots: '{done}／{total} ショット完了。',
    resultCompleted: '全ショット完了。編集できます。',
    resultFailed: '{failed} ショットが失敗し、ラインは停止中。',
    nextBible: '人物・音楽・出力設定を決める',
    nextShots: 'ショットを追加（Bible を継承）',
    nextRun: '生成を開始',
    nextWait: 'ホストの生成完了を待つ',
    nextFix: '失敗したショットを修正して再試行',
    nextAssemble: '編集して書き出す',
    nextUnavailable: '今期は未対応',
  },
};

/** The one place a plan is reduced to what the stage machine needs. */
export function progressOf(plan: FactoryPlan): PlanProgress {
  const summary = summarizeFactory(plan);
  return planProgress({
    hasBible: hasFactoryBible(plan.bible),
    status: plan.status,
    total: summary.total,
    completed: summary.completed,
    failed: summary.failed,
  });
}

function fill(template: string, values: Record<string, number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

export function StatusBoard({
  plans,
  locale,
  onOpenStage,
}: {
  plans: FactoryPlan[];
  locale: StageLocale;
  onOpenStage: (stage: StageKey) => void;
}) {
  const text = copy[locale];
  const stages = stageCopy[locale].stages;

  return (
    <section>
      <div className="mb-8 border-b border-border pb-6">
        <p className="mb-2 text-[10px] font-bold tracking-[0.18em] text-[#e85578]">
          {text.eyebrow}
        </p>
        <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
          {text.title}
        </h1>
        <p className="mt-3 max-w-2xl text-xs leading-6 text-muted-foreground">
          {text.note}
        </p>
      </div>

      {!plans.length ? (
        <div className="grid min-h-64 place-items-center border border-dashed border-border bg-[#fafaf8] p-8 text-center">
          <div className="max-w-md space-y-4">
            <p className="text-sm text-muted-foreground">{text.empty}</p>
            <Button
              type="button"
              className="rounded-none"
              onClick={() => onOpenStage('bible')}
            >
              {text.start}
            </Button>
          </div>
        </div>
      ) : (
        <div className="border border-border bg-white">
          <div className="hidden grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1.3fr)_auto] gap-4 border-b border-border px-5 py-3 text-[9px] font-bold tracking-[0.16em] text-muted-foreground lg:grid">
            <span>{text.project}</span>
            <span>{text.stage}</span>
            <span>{text.last}</span>
            <span>{text.next}</span>
            <span />
          </div>
          {plans.map((plan) => {
            const summary = summarizeFactory(plan);
            const progress = progressOf(plan);
            const values = {
              n: summary.total,
              done: summary.completed,
              total: summary.total,
              failed: summary.failed,
            };
            const attention = progress.statuses[progress.current] === 'attention';
            return (
              <div
                key={plan.id}
                className="grid gap-3 border-b border-border px-5 py-4 last:border-b-0 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,1.3fr)_auto] lg:items-center lg:gap-4"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-extrabold">
                    {plan.title}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {fill(text.shots, values)} · {plan.status.toUpperCase()}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className={`inline-block size-1.5 rounded-full ${
                      attention ? 'bg-amber-500' : 'bg-[#e85578]'
                    }`}
                  />
                  <span className="text-xs font-bold">
                    {String(STAGE_KEYS.indexOf(progress.current)).padStart(
                      2,
                      '0',
                    )}{' '}
                    {stages[progress.current]}
                  </span>
                </div>
                <p className="text-xs leading-5 text-muted-foreground">
                  <span className="lg:hidden">{text.last}: </span>
                  {fill(text[progress.lastResult as keyof typeof text] as string, values)}
                </p>
                <p className="text-xs leading-5">
                  <span className="text-muted-foreground lg:hidden">
                    {text.next}:{' '}
                  </span>
                  <span className="font-bold">
                    {text.owner[progress.owner]}
                  </span>
                  {' · '}
                  {text[progress.nextAction as keyof typeof text] as string}
                </p>
                <Button
                  type="button"
                  variant="outline"
                  className="rounded-none justify-self-start lg:justify-self-end"
                  onClick={() => onOpenStage(progress.current)}
                >
                  {text.open}
                </Button>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
