import assert from 'node:assert/strict';
import test from 'node:test';

import { breakdownFactoryEntries } from '../lib/breakdown-factory.ts';
import { planBreakdown } from '../lib/breakdown.ts';

test('a full-song breakdown becomes local factory shots without truncating the tail', () => {
  const request = {
    prompt: 'base look',
    duration_seconds: 2,
    seed: 42,
    render_mode: 'sequence',
    directing: { camera: 'locked' },
    timeline: {
      audio_id: 'song-1',
      audio_start_seconds: 3,
      audio_mode: 'soundtrack',
      lrc: '[00:00.000]old',
      lrc_timebase: 'output',
      cues: [{ time: 190, action: 'invalid in the old two-second request' }],
    },
  };
  const shots = [
    {
      id: 'shot-0',
      index: 0,
      start: 0,
      end: 100,
      kind: 'lyric',
      endedBy: 'limit',
      lyrics: [{ time: 1.5, text: 'first' }],
      cue: { time: 0, action: 'wide opening', directing: { camera: 'push' } },
    },
    {
      id: 'shot-100',
      index: 1,
      start: 100,
      end: 198.88,
      kind: 'lyric',
      endedBy: 'end',
      lyrics: [{ time: 197.5, text: 'last line' }],
      cue: {
        time: 100,
        action: 'final close-up',
        directing: { emotion: 'hope' },
      },
    },
  ];

  const entries = breakdownFactoryEntries(request, shots);

  assert.equal(entries.length, 2);
  assert.equal(entries[0].request.duration_seconds, 100);
  assert.equal(entries[1].request.duration_seconds, 98.88);
  assert.equal(entries[1].request.timeline.audio_start_seconds, 103);
  assert.deepEqual(entries[1].request.timeline.cues, [
    {
      time: 0,
      action: 'final close-up',
      directing: { camera: 'locked', emotion: 'hope' },
    },
  ]);
  assert.match(entries[1].request.timeline.lrc, /^\[01:37\.500\]last line$/);
  assert.equal(entries[1].startSeconds, 100);
  assert.deepEqual(entries[1].pinned, ['directing', 'timeline']);
  assert.equal(
    entries.reduce((total, entry) => total + entry.request.duration_seconds, 0),
    198.88,
  );
});

test('a 198.88 second song stays complete while every generated job remains locally valid', () => {
  const duration = 198.88;
  const breakdown = planBreakdown({
    durationSeconds: duration,
    beats: Array.from({ length: 398 }, (_, index) => index * 0.5),
    sections: [60, 120, 180],
    segmentSeconds: 10,
  });
  const entries = breakdownFactoryEntries(
    {
      prompt: 'base look',
      duration_seconds: 2,
      seed: 42,
      render_mode: 'sequence',
      segment_seconds: 10,
      timeline: { audio_id: 'song-1', audio_start_seconds: 0 },
    },
    breakdown.shots,
  );

  assert.ok(entries.length > 1);
  assert.ok(entries.every((entry) => entry.request.duration_seconds <= 180));
  assert.ok(
    entries.every((entry) =>
      entry.request.timeline.cues.every(
        (cue) => cue.time >= 0 && cue.time <= entry.request.duration_seconds,
      ),
    ),
  );
  assert.equal(
    entries.at(-1).request.timeline.audio_start_seconds,
    breakdown.shots.at(-1).start,
  );
  assert.equal(
    entries.reduce((total, entry) => total + entry.request.duration_seconds, 0),
    duration,
  );
});
