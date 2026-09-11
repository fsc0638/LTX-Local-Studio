import assert from 'node:assert/strict';
import test from 'node:test';

import { applyDirectorSuggestions } from '../lib/director-analysis.ts';

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
  const long = `  ${'x'.repeat(700)}  `;
  const next = applyDirectorSuggestions(shots, [suggestion('a', long), suggestion('missing', 'x')]);
  assert.equal(next[0].cue.action.length, 600);
  assert.equal(next[1], shots[1]);
});
