/**
 * Automatic shot breakdown: turn what the audio service measured into a shot list.
 *
 * The music analysis (B2) reports beats, section boundaries and a duration; the LRC gives lyric
 * lines. This decides where the cuts go. It is deliberately a pure function with no imports so the
 * same rules can run in the browser while the user drags things around and, later, on the host.
 *
 * Cut priority is structural first: a section boundary is a real change in the arrangement, a lyric
 * line is where a phrase starts, and the segment cap is only a fallback for when neither is nearby.
 * Every cut then snaps to a beat, because a cut that lands off the grid reads as a mistake even
 * when the timing is otherwise right.
 */

/** A lyric line as `lib/lrc-editor.ts` parses it: seconds against the LRC's own timebase. */
export type BreakdownLyric = { time: number; text: string };

/** Mirrors ImportedCue in `lib/timeline-import.ts` so a breakdown can be handed straight to it. */
export type BreakdownCue = {
  time: number;
  action: string;
  directing: Record<string, string>;
};

export type BreakdownShotKind = 'lyric' | 'breathing';

export type BreakdownShot = {
  /**
   * Stable across re-planning and across edits, derived from the start time rather than a
   * counter: after a merge every index below the join shifts, and a list keyed by index would
   * have React reuse the wrong row. Starts are unique within a breakdown, so this is too.
   */
  id: string;
  index: number;
  start: number;
  end: number;
  kind: BreakdownShotKind;
  /** Lines sung inside this shot, with the offset already applied. Empty for a breathing shot. */
  lyrics: BreakdownLyric[];
  /** Why the shot ends where it does - useful in the editor, and the reason the tests can be exact. */
  endedBy: 'section' | 'lyric' | 'limit' | 'end';
  cue: BreakdownCue;
};

export type BreakdownInput = {
  durationSeconds: number;
  /** Beat times from the audio service, seconds, ascending. */
  beats: number[];
  /** Section boundary times from the audio service. Boundaries at 0 or the end are ignored. */
  sections?: number[];
  /** Raw LRC lines. The offset below is applied here, not by the caller. */
  lyrics?: BreakdownLyric[];
  /**
   * Bible `lyric_offset_seconds`, added to every lyric time. Measured at about -0.9 s on the
   * Okinawa album (see docs/GB10_SETUP.md): a constant that can be corrected, not random error.
   */
  lyricOffsetSeconds?: number;
  /** Hard cap on shot length, matching `segment_seconds` in the timeline (2-20 in the importer). */
  segmentSeconds: number;
  /** Bible directing defaults, copied onto every cue. */
  directing?: Record<string, string>;
  /**
   * Shots shorter than this are never created on purpose; a leftover tail this short is absorbed
   * by the shot before it. Defaults to a quarter of the cap.
   */
  minShotSeconds?: number;
  /**
   * Upper bound on shot count. Defaults to 60 to match MAX_CUES in `lib/timeline-import.ts`:
   * one cue per shot, so a breakdown that exceeds it could not be imported back.
   */
  maxShots?: number;
};

export type Breakdown = {
  shots: BreakdownShot[];
  /** Internal cut times only. The opening of the piece is a start, not a cut. */
  cuts: number[];
  beatSeconds: number;
};

const EPSILON = 1e-6;

/** Millisecond precision is enough to separate two cuts and keeps the id readable. */
const shotId = (start: number) => `shot-${start.toFixed(3)}`;

/** Median gap between beats. Median rather than mean so one dropped beat does not skew the grid. */
export function beatInterval(beats: number[], durationSeconds: number): number {
  const gaps: number[] = [];
  for (let i = 1; i < beats.length; i += 1) {
    const gap = beats[i] - beats[i - 1];
    if (gap > EPSILON) gaps.push(gap);
  }
  if (!gaps.length) {
    // No usable grid: fall back to a value that keeps the snapping tolerance finite.
    return durationSeconds > 0 ? durationSeconds : 1;
  }
  gaps.sort((a, b) => a - b);
  const middle = gaps.length >> 1;
  return gaps.length % 2 ? gaps[middle] : (gaps[middle - 1] + gaps[middle]) / 2;
}

/** Index of the beat closest to `time`, or -1 when there are no beats. */
function nearestBeatIndex(beats: number[], time: number): number {
  if (!beats.length) return -1;
  let low = 0;
  let high = beats.length - 1;
  while (low < high) {
    const middle = (low + high) >> 1;
    if (beats[middle] < time) low = middle + 1;
    else high = middle;
  }
  if (low > 0 && Math.abs(beats[low - 1] - time) <= Math.abs(beats[low] - time)) return low - 1;
  return low;
}

/**
 * Snap to the nearest beat, but only within `tolerance`. Returning undefined rather than the raw
 * time is what keeps every cut on the grid: a candidate that cannot be snapped is not used.
 */
export function snapToBeat(
  beats: number[],
  time: number,
  tolerance: number,
): number | undefined {
  const index = nearestBeatIndex(beats, time);
  if (index < 0) return undefined;
  return Math.abs(beats[index] - time) <= tolerance + EPSILON ? beats[index] : undefined;
}

/** The last beat at or before `time`, used when the cap forces a cut with no candidate nearby. */
function beatAtOrBefore(beats: number[], time: number): number | undefined {
  let low = 0;
  let high = beats.length - 1;
  let found: number | undefined;
  while (low <= high) {
    const middle = (low + high) >> 1;
    if (beats[middle] <= time + EPSILON) {
      found = beats[middle];
      low = middle + 1;
    } else {
      high = middle - 1;
    }
  }
  return found;
}

type Candidate = { time: number; kind: 'section' | 'lyric' };

function candidatesFrom(input: BreakdownInput, beats: number[], tolerance: number): Candidate[] {
  const duration = input.durationSeconds;
  const seen = new Map<number, Candidate>();
  const add = (raw: number, kind: 'section' | 'lyric') => {
    if (!Number.isFinite(raw) || raw <= EPSILON || raw >= duration - EPSILON) return;
    const snapped = snapToBeat(beats, raw, tolerance);
    if (snapped === undefined || snapped <= EPSILON || snapped >= duration - EPSILON) return;
    // A section boundary and a lyric line often land on the same beat; the section wins, because
    // it is the stronger reason to cut and the editor labels the shot by it.
    const existing = seen.get(snapped);
    if (!existing || (existing.kind === 'lyric' && kind === 'section')) {
      seen.set(snapped, { time: snapped, kind });
    }
  };
  for (const section of input.sections ?? []) add(section, 'section');
  for (const lyric of offsetLyrics(input)) add(lyric.time, 'lyric');
  return [...seen.values()].sort((a, b) => a.time - b.time);
}

/** Lyric times with the Bible offset applied, dropped if the shift pushes them out of the piece. */
export function offsetLyrics(input: BreakdownInput): BreakdownLyric[] {
  const offset = input.lyricOffsetSeconds ?? 0;
  return (input.lyrics ?? [])
    .map((line) => ({ time: line.time + offset, text: line.text }))
    .filter((line) => Number.isFinite(line.time) && line.time >= -EPSILON)
    .sort((a, b) => a.time - b.time);
}

function buildStarts(
  input: BreakdownInput,
  beats: number[],
  candidates: Candidate[],
  segmentSeconds: number,
  minShotSeconds: number,
): { time: number; endedBy: BreakdownShot['endedBy'] }[] {
  const duration = input.durationSeconds;
  const boundaries: { time: number; endedBy: BreakdownShot['endedBy'] }[] = [];
  let cursor = 0;
  // Bounded so a pathological grid cannot spin here; every pass moves the cursor forward by at
  // least minShotSeconds, so this is generous.
  const guard = Math.ceil(duration / Math.max(minShotSeconds, EPSILON)) + 8;
  for (let pass = 0; pass < guard; pass += 1) {
    if (duration - cursor <= segmentSeconds + EPSILON) break;
    const limit = cursor + segmentSeconds;
    const earliest = cursor + minShotSeconds;
    const inRange = candidates.filter((c) => c.time >= earliest - EPSILON && c.time <= limit + EPSILON);
    // Section first: cut at the earliest one, because a boundary passed over is a boundary missed.
    const section = inRange.find((c) => c.kind === 'section');
    // Otherwise the latest lyric line that still fits, which keeps shots close to the cap and the
    // shot count down rather than chopping at the first phrase after the minimum.
    const lyric = [...inRange].reverse().find((c) => c.kind === 'lyric');
    let next = section?.time ?? lyric?.time;
    let endedBy: BreakdownShot['endedBy'] = section ? 'section' : lyric ? 'lyric' : 'limit';
    if (next === undefined) {
      const forced = beatAtOrBefore(beats, limit);
      next = forced !== undefined && forced > earliest - EPSILON ? forced : limit;
      endedBy = 'limit';
    }
    if (next <= cursor + EPSILON) break;
    boundaries.push({ time: next, endedBy });
    cursor = next;
  }
  return boundaries;
}

/**
 * Cut a piece of music into shots.
 *
 * Throws only on inputs that have no sensible answer (no duration, a cap outside the importer's
 * range); everything else degrades: no beats means nothing snaps and cuts fall on the cap, no
 * lyrics means every shot is a breathing shot.
 */
export function planBreakdown(input: BreakdownInput): Breakdown {
  const duration = input.durationSeconds;
  if (!Number.isFinite(duration) || duration <= 0) {
    throw new Error('durationSeconds must be a positive number');
  }
  if (!Number.isFinite(input.segmentSeconds) || input.segmentSeconds < 2 || input.segmentSeconds > 20) {
    throw new Error('segmentSeconds must be between 2 and 20');
  }
  const beats = [...(input.beats ?? [])]
    .filter((beat) => Number.isFinite(beat) && beat >= 0 && beat <= duration)
    .sort((a, b) => a - b);
  const beatSeconds = beatInterval(beats, duration);
  const maxShots = Math.max(1, input.maxShots ?? 60);
  const minShotSeconds = Math.min(
    input.minShotSeconds ?? input.segmentSeconds / 4,
    input.segmentSeconds,
  );
  const lyrics = offsetLyrics(input);
  const directing = { ...(input.directing ?? {}) };

  // The cap is raised, never lowered, if honouring it would need more shots than may exist. A
  // breakdown with more cues than the importer accepts could not be loaded back into the timeline.
  let segmentSeconds = input.segmentSeconds;
  let boundaries: { time: number; endedBy: BreakdownShot['endedBy'] }[] = [];
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const candidates = candidatesFrom(input, beats, beatSeconds);
    boundaries = buildStarts(input, beats, candidates, segmentSeconds, minShotSeconds);
    if (boundaries.length + 1 <= maxShots) break;
    segmentSeconds = Math.min(20, Math.max(segmentSeconds * 1.25, duration / maxShots));
  }

  const starts = [0, ...boundaries.map((b) => b.time)];
  const shots: BreakdownShot[] = starts.map((start, index) => {
    const end = index + 1 < starts.length ? starts[index + 1] : duration;
    const endedBy = index < boundaries.length ? boundaries[index].endedBy : 'end';
    const inside = lyrics.filter(
      (line) => line.time >= start - EPSILON && line.time < end - EPSILON,
    );
    return {
      id: shotId(start),
      index,
      start,
      end,
      kind: inside.length ? 'lyric' : 'breathing',
      lyrics: inside,
      endedBy,
      // The cue sits at the head of its shot and carries the Bible's directing. The action is left
      // for the user or, later, for B4's draft - an invented one would look like a decision.
      cue: { time: start, action: '', directing: { ...directing } },
    } satisfies BreakdownShot;
  });

  return { shots, cuts: boundaries.map((b) => b.time), beatSeconds };
}

/** Reindex and recompute every cue after the shot list is edited. */
function reseat(shots: BreakdownShot[], lyrics: BreakdownLyric[]): BreakdownShot[] {
  return shots.map((shot, index) => {
    const inside = lyrics.filter(
      (line) => line.time >= shot.start - EPSILON && line.time < shot.end - EPSILON,
    );
    return {
      ...shot,
      index,
      kind: inside.length ? 'lyric' : 'breathing',
      lyrics: inside,
      // The cue follows its shot: after a merge or a split the old time belongs to a shot that is
      // no longer there. The action the user wrote is kept.
      cue: { ...shot.cue, time: shot.start },
    } satisfies BreakdownShot;
  });
}

/** Merge the shot at `index` with the one after it. The later shot's cue action is dropped. */
export function mergeBreakdownShots(
  shots: BreakdownShot[],
  index: number,
  lyrics: BreakdownLyric[] = [],
): BreakdownShot[] {
  if (index < 0 || index + 1 >= shots.length) return shots;
  const first = shots[index];
  const second = shots[index + 1];
  const merged: BreakdownShot = {
    ...first,
    end: second.end,
    endedBy: second.endedBy,
  };
  const next = [...shots.slice(0, index), merged, ...shots.slice(index + 2)];
  return reseat(next, lyrics);
}

/**
 * Split the shot at `index` at `time`, snapped to the nearest beat within one beat. Returns the
 * list unchanged when the split point does not land inside the shot.
 */
export function splitBreakdownShot(
  shots: BreakdownShot[],
  index: number,
  time: number,
  beats: number[],
  lyrics: BreakdownLyric[] = [],
  beatSeconds?: number,
): BreakdownShot[] {
  const shot = shots[index];
  if (!shot) return shots;
  const tolerance = beatSeconds ?? beatInterval(beats, shot.end);
  const at = snapToBeat(beats, time, tolerance) ?? time;
  if (at <= shot.start + EPSILON || at >= shot.end - EPSILON) return shots;
  const head: BreakdownShot = { ...shot, end: at, endedBy: 'limit' };
  const tail: BreakdownShot = {
    ...shot,
    id: shotId(at),
    start: at,
    cue: { ...shot.cue, time: at, action: '' },
  };
  return reseat([...shots.slice(0, index), head, tail, ...shots.slice(index + 1)], lyrics);
}

/** Cues in the shape `lib/timeline-import.ts` accepts, ready to hand to the MV timeline. */
export function breakdownCues(shots: BreakdownShot[]): BreakdownCue[] {
  return shots.map((shot) => ({ ...shot.cue, directing: { ...shot.cue.directing } }));
}
