/**
 * Read a calibration report from infra/gb10/tools/calibrate_embeddings.py into Bible thresholds.
 *
 * The mapping is the one docs/work-orders/C4.md records: fpr 5% becomes the default line, fpr 1%
 * the strict line for adjacent shots. The face and DINOv2 metrics land on separate fields
 * because they are on different scales - the consistency judge uses whichever path scored the
 * frame, and one number cannot serve both.
 *
 * A metric that reports only a note had too few usable pairs. It is left alone rather than
 * guessed, and the report says which lines are still uncalibrated: an import must not turn a
 * half-measured report into a fully calibrated Bible.
 */
export type ThresholdPair = { threshold: number; tpr?: number };
export type ReportMetric =
  | { metric: string; thresholds: { fpr_01: ThresholdPair; fpr_05: ThresholdPair; eer?: ThresholdPair } }
  | { metric: string; note: string };

export type CalibrationReport = {
  root?: string;
  images: number;
  characters: string[];
  missing_faces: string[];
  metrics: ReportMetric[];
};

export type BibleThresholds = {
  cj?: number;
  cj_dino?: number;
  sj?: number;
  mq?: number;
  strict?: { cj?: number; cj_dino?: number; sj?: number; mq?: number };
  calibrated?: boolean;
  report?: {
    images: number;
    characters: string[];
    missing_faces: string[];
    lines: { cj: boolean; cj_dino: boolean; sj: boolean };
    eer?: Partial<Record<'cj' | 'cj_dino' | 'sj', number>>;
    imported_at: string;
  };
};

const METRIC_FIELD: Record<string, 'cj' | 'cj_dino' | 'sj'> = {
  face_facenet: 'cj',
  dinov2_large: 'cj_dino',
  clip_vit_l14: 'sj',
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function unit(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? Math.round(value * 10000) / 10000
    : undefined;
}

/** Parse the JSON the script writes. Throws with a readable message on anything else. */
export function parseCalibrationReport(value: unknown): CalibrationReport {
  if (!isRecord(value)) throw new Error('Calibration report must be a JSON object');
  if (!Array.isArray(value.metrics)) throw new Error('Calibration report has no metrics');
  const metrics = value.metrics.map((item, index) => {
    if (!isRecord(item) || typeof item.metric !== 'string') {
      throw new Error(`metrics[${index}] must name a metric`);
    }
    if (typeof item.note === 'string') return { metric: item.metric, note: item.note };
    if (!isRecord(item.thresholds)) throw new Error(`metrics[${index}] has no thresholds`);
    const pair = (key: string): ThresholdPair => {
      const raw = (item.thresholds as Record<string, unknown>)[key];
      if (!isRecord(raw) || typeof raw.threshold !== 'number' || !Number.isFinite(raw.threshold)) {
        throw new Error(`metrics[${index}].thresholds.${key} is missing`);
      }
      return { threshold: raw.threshold, ...(typeof raw.tpr === 'number' ? { tpr: raw.tpr } : {}) };
    };
    const eerRaw = (item.thresholds as Record<string, unknown>).eer;
    return {
      metric: item.metric,
      thresholds: {
        fpr_01: pair('fpr_01'),
        fpr_05: pair('fpr_05'),
        ...(isRecord(eerRaw) && typeof eerRaw.threshold === 'number' ? { eer: { threshold: eerRaw.threshold } } : {}),
      },
    };
  });
  return {
    ...(typeof value.root === 'string' ? { root: value.root } : {}),
    images: typeof value.images === 'number' ? value.images : 0,
    characters: Array.isArray(value.characters) ? value.characters.map(String) : [],
    missing_faces: Array.isArray(value.missing_faces) ? value.missing_faces.map(String) : [],
    metrics,
  };
}

export type CalibrationImport = {
  thresholds: BibleThresholds;
  /** Lines the report could not set, with the reason, for the UI to say out loud. */
  skipped: { line: 'cj' | 'cj_dino' | 'sj'; reason: string }[];
};

/**
 * Turn a report into the thresholds to merge over the Bible's. Existing values on lines the
 * report cannot set are kept, which is why `existing` is taken: a second, smaller calibration
 * must not erase what an earlier full one measured.
 */
export function thresholdsFromReport(
  report: CalibrationReport,
  existing: BibleThresholds = {},
  now = new Date(),
): CalibrationImport {
  const next: BibleThresholds = { ...existing, strict: { ...(existing.strict ?? {}) } };
  const lines = { cj: false, cj_dino: false, sj: false };
  const eer: NonNullable<BibleThresholds['report']>['eer'] = {};
  const skipped: CalibrationImport['skipped'] = [];
  for (const metric of report.metrics) {
    const field = METRIC_FIELD[metric.metric];
    if (!field) continue; // lab_mean_delta_e runs the other way and is not a judge line.
    if ('note' in metric) {
      skipped.push({ line: field, reason: metric.note });
      continue;
    }
    const loose = unit(metric.thresholds.fpr_05.threshold);
    const strict = unit(metric.thresholds.fpr_01.threshold);
    if (loose === undefined || strict === undefined) {
      skipped.push({ line: field, reason: 'threshold outside 0-1' });
      continue;
    }
    next[field] = loose;
    next.strict![field] = strict;
    lines[field] = true;
    const e = metric.thresholds.eer ? unit(metric.thresholds.eer.threshold) : undefined;
    if (e !== undefined) eer[field] = e;
  }
  // Calibrated means the review page can stop saying "placeholder": at least one consistency
  // line and the style line were measured. A face-only or dino-only report still counts.
  next.calibrated = (lines.cj || lines.cj_dino) && lines.sj;
  next.report = {
    images: report.images,
    characters: report.characters,
    missing_faces: report.missing_faces,
    lines,
    ...(Object.keys(eer).length ? { eer } : {}),
    imported_at: now.toISOString(),
  };
  return { thresholds: next, skipped };
}
