import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_THRESHOLDS,
  consistencyCurve,
  consistencyLine,
  consistencyMethod,
  isRed,
  lights,
  resolveThresholds,
  takeScores,
} from '../lib/review.ts';

// The same fixtures as tests/test_factory_review.py. If the numbers below change, change them
// there too - the point is that both sides agree on exactly these cases.
const RED = {
  media: { kind: 'video', frozen_ratio: 0.1, black_ratio: 0 },
  consistency: { median: 0.62, per_frame: [0.6, 0.64], method_per_frame: ['face_facenet', 'face_facenet'] },
  style: { median: 0.9 },
  motion: { median: 1.2 },
};
const GREEN = { ...RED, consistency: { ...RED.consistency, median: 0.91, per_frame: [0.9, 0.92] } };
const UNSCORED = { status: 'unscored', reason: 'judge_unavailable' };

test('defaults are the architecture placeholders and say they are uncalibrated', () => {
  const t = resolveThresholds({});
  assert.deepEqual([t.cj, t.sj, t.mq], [0.8, 0.85, 0.5]);
  assert.equal(t.calibrated, false);
  assert.deepEqual(DEFAULT_THRESHOLDS, { cj: 0.8, cj_dino: 0.8, sj: 0.85, mq: 0.5 });
});

test('the Bible, then the shot, override the defaults; nonsense is ignored', () => {
  const bible = { thresholds: { cj: 0.7, calibrated: true } };
  assert.equal(resolveThresholds(bible).cj, 0.7);
  assert.equal(resolveThresholds(bible).calibrated, true);
  assert.equal(resolveThresholds(bible, { thresholds: { cj: 0.95 } }).cj, 0.95);
  assert.equal(resolveThresholds({}, { thresholds: { cj: 7 } }).cj, 0.8);
});

test('strict mode uses the stricter set', () => {
  assert.equal(resolveThresholds({}, undefined, true).cj, 0.85);
  assert.equal(resolveThresholds({ thresholds: { cj: 0.7, strict: { cj: 0.78 } } }, undefined, true).cj, 0.78);
});

test('lights match the server on the shared fixtures', () => {
  const t = resolveThresholds({});
  assert.deepEqual(lights(RED, t), { cj: 'red', sj: 'green', mq: 'green' });
  assert.deepEqual(lights(GREEN, t), { cj: 'green', sj: 'green', mq: 'green' });
  assert.deepEqual(lights(UNSCORED, t), { cj: 'unscored', sj: 'unscored', mq: 'unscored' });
  assert.equal(lights(null, t).cj, 'unscored');
  assert.equal(isRed(UNSCORED, t), false, 'no score is not a red light');
  assert.equal(isRed(RED, t), true);
});

test('a still has no motion score', () => {
  const still = { ...GREEN, media: { kind: 'image' }, motion: null };
  assert.equal(takeScores(still).mq, null);
  assert.equal(lights(still, resolveThresholds({})).mq, 'unscored');
});

test('the per-frame curve carries the method that scored each second', () => {
  assert.deepEqual(consistencyCurve(RED), [
    { second: 0, value: 0.6, method: 'face_facenet' },
    { second: 1, value: 0.64, method: 'face_facenet' },
  ]);
  assert.deepEqual(consistencyCurve(UNSCORED), []);
  assert.deepEqual(consistencyCurve(null), []);
});

// Shared with test_factory_review.py as well: a take scored without faces.
const DINO = {
  ...RED,
  consistency: { median: 0.7, per_frame: [0.68, 0.72], method_per_frame: ['dinov2_large', 'dinov2_large'] },
};

test('a take scored by DINOv2 is judged against cj_dino, not cj', () => {
  const t = resolveThresholds({ thresholds: { cj: 0.8, cj_dino: 0.65 } });
  assert.equal(consistencyMethod(DINO), 'dinov2_large');
  assert.equal(consistencyMethod(RED), 'face_facenet');
  assert.equal(consistencyLine(DINO, t), 0.65);
  assert.equal(lights(DINO, t).cj, 'green', '0.70 is above the dino line');
  assert.equal(lights({ ...DINO, consistency: { ...DINO.consistency, median: 0.6 } }, t).cj, 'red');
  // Same median against the face line would be red: the lines really are different.
  assert.equal(lights({ ...RED, consistency: { ...RED.consistency, median: 0.7 } }, t).cj, 'red');
});

test('cj_dino defaults to the same placeholder and can be overridden per shot', () => {
  assert.equal(resolveThresholds({}).cj_dino, 0.8);
  assert.equal(resolveThresholds({}, { thresholds: { cj_dino: 0.6 } }).cj_dino, 0.6);
  assert.equal(resolveThresholds({}, undefined, true).cj_dino, 0.85);
});
