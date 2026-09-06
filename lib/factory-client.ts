import { serviceFetch } from '@/lib/service-session';
import {
  restoreFactoryPlan,
  type FactoryPlan,
  type FactoryShot,
} from '@/lib/production-factory';

/**
 * Client for /api/v1/factory. The host owns the queue now: the browser reads a plan, edits it and
 * asks the host to run it, but never validates or submits a shot itself. That loop lives in
 * ltx-api so it survives a closed tab.
 */

export type FactorySummaryRow = {
  id: string;
  title: string;
  status: FactoryPlan['status'];
  shots: number;
  updatedAt: number;
};

export type FactoryTake = {
  id: string;
  shotId: string;
  jobId: string | null;
  outputUrl: string | null;
  posterUrl: string | null;
  scores: Record<string, unknown> | null;
  verdict: 'pending' | 'accepted' | 'rejected' | 'overridden';
  reason: string | null;
  createdAt: number;
  /** Set when the recycle bin took this take's output. The row stays as history. */
  deletedAt: number | null;
  /** Who accepted this take against a red light, and when. Null for a plain acceptance. */
  overriddenBy: string | null;
  overriddenAt: number | null;
  /** The VLM's sentence, kept once paid for; disagreed_by/at when the reviewer rejected it. */
  opinion: {
    text: string;
    model?: string;
    at?: number;
    disagreed_by?: string;
    disagreed_at?: number;
  } | null;
  /** Present on the project-level listing: the lines and lights in force for this take. */
  thresholds?: import('./review').Thresholds;
  lights?: Record<import('./review').LightKey, import('./review').Light>;
};

export class FactoryRequestError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function call(path: string, init?: RequestInit): Promise<unknown> {
  const response = await serviceFetch(`/api/v1/factory${path}`, init);
  const text = await response.text();
  let body: unknown = undefined;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined;
  }
  if (!response.ok) {
    const detail = (body || {}) as { error?: string; code?: string };
    throw new FactoryRequestError(
      response.status,
      detail.code || 'request_failed',
      detail.error || `HTTP ${response.status}`,
    );
  }
  return body;
}

function json(payload: unknown): RequestInit {
  return {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  };
}

/** Every response that is a plan goes through the same restore the import path uses, so a
 * malformed payload is rejected here rather than halfway down the render tree. */
function plan(body: unknown): FactoryPlan {
  return restoreFactoryPlan(body);
}

export async function listProjects(): Promise<FactorySummaryRow[]> {
  const body = (await call('/projects')) as { projects?: FactorySummaryRow[] };
  return body.projects || [];
}

export async function createProject(
  seed: Partial<FactoryPlan> = {},
): Promise<FactoryPlan> {
  return plan(await call('/projects', json(seed)));
}

export async function getProject(id: string): Promise<FactoryPlan> {
  return plan(await call(`/projects/${id}`));
}

export async function updateProject(
  id: string,
  patch: { title?: string; bible?: FactoryPlan['bible']; status?: FactoryPlan['status'] },
): Promise<FactoryPlan> {
  return plan(await call(`/projects/${id}`, json(patch)));
}

export async function deleteProject(id: string): Promise<void> {
  await call(`/projects/${id}`, { method: 'DELETE' });
}

/** The whole list at once: the editor reorders, merges and splits shots, and a stream of
 * per-shot patches could leave the server holding an order the user never saw. */
export async function replaceShots(
  id: string,
  shots: FactoryShot[],
): Promise<FactoryPlan> {
  return plan(
    await call(
      `/projects/${id}/shots`,
      json({
        shots: shots.map((shot) => ({
          id: shot.id,
          title: shot.title,
          request: shot.request,
          pinned: shot.pinned,
          status: shot.status,
          idempotencyKey: shot.idempotencyKey,
        })),
      }),
    ),
  );
}

/**
 * Make this take the shot's accepted one. The server computes the light itself and records an
 * override if it was red; `strict` asks it to judge against the adjacent-shot thresholds.
 */
export async function acceptTake(takeId: string, strict = false): Promise<FactoryPlan> {
  return plan(await call(`/takes/${takeId}/accept`, json({ strict })));
}

/** Every take in the project, grouped by shot id, each with its thresholds and lights. */
export async function projectTakes(id: string): Promise<Record<string, FactoryTake[]>> {
  const body = (await call(`/projects/${id}/takes`)) as { takes?: Record<string, FactoryTake[]> };
  return body.takes || {};
}

/** Ask the host for one sentence about a take. Charged to the project's draft budget. */
export async function takeOpinion(takeId: string): Promise<NonNullable<FactoryTake['opinion']>> {
  const body = (await call(`/takes/${takeId}/opinion`, json({}))) as {
    opinion: NonNullable<FactoryTake['opinion']>;
  };
  return body.opinion;
}

export type FactoryKeyframe = {
  id: string;
  shotId: string;
  jobId: string | null;
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

export type KeyframeRun = {
  status?: 'running' | 'stopping' | 'stopped' | 'done' | 'failed';
  started_at?: number;
  finished_at?: number;
  total?: number;
  done?: number;
  current?: string | null;
  estimate_seconds?: number;
  error?: string;
};

export type KeyframeListing = {
  run: KeyframeRun;
  keyframes: Record<string, FactoryKeyframe[]>;
  gpu: { holder: string | null; imagegen_loaded: string[] };
  costs: { switch_seconds: number; per_keyframe_seconds: number };
};

export async function projectKeyframes(id: string): Promise<KeyframeListing> {
  return (await call(`/projects/${id}/keyframes`)) as KeyframeListing;
}

/** Start the batch for the whole project; the host runs it and the listing reports progress. */
export async function runKeyframes(id: string): Promise<{ run: KeyframeRun }> {
  return (await call(`/projects/${id}/keyframes/run`, json({}))) as { run: KeyframeRun };
}

export async function stopKeyframes(id: string): Promise<{ run: KeyframeRun }> {
  return (await call(`/projects/${id}/keyframes/stop`, json({}))) as { run: KeyframeRun };
}

/** The keyframe becomes the shot's picture: promoted to an asset, set as image_id and pinned. */
export async function approveKeyframe(keyframeId: string): Promise<FactoryPlan> {
  return plan(await call(`/keyframes/${keyframeId}/approve`, json({})));
}

export async function rejectKeyframe(keyframeId: string, reason: string): Promise<FactoryPlan> {
  return plan(await call(`/keyframes/${keyframeId}/reject`, json({ reason })));
}

export async function disagreeOpinion(takeId: string): Promise<FactoryPlan> {
  return plan(await call(`/takes/${takeId}/disagree`, json({})));
}

/**
 * Send a take back. The reason is required and is carried into the next take's prompt as an
 * "避免：" line; the server keeps earlier lines, so repeated rejections accumulate.
 */
export async function rejectTake(takeId: string, reason: string): Promise<FactoryPlan> {
  return plan(await call(`/takes/${takeId}/reject`, json({ reason })));
}

export async function runProject(id: string): Promise<FactoryPlan> {
  return plan(await call(`/projects/${id}/run`, { method: 'POST' }));
}

export async function pauseProject(id: string): Promise<FactoryPlan> {
  return plan(await call(`/projects/${id}/pause`, { method: 'POST' }));
}

export async function listTakes(shotId: string): Promise<FactoryTake[]> {
  const body = (await call(`/shots/${shotId}/takes`)) as { takes?: FactoryTake[] };
  return body.takes || [];
}

const LEGACY_PREFIX = 'ltx-production-factory-v1:';

/** A plan left in this browser by the pre-B1 build, if any. Returned rather than uploaded so the
 * user chooses: silently pushing local state to the host could resurrect a plan they abandoned. */
export function localPlan(userId: string): FactoryPlan | null {
  try {
    const saved = window.localStorage.getItem(`${LEGACY_PREFIX}${userId || 'local'}`);
    return saved ? restoreFactoryPlan(JSON.parse(saved)) : null;
  } catch {
    return null;
  }
}

export function forgetLocalPlan(userId: string): void {
  try {
    window.localStorage.removeItem(`${LEGACY_PREFIX}${userId || 'local'}`);
  } catch {
    // Storage can be denied; the upload already succeeded, so this is not worth surfacing.
  }
}

/** Move a browser-held plan to the host once, keeping its shots and their idempotency keys. */
export async function uploadLocalPlan(local: FactoryPlan): Promise<FactoryPlan> {
  const created = await createProject({ title: local.title, bible: local.bible });
  return local.shots.length ? replaceShots(created.id, local.shots) : created;
}
