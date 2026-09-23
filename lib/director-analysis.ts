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
  angle?: string;
  lighting: string;
  continuity: string;
  breathing: string;
  prompt: string;
};

const DIRECTOR_ANGLES = new Set([
  'front', 'three_quarter', 'left_three_quarter', 'right_three_quarter', 'profile',
  'left_profile', 'right_profile', 'back', 'low', 'high', 'over_shoulder',
]);

function directorAngle(suggestion: DirectorShotSuggestion): string | undefined {
  const exact = suggestion.angle?.trim();
  if (exact && DIRECTOR_ANGLES.has(exact)) return exact;
  const camera = suggestion.camera?.toLowerCase() || '';
  const aliases: [RegExp, string][] = [
    [/left.*(?:profile|side)|(?:profile|side).*left/, 'left_profile'],
    [/right.*(?:profile|side)|(?:profile|side).*right/, 'right_profile'],
    [/left.*(?:three.quarter|3\/4)|(?:three.quarter|3\/4).*left/, 'left_three_quarter'],
    [/right.*(?:three.quarter|3\/4)|(?:three.quarter|3\/4).*right/, 'right_three_quarter'],
    [/over.the.shoulder|over shoulder/, 'over_shoulder'],
    [/three.quarter|3\/4/, 'three_quarter'],
    [/profile|side view/, 'profile'],
    [/back view|from behind/, 'back'],
    [/low.angle/, 'low'],
    [/high.angle|overhead|bird.s.eye/, 'high'],
    [/front|eye.level|head.on/, 'front'],
  ];
  return aliases.find(([pattern]) => pattern.test(camera))?.[1];
}

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
    const angle = directorAngle(suggestion);
    return {
      ...shot,
      cue: {
        ...shot.cue,
        action: suggestion.prompt.trim().slice(0, 4000),
        directing: { ...shot.cue.directing, ...(angle ? { angle } : {}) },
      },
    };
  });
}
