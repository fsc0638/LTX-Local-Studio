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
export type Thresholds = Record<LightKey, number> & { calibrated: boolean; strict: boolean };

/** The architecture page's placeholders. Marked uncalibrated until C4 writes measured values. */
export const DEFAULT_THRESHOLDS: Record<LightKey, number> = { cj: 0.8, sj: 0.85, mq: 0.5 };
export const DEFAULT_STRICT: Record<LightKey, number> = { cj: 0.85, sj: 0.9, mq: 0.5 };
export const LIGHT_KEYS: LightKey[] = ['cj', 'sj', 'mq'];

type Scores = Record<string, unknown> | null | undefined;

function numbers(raw: unknown): Partial<Record<LightKey, number>> {
  const out: Partial<Record<LightKey, number>> = {};
  if (!raw || typeof raw !== 'object') return out;
  for (const key of LIGHT_KEYS) {
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
    out[key] = value === null ? 'unscored' : value < thresholds[key] ? 'red' : 'green';
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
