import assert from 'node:assert/strict';
import test from 'node:test';

import { syncFactoryMusicToTimeline } from '../lib/factory-timeline.ts';

const asset = {
  id: 'song-1',
  name: 'song.wav',
  kind: 'audio',
  url: '/api/v1/assets/song-1',
};

const timeline = {
  enabled: true,
  music: { ...asset, id: 'old-song' },
  audioStart: 2,
  audioMode: 'condition',
  lrc: '[00:02.00]old',
  lrcTimebase: 'music',
  cues: [{ time: 2, action: 'old cue', directing: {} }],
  segmentSeconds: 10,
};

const bibleMusic = {
  audio_id: 'song-1',
  audio_start_seconds: 0,
  audio_mode: 'soundtrack',
  lrc: '[00:05.00]new',
  lrc_timebase: 'output',
};

test('stage 01 receives music and LRC selected in the Production Bible', () => {
  const synced = syncFactoryMusicToTimeline(timeline, bibleMusic, asset);
  assert.equal(synced.enabled, true);
  assert.equal(synced.music.id, 'song-1');
  assert.equal(synced.audioStart, 0);
  assert.equal(synced.audioMode, 'soundtrack');
  assert.equal(synced.lrc, '[00:05.00]new');
  assert.equal(synced.lrcTimebase, 'output');
  assert.deepEqual(synced.cues, []);
});

test('an identical Bible refresh preserves manually edited cues', () => {
  const current = {
    ...timeline,
    music: asset,
    audioStart: 0,
    audioMode: 'soundtrack',
    lrc: '[00:05.00]new',
    lrcTimebase: 'output',
  };
  assert.equal(syncFactoryMusicToTimeline(current, bibleMusic, asset), current);
});

test('an unresolved or mismatched asset does not replace the timeline', () => {
  assert.equal(
    syncFactoryMusicToTimeline(timeline, bibleMusic, { ...asset, id: 'other' }),
    timeline,
  );
});

test('an unknown Bible timebase falls back to the worker-safe output basis', () => {
  const synced = syncFactoryMusicToTimeline(
    timeline,
    { ...bibleMusic, lrc_timebase: 'unknown' },
    asset,
  );
  assert.equal(synced.lrcTimebase, 'output');
});
