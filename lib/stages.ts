/**
 * Stage state for the production line. Deliberately depends on nothing: it takes the handful of
 * facts it needs so it can be tested on its own and so the rail never has to hold a whole plan.
 */
export type PlanSnapshot = {
  hasBible: boolean;
  status: 'draft' | 'running' | 'paused' | 'completed';
  total: number;
  completed: number;
  failed: number;
  /** Finished shots nobody has judged yet. */
  awaitingReview: number;
  /** Shots with an accepted take. */
  accepted: number;
  /** Shots whose image_id came from an approved keyframe. */
  keyframed: number;
  /** Shots whose newest keyframe is red or yellow and waiting on a person. */
  keyframesAttention: number;
};

/** What the line looks like before a plan exists at all. */
export const EMPTY_PLAN_SNAPSHOT: PlanSnapshot = {
  hasBible: false,
  status: 'draft',
  total: 0,
  completed: 0,
  failed: 0,
  awaitingReview: 0,
  accepted: 0,
  keyframed: 0,
  keyframesAttention: 0,
};

export type StageKey =
  | 'bible'
  | 'breakdown'
  | 'keyframes'
  | 'shoot'
  | 'review'
  | 'post'
  | 'assembly';

/** `disabled` marks a stage this phase does not implement; it still occupies its place in the line. */
export type StageStatus = 'idle' | 'active' | 'attention' | 'done' | 'disabled';

export const STAGE_KEYS: StageKey[] = [
  'bible',
  'breakdown',
  'keyframes',
  'shoot',
  'review',
  'post',
  'assembly',
];

/** Post needs the post adapter (D3). Keyframes arrived in D2, review in C3. */
export const UNAVAILABLE_STAGES: StageKey[] = ['post'];

export type StageOwner = 'user' | 'worker' | 'none';

export type PlanProgress = {
  statuses: Record<StageKey, StageStatus>;
  /** Where the plan currently sits: the first stage that still needs work. */
  current: StageKey;
  /** What the last finished step established, as a translation key. */
  lastResult: string;
  /** Who has to act next. */
  owner: StageOwner;
  nextAction: string;
};

function baseStatuses(plan: PlanSnapshot): Record<StageKey, StageStatus> {
  const allDone = plan.total > 0 && plan.completed === plan.total;
  return {
    bible: plan.hasBible ? 'done' : 'idle',
    breakdown: plan.total ? 'done' : 'idle',
    // Keyframes are optional before shooting: idle until there are shots, attention while a
    // candidate waits on a person, done once every shot starts from an approved keyframe.
    keyframes: plan.keyframesAttention
      ? 'attention'
      : plan.total > 0 && plan.keyframed === plan.total
        ? 'done'
        : 'idle',
    shoot: plan.failed
      ? 'attention'
      : plan.status === 'running'
        ? 'active'
        : allDone
          ? 'done'
          : 'idle',
    // Review asks for a person as soon as one finished shot has no verdict; it is done when every
    // shot has an accepted take. Between those it is simply idle - nothing to look at yet.
    review: plan.awaitingReview
      ? 'attention'
      : plan.total > 0 && plan.accepted === plan.total
        ? 'done'
        : 'idle',
    post: 'disabled',
    assembly: plan.status === 'completed' ? 'done' : 'idle',
  };
}

/**
 * Stage state is derived from the plan, never stored: a plan restored from JSON or from another
 * device shows the same line without carrying its own progress bookkeeping.
 */
export function planProgress(plan: PlanSnapshot): PlanProgress {
  const statuses = baseStatuses(plan);

  // "You are here" is the first stage that is neither finished nor out of scope this phase.
  // Keyframes are optional: an idle keyframe stage is skipped over, and only asks to be current
  // while a candidate is waiting on a person.
  const pending = STAGE_KEYS.find(
    (key) =>
      statuses[key] !== 'done' &&
      statuses[key] !== 'disabled' &&
      !(key === 'keyframes' && statuses[key] === 'idle'),
  );
  const current = pending ?? 'assembly';
  if (pending && statuses[pending] === 'idle') statuses[pending] = 'active';

  let lastResult = 'resultNone';
  if (plan.failed) lastResult = 'resultFailed';
  else if (plan.total > 0 && plan.accepted === plan.total) lastResult = 'resultReviewed';
  else if (plan.status === 'completed') lastResult = 'resultCompleted';
  else if (plan.completed) lastResult = 'resultShots';
  else if (plan.total) lastResult = 'resultBreakdown';
  else if (plan.hasBible) lastResult = 'resultBible';

  let owner: StageOwner = 'user';
  let nextAction = 'nextBible';
  if (plan.failed) {
    nextAction = 'nextFix';
  } else if (plan.status === 'running') {
    owner = 'worker';
    nextAction = 'nextWait';
  } else if (current === 'bible') {
    nextAction = 'nextBible';
  } else if (current === 'breakdown') {
    nextAction = 'nextShots';
  } else if (current === 'shoot') {
    nextAction = 'nextRun';
  } else if (current === 'review') {
    nextAction = plan.awaitingReview ? 'nextReview' : 'nextRun';
  } else if (current === 'keyframes') {
    nextAction = plan.keyframesAttention ? 'nextKeyframesReview' : 'nextKeyframes';
  } else if (current === 'assembly') {
    nextAction = 'nextAssemble';
  } else {
    owner = 'none';
    nextAction = 'nextUnavailable';
  }

  return { statuses, current, lastResult, owner, nextAction };
}
