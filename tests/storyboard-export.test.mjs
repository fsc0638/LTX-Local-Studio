import assert from 'node:assert/strict';
import test from 'node:test';

import { buildStoryboardExportRequest } from '../lib/storyboard-export.ts';
import { projectBible } from '../lib/production-factory.ts';

const bible = {
  character: {
    name: 'Eisa dancer',
    description: 'Traditional Okinawan costume',
    references: [{ image_id: 'portrait-1', view: 'front' }],
  },
  music: {
    audio_id: 'song-1',
    audio_start_seconds: 0,
    audio_mode: 'soundtrack',
    lrc: '[00:01.00]海風起來',
    lrc_timebase: 'output',
  },
  output: { model: 'ltx23-distilled', aspect_ratio: '16:9', fps: 24, profile: 'compat-v1' },
  directing: { emotion: 'hope' },
  lyric_offset_seconds: -0.9,
};

const timeline = {
  enabled: true,
  music: { id: 'song-1', name: 'eisa.wav', kind: 'audio', url: '/audio/song-1' },
  audioStart: 0,
  audioMode: 'soundtrack',
  lrc: '[00:01.00]海風起來',
  lrcTimebase: 'output',
  segmentSeconds: 10,
  cues: [
    { time: 0, action: 'Wide coastal dawn, dancer enters frame.', directing: { emotion: 'hope' } },
    { time: 8, action: 'Low-angle drum performance, rising energy.', directing: { camera: 'dolly' } },
  ],
};

test('stage 01 export replaces sandbox defaults with the complete storyboard request', () => {
  const request = buildStoryboardExportRequest({
    baseRequest: projectBible(bible, {
      prompt: 'Taipei street demo prompt',
      model: 'wrong-model',
      mode: 't2v',
      duration_seconds: 2,
      fps: 8,
      seed: 42,
      audio: false,
      directing: {},
    }),
    timeline,
    durationSeconds: 176.16,
    prompt: 'Okinawan eisa ritual moving from dusk into communal release.',
  });

  assert.equal(request.prompt, 'Okinawan eisa ritual moving from dusk into communal release.');
  assert.equal(request.duration_seconds, 176.16);
  assert.equal(request.render_mode, 'sequence');
  assert.equal(request.audio, true);
  assert.equal(request.model, 'ltx23-distilled');
  assert.equal(request.mode, 'i2v');
  assert.equal(request.image_id, 'portrait-1');
  assert.deepEqual(request.timeline.cues, timeline.cues);
  assert.equal(request.timeline.lrc, bible.music.lrc);
});

test('stage 01 refuses partial exports', () => {
  const input = {
    baseRequest: projectBible(bible, { prompt: 'sandbox' }),
    timeline,
    durationSeconds: 176.16,
    prompt: 'Whole-song world',
  };
  assert.throws(
    () => buildStoryboardExportRequest({ ...input, prompt: ' ' }),
    /storyboard_prompt_required/,
  );
  assert.throws(
    () => buildStoryboardExportRequest({ ...input, timeline: { ...timeline, cues: [] } }),
    /storyboard_cues_required/,
  );
  assert.throws(
    () => buildStoryboardExportRequest({
      ...input,
      timeline: { ...timeline, cues: [{ ...timeline.cues[0], action: '' }] },
    }),
    /storyboard_shot_prompts_required/,
  );
  assert.throws(
    () => buildStoryboardExportRequest({ ...input, durationSeconds: 181 }),
    /storyboard_duration_invalid/,
  );
});
