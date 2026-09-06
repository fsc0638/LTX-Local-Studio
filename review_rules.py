"""Which light a take gets, and where the lines are drawn. Shared by the API and the tests.

The default numbers are the architecture page's placeholders (0.80 / 0.85) and are marked
uncalibrated. C4 replaces them with measured fpr thresholds written into the Bible; until then
the UI says so next to every line. A per-shot override in the shot's request wins over the
Bible, and the Bible wins over these defaults.

lib/review.ts is the same rule for the browser. Keep the two in step; the tests on both sides use
the same fixture numbers so drift shows up as a failing test rather than a disagreement on screen.
"""

# cj and cj_dino are separate lines: facenet and DINOv2 similarities are on different scales, and
# the consistency judge uses whichever path found the frame's face - or did not.
DEFAULT_THRESHOLDS = {"cj": 0.80, "cj_dino": 0.80, "sj": 0.85, "mq": 0.50}
# The stricter set for adjacent shots (C4's fpr 1%). Uncalibrated placeholder: a little above the
# default, enough to make the mode visible without pretending to a measurement.
DEFAULT_STRICT = {"cj": 0.85, "cj_dino": 0.85, "sj": 0.90, "mq": 0.50}
LINE_KEYS = ("cj", "cj_dino", "sj", "mq")


def _numbers(raw):
    out = {}
    for key in LINE_KEYS:
        value = (raw or {}).get(key) if isinstance(raw, dict) else None
        if isinstance(value, (int, float)) and 0 <= value <= 1:
            out[key] = float(value)
    return out


def resolve_thresholds(bible, request=None, strict=False):
    """Bible thresholds over the defaults, then the shot's own override over both."""
    bible_thresholds = (bible or {}).get("thresholds") or {}
    base = dict(DEFAULT_STRICT if strict else DEFAULT_THRESHOLDS)
    base.update(_numbers(bible_thresholds.get("strict") if strict else bible_thresholds))
    base.update(_numbers((request or {}).get("thresholds")))
    calibrated = bool(bible_thresholds.get("calibrated"))
    return {**base, "calibrated": calibrated, "strict": strict}


def consistency_method(scores):
    """Which consistency path scored most frames, or None when there is no per-frame record."""
    if not isinstance(scores, dict):
        return None
    methods = (scores.get("consistency") or {}).get("method_per_frame") or []
    if not methods:
        return None
    faces = sum(1 for m in methods if m == "face_facenet")
    return "face_facenet" if faces * 2 >= len(methods) else "dinov2_large"


def consistency_line(scores, thresholds):
    """The consistency line in force: cj when faces were found, cj_dino when not."""
    return thresholds["cj_dino"] if consistency_method(scores) == "dinov2_large" else thresholds["cj"]


def take_scores(scores):
    """The three numbers the review page draws, or None where the judge had nothing to say."""
    if not isinstance(scores, dict) or scores.get("status") == "unscored":
        return {"cj": None, "sj": None, "mq": None}
    consistency = scores.get("consistency") or {}
    style = scores.get("style") or {}
    media = scores.get("media") or {}
    frozen = media.get("frozen_ratio")
    return {
        "cj": consistency.get("median"),
        "sj": style.get("median"),
        # A still has no motion to score; a video's motion score is how much of it moved.
        "mq": round(1 - frozen, 4) if isinstance(frozen, (int, float)) else None,
    }


def lights(scores, thresholds):
    """'red' below the line, 'green' at or above it, 'unscored' when there is no number.

    Unscored is not red. A judge that is down, a project with no reference images, a still with
    no motion: none of these is evidence against the take, so none of them lights it red.
    """
    values = take_scores(scores)
    result = {}
    for key in ("cj", "sj", "mq"):
        value = values[key]
        line = consistency_line(scores, thresholds) if key == "cj" else thresholds[key]
        if value is None:
            result[key] = "unscored"
        else:
            result[key] = "red" if value < line else "green"
    return result


def is_red(scores, thresholds):
    return "red" in lights(scores, thresholds).values()
