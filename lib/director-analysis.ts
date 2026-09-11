import type { BreakdownShot } from '@/lib/breakdown';

export type DirectorSongAnalysis = {
  genre: string;
  lyrical_meaning: string;
  visual_concept: string;
  emotional_arc: string;
  producer_strategy: string;
};

export type DirectorShotSuggestion = {
  shot_id: string;
  scene: string;
  mood: string;
  atmosphere: string;
  action: string;
  progression: string;
  emotion: string;
  camera: string;
  breathing: string;
  prompt: string;
};

export type DirectorAnalysis = {
  song: DirectorSongAnalysis;
  shots: DirectorShotSuggestion[];
};

/** Applying advice remains an explicit edit. The worker's cue contract caps action at 600 chars. */
export function applyDirectorSuggestions(
  shots: BreakdownShot[],
  suggestions: DirectorShotSuggestion[],
  selectedIds?: Set<string>,
): BreakdownShot[] {
  const byId = new Map(suggestions.map((suggestion) => [suggestion.shot_id, suggestion]));
  return shots.map((shot) => {
    if (selectedIds && !selectedIds.has(shot.id)) return shot;
    const suggestion = byId.get(shot.id);
    if (!suggestion) return shot;
    return {
      ...shot,
      cue: { ...shot.cue, action: suggestion.prompt.trim().slice(0, 600) },
    };
  });
}
