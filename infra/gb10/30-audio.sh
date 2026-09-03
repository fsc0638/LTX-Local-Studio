#!/usr/bin/env bash
# audio venv: librosa (beat grid, sections, energy) and stable-ts (lyric forced alignment). Used by MA/LS.
# WhisperX is deliberately not used: its CTranslate2 aarch64 wheels have no CUDA.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
gb10_ensure_root
gb10_detect_torch
gb10_hf_env

sudo apt-get install -y ffmpeg libsndfile1
venv="$(gb10_make_venv audio)"
gb10_pip_torch "${venv}"
"${venv}/bin/pip" install --upgrade librosa soundfile stable-ts numpy

"${venv}/bin/python" - <<'PY'
import os, numpy as np, torch, librosa, stable_whisper

assert torch.cuda.is_available(), "CUDA not available inside the audio venv"
model = stable_whisper.load_model("large-v3", device="cuda", download_root=os.path.join(os.environ["STUDIO_MODELS"], "whisper"))
print(f"whisper large-v3: ok, peak {torch.cuda.max_memory_allocated() / 1e9:.1f} GB")
audio, lyrics = os.environ.get("STUDIO_TEST_AUDIO"), os.environ.get("STUDIO_TEST_LYRICS")
if not audio:
    print("Set STUDIO_TEST_AUDIO=/path/song.wav [STUDIO_TEST_LYRICS=/path/lyrics.txt STUDIO_TEST_LANG=zh] to run the beat/alignment check")
else:
    y, sr = librosa.load(audio, sr=None, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    times = librosa.frames_to_time(beats, sr=sr)
    print(f"tempo {float(np.atleast_1d(tempo)[0]):.1f} BPM, {len(times)} beats, first {np.round(times[:8], 3).tolist()}")
    if lyrics:
        result = model.align(audio, open(lyrics, encoding="utf-8").read(), language=os.environ.get("STUDIO_TEST_LANG", "zh"))
        out = os.path.splitext(audio)[0] + ".aligned.srt"
        result.to_srt_vtt(out, word_level=True)
        print("word-level alignment ->", out)
PY
gb10_log "audio venv ready: ${venv}"
