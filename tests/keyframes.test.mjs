import test from 'node:test';
import assert from 'node:assert/strict';
import {
  batchEstimateSeconds,
  keyframeLight,
  leadKeyframe,
  needsAttention,
  retrySeed,
  shouldRetry,
} from '../lib/keyframes.ts';
import { consistencyLine, resolveThresholds, takeScores } from '../lib/review.ts';

const face = (median) => ({
  consistency: { median, per_frame: [median], method_per_frame: ['face_facenet'] },
  style: { median: 0.9 },
  media: { kind: 'image' },
});
const t = resolveThresholds({ thresholds: { cj: 0.8 } });
// What the boards do: numbers from lib/review, the verdict from lib/keyframes.
const light = (scores, thresholds = t) =>
  keyframeLight(takeScores(scores).cj, consistencyLine(scores, thresholds));

test('green at or above the line, yellow just under it, red further down', () => {
  assert.equal(light(face(0.8)), 'green');
  assert.equal(light(face(0.76)), 'yellow');
  assert.equal(light(face(0.74)), 'red');
  assert.equal(light({ status: 'unscored' }), 'unscored');
  assert.equal(light(null), 'unscored');
  assert.equal(keyframeLight(0.79, 0.8), 'yellow');
});

test('a no-face keyframe is judged on the dino line', () => {
  const dino = { ...face(0.7), consistency: { median: 0.7, per_frame: [0.7], method_per_frame: ['dinov2_large'] } };
  assert.equal(light(dino, resolveThresholds({ thresholds: { cj: 0.8, cj_dino: 0.65 } })), 'green');
});

test('red retries once with a derived seed, then asks a person', () => {
  assert.equal(shouldRetry('red', 1), true);
  assert.equal(shouldRetry('red', 2), false);
  assert.equal(shouldRetry('yellow', 1), false);
  assert.equal(shouldRetry('green', 1), false);
  assert.notEqual(retrySeed(42), 42);
  assert.equal(retrySeed(42), retrySeed(42), 'reproducible');
});

test('the batch estimate is one model switch plus one generation per shot', () => {
  assert.equal(batchEstimateSeconds(24), 336 + 24 * 26);
  assert.equal(batchEstimateSeconds(24, true), 24 * 26);
  assert.equal(batchEstimateSeconds(0), 0);
});

const rec = (over) => ({
  id: over.id, shotId: 's', attempt: 1, seed: 1, referenceId: null, outputUrl: null, scores: null,
  light: null, verdict: 'pending', assetId: null, reason: null, createdAt: 0, ...over,
});

test('the tile shows the approved keyframe, else the newest pending, else the newest', () => {
  assert.equal(leadKeyframe([]), null);
  const a = rec({ id: 'a', createdAt: 1, verdict: 'rejected' });
  const b = rec({ id: 'b', createdAt: 2 });
  const c = rec({ id: 'c', createdAt: 3, verdict: 'approved' });
  assert.equal(leadKeyframe([a, b]).id, 'b');
  assert.equal(leadKeyframe([a, b, c]).id, 'c');
  assert.equal(leadKeyframe([a]).id, 'a');
});

test('attention is needed only for a pending red or yellow lead', () => {
  assert.equal(needsAttention([rec({ id: 'x', light: 'red' })]), true);
  assert.equal(needsAttention([rec({ id: 'x', light: 'yellow' })]), true);
  assert.equal(needsAttention([rec({ id: 'x', light: 'green' })]), false);
  assert.equal(needsAttention([rec({ id: 'x', light: 'red', verdict: 'approved' })]), false);
  assert.equal(needsAttention([]), false);
});
