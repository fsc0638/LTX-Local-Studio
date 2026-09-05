'use client';

import { useMemo, useState } from 'react';
import {
  mergeBreakdownShots,
  splitBreakdownShot,
  type BreakdownLyric,
  type BreakdownShot,
} from '@/lib/breakdown';

export type BreakdownLocale = 'zh-TW' | 'en' | 'ja';

export const breakdownCopy = {
  'zh-TW': {
    title: '分鏡',
    note: '切點跟著段落與歌詞走，並吸附到拍點。可以合併、拆分或改每一鏡。',
    empty: '還沒有分鏡。先在 00 企劃 Bible 選好音樂，再讓音訊分析跑一次。',
    preview: '預覽分鏡',
    shots: '鏡',
    seconds: '秒',
    breathing: '器樂',
    lyric: '有詞',
    endedBy: { section: '段落邊界', lyric: '歌詞行', limit: '長度上限', end: '曲末' },
    merge: '與下一鏡合併',
    split: '從中間拆開',
    action: '主要動作',
    actionPlaceholder: '留空＝交給導演參數決定',
    cueAt: 'cue',
    lines: '行',
    legendSection: '段落',
    legendBeat: '拍點',
    legendLyric: '歌詞',
    selected: '已選',
    total: '總長',
  },
  en: {
    title: 'Breakdown',
    note: 'Cuts follow the sections and the lyrics, snapped to the beat. Merge, split or edit any shot.',
    empty: 'No breakdown yet. Choose the music in 00 Bible, then run the audio analysis.',
    preview: 'Preview breakdown',
    shots: 'shots',
    seconds: 's',
    breathing: 'Instrumental',
    lyric: 'Sung',
    endedBy: { section: 'Section boundary', lyric: 'Lyric line', limit: 'Length cap', end: 'End of song' },
    merge: 'Merge with next',
    split: 'Split in the middle',
    action: 'Primary action',
    actionPlaceholder: 'Empty means the directing parameters decide',
    cueAt: 'cue',
    lines: 'lines',
    legendSection: 'Sections',
    legendBeat: 'Beats',
    legendLyric: 'Lyrics',
    selected: 'Selected',
    total: 'Total',
  },
  ja: {
    title: '絵コンテ',
    note: 'カットはセクションと歌詞に従い、拍にスナップします。結合・分割・編集ができます。',
    empty: 'まだ絵コンテがありません。00 企画で音楽を選び、音声解析を実行してください。',
    preview: '絵コンテをプレビュー',
    shots: 'カット',
    seconds: '秒',
    breathing: '器楽',
    lyric: '歌詞あり',
    endedBy: { section: 'セクション境界', lyric: '歌詞行', limit: '長さ上限', end: '曲末' },
    merge: '次のカットと結合',
    split: '中央で分割',
    action: '主なアクション',
    actionPlaceholder: '空欄なら演出パラメータに任せる',
    cueAt: 'cue',
    lines: '行',
    legendSection: 'セクション',
    legendBeat: '拍',
    legendLyric: '歌詞',
    selected: '選択中',
    total: '合計',
  },
} as const;

const clock = (seconds: number) => {
  const whole = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(whole / 60)).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`;
};

/**
 * The energy curve the audio service samples about ten times a second, in dB against the loudest
 * frame. Drawn as a filled area rather than a mirrored waveform: it is a loudness envelope, and
 * drawing it symmetrically would imply sample data this never had.
 */
function energyPath(energy: number[], hopSeconds: number, durationSeconds: number): string {
  if (energy.length < 2 || durationSeconds <= 0) return '';
  const floor = -60;
  const points = energy.map((value, index) => {
    const x = Math.min(1000, ((index * hopSeconds) / durationSeconds) * 1000);
    const level = Math.max(0, Math.min(1, (value - floor) / -floor));
    return `${x.toFixed(2)},${(100 - level * 100).toFixed(2)}`;
  });
  return `M0,100 L${points.join(' L')} L1000,100 Z`;
}

export function BreakdownEditor({
  shots,
  lyrics,
  beats,
  sections,
  durationSeconds,
  beatSeconds,
  energy,
  energyHopSeconds,
  locale,
  onChange,
  onPreview,
}: {
  shots: BreakdownShot[];
  lyrics: BreakdownLyric[];
  beats: number[];
  sections: number[];
  durationSeconds: number;
  beatSeconds: number;
  energy?: number[];
  energyHopSeconds?: number;
  locale: BreakdownLocale;
  onChange: (shots: BreakdownShot[]) => void;
  onPreview?: () => void;
}) {
  const text = breakdownCopy[locale];
  const [selected, setSelected] = useState(0);

  const percent = (time: number) =>
    durationSeconds > 0 ? `${Math.max(0, Math.min(100, (time / durationSeconds) * 100))}%` : '0%';

  // A tick every beat is unreadable on a three-minute song at screen width, so thin the grid until
  // the marks are far enough apart to read as a grid rather than a smear.
  const beatStride = useMemo(() => {
    const wanted = 220;
    return Math.max(1, Math.ceil(beats.length / wanted));
  }, [beats.length]);

  const curve = useMemo(
    () => (energy?.length ? energyPath(energy, energyHopSeconds ?? 0.1, durationSeconds) : ''),
    [energy, energyHopSeconds, durationSeconds],
  );

  if (!shots.length) {
    return (
      <section className="rounded-md border border-border bg-white p-6 text-center">
        <p className="text-[13px] text-muted-foreground">{text.empty}</p>
      </section>
    );
  }

  const current = shots[Math.min(selected, shots.length - 1)];
  const update = (next: BreakdownShot[], keep: number) => {
    setSelected(Math.max(0, Math.min(keep, next.length - 1)));
    onChange(next);
  };

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h2 className="text-[15px] font-bold">{text.title}</h2>
          <p className="mt-1 max-w-prose text-[12px] text-muted-foreground">{text.note}</p>
        </div>
        <div className="flex items-center gap-3">
          <p className="font-mono text-[11px] tabular-nums text-muted-foreground">
            {shots.length} {text.shots} · {text.total} {clock(durationSeconds)}
          </p>
          {onPreview ? (
            <button
              type="button"
              onClick={onPreview}
              className="rounded-sm border border-border px-3 py-1.5 text-[11px] font-bold hover:bg-[#faf9f7]"
            >
              {text.preview}
            </button>
          ) : null}
        </div>
      </header>

      <div className="rounded-md border border-border bg-white p-3">
        <div className="relative h-32 w-full overflow-hidden rounded-sm bg-[#faf9f7]">
          <svg
            viewBox="0 0 1000 100"
            preserveAspectRatio="none"
            className="absolute inset-0 h-full w-full"
            aria-hidden="true"
          >
            {sections.map((time, index) => {
              const next = sections[index + 1] ?? durationSeconds;
              const x = (time / durationSeconds) * 1000;
              return (
                <rect
                  key={`band-${time}`}
                  x={x}
                  y={0}
                  width={Math.max(0, ((next - time) / durationSeconds) * 1000)}
                  height={100}
                  fill={index % 2 ? '#f3f0ec' : '#ffffff'}
                />
              );
            })}
            {beats
              .filter((_, index) => index % beatStride === 0)
              .map((time) => (
                <line
                  key={`beat-${time}`}
                  x1={(time / durationSeconds) * 1000}
                  x2={(time / durationSeconds) * 1000}
                  y1={78}
                  y2={100}
                  stroke="#d9d4cd"
                  strokeWidth={1}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
            {curve ? <path d={curve} fill="#e8557826" stroke="none" /> : null}
          </svg>

          {lyrics.map((line) => (
            <span
              key={`lyric-${line.time}`}
              title={line.text}
              style={{ left: percent(line.time) }}
              className="absolute top-0 h-3 w-px bg-[#8c8577]"
            />
          ))}

          <div className="absolute inset-x-0 bottom-0 top-4">
            {shots.map((shot, index) => (
              <button
                key={shot.id}
                type="button"
                onClick={() => setSelected(index)}
                aria-pressed={index === selected}
                title={`${clock(shot.start)} – ${clock(shot.end)}`}
                style={{ left: percent(shot.start), width: percent(shot.end - shot.start) }}
                className={`absolute bottom-0 top-0 border-l text-left ${
                  index === selected
                    ? 'border-[#e85578] bg-[#e8557826]'
                    : 'border-[#c9c3ba] hover:bg-[#00000008]'
                }`}
              >
                <span className="pointer-events-none block px-1 pt-1 font-mono text-[9px] tabular-nums text-muted-foreground">
                  {index + 1}
                </span>
              </button>
            ))}
          </div>
        </div>

        <p className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-3 bg-[#f3f0ec]" /> {text.legendSection}
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-px bg-[#d9d4cd]" /> {text.legendBeat}
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-px bg-[#8c8577]" /> {text.legendLyric}
          </span>
        </p>
      </div>

      <ol className="flex flex-col gap-2">
        {shots.map((shot, index) => {
          const active = index === selected;
          return (
            <li
              key={shot.id}
              className={`rounded-md border bg-white ${
                active ? 'border-[#e85578]' : 'border-border'
              }`}
            >
              <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-3 pt-2">
                <button
                  type="button"
                  onClick={() => setSelected(index)}
                  className="font-mono text-[12px] font-bold tabular-nums"
                >
                  {String(index + 1).padStart(2, '0')}
                </button>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {clock(shot.start)} – {clock(shot.end)} ·{' '}
                  {(shot.end - shot.start).toFixed(2)}
                  {text.seconds}
                </span>
                <span
                  className={`rounded-sm px-1.5 py-0.5 text-[10px] font-bold ${
                    shot.kind === 'breathing'
                      ? 'bg-[#eef2fd] text-[#4a5a8c]'
                      : 'bg-[#fdeef2] text-[#a8365a]'
                  }`}
                >
                  {shot.kind === 'breathing' ? text.breathing : `${text.lyric} · ${shot.lyrics.length} ${text.lines}`}
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {text.endedBy[shot.endedBy]}
                </span>
                <span className="ml-auto font-mono text-[10px] tabular-nums text-muted-foreground">
                  {text.cueAt} {shot.cue.time.toFixed(2)}
                </span>
              </div>

              {shot.lyrics.length ? (
                <p className="px-3 pt-1 text-[12px] leading-relaxed">
                  {shot.lyrics.map((line) => line.text).join(' / ')}
                </p>
              ) : null}

              <div className="flex flex-wrap items-center gap-2 px-3 py-2">
                <label className="flex flex-1 items-center gap-2">
                  <span className="sr-only">{text.action}</span>
                  <input
                    value={shot.cue.action}
                    placeholder={text.actionPlaceholder}
                    onChange={(event) => {
                      const next = shots.map((item, at) =>
                        at === index
                          ? { ...item, cue: { ...item.cue, action: event.target.value } }
                          : item,
                      );
                      update(next, index);
                    }}
                    className="w-full rounded-sm border border-border px-2 py-1 text-[12px]"
                  />
                </label>
                <button
                  type="button"
                  onClick={() =>
                    update(
                      splitBreakdownShot(
                        shots,
                        index,
                        (shot.start + shot.end) / 2,
                        beats,
                        lyrics,
                        beatSeconds,
                      ),
                      index,
                    )
                  }
                  className="rounded-sm border border-border px-2 py-1 text-[11px] hover:bg-[#faf9f7]"
                >
                  {text.split}
                </button>
                <button
                  type="button"
                  disabled={index + 1 >= shots.length}
                  onClick={() => update(mergeBreakdownShots(shots, index, lyrics), index)}
                  className="rounded-sm border border-border px-2 py-1 text-[11px] hover:bg-[#faf9f7] disabled:opacity-40"
                >
                  {text.merge}
                </button>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="sr-only" aria-live="polite">
        {text.selected} {current.index + 1}
      </p>
    </section>
  );
}
