#!/usr/bin/env python3
"""The argv the post adapter returns: ask the loopback post service to process one take.

Standard library only, in ltx-api's own interpreter. The input take and the mask are private
paths ltx-api resolved and placed in the environment (LTX_POST_INPUT, LTX_POST_MASK); nothing in
the request names a path. Progress is polled so the job log shows "NN%" lines.
"""
import json
import os
import sys
import threading
import urllib.error
import urllib.request
import uuid

SERVICE = os.environ.get("LTX_POST_SERVICE", "http://127.0.0.1:8793")
TIMEOUT = int(os.environ.get("LTX_POST_TIMEOUT", "3600"))


def main(argv):
    args = dict(zip(argv[1::2], argv[2::2]))
    request_id = uuid.uuid4().hex
    payload = {"request_id": request_id, "op": args["--op"], "input": os.environ.get("LTX_POST_INPUT", ""),
               "output": args["--output"], "scale": int(args.get("--scale", "2")),
               "target_fps": float(args.get("--target-fps", "0")) or None}
    if os.environ.get("LTX_POST_MASK"):
        payload["mask"] = os.environ["LTX_POST_MASK"]
    done = threading.Event()

    def poll():
        last = -1
        while not done.wait(1.0):
            try:
                with urllib.request.urlopen(f"{SERVICE}/progress/{request_id}", timeout=5) as response:
                    state = json.load(response)
            except (OSError, ValueError):
                continue
            if state.get("progress", 0) != last:
                last = state["progress"]
                print(f"{state.get('phase', 'working')} {last}%", flush=True)

    threading.Thread(target=poll, daemon=True).start()
    print("post: contacting service 2%", flush=True)
    request = urllib.request.Request(f"{SERVICE}/process", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        done.set()
        print(f"post service refused: HTTP {exc.code} {exc.read().decode()[:300]}", flush=True)
        return 2
    except (OSError, ValueError) as exc:
        done.set()
        print(f"post service unavailable: {exc}", flush=True)
        return 3
    done.set()
    print(f"done 100% ({result.get('op')} {result.get('seconds')}s)", flush=True)
    return 0 if os.path.isfile(args["--output"]) else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
