# LTX Local Studio

A local-first web console for securely running LTX-2 and LTX-2.3 video generation on your own GPU.

LTX Local Studio combines a multilingual browser UI, a local job API, and an LTX worker bridge. The current verified configuration targets LTX-2.3 Distilled on NVIDIA GB10 with BF16 and SDPA.

## Features

- Traditional Chinese, English, and Japanese UI
- Text-to-video prompt workflow
- Resolution, frame rate, duration, seed, precision, and memory controls
- Real-time job progress and persistent local output history
- MP4 preview and generated poster frames
- Local-only model weights and outputs
- Environment-based paths for portable GitHub use

## Requirements

- Linux with a supported NVIDIA GPU
- Node.js 22.13 or newer
- Python 3.12 or newer
- A working LTX-2/LTX-2.3 checkout and virtual environment
- LTX-2.3, spatial upscaler, and Gemma model files

## Local setup

1. Install the web dependencies:

   ```bash
   npm install
   ```

2. Copy the environment template:

   ```bash
   cp .env.example .env.local
   ```

3. Set `LTX_REPO_ROOT` and `LTX_PYTHON` in `.env.local`.

4. Start the UI and local inference API:

   ```bash
   npm run dev
   ```

5. Open `http://localhost:3000`.

## Repository safety

This repository intentionally excludes:

- model checkpoints and Hugging Face caches
- generated videos, poster frames, and logs
- `.env.local`, credentials, tokens, and tunnel configuration
- dependencies and build output

Never expose port 8787 directly to the internet. For remote access, place authentication, rate limiting, and a same-origin HTTPS gateway in front of the loopback-only API. See [Remote access architecture](docs/REMOTE_ACCESS.md).

## Project layout

```text
app/                   Multilingual web interface
components/ui/         Styled UI primitives
public/generated/      Local outputs (ignored by Git)
scripts/dev.sh         Local UI + API launcher
scripts/run-ltx-2.3.sh Portable LTX runner
local_backend.py       Loopback-only job API
extract_poster.py      Video poster extraction
docs/                  Architecture documentation
```

## Status

The local text-to-video workflow is functional. Remote authentication and the public HTTPS gateway are the next implementation phase.
