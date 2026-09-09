import test from 'node:test';
import assert from 'node:assert/strict';
import { assemblyFileName, assemblyReadiness } from '../lib/assembly.ts';

const shot = (id, acceptedTakeId) => ({
  id, title: `SHOT ${id}`, request: { prompt: 'x' }, pinned: [], status: 'succeeded', idempotencyKey: 'k' + id, progress: 100,
  ...(acceptedTakeId ? { acceptedTakeId } : {}),
});
const plan = (shots) => ({
  format: 'ltx-production-factory', version: 2, id: 'p', title: 'MV', bible: { output: {}, lyric_offset_seconds: -0.9 },
  status: 'completed', createdAt: '', updatedAt: '', shots,
});

test('ready only when every shot has an accepted take, and the missing ones are listed in order', () => {
  assert.deepEqual(assemblyReadiness(null), { ready: false, missing: [], total: 0 });
  assert.deepEqual(assemblyReadiness(plan([])), { ready: false, missing: [], total: 0 });
  const p = plan([shot('a', 't1'), shot('b'), shot('c', 't3'), shot('d')]);
  const r = assemblyReadiness(p);
  assert.equal(r.ready, false);
  assert.deepEqual(r.missing.map((m) => [m.index, m.title]), [[1, 'SHOT b'], [3, 'SHOT d']]);
  assert.equal(r.total, 4);
  assert.equal(assemblyReadiness(plan([shot('a', 't1'), shot('b', 't2')])).ready, true);
});

test('file names are safe and keep the title', () => {
  assert.equal(assemblyFileName('三線リフで帰ろう / MV', 'mp4'), '三線リフで帰ろう-MV.mp4');
  assert.equal(assemblyFileName('  ', 'json'), 'cut.manifest.json');
  assert.equal(assemblyFileName('a:b*c?', 'json'), 'a-b-c.manifest.json');
});
