import test from 'node:test';
import assert from 'node:assert/strict';
import {
  beatInterval,
  breakdownCues,
  mergeBreakdownShots,
  planBreakdown,
  snapToBeat,
  splitBreakdownShot,
} from '../lib/breakdown.ts';

/**
 * Shaped like 三線リフで帰ろう as the audio service measured it: 166.4 s, 104.17 BPM, 285 beats,
 * 11 section boundaries, 40 lyric lines. See the alignment section of docs/GB10_SETUP.md.
 */
const DURATION = 166.4;
const BEAT = 60 / 104.17;
const beats = Array.from({ length: 285 }, (_, i) => Number((i * BEAT).toFixed(3)));
const sections = [14.4, 31.7, 48.9, 62.3, 79.8, 95.1, 110.6, 124.2, 139.5, 152.8, 161.2];
const lyrics = Array.from({ length: 40 }, (_, i) => ({
  time: Number((10.4 + i * 3.85).toFixed(2)),
  text: `line ${i + 1}`,
}));

const song = (over = {}) => ({
  durationSeconds: DURATION,
  beats,
  sections,
  lyrics,
  lyricOffsetSeconds: -0.9,
  segmentSeconds: 10,
  directing: { camera: 'static', lighting: 'warm' },
  ...over,
});

const onBeat = (time) => beats.some((beat) => Math.abs(beat - time) < 1e-6);

test('a 166 second song at segment_seconds=10 lands in the expected shot count', () => {
  const { shots } = planBreakdown(song());
  assert.ok(shots.length >= 17 && shots.length <= 24, `got ${shots.length} shots`);
});

test('no shot runs past the cap, and the shots tile the song without gaps', () => {
  const { shots } = planBreakdown(song());
  assert.equal(shots[0].start, 0);
  assert.equal(shots.at(-1).end, DURATION);
  for (const shot of shots) {
    assert.ok(shot.end - shot.start <= 10 + 1e-6, `shot ${shot.index} is ${shot.end - shot.start}s`);
    assert.ok(shot.end > shot.start);
  }
  for (let i = 1; i < shots.length; i += 1) {
    assert.equal(shots[i].start, shots[i - 1].end);
  }
});

test('every cut sits on a beat', () => {
  const { shots, cuts } = planBreakdown(song());
  assert.equal(cuts.length, shots.length - 1);
  for (const cut of cuts) assert.ok(onBeat(cut), `cut at ${cut} is off the grid`);
});

test('a cut is never further than one beat from the boundary that caused it', () => {
  const { shots } = planBreakdown(song());
  const wanted = [...sections, ...lyrics.map((line) => line.time - 0.9)];
  for (const shot of shots) {
    if (shot.endedBy !== 'section' && shot.endedBy !== 'lyric') continue;
    const nearest = Math.min(...wanted.map((time) => Math.abs(time - shot.end)));
    assert.ok(nearest <= BEAT + 1e-6, `shot ${shot.index} ends ${nearest}s from any boundary`);
  }
});

test('section boundaries win over lyric lines and are not passed over', () => {
  const { cuts } = planBreakdown(song());
  const snappedSections = sections
    .map((time) => snapToBeat(beats, time, BEAT))
    .filter((time) => time !== undefined);
  for (const boundary of snappedSections) {
    assert.ok(cuts.includes(boundary), `section boundary ${boundary} was skipped`);
  }
});

test('the Bible offset moves the lyric times the shots are grouped by', () => {
  const shifted = planBreakdown(song({ lyricOffsetSeconds: -0.9 }));
  const raw = planBreakdown(song({ lyricOffsetSeconds: 0 }));
  const first = shifted.shots.flatMap((shot) => shot.lyrics)[0];
  assert.equal(Number(first.time.toFixed(2)), 9.5);
  assert.equal(raw.shots.flatMap((shot) => shot.lyrics)[0].time, 10.4);
});

test('a stretch with no words becomes a breathing shot', () => {
  // The song opens with an instrumental bar: the first lyric lands at 10.4 - 0.9 = 9.5 s.
  const { shots } = planBreakdown(song());
  assert.equal(shots[0].kind, 'breathing');
  assert.equal(shots[0].lyrics.length, 0);
  assert.ok(shots.some((shot) => shot.kind === 'lyric'));
});

test('with no lyrics at all every shot is a breathing shot', () => {
  const { shots } = planBreakdown(song({ lyrics: [] }));
  assert.ok(shots.length > 0);
  assert.ok(shots.every((shot) => shot.kind === 'breathing'));
});

test('each cue sits at the head of its shot, carries the Bible and leaves the action empty', () => {
  const { shots } = planBreakdown(song());
  for (const shot of shots) {
    assert.equal(shot.cue.time, shot.start);
    assert.equal(shot.cue.action, '');
    assert.deepEqual(shot.cue.directing, { camera: 'static', lighting: 'warm' });
  }
  const cues = breakdownCues(shots);
  assert.equal(new Set(cues.map((cue) => cue.time)).size, cues.length);
  cues[0].directing.camera = 'dolly';
  assert.equal(shots[0].cue.directing.camera, 'static');
});

test('merging two shots recomputes the cues and the lyrics they hold', () => {
  const input = song();
  const { shots } = planBreakdown(input);
  const lines = shots.flatMap((shot) => shot.lyrics);
  const before = shots.length;
  const merged = mergeBreakdownShots(shots, 1, lines);

  assert.equal(merged.length, before - 1);
  assert.equal(merged[1].start, shots[1].start);
  assert.equal(merged[1].end, shots[2].end);
  assert.equal(merged[1].cue.time, merged[1].start);
  assert.deepEqual(
    merged[1].lyrics.map((line) => line.time),
    [...shots[1].lyrics, ...shots[2].lyrics].map((line) => line.time),
  );
  merged.forEach((shot, index) => {
    assert.equal(shot.index, index);
    assert.equal(shot.cue.time, shot.start);
  });
  assert.equal(merged.at(-1).end, DURATION);
});

test('merging past the end of the list changes nothing', () => {
  const { shots } = planBreakdown(song());
  assert.equal(mergeBreakdownShots(shots, shots.length - 1), shots);
  assert.equal(mergeBreakdownShots(shots, -1), shots);
});

test('a split snaps to a beat and gives the tail its own empty cue', () => {
  const input = song();
  const { shots } = planBreakdown(input);
  const lines = shots.flatMap((shot) => shot.lyrics);
  const target = shots[3];
  const middle = (target.start + target.end) / 2;
  const split = splitBreakdownShot(shots, 3, middle + 0.1, beats, lines, BEAT);

  assert.equal(split.length, shots.length + 1);
  assert.ok(onBeat(split[3].end), 'the split point is off the grid');
  assert.equal(split[4].start, split[3].end);
  assert.equal(split[4].cue.time, split[4].start);
  assert.equal(split[4].cue.action, '');
  assert.equal(split[4].end, target.end);
  split.forEach((shot, index) => assert.equal(shot.index, index));
});

test('a split outside the shot is refused', () => {
  const { shots } = planBreakdown(song());
  assert.equal(splitBreakdownShot(shots, 3, shots[3].start, beats), shots);
  assert.equal(splitBreakdownShot(shots, 3, shots[3].end + 5, beats), shots);
  assert.equal(splitBreakdownShot(shots, 99, 10, beats), shots);
});

test('the shot count is capped so the breakdown can still be imported as cues', () => {
  const { shots } = planBreakdown(song({ segmentSeconds: 2, maxShots: 60 }));
  assert.ok(shots.length <= 60, `got ${shots.length} shots`);
});

test('snapping refuses a candidate further than the tolerance', () => {
  assert.equal(snapToBeat([0, 1, 2], 1.2, 0.3), 1);
  assert.equal(snapToBeat([0, 1, 2], 1.5, 0.3), undefined);
  assert.equal(snapToBeat([], 1, 1), undefined);
});

test('the beat grid is measured by the median, so one dropped beat does not widen it', () => {
  assert.equal(Number(beatInterval([0, 0.5, 1, 2, 2.5], 3).toFixed(3)), 0.5);
  assert.equal(beatInterval([], 4), 4);
});

test('without beats the cuts fall back to the cap rather than throwing', () => {
  const { shots } = planBreakdown(song({ beats: [], sections: [], lyrics: [] }));
  for (const shot of shots) assert.ok(shot.end - shot.start <= 10 + 1e-6);
  assert.equal(shots.at(-1).end, DURATION);
});

test('impossible inputs are rejected rather than guessed at', () => {
  assert.throws(() => planBreakdown(song({ durationSeconds: 0 })), /durationSeconds/);
  assert.throws(() => planBreakdown(song({ segmentSeconds: 1 })), /segmentSeconds/);
  assert.throws(() => planBreakdown(song({ segmentSeconds: 25 })), /segmentSeconds/);
});
