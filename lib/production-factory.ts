export const FACTORY_FORMAT = 'ltx-production-factory';
export const FACTORY_VERSION = 1;
export const MAX_FACTORY_SHOTS = 100;

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

export function createFactoryPlan(id: string, now = new Date()): FactoryPlan {
  const stamp = now.toISOString();
  return {
    format: FACTORY_FORMAT,
    version: FACTORY_VERSION,
    id,
    title: 'UNTITLED PRODUCTION',
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
): FactoryShot {
  const request = normalizeFactoryRequest(requestValue);
  return {
    id,
    title: title(titleValue, `SHOT ${String(index + 1).padStart(2, '0')}`),
    request,
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
  if (raw.format !== FACTORY_FORMAT || raw.version !== FACTORY_VERSION) {
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
  if (Array.isArray(parsed)) {
    entries = parsed;
  } else {
    const root = record(parsed, 'Factory import');
    if (root.format === FACTORY_FORMAT) {
      if (root.version !== FACTORY_VERSION) {
        throw new Error('Unsupported production factory version');
      }
      plan.title = title(root.title, plan.title);
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
        (key) => !['title', 'request'].includes(key),
      );
      if (extra.length)
        throw new Error(
          `shots[${index}] has unsupported fields: ${extra.join(', ')}`,
        );
      return createFactoryShot(row.request, makeId(), index, row.title);
    }
    return createFactoryShot(row, makeId(), index);
  });
  return plan;
}

export function serializeFactoryPlan(plan: FactoryPlan): string {
  return `${JSON.stringify(
    {
      format: FACTORY_FORMAT,
      version: FACTORY_VERSION,
      title: plan.title,
      shots: plan.shots.map((shot) => ({
        title: shot.title,
        request: shot.request,
      })),
    },
    null,
    2,
  )}\n`;
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
