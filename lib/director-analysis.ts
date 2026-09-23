import type { BreakdownShot } from '@/lib/breakdown';

export type DirectorSongAnalysis = {
  genre: string;
  lyrical_meaning: string;
  visual_concept: string;
  story_outline: string;
  emotional_arc: string;
  continuity_rules: string;
  producer_strategy: string;
};

export type DirectorShotSuggestion = {
  shot_id: string;
  scene: string;
  mood: string;
  atmosphere: string;
  character_appearance: string;
  wardrobe: string;
  facial_expression: string;
  body_language: string;
  action: string;
  progression: string;
  emotion: string;
  camera: string;
  lighting: string;
  continuity: string;
  breathing: string;
  prompt: string;
};

export type DirectorAnalysis = {
  song: DirectorSongAnalysis;
  shots: DirectorShotSuggestion[];
};

export function canRunDirectorAnalysis({
  projectId,
  musicId,
  draftAvailable,
  breakdownBusy,
  directorBusy,
}: {
  projectId?: string;
  musicId?: string;
  draftAvailable?: boolean;
  breakdownBusy: boolean;
  directorBusy: boolean;
}): boolean {
  return Boolean(projectId && musicId && draftAvailable === true && !breakdownBusy && !directorBusy);
}

/** Applying advice remains an explicit edit. The worker accepts one full local-model prompt. */
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
      cue: { ...shot.cue, action: suggestion.prompt.trim().slice(0, 4000) },
    };
  });
}
