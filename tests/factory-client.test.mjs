import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(
  new URL('../lib/factory-client.ts', import.meta.url),
  'utf8',
);

test('factory run and pause send explicit JSON bodies', () => {
  assert.match(source, /call\(`\/projects\/\$\{id\}\/run`, json\(\{\}\)\)/);
  assert.match(source, /call\(`\/projects\/\$\{id\}\/pause`, json\(\{\}\)\)/);
});

test('the factory pause control calls the host instead of only changing browser state', () => {
  const component = readFileSync(
    new URL('../components/production-factory.tsx', import.meta.url),
    'utf8',
  );
  assert.match(component, /runOnHost\(factory\.pauseProject\)/);
});
