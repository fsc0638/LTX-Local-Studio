import test from 'node:test';
import assert from 'node:assert/strict';
import { parseCalibrationReport, thresholdsFromReport } from '../lib/calibration.ts';

// Hand-written, in the exact shape infra/gb10/tools/calibrate_embeddings.py writes. The numbers
// are plausible, not measured: this tests the import, not the judges.
const REPORT = {
  root: '/x/calibration',
  images: 24,
  characters: ['美佳', '阿順'],
  missing_faces: ['/x/calibration/美佳/back-01.png', '/x/calibration/阿順/wide-03.jpg'],
  metrics: [
    { metric: 'face_facenet', same: { mean: 0.81, std: 0.06, worst: 0.62 }, different: { mean: 0.31, std: 0.1, closest: 0.58 },
      thresholds: { fpr_01: { threshold: 0.612, tpr: 0.94 }, fpr_05: { threshold: 0.548, tpr: 0.98 }, eer: { threshold: 0.575, fnr: 0.03, fpr: 0.03 } } },
    { metric: 'dinov2_large', same: { mean: 0.77, std: 0.05, worst: 0.6 }, different: { mean: 0.41, std: 0.09, closest: 0.66 },
      thresholds: { fpr_01: { threshold: 0.702, tpr: 0.9 }, fpr_05: { threshold: 0.655, tpr: 0.96 }, eer: { threshold: 0.68, fnr: 0.05, fpr: 0.05 } } },
    { metric: 'clip_vit_l14', same: { mean: 0.88, std: 0.03, worst: 0.79 }, different: { mean: 0.7, std: 0.05, closest: 0.8 },
      thresholds: { fpr_01: { threshold: 0.823, tpr: 0.93 }, fpr_05: { threshold: 0.796, tpr: 0.97 }, eer: { threshold: 0.81, fnr: 0.04, fpr: 0.04 } } },
    { metric: 'lab_mean_delta_e', same: { mean: 6, std: 2, worst: 12 }, different: { mean: 18, std: 5, closest: 9 },
      thresholds: { fpr_01: { threshold: -8.5, tpr: 0.8 }, fpr_05: { threshold: -10.2, tpr: 0.9 }, eer: { threshold: -9.1, fnr: 0.1, fpr: 0.1 } } },
  ],
};

test('fpr 5% becomes the default line and fpr 1% the strict line, per metric', () => {
  const { thresholds, skipped } = thresholdsFromReport(parseCalibrationReport(REPORT), {}, new Date('2026-09-06T00:00:00Z'));
  assert.equal(thresholds.cj, 0.548);
  assert.equal(thresholds.cj_dino, 0.655);
  assert.equal(thresholds.sj, 0.796);
  assert.deepEqual(thresholds.strict, { cj: 0.612, cj_dino: 0.702, sj: 0.823 });
  assert.equal(thresholds.calibrated, true);
  assert.deepEqual(skipped, []);
  assert.deepEqual(thresholds.report.lines, { cj: true, cj_dino: true, sj: true });
  assert.deepEqual(thresholds.report.eer, { cj: 0.575, cj_dino: 0.68, sj: 0.81 });
  assert.equal(thresholds.report.imported_at, '2026-09-06T00:00:00.000Z');
});

test('the colour metric is never a judge line', () => {
  const { thresholds } = thresholdsFromReport(parseCalibrationReport(REPORT));
  assert.ok(!('lab_mean_delta_e' in thresholds));
  assert.ok(!('mq' in thresholds), 'motion is not calibrated by this report');
});

test('missing faces travel with the thresholds so the UI can list them', () => {
  const { thresholds } = thresholdsFromReport(parseCalibrationReport(REPORT));
  assert.deepEqual(thresholds.report.missing_faces, REPORT.missing_faces);
  assert.equal(thresholds.report.images, 24);
  assert.deepEqual(thresholds.report.characters, ['美佳', '阿順']);
});

test('a face metric that only has a note leaves the face line alone and says so', () => {
  const fewFaces = {
    ...REPORT,
    metrics: [{ metric: 'face_facenet', note: 'not enough pairs' }, ...REPORT.metrics.slice(1)],
  };
  const { thresholds, skipped } = thresholdsFromReport(parseCalibrationReport(fewFaces), { cj: 0.8 });
  assert.equal(thresholds.cj, 0.8, 'the existing face line is kept, not replaced by a guess');
  assert.equal(thresholds.cj_dino, 0.655);
  assert.equal(thresholds.calibrated, true, 'dino plus style is still a calibrated report');
  assert.deepEqual(thresholds.report.lines, { cj: false, cj_dino: true, sj: true });
  assert.deepEqual(skipped, [{ line: 'cj', reason: 'not enough pairs' }]);
});

test('a report with no style metric is not calibrated', () => {
  const noStyle = { ...REPORT, metrics: REPORT.metrics.filter((m) => m.metric !== 'clip_vit_l14') };
  const { thresholds } = thresholdsFromReport(parseCalibrationReport(noStyle));
  assert.equal(thresholds.calibrated, false);
});

test('a second, smaller calibration does not erase an earlier full one', () => {
  const first = thresholdsFromReport(parseCalibrationReport(REPORT)).thresholds;
  const dinoOnly = { ...REPORT, metrics: REPORT.metrics.filter((m) => m.metric === 'dinov2_large' || m.metric === 'clip_vit_l14') };
  const second = thresholdsFromReport(parseCalibrationReport(dinoOnly), first).thresholds;
  assert.equal(second.cj, first.cj);
  assert.equal(second.strict.cj, first.strict.cj);
});

test('malformed reports are refused with a reason', () => {
  assert.throws(() => parseCalibrationReport('nope'), /JSON object/);
  assert.throws(() => parseCalibrationReport({ images: 3 }), /no metrics/);
  assert.throws(() => parseCalibrationReport({ metrics: [{ metric: 'face_facenet', thresholds: {} }] }), /fpr_01 is missing/);
  assert.throws(() => parseCalibrationReport({ metrics: [{ thresholds: {} }] }), /name a metric/);
});
