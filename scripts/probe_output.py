"""Report video-stream timing separately from audio/container timing, without GPU."""
import json
import sys
import av


def probe(path):
    with av.open(path) as container:
        stream = container.streams.video[0]
        frames = stream.frames or None
        fps = float(stream.average_rate) if stream.average_rate else None
        duration = float(stream.duration * stream.time_base) if stream.duration is not None else None
        return {"verified": True, "measurement": "container_metadata", "frames": frames,
                "fps": fps, "video_seconds": duration,
                "container_seconds": container.duration / av.time_base if container.duration is not None else None}


if __name__ == "__main__":
    print(json.dumps(probe(sys.argv[1])))
