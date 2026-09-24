# Motion Canvas workspace

Motion Canvas is exposed from the Sandbox model/tool selector, but it is a deterministic
TypeScript animation renderer rather than an AI model. The UI labels it accordingly.

## Phase 1: interactive project builder

The Sandbox workspace collects:

- project name, opening title, narration/visual script and language;
- canvas width, height, frame rate, duration and visual theme;
- optional caption and lip-sync tracks;
- an uploaded voice-over and character/key-visual asset;
- host audio analysis (Whisper/stable-ts/librosa) and links to installed image adapters.

`Download Motion Canvas project` creates a ZIP containing a standalone Motion Canvas 3.17.2
project, selected private assets, a project manifest, TypeScript scene, FFmpeg exporter config
and setup instructions. The user opens that project in Motion Canvas Editor and starts the
render there. Asset bytes are read through the authenticated same-origin media endpoint and are
only copied into the user-requested download.

The generated manifest is `ltx-motion-canvas-v1`. It records tool results and source asset IDs,
but contains no credentials, host paths or executable input supplied by a model.

## Phase 2: background rendering

Motion Canvas does not currently publish a documented headless rendering CLI. A one-click LTX
job therefore needs a separately reviewed loopback renderer that controls a managed browser,
uses fixed project templates, validates every input, renders to a private work directory and
passes the result through the existing MP4 checks before publication.

Phase 2 must not execute arbitrary TSX from a request. It also needs explicit deployment approval
before enabling a new service or systemd unit. Until then, the Sandbox states clearly that the
Editor render step is interactive.
