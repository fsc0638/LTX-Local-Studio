/**
 * Which light a take gets, and where the lines are drawn - the browser's copy of review_rules.py.
 *
 * Two implementations of one rule is a cost, paid so the page can draw lights without a round
 * trip and the server can decide a verdict without trusting the page. tests/review.test.mjs and
 * tests/test_factory_review.py use the same fixture numbers; if the two ever drift, a test fails
 * rather than the screen quietly disagreeing with the record.
 */
export type LightKey = 'cj' | 'sj' | 'mq';
export type Light = 'red' | 'green' | 'unscored';
export type LineKey = LightKey | 'cj_dino';
export type Thresholds = Record<LineKey, number> & { calibrated: boolean; strict: boolean };

/**
 * The architecture page's placeholders. Marked uncalibrated until C4 writes measured values.
 * cj and cj_dino are separate lines: facenet and DINOv2 similarities are on different scales,
 * and the consistency judge uses whichever path found the frame's face - or did not.
 */
export const DEFAULT_THRESHOLDS: Record<LineKey, number> = { cj: 0.8, cj_dino: 0.8, sj: 0.85, mq: 0.5 };
export const DEFAULT_STRICT: Record<LineKey, number> = { cj: 0.85, cj_dino: 0.85, sj: 0.9, mq: 0.5 };
export const LIGHT_KEYS: LightKey[] = ['cj', 'sj', 'mq'];
export const LINE_KEYS: LineKey[] = ['cj', 'cj_dino', 'sj', 'mq'];

type Scores = Record<string, unknown> | null | undefined;

function numbers(raw: unknown): Partial<Record<LineKey, number>> {
  const out: Partial<Record<LineKey, number>> = {};
  if (!raw || typeof raw !== 'object') return out;
  for (const key of LINE_KEYS) {
    const value = (raw as Record<string, unknown>)[key];
    if (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1) {
      out[key] = value;
    }
  }
  return out;
}

/** Bible thresholds over the defaults, then the shot's own override over both. */
export function resolveThresholds(
  bible: Record<string, unknown> | null | undefined,
  request?: Record<string, unknown> | null,
  strict = false,
): Thresholds {
  const bibleThresholds = ((bible ?? {}) as { thresholds?: Record<string, unknown> }).thresholds ?? {};
  const base = { ...(strict ? DEFAULT_STRICT : DEFAULT_THRESHOLDS) };
  Object.assign(base, numbers(strict ? bibleThresholds.strict : bibleThresholds));
  Object.assign(base, numbers((request ?? {}).thresholds));
  return { ...base, calibrated: Boolean(bibleThresholds.calibrated), strict };
}

/** Which consistency path scored most of the frames: the line to judge the median against. */
export function consistencyMethod(scores: Scores): 'face_facenet' | 'dinov2_large' | null {
  if (!scores || typeof scores !== 'object') return null;
  const consistency = (scores.consistency ?? null) as { method_per_frame?: unknown[] } | null;
  const methods = consistency?.method_per_frame;
  if (!Array.isArray(methods) || !methods.length) return null;
  const faces = methods.filter((m) => m === 'face_facenet').length;
  return faces * 2 >= methods.length ? 'face_facenet' : 'dinov2_large';
}

/** The consistency line in force for a take: cj when faces were found, cj_dino when not. */
export function consistencyLine(scores: Scores, thresholds: Thresholds): number {
  return consistencyMethod(scores) === 'dinov2_large' ? thresholds.cj_dino : thresholds.cj;
}

/** The three numbers the page draws, or null where the judge had nothing to say. */
export function takeScores(scores: Scores): Record<LightKey, number | null> {
  if (!scores || typeof scores !== 'object' || scores.status === 'unscored') {
    return { cj: null, sj: null, mq: null };
  }
  const consistency = (scores.consistency ?? {}) as { median?: number };
  const style = (scores.style ?? {}) as { median?: number };
  const media = (scores.media ?? {}) as { frozen_ratio?: number };
  const frozen = media.frozen_ratio;
  return {
    cj: typeof consistency.median === 'number' ? consistency.median : null,
    sj: typeof style.median === 'number' ? style.median : null,
    // A still has no motion to score; a video's motion score is how much of it moved.
    mq: typeof frozen === 'number' ? Math.round((1 - frozen) * 10000) / 10000 : null,
  };
}

/**
 * 'red' below the line, 'green' at or above it, 'unscored' when there is no number.
 * Unscored is not red: no evidence against a take is not evidence against it.
 */
export function lights(scores: Scores, thresholds: Thresholds): Record<LightKey, Light> {
  const values = takeScores(scores);
  const out = {} as Record<LightKey, Light>;
  for (const key of LIGHT_KEYS) {
    const value = values[key];
    const line = key === 'cj' ? consistencyLine(scores, thresholds) : thresholds[key];
    out[key] = value === null ? 'unscored' : value < line ? 'red' : 'green';
  }
  return out;
}

export function isRed(scores: Scores, thresholds: Thresholds): boolean {
  return Object.values(lights(scores, thresholds)).includes('red');
}

/** Per-frame consistency, one point a second, for the drawer's curve. Empty when unscored. */
export function consistencyCurve(scores: Scores): { second: number; value: number; method: string }[] {
  if (!scores || typeof scores !== 'object') return [];
  const consistency = (scores.consistency ?? null) as
    | { per_frame?: unknown[]; method_per_frame?: unknown[] }
    | null;
  if (!consistency || !Array.isArray(consistency.per_frame)) return [];
  const methods = Array.isArray(consistency.method_per_frame) ? consistency.method_per_frame : [];
  return consistency.per_frame.flatMap((value, index) =>
    typeof value === 'number'
      ? [{ second: index, value, method: String(methods[index] ?? '') }]
      : [],
  );
}
