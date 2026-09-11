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
    overallPrompt: '整支 MV 視覺提示詞',
    overallPromptHint: '這段會成為每一鏡共用的世界觀；必須確認後才能匯出完整分鏡 JSON。',
    adoptConcept: '採用為整體提示詞',
    exportNeedsBreakdown: '先完成自動分鏡，才能匯出完整分鏡 JSON。',
    exportNeedsPrompt: '請填寫整支 MV 視覺提示詞，或採用 AI 導演的視覺概念。',
    exportNeedsShotPrompts: '每一鏡都要有提示詞；請逐鏡填寫，或採用全部 AI 導演建議。',
    exportBadDuration: '歌曲分析尚未取得有效總長（必須介於 0–180 秒），請重新執行自動分鏡。',
    exportReady: '匯出內容已包含歌曲總長、完整 LRC 與目前全部分鏡。',
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
    overallPrompt: 'Whole-MV visual prompt',
    overallPromptHint: 'This is the shared visual world for every shot. Review it before exporting the complete shot JSON.',
    adoptConcept: 'Use as overall prompt',
    exportNeedsBreakdown: 'Run the automatic breakdown before exporting complete shot JSON.',
    exportNeedsPrompt: 'Enter a whole-MV visual prompt or accept the AI director visual concept.',
    exportNeedsShotPrompts: 'Every shot needs a prompt. Edit each shot or apply all AI director suggestions.',
    exportBadDuration: 'Song analysis has no valid total duration (0–180 seconds). Run the automatic breakdown again.',
    exportReady: 'The export includes the song duration, full LRC and every current shot.',
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
    overallPrompt: 'MV全体の映像プロンプト',
    overallPromptHint: '全カットで共有する世界観です。確認してから完全なショットJSONを書き出してください。',
    adoptConcept: '全体プロンプトに採用',
    exportNeedsBreakdown: '自動絵コンテを完了してから完全なショットJSONを書き出してください。',
    exportNeedsPrompt: 'MV全体の映像プロンプトを入力するか、AI監督の映像コンセプトを採用してください。',
    exportNeedsShotPrompts: '全カットにプロンプトが必要です。各カットを編集するか、AI監督の提案をすべて採用してください。',
    exportBadDuration: '曲の長さが有効ではありません（0～180秒）。自動絵コンテをもう一度実行してください。',
    exportReady: '書き出しには曲の長さ、完全なLRC、現在の全カットが含まれます。',
  },
} as const;

export function DirectorSummary({
  locale,
  analysis,
  onApplyAll,
  onAdoptConcept,
}: {
  locale: BreakdownLocale;
  analysis: DirectorAnalysis;
  onApplyAll: () => void;
  onAdoptConcept: () => void;
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
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={onAdoptConcept}
            className="rounded-sm border border-[#11786f] bg-white px-3 py-2 text-[11px] font-bold text-[#11786f] hover:bg-[#ddf6f2]"
          >
            {text.adoptConcept}
          </button>
          <button
            type="button"
            onClick={onApplyAll}
            className="rounded-sm bg-[#171918] px-3 py-2 text-[11px] font-bold text-white hover:bg-[#e85578]"
          >
            {text.applyAll}
          </button>
        </div>
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
