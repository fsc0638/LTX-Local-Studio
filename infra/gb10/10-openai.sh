#!/usr/bin/env bash
# Verify OpenAI access for the LLM/VLM agents: one structured-output call, one vision call.
# The key lives in a 0600 file created by a person; this script never prints or copies it.
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

key_file="${STUDIO_OPENAI_KEY_FILE:-${STUDIO_SECRETS}/openai}"
install -d -m 700 "${STUDIO_SECRETS}"
if [[ ! -f "${key_file}" ]]; then
  cat >&2 <<MSG
Missing ${key_file}. Create it yourself, then rerun:
  umask 077 && printf '%s' 'sk-...' > ${key_file}
MSG
  exit 1
fi
[[ "$(stat -c %a "${key_file}")" == "600" ]] || gb10_die "${key_file} must be mode 600"

STUDIO_OPENAI_KEY_FILE="${key_file}" \
STUDIO_OPENAI_MODEL="${STUDIO_OPENAI_MODEL:-gpt-5.6}" \
STUDIO_OPENAI_EFFORT="${STUDIO_OPENAI_EFFORT:-high}" \
python3 - <<'PY'
import base64, json, os, struct, sys, urllib.error, urllib.request, zlib

key = open(os.environ["STUDIO_OPENAI_KEY_FILE"], encoding="utf-8").read().strip()
model, effort = os.environ["STUDIO_OPENAI_MODEL"], os.environ["STUDIO_OPENAI_EFFORT"]


def call(body):
    req = urllib.request.Request("https://api.openai.com/v1/responses", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code}: {exc.read().decode()[:600]}")


def text_of(resp):
    return "".join(part.get("text", "") for item in resp.get("output", []) if item.get("type") == "message"
                   for part in item.get("content", []))


def solid_png(width, height, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


schema = {"type": "object", "properties": {"ok": {"type": "boolean"}, "model_seen": {"type": "string"}},
          "required": ["ok", "model_seen"], "additionalProperties": False}
llm = call({"model": model, "reasoning": {"effort": effort},
            "input": "Reply with ok=true and model_seen set to the model name you are running as.",
            "text": {"format": {"type": "json_schema", "name": "probe", "schema": schema, "strict": True}}})
parsed = json.loads(text_of(llm))
print("LLM structured output:", parsed, "| usage:", llm.get("usage"))
assert parsed.get("ok") is True

image = base64.b64encode(solid_png(16, 16, (220, 20, 20))).decode()
vlm = call({"model": model, "reasoning": {"effort": effort},
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": "What single color fills this image? Answer with one lowercase word."},
                {"type": "input_image", "image_url": f"data:image/png;base64,{image}"}]}]})
answer = text_of(vlm).strip().lower()
print("VLM answer:", answer, "| usage:", vlm.get("usage"))
assert "red" in answer, "vision probe did not see a red image"
print(f"OpenAI OK: model={model} effort={effort}")
PY
