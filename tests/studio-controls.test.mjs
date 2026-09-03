import test from 'node:test';
import assert from 'node:assert/strict';
import {durationFrames, maximumDurationInput, sequenceFrames} from '../lib/video-settings.ts';
import {readSession, serviceFetch, signOut, sessionChangeKey} from '../lib/service-session.ts';
import {displayedLrcTime, formatLrcRows, parseLrcRows, storedLrcTime} from '../lib/lrc-editor.ts';

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
