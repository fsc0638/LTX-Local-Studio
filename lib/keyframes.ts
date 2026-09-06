/**
 * Keyframe rules the page and the tests share. Pure: no fetch, no React.
 *
 * The light is the consistency judge's number against the line in force, with a band of yellow
 * below green: a keyframe a little under the line is worth a look, not a rerun. Red reruns once
 * with a different seed before a person is asked - one retry, because a second red on a second
 * seed is information about the reference, not bad luck.
 */
export type KeyframeLight = 'green' | 'yellow' | 'red' | 'unscored';

/** How far under the line still counts as yellow rather than red. */
export const YELLOW_BAND = 0.05;

/**
 * The consistency number against the line in force. The caller computes both with lib/review
 * (takeScores and consistencyLine) - this file imports nothing so it can be tested under node
 * without a bundler, and so the rule reads as arithmetic.
 */
export function keyframeLight(cj: number | null, line: number): KeyframeLight {
  if (cj === null) return 'unscored';
  if (cj >= line) return 'green';
  return cj >= line - YELLOW_BAND ? 'yellow' : 'red';
}

/** Whether a red keyframe should be generated again automatically. Once, and only once. */
export function shouldRetry(light: KeyframeLight, attempt: number): boolean {
  return light === 'red' && attempt < 2;
}

/** A different seed for the retry, derived rather than random so a rerun is reproducible. */
export function retrySeed(seed: number): number {
  return (seed + 7919) % 2147483647;
}

/** Switching the GPU to the image model and back costs one model load; then it is per shot. */
export const MODEL_SWITCH_SECONDS = 336;
export const PER_KEYFRAME_SECONDS = 26;

export function batchEstimateSeconds(shots: number, modelAlreadyLoaded = false): number {
  if (shots <= 0) return 0;
  return (modelAlreadyLoaded ? 0 : MODEL_SWITCH_SECONDS) + shots * PER_KEYFRAME_SECONDS;
}

export type KeyframeRecord = {
  id: string;
  shotId: string;
  attempt: number;
  seed: number;
  referenceId: string | null;
  outputUrl: string | null;
  scores: Record<string, unknown> | null;
  light: 'green' | 'yellow' | 'red' | null;
  verdict: 'pending' | 'approved' | 'rejected' | 'failed';
  assetId: string | null;
  reason: string | null;
  createdAt: number;
};

/** The candidate a shot's tile shows: the approved one, else the newest pending, else the newest. */
export function leadKeyframe(records: KeyframeRecord[]): KeyframeRecord | null {
  if (!records.length) return null;
  const approved = records.find((r) => r.verdict === 'approved');
  if (approved) return approved;
  const sorted = [...records].sort((a, b) => b.createdAt - a.createdAt);
  return sorted.find((r) => r.verdict === 'pending') ?? sorted[0];
}

/** Shots that still need a person: newest candidate is red after its retry, or yellow. */
export function needsAttention(records: KeyframeRecord[]): boolean {
  const lead = leadKeyframe(records);
  if (!lead || lead.verdict !== 'pending') return false;
  return lead.light === 'red' || lead.light === 'yellow';
}
