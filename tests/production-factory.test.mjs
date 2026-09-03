import test from 'node:test';
import assert from 'node:assert/strict';
import {
  activeFactoryShot,
  createFactoryPlan,
  createFactoryShot,
  nextQueuedShot,
  parseFactoryImport,
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
