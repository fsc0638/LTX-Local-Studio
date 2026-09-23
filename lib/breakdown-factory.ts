import type { BreakdownShot } from './breakdown';
import type { FactoryRequest } from './production-factory';

export type BreakdownFactoryEntry = {
  title: string;
  request: FactoryRequest;
  pinned: string[];
  startSeconds: number;
};

const rounded = (value: number) => Math.round(value * 1000) / 1000;

const localLrc = (shot: BreakdownShot) =>
  shot.lyrics
    .map((line) => {
      const safe = Math.max(0, rounded(line.time - shot.start));
      const minutes = Math.floor(safe / 60);
      const seconds = (safe - minutes * 60).toFixed(3).padStart(6, '0');
      return `[${String(minutes).padStart(2, '0')}:${seconds}]${line.text}`;
    })
    .join('\n');

const timestamp = (value: number) => {
  const safe = Math.max(0, rounded(value));
  const minutes = Math.floor(safe / 60);
  const seconds = (safe - minutes * 60).toFixed(3).padStart(6, '0');
  return `${String(minutes).padStart(2, '0')}:${seconds}`;
};

/**
 * Turn a full-song breakdown into independently valid factory jobs.
 *
 * A worker sequence is capped at 180 seconds, while a production can be longer. Each breakdown
 * shot therefore carries a local 0-based timeline and advances the source-audio offset. Assembly
 * later concatenates the accepted takes and lays the Bible's original song over the whole movie.
 */
export function breakdownFactoryEntries(
  request: FactoryRequest,
  shots: BreakdownShot[],
): BreakdownFactoryEntry[] {
  const sourceTimeline =
    request.timeline && typeof request.timeline === 'object'
      ? (request.timeline as Record<string, unknown>)
      : undefined;
  if (!sourceTimeline || typeof sourceTimeline.audio_id !== 'string') return [];

  const sourceStart = Number(sourceTimeline.audio_start_seconds || 0);
  const sourceSeed = Number(request.seed || 0);
  const sourceDirecting =
    request.directing && typeof request.directing === 'object'
      ? (request.directing as Record<string, string>)
      : {};

  return shots.map((shot, index) => {
    const duration = rounded(shot.end - shot.start);
    const action = shot.cue.action.trim();
    const directing = { ...sourceDirecting, ...shot.cue.directing };
    const timeline = {
      ...sourceTimeline,
      audio_start_seconds: rounded(sourceStart + shot.start),
      lrc: localLrc(shot),
      lrc_timebase: 'output',
      cues: [{ time: 0, action, directing }],
    };
    return {
      title: `SHOT ${String(index + 1).padStart(2, '0')} · ${timestamp(shot.start)}–${timestamp(shot.end)}`,
      request: {
        ...request,
        prompt: action || request.prompt,
        duration_seconds: duration,
        seed: Number.isFinite(sourceSeed) ? sourceSeed + index : index,
        directing,
        timeline,
      },
      // These two fields deliberately differ by shot and must survive Bible reprojection.
      pinned: ['directing', 'timeline'],
      startSeconds: rounded(shot.start),
    };
  });
}
