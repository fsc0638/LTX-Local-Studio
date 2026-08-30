/** Explicit, bounded GPU acceptance check. No training, remote uploads or project IDs. */
import assert from 'node:assert/strict';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { basename, extname } from 'node:path';
import { LTXWorker } from './worker-client.mjs';

const args = process.argv.slice(2);
const option = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
const apiKey = process.env.LTX_WORKER_API_KEY || (await readFile(
  process.env.LTX_WORKER_API_KEY_FILE || new URL('../data/worker/api-key', import.meta.url), 'utf8')).trim();
const worker = new LTXWorker({baseUrl: process.env.LTX_WORKER_BASE_URL || 'http://127.0.0.1:8787', apiKey,
  accessClientId: process.env.CF_ACCESS_CLIENT_ID, accessClientSecret: process.env.CF_ACCESS_CLIENT_SECRET});
const caps = await worker.capabilities();
assert.equal(caps.contract_version, '1.1.0');
const payload = {prompt: 'A cinematic ocean sunrise. Gentle waves roll toward the shore. The camera remains still. Natural sea ambience.',
  profile: option('--profile', 'preview-v1'), duration_seconds: 1, fps: 24, seed: 42,
  audio: args.includes('--audio'), timeout_seconds: 600};
const reference = option('--reference', null);
if (reference) {
  if (!args.includes('--generate')) throw new Error('--reference uploads only with explicit --generate');
  const mime = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp'}[extname(reference).toLowerCase()];
  if (!mime) throw new Error('Reference must be a supported image');
  const asset = await worker.upload(await readFile(reference), {name: basename(reference), contentType: mime});
  Object.assign(payload, {mode: 'i2v', image_id: asset.id, image_strength: 0.65});
}
const resolved = await worker.validate(payload);
console.log(JSON.stringify({validation: resolved}));
if (!args.includes('--generate')) {
  console.log('Validation only. Add --generate to explicitly run one 1-second GPU test.');
} else {
  const outputRoot = new URL('../outputs/worker-acceptance/', import.meta.url);
  await mkdir(outputRoot, {recursive: true, mode: 0o700});
  const key = `smoke-v11-${randomUUID()}`;
  const requestPath = new URL(`${key}.request.json`, outputRoot);
  await writeFile(requestPath, JSON.stringify({key, payload}, null, 2), {flag: 'wx', mode: 0o600});
  let job = await worker.submit(payload, key);
  console.log(JSON.stringify({accepted: job.id}));
  const replay = await worker.submit(payload, key);
  assert.equal(replay.id, job.id);
  assert.equal(replay.idempotent_replay, true);
  const deadline = Date.now() + 660_000;
  let phase = '';
  while (['queued', 'running'].includes(job.status)) {
    if (Date.now() > deadline) throw new Error(`Polling deadline exceeded; inspect existing job ${job.id}, do not resubmit with a new key blindly.`);
    await new Promise(resolve => setTimeout(resolve, 2000));
    job = await worker.job(job.id);
    if (job.phase !== phase) {
      console.log(JSON.stringify({id: job.id, status: job.status, phase: job.phase, progress: job.progress}));
      phase = job.phase;
    }
  }
  await writeFile(new URL(`${job.id}.json`, outputRoot), JSON.stringify({key, payload, job}, null, 2), {flag: 'wx', mode: 0o600});
  assert.equal(job.status, 'succeeded', JSON.stringify(job.error));
  assert.equal(job.quality_control?.passed, true);
  assert.equal(job.measured_media?.measurement, 'full_decode');
  assert.equal(job.measured_media.frames, 25);
  const bytes = Buffer.from(await (await worker.video(job.id)).arrayBuffer());
  assert.equal(createHash('sha256').update(bytes).digest('hex'), job.artifacts[0].sha256);
  assert.equal(bytes.length, job.artifacts[0].size_bytes);
  const range = Buffer.from(await (await worker.video(job.id, 'bytes=0-15')).arrayBuffer());
  assert.deepEqual(range, bytes.subarray(0, 16));
  await writeFile(new URL(`${job.id}.mp4`, outputRoot), bytes, {flag: 'wx', mode: 0o600});
  console.log(JSON.stringify({passed: true, id: job.id, runtime_seconds: job.runtime_seconds,
    measured_media: job.measured_media, quality_control: job.quality_control, sha256: job.artifacts[0].sha256}));
}
