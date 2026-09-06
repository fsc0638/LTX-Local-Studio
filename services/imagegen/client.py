#!/usr/bin/env python3
"""The argv the imagegen adapters return: ask the loopback service for one image.

Runs in ltx-api's own interpreter, so it needs nothing but the standard library. It holds one
POST open for the whole generation (loading Qwen alone can take six minutes) and, on a second
thread, polls the service's progress so the job runner's log sees "NN%" lines and can show them.

Everything it sends is either the validated payload or a path ltx-api resolved and put in the
environment (LTX_IMAGE, LTX_IMAGE_2, LTX_IMAGE_3). Nothing from the request reaches a shell.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

SERVICE = os.environ.get("LTX_IMAGEGEN_SERVICE", "http://127.0.0.1:8792")
TIMEOUT = int(os.environ.get("LTX_IMAGEGEN_TIMEOUT", "1800"))


def main(argv):
    args = dict(zip(argv[1::2], argv[2::2]))
    output = args["--output"]
    references = [os.environ[key] for key in ("LTX_IMAGE", "LTX_IMAGE_2", "LTX_IMAGE_3") if os.environ.get(key)]
    request_id = uuid.uuid4().hex
    payload = {"request_id": request_id, "model": args["--model"], "prompt": args["--prompt"],
               "steps": int(args.get("--steps", "8")), "seed": int(args.get("--seed", "42")),
               "size": args.get("--size", "1024x1024"), "lightning": args.get("--lightning", "1") == "1",
               "references": references, "output": output}
    done = threading.Event()

    def poll():
        last = -1
        while not done.wait(0.5):
            try:
                with urllib.request.urlopen(f"{SERVICE}/progress/{request_id}", timeout=5) as response:
                    state = json.load(response)
            except (OSError, ValueError):
                continue
            if state.get("progress", 0) != last:
                last = state["progress"]
                print(f"{state.get('phase', 'working')} {last}%", flush=True)

    threading.Thread(target=poll, daemon=True).start()
    print("imagegen: contacting service 2%", flush=True)
    request = urllib.request.Request(f"{SERVICE}/generate", data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        done.set()
        print(f"imagegen service refused: HTTP {exc.code} {exc.read().decode()[:300]}", flush=True)
        return 2
    except (OSError, ValueError) as exc:
        done.set()
        print(f"imagegen service unavailable: {exc}", flush=True)
        return 3
    done.set()
    print(f"done 100% ({result.get('model')} {result.get('seconds')}s, loads={result.get('loads')})", flush=True)
    return 0 if os.path.isfile(output) else 4


if __name__ == "__main__":
    sys.exit(main(sys.argv))
