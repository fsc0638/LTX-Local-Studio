import test from 'node:test';
import assert from 'node:assert/strict';
import {
  EMPTY_PLAN_SNAPSHOT,
  planProgress,
  STAGE_KEYS,
  UNAVAILABLE_STAGES,
} from '../lib/stages.ts';

const snapshot = (over = {}) => ({
  hasBible: false,
  status: 'draft',
  total: 0,
  completed: 0,
  failed: 0,
  awaitingReview: 0,
  accepted: 0,
  keyframed: 0,
  keyframesAttention: 0,
  ...over,
});

test('an empty plan points at the Bible and waits on the user', () => {
  const progress = planProgress(snapshot());
  assert.equal(progress.current, 'bible');
  assert.equal(progress.statuses.bible, 'active');
  assert.equal(progress.owner, 'user');
  assert.equal(progress.lastResult, 'resultNone');
  assert.equal(progress.nextAction, 'nextBible');
});

test('a Bible with no shots moves the line to the breakdown', () => {
  const progress = planProgress(snapshot({ hasBible: true }));
  assert.equal(progress.statuses.bible, 'done');
  assert.equal(progress.current, 'breakdown');
  assert.equal(progress.statuses.breakdown, 'active');
  assert.equal(progress.lastResult, 'resultBible');
});

test('stages this phase does not implement stay disabled and never become current', () => {
  const progress = planProgress(snapshot({ hasBible: true, total: 1 }));
  for (const key of UNAVAILABLE_STAGES) {
    assert.equal(progress.statuses[key], 'disabled', key);
  }
  assert.equal(progress.current, 'shoot');
  assert.ok(!UNAVAILABLE_STAGES.includes(progress.current));
});

test('a running plan hands the next step to the host', () => {
  const progress = planProgress(
    snapshot({ hasBible: true, total: 1, status: 'running' }),
  );
  assert.equal(progress.statuses.shoot, 'active');
  assert.equal(progress.owner, 'worker');
  assert.equal(progress.nextAction, 'nextWait');
});

test('a failed shot asks for a person and outranks a completed one', () => {
  const progress = planProgress(
    snapshot({
      hasBible: true,
      total: 2,
      completed: 1,
      failed: 1,
      status: 'paused',
    }),
  );
  assert.equal(progress.statuses.shoot, 'attention');
  assert.equal(progress.current, 'shoot');
  assert.equal(progress.owner, 'user');
  assert.equal(progress.lastResult, 'resultFailed');
  assert.equal(progress.nextAction, 'nextFix');
});

test('every stage key gets a status and the order is stable', () => {
  const progress = planProgress(snapshot());
  assert.deepEqual(Object.keys(progress.statuses).sort(), [...STAGE_KEYS].sort());
  assert.deepEqual(STAGE_KEYS, [
    'bible',
    'breakdown',
    'keyframes',
    'shoot',
    'review',
    'post',
    'assembly',
  ]);
});

test('the line has a valid state before any plan exists', () => {
  const progress = planProgress(EMPTY_PLAN_SNAPSHOT);
  assert.equal(progress.current, 'bible');
  assert.equal(progress.statuses.bible, 'active');
  assert.equal(progress.owner, 'user');
});

test('review asks for a person once a finished shot has no verdict', () => {
  const progress = planProgress(snapshot({ hasBible: true, total: 3, completed: 3, awaitingReview: 2, accepted: 1 }));
  assert.equal(progress.statuses.review, 'attention');
  assert.equal(progress.current, 'review');
  assert.equal(progress.owner, 'user');
  assert.equal(progress.nextAction, 'nextReview');
});

test('review is done when every shot has an accepted take', () => {
  const progress = planProgress(snapshot({ hasBible: true, total: 3, completed: 3, accepted: 3, status: 'completed' }));
  assert.equal(progress.statuses.review, 'done');
  assert.equal(progress.lastResult, 'resultReviewed');
  assert.equal(progress.current, 'assembly');
});

test('review is idle, not disabled, while nothing has finished', () => {
  const progress = planProgress(snapshot({ hasBible: true, total: 3 }));
  assert.equal(progress.statuses.review, 'idle');
  assert.ok(!UNAVAILABLE_STAGES.includes('review'));
});

test('keyframes are idle, not disabled, and ask for a person when a candidate is red or yellow', () => {
  assert.ok(!UNAVAILABLE_STAGES.includes('keyframes'));
  const idle = planProgress(snapshot({ hasBible: true, total: 3 }));
  assert.equal(idle.statuses.keyframes, 'idle');
  const attention = planProgress(snapshot({ hasBible: true, total: 3, keyframesAttention: 1 }));
  assert.equal(attention.statuses.keyframes, 'attention');
  assert.equal(attention.current, 'keyframes');
  assert.equal(attention.nextAction, 'nextKeyframesReview');
});

test('keyframes are done when every shot starts from an approved one', () => {
  const progress = planProgress(snapshot({ hasBible: true, total: 3, keyframed: 3 }));
  assert.equal(progress.statuses.keyframes, 'done');
});

test('post is idle and skipped over: assembly follows review directly', () => {
  assert.ok(!UNAVAILABLE_STAGES.includes('post'));
  const progress = planProgress(snapshot({ hasBible: true, total: 3, completed: 3, accepted: 3, status: 'completed' }));
  assert.equal(progress.statuses.post, 'idle');
  assert.equal(progress.current, 'assembly');
});
