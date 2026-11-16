"""CPU-only bounded composition using installed PyAV, no external shell commands."""
import json
import sys
from fractions import Fraction

import av
import numpy as np
from PIL import Image, ImageOps

RATE = 48000


def audio_samples(path, start, seconds, *, pad=False):
    """Return stereo float32 PCM for a bounded interval, ignoring encoder delay."""
    end = start + seconds
    if start < 0 or seconds <= 0 or end > 621:
        raise ValueError("Invalid audio interval")
    chunks = []
    position = 0
    first, last = round(start * RATE), round(end * RATE)
    with av.open(str(path)) as source:
        resampler = av.AudioResampler(format="fltp", layout="stereo", rate=RATE)
        def collect(frame):
            nonlocal position
            data = frame.to_ndarray()
            left, right = max(first, position), min(last, position + frame.samples)
            if left < right:
                chunks.append(data[:, left - position:right - position])
            position += frame.samples
        for frame in source.decode(audio=0):
            for converted in resampler.resample(frame):
                collect(converted)
            if position >= last:
                break
        else:
            for converted in resampler.resample(None):
                collect(converted)
    result = np.concatenate(chunks, axis=1) if chunks else np.zeros((2, 0), dtype=np.float32)
    count = round(seconds * RATE)
    if result.shape[1] < count:
        if not pad and count - result.shape[1] > RATE * 0.025:
            raise ValueError("Music shorter than requested interval")
        result = np.pad(result, ((0, 0), (0, count - result.shape[1])))
    return np.ascontiguousarray(result[:, :count], dtype=np.float32)


def audio_packets(stream, samples):
    for offset in range(0, samples.shape[1], 1024):
        frame = av.AudioFrame.from_ndarray(np.ascontiguousarray(samples[:, offset:offset + 1024]), format="fltp", layout="stereo")
        frame.sample_rate = RATE
        frame.pts = offset
        frame.time_base = Fraction(1, RATE)
        yield from stream.encode(frame)
    yield from stream.encode(None)


def encode_audio(container, stream, samples):
    for packet in audio_packets(stream, samples):
        container.mux(packet)


def audio_clip(source, output, start, seconds):
    # A shot's rounded inference tail may need a few silent samples. The final
    # soundtrack is independently rebuilt from the original continuous master.
    samples = audio_samples(source, start, seconds, pad=True)
    with av.open(str(output), "w", format="wav") as dest:
        stream = dest.add_stream("pcm_s16le", rate=RATE)
        stream.layout = "stereo"
        encode_audio(dest, stream, samples)


def prepare_image(source, output, width, height, background_mode="source"):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if background_mode == "alpha_neutral":
            if "A" not in image.getbands() or image.getchannel("A").getextrema() == (255, 255):
                raise ValueError("alpha_neutral requires a transparent PNG subject cutout")
            foreground = image.convert("RGBA")
            neutral = Image.new("RGBA", foreground.size, (127, 127, 127, 255))
            neutral.alpha_composite(foreground)
            image = neutral.convert("RGB")
        elif background_mode == "source":
            image = image.convert("RGB")
        else:
            raise ValueError("Unknown reference background mode")
        fitted = ImageOps.contain(image, (width, height), Image.Resampling.LANCZOS)
        canvas_color = (127, 127, 127) if background_mode == "alpha_neutral" else (0, 0, 0)
        canvas = Image.new("RGB", (width, height), canvas_color)
        canvas.paste(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
        canvas.save(output)


def assemble(manifest, output):
    with open(manifest, encoding="utf-8") as source:
        plan = json.load(source)
    fps, width, height = plan["fps"], plan["width"], plan["height"]
    total = sum(shot["keep_frames"] for shot in plan["segments"])
    if not 1 <= len(plan["segments"]) <= 120 or total / fps > 180.125:
        raise ValueError("Composition exceeds resource limits")
    soundtrack = None
    if plan.get("audio_path"):
        # Admission validates the requested music length. Only the final output
        # frame's rounding tail can be padded; music is never looped or stretched.
        soundtrack = audio_samples(plan["audio_path"], plan.get("audio_start_seconds", 0), total / fps, pad=True)
    elif plan.get("audio"):
        soundtrack = np.concatenate([audio_samples(shot["path"], 0, shot["keep_frames"] / fps, pad=True)
                                     for shot in plan["segments"]], axis=1)
    with av.open(str(output), "w", format="mp4", options={"movflags": "+faststart"}) as dest:
        stream = dest.add_stream("libx264", rate=fps)
        stream.width, stream.height, stream.pix_fmt = width, height, "yuv420p"
        stream.options = {"crf": "18", "preset": "fast"}
        audio_stream = dest.add_stream("aac", rate=RATE) if soundtrack is not None else None
        if audio_stream is not None:
            audio_stream.layout = "stereo"
            audio_stream.bit_rate = 192000
        packets = iter(audio_packets(audio_stream, soundtrack)) if soundtrack is not None else iter(())
        next_audio = next(packets, None)
        written = 0
        for shot in plan["segments"]:
            count = 0
            with av.open(shot["path"]) as source:
                for frame in source.decode(video=0):
                    if count == shot["keep_frames"]:
                        break
                    if (frame.width, frame.height) != (width, height):
                        raise ValueError("Shot dimensions changed")
                    frame.pts, frame.time_base = written, Fraction(1, fps)
                    frame.pict_type = av.video.frame.PictureType.NONE
                    for packet in stream.encode(frame):
                        dest.mux(packet)
                    written += 1
                    count += 1
                    # Interleave as the timeline advances, instead of buffering
                    # all video or placing the entire soundtrack at the end.
                    while next_audio is not None and float(next_audio.pts * next_audio.time_base) <= written / fps:
                        dest.mux(next_audio)
                        next_audio = next(packets, None)
            if count != shot["keep_frames"]:
                raise ValueError("Incomplete shot: refusing freeze-frame or loop padding")
        for packet in stream.encode(None):
            dest.mux(packet)
        while next_audio is not None:
            dest.mux(next_audio)
            next_audio = next(packets, None)
    print(json.dumps({"assembled_frames": written, "seconds": written / fps}))


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "audio":
        audio_clip(args[0], args[1], float(args[2]), float(args[3]))
    elif mode == "image":
        prepare_image(args[0], args[1], int(args[2]), int(args[3]), args[4] if len(args) > 4 else "source")
    elif mode == "assemble":
        assemble(*args)
    else:
        raise SystemExit("Unknown operation")
