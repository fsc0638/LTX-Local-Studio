"""CPU-only technical release gate. Visual heuristics are warnings, not review."""
import json
import math
import sys

import av
import numpy as np


def check_output(path, expected):
    report = {"version": "full-decode-v1", "passed": False, "errors": [], "warnings": [],
              "visual_review_required": True, "metrics": {}}
    measured = {"verified": False, "measurement": "full_decode"}
    errors, warnings, metrics = report["errors"], report["warnings"], report["metrics"]
    try:
        with av.open(str(path)) as container:
            if "mp4" not in container.format.name.split(","):
                raise ValueError("Expected an MP4 container")
            if len(container.streams.video) != 1:
                raise ValueError("Expected exactly one video stream")
            stream = container.streams.video[0]
            fps = float(stream.average_rate or 0)
            if not math.isfinite(fps) or fps <= 0:
                raise ValueError("Invalid video frame rate")
            width, height = stream.width, stream.height
            count = black = frozen = 0
            first_time = last_time = previous = None
            timestamps_valid = True
            for frame in container.decode(video=0):
                count += 1
                # Bounded decode for malformed or unexpectedly long output.
                if count > expected["frames"] + 1:
                    errors.append("unexpected_extra_frames")
                    break
                if frame.width != expected["width"] or frame.height != expected["height"]:
                    if "dimension_mismatch" not in errors:
                        errors.append("dimension_mismatch")
                timestamp = float(frame.pts * frame.time_base) if frame.pts is not None else None
                if timestamp is None or (last_time is not None and timestamp <= last_time):
                    timestamps_valid = False
                if first_time is None:
                    first_time = timestamp
                last_time = timestamp
                sample = frame.reformat(width=32, height=18, format="gray").to_ndarray().astype(np.float32)
                black += int(sample.mean() < 8 and sample.std() < 4)
                frozen += int(previous is not None and np.abs(sample - previous).mean() < 0.5)
                previous = sample
            if count != expected["frames"]:
                errors.append("frame_count_mismatch")
            if abs(fps - expected["fps"]) > 0.001:
                errors.append("fps_mismatch")
            if not timestamps_valid or first_time is None or last_time is None:
                errors.append("invalid_video_timestamps")
                duration = None
            else:
                duration = last_time - first_time + 1 / fps
                if abs(duration - expected["frames"] / expected["fps"]) > 0.5 / expected["fps"]:
                    errors.append("duration_mismatch")
            measured.update(frames=count, fps=fps, width=width, height=height, video_seconds=duration,
                            video_codec=stream.codec_context.name,
                            container_seconds=container.duration / av.time_base if container.duration is not None else None)
            metrics.update(black_frame_ratio=round(black / max(count, 1), 4),
                           near_static_transition_ratio=round(frozen / max(count - 1, 1), 4))
            if black:
                warnings.append("near_black_frames_detected")
            if frozen / max(count - 1, 1) >= 0.2:
                warnings.append("near_static_frames_detected")

        with av.open(str(path)) as container:
            if len(container.streams.audio) > 1:
                errors.append("multiple_audio_streams")
            has_audio = bool(container.streams.audio)
            measured["has_audio"] = has_audio
            if expected["audio"] and not has_audio:
                errors.append("missing_audio_stream")
            if not expected["audio"] and has_audio:
                errors.append("unexpected_audio_stream")
            if has_audio:
                measured["audio_codec"] = container.streams.audio[0].codec_context.name
                seconds = 0.0
                audio_frames = 0
                for frame in container.decode(audio=0):
                    audio_frames += 1
                    seconds += frame.samples / frame.sample_rate
                    if seconds > expected["frames"] / expected["fps"] + 10:
                        errors.append("unexpected_audio_length")
                        break
                measured.update(audio_seconds=seconds, decoded_audio_frames=audio_frames)
                if audio_frames == 0:
                    errors.append("empty_audio_stream")
                if abs(seconds - expected["frames"] / expected["fps"]) > 0.25:
                    warnings.append("audio_video_duration_difference")
    except Exception as exc:
        errors.append("decode_failed")
        report["detail"] = f"{type(exc).__name__}: {exc}"[:500]
    report["passed"] = not errors
    measured["verified"] = report["passed"]
    return {"quality_control": report, "measured_media": measured}


if __name__ == "__main__":
    print(json.dumps(check_output(sys.argv[1], json.loads(sys.argv[2])), allow_nan=False))
