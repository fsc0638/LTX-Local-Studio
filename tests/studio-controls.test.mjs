import test from 'node:test';
import assert from 'node:assert/strict';
import {durationFrames, maximumDurationInput, sequenceFrames} from '../lib/video-settings.ts';
import {readSession, serviceFetch, signOut, sessionChangeKey} from '../lib/service-session.ts';
import {displayedLrcTime, formatLrcRows, parseLrcRows, resetLrcTimes, storedLrcTime} from '../lib/lrc-editor.ts';
import {parseTimelineImport, serializeShotPlan} from '../lib/timeline-import.ts';

test('LRC rows expose editable seconds and follow the selected music start', () => {
  const rows = parseLrcRows('[00:05.50]First line\n[00:08.000]Second line');
  assert.deepEqual(rows, [{time:5.5,text:'First line'},{time:8,text:'Second line'}]);
  assert.equal(displayedLrcTime(rows[0].time, 2, 'music'), 3.5);
  assert.equal(storedLrcTime(4.25, 2, 'music'), 6.25);
  assert.equal(formatLrcRows([{time:6.25,text:'First line'}]), '[00:06.250]First line');
});

test('duration is rounded up; changing FPS never silently trims the request', () => {
  assert.equal(durationFrames(20, 24, 481), 481);
  assert.equal(durationFrames(20, 30, 481), null);
  assert.equal(durationFrames(20, 30, 601), 601);
  assert.equal(durationFrames(30, 16, 481), 481);
  assert.equal(durationFrames(60, 8, 481), 481);
  for (const fps of [8,16,24,25,30,50,60]) {
    const maximum = Number(maximumDurationInput(481, fps));
    assert.equal(durationFrames(maximum, fps, 481), 481);
    for (const seconds of [0.1,0.667,1,2,5,10]) {
      const frames = durationFrames(seconds, fps, 481);
      if (frames !== null) { assert.ok(frames / fps >= seconds); assert.equal((frames - 1) % 8, 0); }
    }
  }
  for (const seconds of [0,-1,NaN,Infinity]) assert.equal(durationFrames(seconds,24,481), null);
});

const response = (data, status = 200) => Response.json(data, {status});
test('sequence supports 180 seconds without reducing FPS or stretching footage', () => {
  for (const fps of [8,16,24,25,30,50,60]) assert.equal(sequenceFrames(180,fps),180*fps);
  assert.equal(sequenceFrames(180.01,24),null);
  assert.equal(sequenceFrames(NaN,24),null);
  assert.equal(sequenceFrames(0.01,24),null);
  assert.equal(sequenceFrames(4.01,24),97);
});
const session = token => ({required:true, authenticated:true, user:{id:'test-user'}, csrf_token:token});
function browserGlobals(t, storage = {setItem:() => {}}) {
  for (const [key, value] of Object.entries({window:new EventTarget(), localStorage:storage})) {
    const original = Object.getOwnPropertyDescriptor(globalThis, key);
    Object.defineProperty(globalThis, key, {value, configurable:true, writable:true});
    t.after(() => { if (original) Object.defineProperty(globalThis,key,original); else delete globalThis[key]; });
  }
}

test('logout retries stale CSRF once, notifies other tabs, and returns a safe URL', async t => {
  const saved = new Map();
  t.mock.method(globalThis, 'fetch');
  browserGlobals(t, {setItem:(key,value) => saved.set(key,value)});
  const calls = [];
  let post = 0;
  globalThis.fetch.mock.mockImplementation(async (url, init) => {
    calls.push([url, new Headers(init.headers).get('X-CSRF-Token')]);
    if (url.endsWith('/session')) return response(session(post ? 'fresh-token' : 'stale-token'));
    post++;
    if (post === 1) return response({code:'csrf_failed'},403);
    assert.equal(new Headers(init.headers).get('X-CSRF-Token'), 'fresh-token');
    return response({ok:true,cloudflare_logout_url:'/cdn-cgi/access/logout'});
  });
  await readSession();
  assert.equal(await signOut(true), '/cdn-cgi/access/logout');
  assert.equal(post,2);
  assert.equal(calls.length,4);
  assert.ok(saved.get(sessionChangeKey));
});

test('non-CSRF failures never replay mutations or report logout success', async t => {
  t.mock.method(globalThis, 'fetch', async () => response(session('current-token')));
  browserGlobals(t);
  await readSession();
  globalThis.fetch.mock.resetCalls();
  globalThis.fetch.mock.mockImplementation(async () => response({code:'cloudflare_email_mismatch'},403));
  const result = await serviceFetch('/api/v1/jobs', {method:'POST',body:'{}'});
  assert.equal(result.status,403);
  assert.equal(globalThis.fetch.mock.callCount(),1);
  await assert.rejects(signOut(), /Sign-out failed/);
});

test('sign-out cannot redirect to an external URL supplied by a response', async t => {
  t.mock.method(globalThis, 'fetch', async () => response(session('current-token')));
  browserGlobals(t);
  await readSession();
  globalThis.fetch.mock.mockImplementation(async () => response({ok:true,cloudflare_logout_url:'https://evil.invalid/'}));
  assert.equal(await signOut(true), '/auth/login?signed_out=1');
});

test('resetting times restores the imported timestamps and keeps edited lyrics', () => {
  const baseline = parseLrcRows('[00:05.000]First\n[00:09.000]Second');
  const edited = [{time:1,text:'First, tidied'},{time:2,text:'Second'},{time:30,text:'Added later'}];
  assert.deepEqual(resetLrcTimes(edited, baseline), [
    {time:5,text:'First, tidied'},{time:9,text:'Second'},{time:30,text:'Added later'},
  ]);
  assert.deepEqual(resetLrcTimes([], baseline), []);
});

const catalog = {emotion:{calm:{},hope:{}}, camera:{locked:{}}};
test('a full job payload imports its timeline and reports fields it cannot apply', () => {
  const imported = parseTimelineImport(JSON.stringify({
    prompt:'A performer by the sea', model:'ltx23-distilled', render_mode:'sequence',
    duration_seconds:120, segment_seconds:8, directing:{emotion:'hope'},
    timeline:{lrc:'[00:02.00]Line', lrc_timebase:'music', audio_id:'a'.repeat(32),
      audio_start_seconds:12, audio_mode:'condition',
      cues:[{time:9,action:'Turns away',directing:{emotion:'calm'}},{time:1,action:'Looks up'}]},
  }), catalog);
  assert.equal(imported.lrc, '[00:02.00]Line');
  assert.equal(imported.lrcTimebase, 'music');
  assert.equal(imported.durationSeconds, 120);
  assert.equal(imported.segmentSeconds, 8);
  assert.equal(imported.audioStart, 12);
  assert.equal(imported.audioMode, 'condition');
  assert.equal(imported.audioId, 'a'.repeat(32));
  assert.deepEqual(imported.cues.map(cue => cue.time), [1, 9]);
  assert.deepEqual(imported.cues[1].directing, {emotion:'calm'});
  assert.deepEqual(imported.cues[0].directing, {});
  // Prompt-level settings belong to the request, not the timeline panel.
  assert.deepEqual(imported.ignored.sort(), ['directing','model','prompt','render_mode']);
});

test('a bare timeline subset imports without touching unrelated settings', () => {
  const imported = parseTimelineImport('{"cues":[{"time":4,"action":"Steps forward"}]}', catalog);
  assert.equal(imported.lrc, undefined);
  assert.equal(imported.durationSeconds, undefined);
  assert.deepEqual(imported.cues, [{time:4,action:'Steps forward',directing:{}}]);
  assert.deepEqual(imported.ignored, []);
});

test('imported shot plans are rejected before they can reach the worker', () => {
  const fails = (source, fragment) =>
    assert.throws(() => parseTimelineImport(source, catalog), error => error.message.includes(fragment));
  fails('not json', 'not valid JSON');
  fails('[]', 'must be a JSON object');
  fails('{"prompt":"only a prompt"}', 'Provide a "timeline" object');
  fails('{"timeline":{"lrc":"","tempo":120}}', 'found tempo');
  fails('{"cues":[{"time":1,"shot":"wide"}]}', 'found shot');
  fails('{"cues":[{"time":1},{"time":1}]}', 'cannot share a timestamp');
  fails('{"cues":[{"time":181}]}', 'between 0 and 180');
  fails('{"cues":[{"time":"4"}]}', 'must be a number');
  fails('{"cues":[{"time":1,"directing":{"lighting":"warm"}}]}', 'not a directing field');
  fails('{"cues":[{"time":1,"directing":{"emotion":"furious"}}]}', 'not a supported option');
  fails('{"cues":[{"time":1,"action":' + JSON.stringify('x'.repeat(601)) + '}]}', 'up to 600 characters');
  fails(JSON.stringify({cues:Array.from({length:61},(_,i)=>({time:i}))}), 'At most 60');
  fails('{"lrc":"x","lrc_timebase":"bar"}', 'must be "output" or "music"');
  fails('{"lrc":"x","audio_mode":"loud"}', 'must be "soundtrack" or "condition"');
});

test('directing options are trusted to the worker when no catalog has loaded', () => {
  const imported = parseTimelineImport('{"cues":[{"time":1,"directing":{"emotion":"calm"}}]}', undefined);
  assert.deepEqual(imported.cues[0].directing, {emotion:'calm'});
});

test('an exported shot plan is the standard payload and imports back unchanged', () => {
  const request = {
    prompt:'A performer by the sea', model:'ltx23-distilled', mode:'t2v',
    duration_seconds:60, fps:24, audio:true, render_mode:'sequence', segment_seconds:10,
    image_id:undefined, directing:{emotion:'hope'},
    timeline:{audio_id:undefined, audio_start_seconds:0, audio_mode:'soundtrack',
      lrc:'[00:02.000]Line one\n[00:06.500]Line two', lrc_timebase:'output',
      cues:[{time:2,action:'Looks up',directing:{emotion:'calm'}}]},
  };
  const {filename, source} = serializeShotPlan(request, new Date('2026-09-03T15:04:05Z'));
  assert.equal(filename, 'ltx-shot-plan-20260903T150405.json');
  assert.equal(source.endsWith('\n'), true);
  // Keys the request left undefined must not survive as JSON nulls.
  const written = JSON.parse(source);
  assert.equal('image_id' in written, false);
  assert.equal(written.timeline.audio_id, undefined);
  const imported = parseTimelineImport(source, {emotion:{calm:{},hope:{}}});
  assert.equal(imported.lrc, request.timeline.lrc);
  assert.equal(imported.lrcTimebase, 'output');
  assert.equal(imported.durationSeconds, 60);
  assert.equal(imported.segmentSeconds, 10);
  assert.deepEqual(imported.cues, request.timeline.cues);
  assert.deepEqual(imported.ignored.sort(), ['audio','directing','fps','mode','model','prompt','render_mode']);
});
