type FactoryRequest = Record<string, unknown> & { prompt: string };

type StoryboardTimeline = {
  music: { id: string } | null;
  audioStart: number;
  audioMode: string;
  lrc: string;
  lrcTimebase: 'output' | 'music';
  segmentSeconds: number;
  cues: { time: number; action: string; directing: Record<string, string> }[];
};

export type StoryboardExportInput = {
  baseRequest: FactoryRequest;
  timeline: StoryboardTimeline;
  durationSeconds: number;
  prompt: string;
};

/**
 * Build the full-song request exported from stage 01.
 *
 * The sandbox and the storyboard share controls, but their payloads must not share defaults:
 * stage 01 always exports the measured song duration, the current shot cues and an explicitly
 * reviewed whole-song prompt. Project Bible locks are projected before those live timeline values.
 */
export function buildStoryboardExportRequest({
  baseRequest,
  timeline,
  durationSeconds,
  prompt,
}: StoryboardExportInput): FactoryRequest {
  const cleanPrompt = prompt.trim();
  if (!cleanPrompt) throw new Error('storyboard_prompt_required');
  if (!timeline.music) throw new Error('storyboard_music_required');
  if (!timeline.cues.length) throw new Error('storyboard_cues_required');
  if (timeline.cues.some((cue) => !cue.action.trim())) {
    throw new Error('storyboard_shot_prompts_required');
  }
  if (
    !Number.isFinite(durationSeconds) ||
    durationSeconds <= 0 ||
    durationSeconds > 180
  ) {
    throw new Error('storyboard_duration_invalid');
  }

  return {
    ...baseRequest,
    prompt: cleanPrompt,
    duration_seconds: Math.round(durationSeconds * 1000) / 1000,
    render_mode: 'sequence',
    segment_seconds: timeline.segmentSeconds,
    audio: true,
    timeline: {
      audio_id: timeline.music.id,
      audio_start_seconds: timeline.audioStart,
      audio_mode: timeline.audioMode,
      lrc: timeline.lrc,
      lrc_timebase: timeline.lrcTimebase,
      cues: timeline.cues.map((cue) => ({
        time: cue.time,
        action: cue.action,
        directing: { ...cue.directing },
      })),
    },
  };
}
