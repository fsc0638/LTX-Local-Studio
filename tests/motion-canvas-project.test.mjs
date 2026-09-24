import assert from 'node:assert/strict';
import test from 'node:test';

import {
  motionCanvasDependencies,
  motionCanvasViteConfig,
} from '../lib/motion-canvas-project.ts';

test('generated Motion Canvas projects pin one compatible dependency set', () => {
  assert.equal(motionCanvasDependencies['@motion-canvas/core'], '3.17.2');
  assert.equal(motionCanvasDependencies['@motion-canvas/2d'], '3.17.2');
  assert.equal(
    motionCanvasDependencies['@motion-canvas/vite-plugin'],
    '3.17.2',
  );
  assert.equal(motionCanvasDependencies['@motion-canvas/ffmpeg'], '3.17.2');
  assert.equal(motionCanvasDependencies.vite, '5.4.21');
  for (const version of Object.values(motionCanvasDependencies)) {
    assert.doesNotMatch(version, /^[~^]/);
  }
});

test('generated Vite config unwraps CommonJS defaults before invoking plugins', () => {
  assert.match(motionCanvasViteConfig, /while \(/);
  assert.match(motionCanvasViteConfig, /'default' in candidate/);
  assert.match(motionCanvasViteConfig, /motionCanvas\(\), ffmpeg\(\)/);
});
