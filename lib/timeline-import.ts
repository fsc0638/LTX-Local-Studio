/**
 * Client-side import of a shot plan written as JSON, so another language model
 * can produce a file that this UI understands. Limits mirror mv_timeline.py so
 * a bad file is rejected here with a readable message instead of at the worker.
 * Imported text is data, never code: nothing is evaluated and unknown fields are
 * reported rather than forwarded.
 */
const MAX_SECONDS = 180;
const MAX_CUES = 60;
const MAX_ACTION = 600;
const MAX_LRC = 16000;
const TIMELINE_FIELDS = [
  'audio_id',
  'audio_start_seconds',
  'audio_mode',
  'lrc',
  'lrc_timebase',
  'cues',
];
const CUE_FIELDS = ['time', 'action', 'directing'];

export type ImportedCue = {
  time: number;
  action: string;
  directing: Record<string, string>;
};
export type DirectingCatalog =
  | Record<string, Record<string, unknown>>
  | undefined;
export type TimelineImport = {
  lrc?: string;
  lrcTimebase?: 'output' | 'music';
  cues?: ImportedCue[];
  audioId?: string;
  audioStart?: number;
  audioMode?: string;
  segmentSeconds?: number;
  durationSeconds?: number;
  /** Top-level keys that carry no timeline meaning; surfaced, never applied. */
  ignored: string[];
};

function asRecord(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return value as Record<string, unknown>;
}

function asNumber(
  value: unknown,
  label: string,
  minimum: number,
  maximum: number,
): number {
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    value < minimum ||
    value > maximum
  ) {
    throw new Error(`${label} must be a number between ${minimum} and ${maximum}`);
  }
  return value;
}

function normalizeDirecting(
  raw: unknown,
  catalog: DirectingCatalog,
  label: string,
): Record<string, string> {
  if (raw === undefined) return {};
  const record = asRecord(raw, label);
  const result: Record<string, string> = {};
  for (const [key, value] of Object.entries(record)) {
    if (typeof value !== 'string') {
      throw new Error(`${label}.${key} must be a string`);
    }
    // Without a loaded catalog the worker stays the authority on valid options.
    if (catalog) {
      if (!catalog[key]) throw new Error(`${label}.${key} is not a directing field`);
      if (!catalog[key][value]) {
        throw new Error(`${label}.${key}="${value}" is not a supported option`);
      }
    }
    result[key] = value;
  }
  return result;
}

function normalizeCues(raw: unknown, catalog: DirectingCatalog): ImportedCue[] {
  if (!Array.isArray(raw)) throw new Error('cues must be an array');
  if (raw.length > MAX_CUES) {
    throw new Error(`At most ${MAX_CUES} action cues are supported`);
  }
  const cues = raw.map((item, index) => {
    const label = `cues[${index}]`;
    const record = asRecord(item, label);
    const extra = Object.keys(record).filter((key) => !CUE_FIELDS.includes(key));
    if (extra.length) {
      throw new Error(`${label} accepts time, action and directing only; found ${extra.join(', ')}`);
    }
    const action = record.action === undefined ? '' : record.action;
    if (typeof action !== 'string' || action.length > MAX_ACTION) {
      throw new Error(`${label}.action must be text up to ${MAX_ACTION} characters`);
    }
    return {
      time: asNumber(record.time, `${label}.time`, 0, MAX_SECONDS),
      action,
      directing: normalizeDirecting(record.directing, catalog, `${label}.directing`),
    };
  });
  cues.sort((a, b) => a.time - b.time);
  if (new Set(cues.map((cue) => cue.time)).size !== cues.length) {
    throw new Error('Action cues cannot share a timestamp');
  }
  return cues;
}

function readTimeline(
  timeline: Record<string, unknown>,
  catalog: DirectingCatalog,
  result: TimelineImport,
): void {
  if (timeline.lrc !== undefined) {
    if (typeof timeline.lrc !== 'string' || timeline.lrc.length > MAX_LRC) {
      throw new Error(`lrc must be text up to ${MAX_LRC} characters`);
    }
    result.lrc = timeline.lrc;
  }
  if (timeline.lrc_timebase !== undefined) {
    if (timeline.lrc_timebase !== 'output' && timeline.lrc_timebase !== 'music') {
      throw new Error('lrc_timebase must be "output" or "music"');
    }
    result.lrcTimebase = timeline.lrc_timebase;
  }
  if (timeline.audio_mode !== undefined) {
    if (timeline.audio_mode !== 'soundtrack' && timeline.audio_mode !== 'condition') {
      throw new Error('audio_mode must be "soundtrack" or "condition"');
    }
    result.audioMode = timeline.audio_mode;
  }
  if (timeline.audio_start_seconds !== undefined) {
    result.audioStart = asNumber(
      timeline.audio_start_seconds,
      'audio_start_seconds',
      0,
      600,
    );
  }
  if (timeline.audio_id !== undefined && timeline.audio_id !== null) {
    if (typeof timeline.audio_id !== 'string') {
      throw new Error('audio_id must be an asset ID string');
    }
    result.audioId = timeline.audio_id;
  }
  if (timeline.cues !== undefined) result.cues = normalizeCues(timeline.cues, catalog);
}

/**
 * Accepts either a full /api/v1/jobs payload (detected by a nested `timeline`
 * object) or a bare timeline subset such as `{ "lrc": "...", "cues": [...] }`.
 */
export function parseTimelineImport(
  source: string,
  catalog: DirectingCatalog,
): TimelineImport {
  let data: unknown;
  try {
    data = JSON.parse(source);
  } catch {
    throw new Error('The file is not valid JSON');
  }
  const root = asRecord(data, 'Import');
  const result: TimelineImport = { ignored: [] };
  if (root.timeline !== undefined) {
    const timeline = asRecord(root.timeline, 'timeline');
    const extra = Object.keys(timeline).filter(
      (key) => !TIMELINE_FIELDS.includes(key),
    );
    if (extra.length) {
      throw new Error(`timeline accepts ${TIMELINE_FIELDS.join(', ')} only; found ${extra.join(', ')}`);
    }
    readTimeline(timeline, catalog, result);
    if (root.duration_seconds !== undefined) {
      result.durationSeconds = asNumber(
        root.duration_seconds,
        'duration_seconds',
        0.125,
        MAX_SECONDS,
      );
    }
    if (root.segment_seconds !== undefined) {
      result.segmentSeconds = asNumber(root.segment_seconds, 'segment_seconds', 2, 20);
    }
    result.ignored = Object.keys(root).filter(
      (key) => !['timeline', 'duration_seconds', 'segment_seconds'].includes(key),
    );
    return result;
  }
  if (root.lrc === undefined && root.cues === undefined) {
    throw new Error('Provide a "timeline" object, or "lrc" and/or "cues" at the top level');
  }
  readTimeline(root, catalog, result);
  result.ignored = Object.keys(root).filter((key) => !TIMELINE_FIELDS.includes(key));
  return result;
}
