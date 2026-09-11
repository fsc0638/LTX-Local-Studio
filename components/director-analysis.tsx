'use client';

import type { DirectorAnalysis } from '@/lib/director-analysis';
import type { BreakdownLocale } from '@/components/breakdown-editor';

export const directorCopy = {
  'zh-TW': {
    analyze: 'AI 導演分析',
    analyzing: '導演分析中…',
    unavailable: '主機未設定 OpenAI，無法分析。',
    needsBreakdown: '先完成自動分鏡。',
    disclosure: '按下後會把企劃、完整 LRC、節拍／能量摘要與分鏡送至 OpenAI，並計入本專案 token 額度。建議不會自動套用。',
    failed: 'AI 導演分析失敗，請稍後再試。',
    budget: '本專案的 AI 草稿額度已用完。',
    title: '整首歌導演提案',
    applyAll: '採用全部鏡頭提示詞',
    genre: '歌曲類型',
    meaning: '歌詞意境',
    concept: '視覺概念',
    arc: '情緒曲線',
    strategy: '製作人策略',
  },
  en: {
    analyze: 'AI director analysis',
    analyzing: 'Director analysing…',
    unavailable: 'OpenAI is not configured on this host.',
    needsBreakdown: 'Run the automatic breakdown first.',
    disclosure: 'This sends the Bible, full LRC, beat/energy summary and breakdown to OpenAI and charges the project token budget. Suggestions are never applied automatically.',
    failed: 'AI director analysis failed. Try again later.',
    budget: 'This project has spent its AI draft budget.',
    title: 'Whole-song director treatment',
    applyAll: 'Apply every shot prompt',
    genre: 'Song type',
    meaning: 'Lyrical meaning',
    concept: 'Visual concept',
    arc: 'Emotional arc',
    strategy: 'Producer strategy',
  },
  ja: {
    analyze: 'AI監督分析',
    analyzing: '監督が分析中…',
    unavailable: 'このホストにはOpenAIが設定されていません。',
    needsBreakdown: '先に自動絵コンテを実行してください。',
    disclosure: '企画、完全なLRC、拍／エネルギー概要、絵コンテをOpenAIへ送り、プロジェクトのtoken枠を使用します。提案は自動適用されません。',
    failed: 'AI監督分析に失敗しました。後でもう一度お試しください。',
    budget: 'このプロジェクトのAI下書き上限に達しました。',
    title: '楽曲全体の監督提案',
    applyAll: '全カットのプロンプトを採用',
    genre: '曲の種類',
    meaning: '歌詞の意味',
    concept: '映像コンセプト',
    arc: '感情の流れ',
    strategy: 'プロデューサー戦略',
  },
} as const;

export function DirectorSummary({
  locale,
  analysis,
  onApplyAll,
}: {
  locale: BreakdownLocale;
  analysis: DirectorAnalysis;
  onApplyAll: () => void;
}) {
  const text = directorCopy[locale];
  const rows = [
    [text.genre, analysis.song.genre],
    [text.meaning, analysis.song.lyrical_meaning],
    [text.concept, analysis.song.visual_concept],
    [text.arc, analysis.song.emotional_arc],
    [text.strategy, analysis.song.producer_strategy],
  ];
  return (
    <section className="space-y-3 rounded-md border border-[#bfe8e3] bg-[#f0fbf9] p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-bold">{text.title}</h2>
        <button
          type="button"
          onClick={onApplyAll}
          className="rounded-sm bg-[#171918] px-3 py-2 text-[11px] font-bold text-white hover:bg-[#e85578]"
        >
          {text.applyAll}
        </button>
      </div>
      <dl className="grid gap-3 lg:grid-cols-2">
        {rows.map(([label, value]) => (
          <div key={label} className="border-l-2 border-[#25b6a6] pl-3">
            <dt className="text-[10px] font-bold text-muted-foreground">{label}</dt>
            <dd className="mt-1 text-[12px] leading-5">{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
