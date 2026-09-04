export const FACTORY_FORMAT = 'ltx-production-factory';
export const FACTORY_VERSION = 2;
export const MAX_FACTORY_SHOTS = 100;

export type FactoryCharacter = {
  name: string;
  description: string;
  references: { image_id: string; view: string }[];
};
export type FactoryMusic = {
  audio_id: string;
  audio_start_seconds: number;
  audio_mode: string;
  lrc: string;
  lrc_timebase: string;
};
export type FactoryOutput = {
  model?: string;
  aspect_ratio?: string;
  fps?: number;
  profile?: string;
  audio?: boolean;
};
export type FactoryBible = {
  character?: FactoryCharacter;
  music?: FactoryMusic;
  output: FactoryOutput;
  directing?: Record<string, string>;
  lyric_offset_seconds: number;
};

export type FactoryRunState = 'draft' | 'running' | 'paused' | 'completed';
export type FactoryShotState =
  | 'draft'
  | 'queued'
  | 'validating'
  | 'submitting'
  | 'running'
  | 'succeeded'
  | 'failed';

export type FactoryRequest = Record<string, unknown> & { prompt: string };
export type FactoryShot = {
  id: string;
  title: string;
  request: FactoryRequest;
  pinned: string[];
  status: FactoryShotState;
  idempotencyKey: string;
  jobId?: string;
  statusUrl?: string;
  outputUrl?: string;
  posterUrl?: string;
  progress: number;
  message?: string;
  error?: string;
};

export type FactoryPlan = {
  format: typeof FACTORY_FORMAT;
  version: typeof FACTORY_VERSION;
  id: string;
  title: string;
  bible: FactoryBible;
  status: FactoryRunState;
  createdAt: string;
  updatedAt: string;
  shots: FactoryShot[];
};

export type FactorySummary = {
  total: number;
  waiting: number;
  active: number;
  completed: number;
  failed: number;
};

const shotStates = new Set<FactoryShotState>([
  'draft',
  'queued',
  'validating',
  'submitting',
  'running',
  'succeeded',
  'failed',
]);
const runStates = new Set<FactoryRunState>([
  'draft',
  'running',
  'paused',
  'completed',
]);
const PROJECTED_FIELDS = [
  'character',
  'timeline',
  'render_mode',
  'directing',
  'model',
  'aspect_ratio',
  'fps',
  'profile',
  'audio',
] as const;

function record(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} must be a JSON object`);
  }
  return value as Record<string, unknown>;
}

function title(value: unknown, fallback: string): string {
  if (value === undefined) return fallback;
  if (typeof value !== 'string' || !value.trim() || value.length > 120) {
    throw new Error('Shot titles must contain 1–120 characters');
  }
  return value.trim();
}

export function normalizeFactoryRequest(value: unknown): FactoryRequest {
  const raw = record(value, 'Shot request');
  if (
    typeof raw.prompt !== 'string' ||
    !raw.prompt.trim() ||
    raw.prompt.length > 4000
  ) {
    throw new Error('Every shot requires a prompt of 1–4000 characters');
  }
  const encoded = JSON.stringify(raw);
  if (encoded.length > 128_000) {
    throw new Error('A shot request cannot exceed 128000 JSON characters');
  }
  return JSON.parse(encoded) as FactoryRequest;
}

function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function emptyFactoryBible(): FactoryBible {
  return { output: {}, lyric_offset_seconds: -0.9 };
}

export function normalizeFactoryBible(value: unknown): FactoryBible {
  if (value === undefined) return emptyFactoryBible();
  const raw = record(value, 'Factory bible');
  const extra = Object.keys(raw).filter(
    (key) =>
      ![
        'character',
        'music',
        'output',
        'directing',
        'lyric_offset_seconds',
      ].includes(key),
  );
  if (extra.length)
    throw new Error(
      `Factory bible has unsupported fields: ${extra.join(', ')}`,
    );
  const bible = clone({
    ...(raw.character
      ? { character: record(raw.character, 'Bible character') }
      : {}),
    ...(raw.music ? { music: record(raw.music, 'Bible music') } : {}),
    output: raw.output ? record(raw.output, 'Bible output') : {},
    ...(raw.directing
      ? { directing: record(raw.directing, 'Bible directing') }
      : {}),
    lyric_offset_seconds:
      typeof raw.lyric_offset_seconds === 'number' &&
      Number.isFinite(raw.lyric_offset_seconds)
        ? raw.lyric_offset_seconds
        : -0.9,
  }) as FactoryBible;
  if (JSON.stringify(bible).length > 128_000) {
    throw new Error('Factory bible cannot exceed 128000 JSON characters');
  }
  return bible;
}

export function hasFactoryBible(bible: FactoryBible): boolean {
  return Boolean(
    bible.character ||
    bible.music ||
    bible.directing ||
    Object.keys(bible.output).length,
  );
}

export function projectBible(
  bibleValue: FactoryBible,
  requestValue: FactoryRequest,
): FactoryRequest {
  const bible = normalizeFactoryBible(bibleValue);
  const request = normalizeFactoryRequest(requestValue);
  const projected: FactoryRequest = { ...request };
  if (bible.character) projected.character = clone(bible.character);
  if (bible.music) {
    projected.render_mode = 'sequence';
    projected.audio = true;
    projected.timeline = clone(bible.music);
  }
  if (bible.directing) projected.directing = clone(bible.directing);
  Object.assign(projected, clone(bible.output));
  return normalizeFactoryRequest(projected);
}

export function createFactoryPlan(id: string, now = new Date()): FactoryPlan {
  const stamp = now.toISOString();
  return {
    format: FACTORY_FORMAT,
    version: FACTORY_VERSION,
    id,
    title: 'UNTITLED PRODUCTION',
    bible: emptyFactoryBible(),
    status: 'draft',
    createdAt: stamp,
    updatedAt: stamp,
    shots: [],
  };
}

export function createFactoryShot(
  requestValue: unknown,
  id: string,
  index: number,
  titleValue?: unknown,
  pinned: string[] = [],
): FactoryShot {
  const request = normalizeFactoryRequest(requestValue);
  return {
    id,
    title: title(titleValue, `SHOT ${String(index + 1).padStart(2, '0')}`),
    request,
    pinned: [...new Set(pinned)].sort(),
    status: 'draft',
    idempotencyKey: `factory-${id}`,
    progress: 0,
  };
}

function safePath(value: unknown, prefix: string): string | undefined {
  return typeof value === 'string' &&
    value.startsWith(prefix) &&
    !value.startsWith('//')
    ? value
    : undefined;
}

export function restoreFactoryPlan(value: unknown): FactoryPlan {
  const raw = record(value, 'Saved factory');
  const legacy = raw.version === 1;
  if (
    raw.format !== FACTORY_FORMAT ||
    (!legacy && raw.version !== FACTORY_VERSION)
  ) {
    throw new Error('Unsupported production factory format');
  }
  if (typeof raw.id !== 'string' || !raw.id || typeof raw.title !== 'string') {
    throw new Error('Saved factory identity is invalid');
  }
  if (!Array.isArray(raw.shots) || raw.shots.length > MAX_FACTORY_SHOTS) {
    throw new Error(`A production supports up to ${MAX_FACTORY_SHOTS} shots`);
  }
  const shots = raw.shots.map((item, index) => {
    const shot = record(item, `shots[${index}]`);
    if (typeof shot.id !== 'string' || !shot.id) {
      throw new Error(`shots[${index}].id is invalid`);
    }
    let status = shotStates.has(shot.status as FactoryShotState)
      ? (shot.status as FactoryShotState)
      : 'draft';
    const jobId = typeof shot.jobId === 'string' ? shot.jobId : undefined;
    const statusUrl = safePath(shot.statusUrl, '/api/');
    if (status === 'validating' || status === 'submitting') status = 'queued';
    if (status === 'running' && (!jobId || !statusUrl)) status = 'queued';
    return {
      id: shot.id,
      title: title(shot.title, `SHOT ${String(index + 1).padStart(2, '0')}`),
      request: normalizeFactoryRequest(shot.request),
      pinned: legacy
        ? Object.keys(normalizeFactoryRequest(shot.request)).sort()
        : Array.isArray(shot.pinned)
          ? [
              ...new Set(
                shot.pinned.filter(
                  (item): item is string => typeof item === 'string',
                ),
              ),
            ].sort()
          : [],
      status,
      idempotencyKey:
        typeof shot.idempotencyKey === 'string' &&
        shot.idempotencyKey.length >= 8
          ? shot.idempotencyKey
          : `factory-${shot.id}`,
      jobId,
      statusUrl,
      outputUrl: safePath(shot.outputUrl, '/'),
      posterUrl: safePath(shot.posterUrl, '/'),
      progress:
        typeof shot.progress === 'number' && Number.isFinite(shot.progress)
          ? Math.max(0, Math.min(100, shot.progress))
          : 0,
      message:
        typeof shot.message === 'string'
          ? shot.message.slice(0, 500)
          : undefined,
      error:
        typeof shot.error === 'string' ? shot.error.slice(0, 1000) : undefined,
    } satisfies FactoryShot;
  });
  const status = runStates.has(raw.status as FactoryRunState)
    ? (raw.status as FactoryRunState)
    : 'draft';
  return {
    format: FACTORY_FORMAT,
    version: FACTORY_VERSION,
    id: raw.id,
    title: title(raw.title, 'UNTITLED PRODUCTION'),
    bible: legacy ? emptyFactoryBible() : normalizeFactoryBible(raw.bible),
    status:
      status === 'completed' &&
      shots.some((shot) => shot.status !== 'succeeded')
        ? 'paused'
        : status,
    createdAt:
      typeof raw.createdAt === 'string'
        ? raw.createdAt
        : new Date().toISOString(),
    updatedAt:
      typeof raw.updatedAt === 'string'
        ? raw.updatedAt
        : new Date().toISOString(),
    shots,
  };
}

export function parseFactoryImport(
  source: string,
  makeId: () => string,
  now = new Date(),
): FactoryPlan {
  if (source.length > 1_000_000) throw new Error('Factory JSON exceeds 1 MB');
  let parsed: unknown;
  try {
    parsed = JSON.parse(source);
  } catch {
    throw new Error('The file is not valid JSON');
  }
  const plan = createFactoryPlan(makeId(), now);
  let entries: unknown[];
  let legacy = true;
  if (Array.isArray(parsed)) {
    entries = parsed;
  } else {
    const root = record(parsed, 'Factory import');
    if (root.format === FACTORY_FORMAT) {
      if (root.version !== 1 && root.version !== FACTORY_VERSION) {
        throw new Error('Unsupported production factory version');
      }
      legacy = root.version === 1;
      plan.title = title(root.title, plan.title);
      plan.bible = legacy
        ? emptyFactoryBible()
        : normalizeFactoryBible(root.bible);
      if (!Array.isArray(root.shots))
        throw new Error('Factory shots must be an array');
      entries = root.shots;
    } else if (typeof root.prompt === 'string') {
      entries = [root];
    } else {
      throw new Error(
        'Provide a factory manifest, a shot array, or one job request',
      );
    }
  }
  if (!entries.length || entries.length > MAX_FACTORY_SHOTS) {
    throw new Error(`A production requires 1–${MAX_FACTORY_SHOTS} shots`);
  }
  plan.shots = entries.map((entry, index) => {
    const row = record(entry, `shots[${index}]`);
    if ('request' in row) {
      const extra = Object.keys(row).filter(
        (key) => !['title', 'request', 'pinned'].includes(key),
      );
      if (extra.length)
        throw new Error(
          `shots[${index}] has unsupported fields: ${extra.join(', ')}`,
        );
      const request = normalizeFactoryRequest(row.request);
      const pinned = legacy
        ? Object.keys(request)
        : Array.isArray(row.pinned)
          ? row.pinned.filter(
              (item): item is string => typeof item === 'string',
            )
          : [];
      return createFactoryShot(request, makeId(), index, row.title, pinned);
    }
    const request = normalizeFactoryRequest(row);
    return createFactoryShot(
      request,
      makeId(),
      index,
      undefined,
      Object.keys(request),
    );
  });
  return plan;
}

export function serializeFactoryPlan(plan: FactoryPlan): string {
  return `${JSON.stringify(
    {
      format: FACTORY_FORMAT,
      version: FACTORY_VERSION,
      title: plan.title,
      bible: plan.bible,
      shots: plan.shots.map((shot) => ({
        title: shot.title,
        request: shot.request,
        pinned: shot.pinned,
      })),
    },
    null,
    2,
  )}\n`;
}

export function pinFactoryField(shot: FactoryShot, field: string): FactoryShot {
  return { ...shot, pinned: [...new Set([...shot.pinned, field])].sort() };
}

export function unpinFactoryField(
  shot: FactoryShot,
  field: string,
): FactoryShot {
  return { ...shot, pinned: shot.pinned.filter((item) => item !== field) };
}

export function reprojectShots(
  plan: FactoryPlan,
  bibleValue: FactoryBible = plan.bible,
): FactoryPlan {
  const bible = normalizeFactoryBible(bibleValue);
  const template = projectBible(bible, { prompt: 'projection-template' });
  return {
    ...plan,
    bible,
    shots: plan.shots.map((shot) => {
      if (!['draft', 'queued', 'failed'].includes(shot.status)) return shot;
      const request: FactoryRequest = clone(shot.request);
      for (const field of PROJECTED_FIELDS) {
        if (shot.pinned.includes(field)) continue;
        if (field in template) request[field] = clone(template[field]);
        else delete request[field];
      }
      return { ...shot, request: normalizeFactoryRequest(request) };
    }),
  };
}

export function countPinnedShots(plan: FactoryPlan): number {
  return plan.shots.filter((shot) => shot.pinned.length > 0).length;
}

export function summarizeFactory(plan: FactoryPlan): FactorySummary {
  return plan.shots.reduce<FactorySummary>(
    (summary, shot) => {
      if (['draft', 'queued'].includes(shot.status)) summary.waiting += 1;
      if (['validating', 'submitting', 'running'].includes(shot.status))
        summary.active += 1;
      if (shot.status === 'succeeded') summary.completed += 1;
      if (shot.status === 'failed') summary.failed += 1;
      return summary;
    },
    {
      total: plan.shots.length,
      waiting: 0,
      active: 0,
      completed: 0,
      failed: 0,
    },
  );
}

export function nextQueuedShot(plan: FactoryPlan): FactoryShot | undefined {
  return plan.shots.find((shot) => shot.status === 'queued');
}

export function activeFactoryShot(plan: FactoryPlan): FactoryShot | undefined {
  return plan.shots.find((shot) =>
    ['validating', 'submitting', 'running'].includes(shot.status),
  );
}

export function reopenFactoryShot(
  shot: FactoryShot,
  idempotencyKey: string,
): FactoryShot {
  return {
    ...shot,
    status: 'draft',
    idempotencyKey,
    progress: 0,
    message: undefined,
    error: undefined,
  };
}

export function clearFactoryShotOutput(
  shot: FactoryShot,
  idempotencyKey: string,
): FactoryShot {
  return {
    ...shot,
    status: 'draft',
    idempotencyKey,
    jobId: undefined,
    statusUrl: undefined,
    outputUrl: undefined,
    posterUrl: undefined,
    progress: 0,
    message: undefined,
    error: undefined,
  };
}
