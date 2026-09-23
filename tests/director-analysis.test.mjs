import assert from 'node:assert/strict';
import test from 'node:test';

import { applyDirectorSuggestions, canRunDirectorAnalysis } from '../lib/director-analysis.ts';

const shots = [
  { id: 'a', cue: { time: 0, action: 'human edit', directing: {} } },
  { id: 'b', cue: { time: 5, action: '', directing: {} } },
];
const suggestion = (id, prompt) => ({ shot_id: id, prompt });

test('AI director advice changes only the explicitly accepted shot', () => {
  const next = applyDirectorSuggestions(
    shots,
    [suggestion('a', 'new a'), suggestion('b', 'new b')],
    new Set(['b']),
  );
  assert.equal(next[0], shots[0]);
  assert.equal(next[0].cue.action, 'human edit');
  assert.equal(next[1].cue.action, 'new b');
});

test('apply all uses worker-safe trimmed prompts and ignores unknown ids', () => {
  const long = `  ${'x'.repeat(4100)}  `;
  const next = applyDirectorSuggestions(shots, [suggestion('a', long), suggestion('missing', 'x')]);
  assert.equal(next[0].cue.action.length, 4000);
  assert.equal(next[1], shots[1]);
});

test('AI director remains available after reload before breakdown state is rebuilt', () => {
  assert.equal(canRunDirectorAnalysis({
    projectId: 'project-1', musicId: 'music-1', draftAvailable: true,
    breakdownBusy: false, directorBusy: false,
  }), true);
});

test('AI director stays unavailable without its required host and project inputs', () => {
  const ready = {
    projectId: 'project-1', musicId: 'music-1', draftAvailable: true,
    breakdownBusy: false, directorBusy: false,
  };
  assert.equal(canRunDirectorAnalysis({ ...ready, projectId: undefined }), false);
  assert.equal(canRunDirectorAnalysis({ ...ready, musicId: undefined }), false);
  assert.equal(canRunDirectorAnalysis({ ...ready, draftAvailable: false }), false);
  assert.equal(canRunDirectorAnalysis({ ...ready, breakdownBusy: true }), false);
  assert.equal(canRunDirectorAnalysis({ ...ready, directorBusy: true }), false);
});
