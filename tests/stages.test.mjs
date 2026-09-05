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
