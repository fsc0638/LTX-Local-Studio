import test from 'node:test';
import assert from 'node:assert/strict';
import {
  activeFactoryShot,
  clearFactoryShotOutput,
  createFactoryPlan,
  createFactoryShot,
  nextQueuedShot,
  parseFactoryImport,
  reopenFactoryShot,
  restoreFactoryPlan,
  serializeFactoryPlan,
  summarizeFactory,
} from '../lib/production-factory.ts';

const ids = (...values) => {
  let index = 0;
  return () => values[index++];
};

test('factory imports standard job requests and exports only portable plan data', () => {
  const plan = parseFactoryImport(
    JSON.stringify([
      { prompt: 'Opening shot', duration_seconds: 4, aspect_ratio: '16:9' },
      { prompt: 'Closing shot', duration_seconds: 6, fps: 24 },
    ]),
    ids('factory', 'shot-a', 'shot-b'),
    new Date('2026-09-03T10:00:00Z'),
  );
  assert.equal(plan.shots.length, 2);
  assert.equal(plan.shots[0].idempotencyKey, 'factory-shot-a');
  plan.shots[0].status = 'succeeded';
  plan.shots[0].jobId = 'server-job';
  const exported = JSON.parse(serializeFactoryPlan(plan));
  assert.equal(exported.format, 'ltx-production-factory');
  assert.equal(exported.version, 1);
  assert.equal(exported.shots[0].request.prompt, 'Opening shot');
  assert.equal('status' in exported.shots[0], false);
  assert.equal('jobId' in exported.shots[0], false);
});

test('factory queue summary and selectors keep one active GPU shot', () => {
  const plan = createFactoryPlan('factory');
  plan.shots = [
    createFactoryShot({ prompt: 'One' }, 'one', 0),
    createFactoryShot({ prompt: 'Two' }, 'two', 1),
    createFactoryShot({ prompt: 'Three' }, 'three', 2),
  ];
  plan.shots[0].status = 'running';
  plan.shots[0].jobId = 'job-one';
  plan.shots[0].statusUrl = '/api/v1/jobs/job-one';
  plan.shots[1].status = 'queued';
  plan.shots[2].status = 'succeeded';
  assert.equal(activeFactoryShot(plan)?.id, 'one');
  assert.equal(nextQueuedShot(plan)?.id, 'two');
  assert.deepEqual(summarizeFactory(plan), {
    total: 3,
    waiting: 1,
    active: 1,
    completed: 1,
    failed: 0,
  });
});

test('restoring resets half-submitted work and rejects unsafe artifact URLs', () => {
  const plan = createFactoryPlan('factory');
  const shot = createFactoryShot({ prompt: 'A safe shot' }, 'shot', 0);
  shot.status = 'submitting';
  shot.outputUrl = 'https://evil.invalid/tracker.mp4';
  plan.shots = [shot];
  const restored = restoreFactoryPlan(plan);
  assert.equal(restored.shots[0].status, 'queued');
  assert.equal(restored.shots[0].outputUrl, undefined);
});

test('malformed or oversized factory plans fail before reaching the worker', () => {
  const makeId = ids('factory', 'shot');
  assert.throws(() => parseFactoryImport('not json', makeId), /not valid JSON/);
  assert.throws(() => parseFactoryImport('[]', makeId), /requires 1/);
  assert.throws(
    () => parseFactoryImport(JSON.stringify([{ prompt: '' }]), makeId),
    /requires a prompt/,
  );
  assert.throws(
    () =>
      parseFactoryImport(
        JSON.stringify({
          format: 'ltx-production-factory',
          version: 1,
          title: 'MV',
          shots: [{ request: { prompt: 'Shot' }, shell: 'rm' }],
        }),
        makeId,
      ),
    /unsupported fields/,
  );
});

test('completed shots can reopen for another take while keeping the previous output', () => {
  const shot = createFactoryShot({ prompt: 'First take' }, 'shot', 0);
  Object.assign(shot, {
    status: 'succeeded',
    jobId: 'abcdef123456',
    outputUrl: '/generated/take-one.mp4',
    posterUrl: '/generated/take-one.jpg',
    progress: 100,
  });
  const reopened = reopenFactoryShot(shot, 'factory-shot-take-two');
  assert.equal(reopened.status, 'draft');
  assert.equal(reopened.idempotencyKey, 'factory-shot-take-two');
  assert.equal(reopened.outputUrl, '/generated/take-one.mp4');
  assert.equal(reopened.jobId, 'abcdef123456');
  assert.equal(reopened.progress, 0);
});

test('deleting a generated output keeps the shot ready for maintenance', () => {
  const shot = createFactoryShot({ prompt: 'Try again' }, 'shot', 0);
  Object.assign(shot, {
    status: 'succeeded',
    jobId: 'abcdef123456',
    statusUrl: '/api/v1/jobs/abcdef123456',
    outputUrl: '/generated/take.mp4',
    posterUrl: '/generated/take.jpg',
    progress: 100,
  });
  const cleared = clearFactoryShotOutput(shot, 'factory-shot-next-take');
  assert.equal(cleared.status, 'draft');
  assert.equal(cleared.idempotencyKey, 'factory-shot-next-take');
  assert.equal(cleared.jobId, undefined);
  assert.equal(cleared.outputUrl, undefined);
  assert.equal(cleared.request.prompt, 'Try again');
});
