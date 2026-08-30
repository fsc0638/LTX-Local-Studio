import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { test } from 'node:test';
import { LTXWorker, WorkerError } from '../examples/worker-client.mjs';

test('server-only client validates origin and credential shape', () => {
  const apiKey = 'x'.repeat(48);
  assert.throws(() => new LTXWorker({baseUrl:'http://example.com', apiKey}));
  assert.throws(() => new LTXWorker({baseUrl:'https://user:secret@example.com', apiKey}));
  assert.throws(() => new LTXWorker({baseUrl:'https://example.com/private', apiKey}));
  assert.throws(() => new LTXWorker({baseUrl:'https://example.com', apiKey, accessClientId:'id'}));
  const client = new LTXWorker({baseUrl:'https://example.com', apiKey});
  assert.throws(() => client.job('../../secret'));
  assert.throws(() => client.submit({}, ''));
  assert.throws(() => client.jobs({limit: 101}));
  assert.throws(() => client.cancel('../../secret'));
});

test('headers, JSON, busy response, authenticated range, redirect refusal', async t => {
  const requests = [];
  let mode = 'normal';
  const server = createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    requests.push({url:req.url, headers:req.headers, body:Buffer.concat(chunks).toString()});
    if (mode === 'redirect') { res.writeHead(302, {Location:'/login'}); res.end(); return; }
    if (mode === 'html') { res.writeHead(200, {'Content-Type':'text/html'}); res.end('<p>Login</p>'); return; }
    if (mode === 'busy') { res.writeHead(409, {'Content-Type':'application/json','Retry-After':'5'}); res.end(JSON.stringify({code:'worker_busy',error:'Busy'})); return; }
    if (req.url.includes('/video')) { res.writeHead(206, {'Content-Type':'video/mp4'}); res.end('mp4'); return; }
    res.writeHead(200, {'Content-Type':'application/json'}); res.end(JSON.stringify({id:'abcdef012345'}));
  });
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); }));
  const worker = new LTXWorker({baseUrl:`http://127.0.0.1:${server.address().port}`, apiKey:'x'.repeat(48),accessClientId:'cf-id',accessClientSecret:'cf-secret'});
  await worker.submit({prompt:'test'}, 'request-001');
  assert.equal(requests[0].headers.authorization, `Bearer ${'x'.repeat(48)}`);
  assert.equal(requests[0].headers['cf-access-client-id'], 'cf-id');
  assert.equal(requests[0].headers['cf-access-client-secret'], 'cf-secret');
  assert.equal(requests[0].headers['idempotency-key'], 'request-001');
  assert.equal(JSON.parse(requests[0].body).prompt, 'test');
  assert.equal(await (await worker.video('abcdef012345', 'bytes=0-2')).text(), 'mp4');
  assert.equal(requests[1].headers.range, 'bytes=0-2');
  await worker.validate({prompt: 'test', profile: 'preview-v1'});
  assert.equal(requests[2].url, '/api/v1/validate');
  assert.equal(JSON.parse(requests[2].body).profile, 'preview-v1');
  await worker.cancel('abcdef012345');
  assert.equal(requests[3].url, '/api/v1/jobs/abcdef012345/cancel');
  await worker.jobs({limit: 2, offset: 1});
  assert.equal(requests[4].url, '/api/v1/jobs?limit=2&offset=1');
  await worker.schema();
  assert.equal(requests[5].url, '/api/v1/openapi.json');
  mode = 'busy';
  await assert.rejects(worker.capabilities(), error => error instanceof WorkerError && error.code === 'worker_busy' && error.retryAfter === 5);
  mode = 'html';
  await assert.rejects(worker.capabilities(), /Expected API JSON/);
  mode = 'redirect';
  const before = requests.length;
  await assert.rejects(worker.capabilities());
  assert.equal(requests.length, before + 1); // no second request to login
});
