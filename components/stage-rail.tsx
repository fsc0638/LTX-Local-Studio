'use client';

import {
  STAGE_KEYS,
  UNAVAILABLE_STAGES,
  type StageKey,
  type StageStatus,
} from '@/lib/stages';

export type RailKey = StageKey | 'board' | 'sandbox' | 'workstation';

export const stageCopy = {
  'zh-TW': {
    line: '製作線',
    board: '狀態板',
    tools: '工具',
    sandbox: '沙盒',
    sandboxNote: '單鏡實驗與診斷',
    workstation: '工站',
    workstationNote: '裝置與執行環境',
    unavailable: '本期未啟用',
    stages: {
      bible: '企劃 Bible',
      breakdown: '分鏡',
      keyframes: '關鍵格',
      shoot: '拍攝',
      review: '審片',
      post: '後製',
      assembly: '組片交付',
    },
    status: {
      idle: '未開始',
      active: '進行中',
      attention: '待人決定',
      done: '通過',
      disabled: '未啟用',
    },
  },
  en: {
    line: 'PRODUCTION LINE',
    board: 'Status board',
    tools: 'TOOLS',
    sandbox: 'Sandbox',
    sandboxNote: 'Single-shot experiments and diagnostics',
    workstation: 'Workstation',
    workstationNote: 'Device and runtime',
    unavailable: 'Not enabled this phase',
    stages: {
      bible: 'Project Bible',
      breakdown: 'Breakdown',
      keyframes: 'Keyframes',
      shoot: 'Generation',
      review: 'Review',
      post: 'Post',
      assembly: 'Assembly',
    },
    status: {
      idle: 'Not started',
      active: 'In progress',
      attention: 'Needs you',
      done: 'Passed',
      disabled: 'Not enabled',
    },
  },
  ja: {
    line: '制作ライン',
    board: 'ステータスボード',
    tools: 'ツール',
    sandbox: 'サンドボックス',
    sandboxNote: '単一ショットの実験と診断',
    workstation: 'ワークステーション',
    workstationNote: 'デバイスと実行環境',
    unavailable: '今期は未対応',
    stages: {
      bible: '企画 Bible',
      breakdown: '絵コンテ',
      keyframes: 'キーフレーム',
      shoot: '生成',
      review: '試写',
      post: '仕上げ',
      assembly: '編集・納品',
    },
    status: {
      idle: '未開始',
      active: '進行中',
      attention: '要判断',
      done: '通過',
      disabled: '未対応',
    },
  },
};

export type StageLocale = keyof typeof stageCopy;

const dotClass: Record<StageStatus, string> = {
  idle: 'bg-border',
  active: 'bg-[#e85578]',
  attention: 'bg-amber-500',
  done: 'bg-[#11786f]',
  disabled: 'bg-transparent border border-border',
};

const badgeClass: Record<StageStatus, string> = {
  idle: 'text-muted-foreground',
  active: 'text-[#e85578]',
  attention: 'text-amber-700',
  done: 'text-[#11786f]',
  disabled: 'text-muted-foreground',
};

function stageIndex(key: StageKey): string {
  return String(STAGE_KEYS.indexOf(key)).padStart(2, '0');
}

export function StageRail({
  active,
  statuses,
  locale,
  onSelect,
}: {
  active: RailKey;
  statuses: Record<StageKey, StageStatus>;
  locale: StageLocale;
  onSelect: (key: RailKey) => void;
}) {
  const text = stageCopy[locale];

  // The rail is a list of destinations, so it stays a <nav><ol>; the mobile stepper is the same
  // markup laid out horizontally rather than a second component that could drift.
  return (
    <nav
      aria-label={text.line}
      className="border-b border-border bg-white lg:sticky lg:top-28 lg:self-start lg:border-b-0 lg:bg-transparent"
    >
      <p className="hidden px-1 pb-3 text-[9px] font-bold tracking-[0.2em] text-muted-foreground lg:block">
        {text.line}
      </p>

      <ol className="flex snap-x gap-1 overflow-x-auto px-3 py-3 lg:flex-col lg:gap-0 lg:overflow-visible lg:px-0 lg:py-0">
        <li className="snap-start lg:border-b lg:border-border">
          <button
            type="button"
            onClick={() => onSelect('board')}
            aria-current={active === 'board' ? 'page' : undefined}
            className={`flex w-full shrink-0 items-center gap-2 whitespace-nowrap border-l-2 px-3 py-2 text-left text-[11px] font-bold tracking-[0.1em] lg:px-2 lg:py-3 ${
              active === 'board'
                ? 'border-[#e85578] bg-[#fdeef2] text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {text.board}
          </button>
        </li>

        {STAGE_KEYS.map((key) => {
          const status = statuses[key];
          const unavailable = UNAVAILABLE_STAGES.includes(key);
          const selected = active === key;
          return (
            <li key={key} className="snap-start lg:border-b lg:border-border">
              <button
                type="button"
                onClick={() => onSelect(key)}
                aria-current={selected ? 'page' : undefined}
                className={`flex w-full shrink-0 items-center gap-2 whitespace-nowrap border-l-2 px-3 py-2 text-left lg:grid lg:grid-cols-[18px_1fr] lg:items-baseline lg:gap-x-2 lg:px-2 lg:py-3 ${
                  selected
                    ? 'border-[#e85578] bg-[#fdeef2]'
                    : 'border-transparent hover:bg-[#faf9f7]'
                } ${unavailable && !selected ? 'opacity-55' : ''}`}
              >
                <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
                  {stageIndex(key)}
                </span>
                <span className="flex items-baseline gap-2 lg:flex-col lg:items-start lg:gap-0.5">
                  <span className="text-[12px] font-bold tracking-[0.04em]">
                    {text.stages[key]}
                  </span>
                  <span
                    className={`flex items-center gap-1 text-[9px] font-bold tracking-[0.1em] ${badgeClass[status]}`}
                  >
                    <span
                      aria-hidden="true"
                      className={`inline-block size-1.5 rounded-full ${dotClass[status]}`}
                    />
                    {unavailable ? text.unavailable : text.status[status]}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>

      {/* Sandbox and workstation are not part of the line; they sit below it and read quieter. */}
      <div className="hidden pt-5 lg:block">
        <p className="px-1 pb-2 text-[9px] font-bold tracking-[0.2em] text-muted-foreground">
          {text.tools}
        </p>
        {(
          [
            ['sandbox', text.sandbox, text.sandboxNote],
            ['workstation', text.workstation, text.workstationNote],
          ] as [RailKey, string, string][]
        ).map(([key, label, note]) => (
          <button
            key={key}
            type="button"
            onClick={() => onSelect(key)}
            aria-current={active === key ? 'page' : undefined}
            className={`block w-full border-l-2 px-2 py-2 text-left ${
              active === key
                ? 'border-[#e85578] bg-[#fdeef2] text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <span className="block text-[11px] font-bold tracking-[0.04em]">
              {label}
            </span>
            <span className="block text-[9px] leading-4 text-muted-foreground">
              {note}
            </span>
          </button>
        ))}
      </div>

      <div className="flex gap-1 border-t border-border px-3 py-2 lg:hidden">
        {(
          [
            ['sandbox', text.sandbox],
            ['workstation', text.workstation],
          ] as [RailKey, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => onSelect(key)}
            aria-current={active === key ? 'page' : undefined}
            className={`border px-3 py-1.5 text-[10px] font-bold tracking-[0.1em] ${
              active === key
                ? 'border-[#e85578] bg-[#fdeef2] text-foreground'
                : 'border-transparent text-muted-foreground'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </nav>
  );
}
