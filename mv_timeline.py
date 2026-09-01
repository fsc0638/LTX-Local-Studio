"""Bounded, project-independent MV shot planning. Text is data, never code."""
import math
import re

MAX_SECONDS = 180
MAX_SEGMENTS = 120


def option(zh, en, ja, prompt):
    return {"label": {"zh-TW": zh, "en": en, "ja": ja}, "prompt": prompt}


DIRECTING = {
    "shot_size": {
        "wide": option("遠景／建立鏡頭", "Wide / establishing", "遠景／導入", "Wide establishing shot showing the subject's relationship to the environment."),
        "full": option("全身景", "Full shot", "全身", "Full-body shot with head and feet visible and grounded steps."),
        "medium": option("中景 MS", "Medium shot", "ミディアム", "Medium shot, framed from the waist up."),
        "mcu": option("中近景 MCU", "Medium close-up", "ミディアム・クローズアップ", "Medium close-up from the chest up, with visible shoulders and natural breathing."),
        "close": option("特寫 CU", "Close-up", "クローズアップ", "Close-up on the face, with clear eyes and subtle facial expression."),
        "insert": option("細節／插入鏡頭", "Detail / cutaway", "ディテール／挿入", "An insert shot emphasizing one meaningful detail or prop."),
        "breathing": option("情緒留白 Breathing Frame", "Breathing frame", "余韻のショット", "A quiet breathing frame: subtle breathing, a natural blink and gentle hair movement; hold a pause at the end and leave negative space ahead of the gaze."),
    },
    "angle": {
        "front": option("正面平視", "Front / eye level", "正面／目線", "Front view at eye level."),
        "three_quarter": option("3/4 側前方約45°", "Three-quarter / 45°", "斜め前45度", "Three-quarter view, the subject turned about 45 degrees relative to the camera."),
        "profile": option("側面90°", "Profile / 90°", "横顔90度", "Side profile, approximately 90 degrees to the camera."),
        "low": option("低角度仰拍", "Low angle", "ローアングル", "A low camera angle looking gently upward."),
        "high": option("高角度俯拍", "High angle", "ハイアングル", "A high camera angle looking gently downward."),
        "over_shoulder": option("過肩鏡頭", "Over the shoulder", "肩越し", "Over-the-shoulder composition with a clear eyeline toward the subject."),
    },
    "camera": {
        "locked": option("固定鏡頭", "Locked camera", "固定", "Locked camera, stable framing throughout this shot."),
        "push": option("緩慢推近", "Slow push-in", "ゆっくり寄る", "The camera makes one slow, smooth push-in."),
        "pull": option("緩慢拉遠", "Slow pull-back", "ゆっくり引く", "The camera slowly pulls back to reveal the surroundings."),
        "track": option("平行跟拍", "Tracking", "並行移動", "A smooth lateral tracking shot following the subject."),
        "orbit": option("小幅環繞", "Gentle arc", "小さな回り込み", "The camera makes a gentle, limited arc around the subject."),
    },
    "emotion": {
        "calm": option("平靜／自然呼吸", "Calm", "穏やか", "Relaxed shoulders, steady gaze and slow natural breathing."),
        "longing": option("思念／欲言又止", "Longing", "恋しさ", "The gaze lingers off-screen, lips part slightly, then a restrained exhale."),
        "sad": option("悲傷／釋放", "Sadness / release", "悲しみ／解放", "The gaze lowers, fingers slowly relax and the shoulders drop on an exhale."),
        "hope": option("希望／抬眼", "Hope", "希望", "The eyes lift toward the light, posture opens and a small smile appears."),
        "resolve": option("堅定／迎向鏡頭", "Resolve", "決意", "The subject steadies their gaze, lifts their chin slightly and holds a grounded posture."),
        "joy": option("喜悅／輕快", "Joy", "喜び", "Bright eyes, an unforced smile and light, buoyant movement."),
    },
    "performance": {
        "natural": option("自然動作", "Natural action", "自然な動き", "Natural, restrained physical performance."),
        "speaking": option("說話表演（同步實驗）", "Speaking (experimental sync)", "話す（同期は実験的）", "The subject speaks the supplied words, with restrained gestures and a clearly visible mouth."),
        "singing": option("演唱表演（同步實驗）", "Singing (experimental sync)", "歌う（同期は実験的）", "The subject sings expressively to the supplied music, with a clearly visible mouth and controlled head movement."),
    },
}


def normalize_directing(raw):
    if not isinstance(raw, dict) or set(raw) - set(DIRECTING):
        raise ValueError("Invalid directing settings")
    for key, value in raw.items():
        if not isinstance(value, str) or value not in DIRECTING[key]:
            raise ValueError(f"Unsupported directing.{key}")
    return dict(raw)


def compose_prompt(prompt, directing, action="", lyrics=""):
    parts = [prompt] + [DIRECTING[key][value]["prompt"] for key, value in directing.items()]
    if action:
        parts.append("Primary action in this shot: " + action)
    if lyrics:
        parts.append("Words for this shot: " + lyrics)
    result = " ".join(parts)
    if len(result) > 6000:
        raise ValueError("Combined shot prompt exceeds 6000 characters; shorten prompt or lyrics")
    return result


def parse_lrc(text):
    if not isinstance(text, str) or len(text) > 16000:
        raise ValueError("LRC must be text, maximum 16000 characters")
    offset = 0
    entries = []
    stamp = re.compile(r"\[(\d{1,3}):([0-5]\d)(?:[.:](\d{1,3}))?\]")
    for number, line in enumerate(text.lstrip("\ufeff").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if match := re.fullmatch(r"\[offset:([+-]?\d+)\]", line, re.I):
            offset = int(match[1]) / 1000
            continue
        if re.fullmatch(r"\[(ar|ti|al|by|re|ve|length):[^\]]*\]", line, re.I):
            continue
        matches = list(stamp.finditer(line))
        lyrics = stamp.sub("", line).strip()
        if not matches or matches[0].start() != 0 or "[" in lyrics or "]" in lyrics or "<" in lyrics:
            raise ValueError(f"LRC line {number}: use [mm:ss.xx]lyrics; word-level LRC is not supported")
        if len(lyrics) > 500:
            raise ValueError(f"LRC line {number} is too long")
        for match in matches:
            fraction = float("0." + match[3]) if match[3] else 0
            entries.append({"time": int(match[1]) * 60 + int(match[2]) + fraction, "text": lyrics})
        if len(entries) > 120:
            raise ValueError("At most 120 LRC timestamps are supported")
    grouped = {}
    for entry in entries:
        timestamp = round(entry["time"] + offset, 6)
        if timestamp < 0:
            raise ValueError("LRC offset creates a negative timestamp")
        grouped.setdefault(timestamp, []).append(entry["text"])
    return [{"time": timestamp, "text": " / ".join(dict.fromkeys(lines))} for timestamp, lines in sorted(grouped.items())]


def number(value, name, minimum, maximum):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be {minimum}–{maximum}")
    return value


def normalize_sequence(raw, payload, max_frames, asset_lookup):
    duration = number(raw.get("duration_seconds"), "duration_seconds", 0.125, MAX_SECONDS)
    fps = payload["fps"]
    total = math.ceil(duration * fps)
    segment_seconds = number(raw.get("segment_seconds", 10), "segment_seconds", 2, 20)
    max_keep = min(math.floor(segment_seconds * fps), max_frames)
    # Each shot rounds upward for inference; composition keeps exactly max_keep.
    timeline = raw.get("timeline", {})
    if not isinstance(timeline, dict) or set(timeline) - {"audio_id", "audio_start_seconds", "audio_mode", "lrc", "cues"}:
        raise ValueError("Invalid timeline fields")
    audio_id = timeline.get("audio_id")
    audio_mode = timeline.get("audio_mode", "soundtrack")
    if audio_mode not in {"soundtrack", "condition"} or (audio_mode == "condition" and not audio_id):
        raise ValueError("audio_mode=condition requires imported music")
    start = number(timeline.get("audio_start_seconds", 0), "audio_start_seconds", 0, 600)
    if audio_id is not None:
        if not isinstance(audio_id, str):
            raise ValueError("audio_id must be an uploaded asset ID")
        asset = asset_lookup(audio_id)
        if asset.get("kind") != "audio":
            raise ValueError("timeline.audio_id must be an audio asset")
        if start + duration > asset.get("duration_seconds", 0) + 0.025:
            raise ValueError("Music is shorter than the requested timeline; reduce duration or start offset")
        if not payload["audio"]:
            raise ValueError("Imported music requires audio=true")
    elif start:
        raise ValueError("audio_start_seconds requires audio_id")
    lrc = timeline.get("lrc", "")
    lyrics = parse_lrc(lrc)
    cues = timeline.get("cues", [])
    if not isinstance(cues, list) or len(cues) > 60:
        raise ValueError("At most 60 action cues are supported")
    clean_cues = []
    for cue in cues:
        if not isinstance(cue, dict) or set(cue) - {"time", "action", "directing"}:
            raise ValueError("Cue accepts time, action and directing only")
        when = number(cue.get("time"), "cue.time", 0, duration)
        if when >= duration:
            raise ValueError("Action cue must start before the end of the video")
        action = cue.get("action", "")
        if not isinstance(action, str) or len(action) > 600:
            raise ValueError("Cue action must be text, maximum 600 characters")
        clean_cues.append({"time": when, "action": action, "directing": normalize_directing(cue.get("directing", {}))})
    clean_cues.sort(key=lambda cue: cue["time"])
    if len({c["time"] for c in clean_cues}) != len(clean_cues):
        raise ValueError("Action cues cannot have duplicate timestamps")
    points = sorted({0, total, *(min(total, math.ceil(c["time"] * fps)) for c in lyrics + clean_cues if c["time"] < duration)})
    boundaries = [0]
    for end in points[1:]:
        while end - boundaries[-1] > max_keep:
            boundaries.append(boundaries[-1] + max_keep)
        boundaries.append(end)
    if len(boundaries) - 1 > MAX_SEGMENTS:
        raise ValueError("Timeline exceeds 120 shots; remove closely spaced cues or increase shot length")
    segments = []
    for first, last in zip(boundaries, boundaries[1:]):
        when = first / fps
        cue = next((cue for cue in reversed(clean_cues) if cue["time"] <= when + 1e-6), {})
        lyric = next((cue["text"] for cue in reversed(lyrics) if cue["time"] <= when + 1e-6), "")
        directing = {**payload.get("directing", {}), **cue.get("directing", {})}
        keep = last - first
        segments.append({"index": len(segments) + 1, "start_frame": first, "keep_frames": keep,
                         "frames": max(9, math.ceil((keep - 1) / 8) * 8 + 1), "start_seconds": when,
                         "duration_seconds": keep / fps, "lyrics": lyric, "action": cue.get("action", ""),
                         "directing": directing, "prompt": compose_prompt(payload["prompt"], directing, cue.get("action", ""), lyric)})
    return {"render_mode": "sequence", "frames": total, "duration_seconds": duration, "segment_seconds": segment_seconds,
            "timeline": {"audio_id": audio_id, "audio_start_seconds": start, "audio_mode": audio_mode, "lrc": lrc, "cues": clean_cues},
            "segments": segments, "timeline_warnings": ["LRC timestamps after the requested duration are not rendered."] if any(c["time"] >= duration for c in lyrics) else []}
