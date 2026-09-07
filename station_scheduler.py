"""Which workstation a job needs, which job to run next, and what a plan will cost.

A workstation is what holds the GPU: LTX for video, the image service for keyframes, or none
for the post tools and text. Switching between the two big ones costs a model load - the D1
measurements put Qwen at 336 s - so the scheduler runs everything queued for the station that
holds the GPU before it hands over, and hands over to the station with the most work waiting.

Every function here is pure. The scheduler feeds it what it read from the store; the estimate
takes rolling averages the job store measured and falls back to the numbers in
docs/GB10_SETUP.md (and D1's section of the roadmap) when a model has no history yet. Those
fallbacks are named as such in the output, because an estimate that hides which of its inputs
were guessed is not an estimate.
"""

STATIONS = ("ltx", "imagegen", "none")

# From docs/GB10_SETUP.md and the D1 measurements. Seconds. Used only until the job store has
# runtime_seconds for the model; the estimate says which numbers came from here.
DEFAULT_RUNTIME = {
    "ltx23-distilled": 150.0,        # a distilled 5 s shot with model load, before any history
    "qwen-image-edit-2509": 25.8,
    "z-image-turbo": 12.9,
    "post-vx": 60.0,
}
# What switching *to* a station costs once, on top of the jobs: the image model's load. LTX loads
# per job and that time is already inside its runtime average, so its switch cost is zero.
SWITCH_SECONDS = {"ltx": 0.0, "imagegen": 336.0, "none": 0.0}


def station_of(model, adapters=None):
    """The workstation a model needs. `adapters` is model_registry.ADAPTERS when available."""
    adapter = (adapters or {}).get(model)
    if adapter is not None:
        declared = getattr(adapter, "gpu_tenant", "") or ""
        if declared in STATIONS:
            return declared
        media = getattr(adapter, "media_type", "video")
        return "ltx" if media == "video" else "imagegen" if media == "image" else "none"
    if model == "ltx23-distilled":
        return "ltx"
    if model in ("qwen-image-edit-2509", "z-image-turbo"):
        return "imagegen"
    return "none"


def choose_next(candidates, holder, queued_by_station):
    """Pick the next job from one candidate per project.

    candidates: [{"project_id", "shot", "station"}] in project order.
    holder: the station on the GPU now ("ltx" / "imagegen") or None.
    queued_by_station: {"ltx": n, "imagegen": n, "none": n} across all running projects.

    Same station as the holder first - a switch is paid once and should serve everything that
    is waiting. With no holder, or nothing waiting for it, the station with the most queued
    work goes first, so the one switch serves the largest group. Station "none" never needs the
    GPU and runs whenever it is the only thing waiting, or alongside nothing: it is not made to
    wait for a switch it does not need.
    """
    if not candidates:
        return None
    if holder in ("ltx", "imagegen"):
        for candidate in candidates:
            if candidate["station"] == holder:
                return candidate
    free = [c for c in candidates if c["station"] == "none"]
    if free and not any(c["station"] in ("ltx", "imagegen") for c in candidates):
        return free[0]
    order = sorted(("ltx", "imagegen"), key=lambda s: -queued_by_station.get(s, 0))
    for station in order:
        for candidate in candidates:
            if candidate["station"] == station:
                return candidate
    return candidates[0]


def switch_count(stations, holder=None):
    """How many station changes a sequence of jobs incurs, starting from `holder`."""
    switches = 0
    current = holder
    for station in stations:
        if station == "none":
            continue
        if current is not None and station != current:
            switches += 1
        current = station
    return switches


def group_by_station(stations, holder=None):
    """The order the scheduler will actually use: the holder's station first, then the larger
    remaining group. Returns the stations in that order."""
    counts = {}
    for station in stations:
        counts[station] = counts.get(station, 0) + 1
    order = []
    if holder in counts and holder in ("ltx", "imagegen"):
        order.append(holder)
    for station in sorted((s for s in counts if s in ("ltx", "imagegen") and s not in order),
                          key=lambda s: -counts[s]):
        order.append(station)
    if "none" in counts:
        order.append("none")
    result = []
    for station in order:
        result.extend([station] * counts[station])
    return result


def estimate(shot_models, holder=None, averages=None, openai_tokens=0):
    """Seconds for a plan's remaining shots, run grouped, plus what was measured versus assumed.

    shot_models: the model of each shot still to run.
    averages: {model: rolling mean runtime_seconds} from the job store; missing models fall back
    to DEFAULT_RUNTIME and are listed under "assumed".
    """
    averages = averages or {}
    generate = 0.0
    assumed, measured = set(), set()
    stations = []
    for model in shot_models:
        if model in averages and averages[model]:
            generate += float(averages[model])
            measured.add(model)
        else:
            generate += DEFAULT_RUNTIME.get(model, 60.0)
            assumed.add(model)
        stations.append(station_of(model))
    ordered = group_by_station(stations, holder)
    switches = switch_count(ordered, holder)
    # Each switch into a station pays that station's load; count them by destination.
    switch_seconds = 0.0
    current = holder
    for station in ordered:
        if station == "none":
            continue
        if current is not None and station != current:
            switch_seconds += SWITCH_SECONDS.get(station, 0.0)
        current = station
    return {"generate_seconds": round(generate, 1), "switches": switches,
            "switch_seconds": round(switch_seconds, 1),
            "total_seconds": round(generate + switch_seconds, 1),
            "openai_tokens": int(openai_tokens),
            "assumed_models": sorted(assumed), "measured_models": sorted(measured)}


def budget_warnings(estimate_result, budget):
    """Over budget is a warning, never a stop. `budget` is the Bible's {gpu_seconds, openai_tokens}."""
    warnings = []
    budget = budget or {}
    limit = budget.get("gpu_seconds")
    if isinstance(limit, (int, float)) and limit > 0 and estimate_result["total_seconds"] > limit:
        warnings.append({"kind": "gpu_seconds", "limit": limit, "estimate": estimate_result["total_seconds"]})
    limit = budget.get("openai_tokens")
    if isinstance(limit, (int, float)) and limit > 0 and estimate_result["openai_tokens"] > limit:
        warnings.append({"kind": "openai_tokens", "limit": limit, "estimate": estimate_result["openai_tokens"]})
    return warnings
