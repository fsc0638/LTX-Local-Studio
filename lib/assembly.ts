/**
 * Assembly readiness, pure. The cut takes exactly one take per shot - the one review accepted -
 * so a plan is ready when every shot has one, and the list of shots that do not is what the page
 * shows next to the disabled button.
 */
import type { FactoryPlan, FactoryShot } from './production-factory';

export type AssemblyReadiness = {
  ready: boolean;
  /** Shots without an accepted take, in plan order. */
  missing: { index: number; id: string; title: string }[];
  total: number;
};

export function assemblyReadiness(plan: FactoryPlan | null): AssemblyReadiness {
  if (!plan || !plan.shots.length) return { ready: false, missing: [], total: 0 };
  const missing = plan.shots
    .map((shot: FactoryShot, index: number) => ({ index, id: shot.id, title: shot.title, ok: Boolean(shot.acceptedTakeId) }))
    .filter((item) => !item.ok)
    .map(({ index, id, title }) => ({ index, id, title }));
  return { ready: missing.length === 0, missing, total: plan.shots.length };
}

/** A file name for the cut and its manifest, safe for a download attribute. */
export function assemblyFileName(title: string, kind: 'mp4' | 'json'): string {
  const base = title.replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'cut';
  return kind === 'mp4' ? `${base}.mp4` : `${base}.manifest.json`;
}
