import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildMotionCanvasScene,
  motionCanvasDependencies,
  motionCanvasMacLauncher,
  motionCanvasViteConfig,
  parseMotionCanvasTimeline,
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

test('LRC metadata is ignored and timestamped lyrics become ordered cues', () => {
  const cues = parseMotionCanvasTimeline(
    `[ti:エイサーの足音]
[by:美羽 Reels Studio 打拍對時]
[00:18.19]ドン ドン パッ と夜が鳴る
[00:22.09]体育館から 音がこぼれる
[00:26.44]汗のにおいと 夕立のあと
[00:30.85]スニーカーだけが 先に走る`,
    36,
    '測試',
  );
  assert.deepEqual(cues, [
    { start: 18.19, end: 22.09, text: 'ドン ドン パッ と夜が鳴る' },
    { start: 22.09, end: 26.44, text: '体育館から 音がこぼれる' },
    { start: 26.44, end: 30.85, text: '汗のにおいと 夕立のあと' },
    { start: 30.85, end: 36, text: 'スニーカーだけが 先に走る' },
  ]);
});

test('plain scripts are spread across the requested duration', () => {
  assert.deepEqual(parseMotionCanvasTimeline('first\nsecond', 8, 'fallback'), [
    { start: 0, end: 4, text: 'first' },
    { start: 4, end: 8, text: 'second' },
  ]);
});

test('generated scene advances captions and animates a supplied character', () => {
  const scene = buildMotionCanvasScene({
    headline: '測試',
    width: 1920,
    height: 1080,
    duration: 8,
    palette: {
      bg: '#fff',
      ink: '#111',
      accent: '#f00',
      paper: '#eee',
    },
    cues: [
      { start: 0, end: 4, text: 'first' },
      { start: 4, end: 8, text: 'second' },
    ],
    characterFile: 'character.png',
  });
  assert.match(scene, /caption\(\)\.text\(cue\.text\)/);
  assert.match(scene, /characterImage\(\)\.position\.x/);
  assert.match(scene, /progress\(\)\.scale\.x/);
  assert.doesNotMatch(scene, /\[ti:/);
});

test('macOS launcher installs locally, starts the editor, and opens localhost', () => {
  assert.match(motionCanvasMacLauncher, /npm install/);
  assert.match(motionCanvasMacLauncher, /npm start/);
  assert.match(motionCanvasMacLauncher, /open http:\/\/127\.0\.0\.1:9000\//);
  assert.doesNotMatch(motionCanvasMacLauncher, /sudo/);
});
