import type { Asset } from '@/components/media-library';
import type { TimelineDraft } from '@/components/mv-controls';
import type { FactoryMusic } from '@/lib/production-factory';

/**
 * Keep stage 01 on the same music source as the Production Bible.
 *
 * The Bible stores only an asset id while the timeline editor needs the full asset record. The
 * caller resolves that record from the signed-in user's media library before applying this bridge.
 * Existing cues are discarded only when their music or lyric source changed; otherwise opening the
 * stage is idempotent and preserves manual cue edits.
 */
export function syncFactoryMusicToTimeline(
  current: TimelineDraft,
  music: FactoryMusic,
  asset: Asset,
): TimelineDraft {
  if (asset.id !== music.audio_id) return current;

  const lrcTimebase =
    music.lrc_timebase === 'music' || music.lrc_timebase === 'output'
      ? music.lrc_timebase
      : 'output';
  const sourceChanged =
    current.music?.id !== asset.id ||
    current.audioStart !== music.audio_start_seconds ||
    current.audioMode !== music.audio_mode ||
    current.lrc !== music.lrc ||
    current.lrcTimebase !== lrcTimebase;

  if (!sourceChanged && current.enabled) return current;
  return {
    ...current,
    enabled: true,
    music: asset,
    audioStart: music.audio_start_seconds,
    audioMode: music.audio_mode,
    lrc: music.lrc,
    lrcTimebase,
    cues: sourceChanged ? [] : current.cues,
  };
}
