"""Local shared media storage. No caller-supplied filesystem paths are accepted."""
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from video_settings import image_geometry

ROOT = Path(__file__).resolve().parent
UPLOAD_DIR = Path(os.environ.get("LTX_UPLOAD_DIR", ROOT / "uploads")).resolve()
MAX_UPLOAD = 50 * 1024 * 1024
MAX_LIBRARY = 2 * 1024 * 1024 * 1024
UPLOAD_LOCK = threading.Lock()
FORMATS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "video/mp4": ".mp4",
           "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/mpeg": ".mp3", "audio/flac": ".flac",
           "audio/x-flac": ".flac", "audio/mp4": ".m4a", "audio/ogg": ".ogg"}


def asset_by_id(asset_id):
    if not re.fullmatch(r"[a-f0-9]{32}", asset_id):
        raise ValueError("無效的素材 ID。")
    try:
        asset = json.loads((UPLOAD_DIR / f"{asset_id}.json").read_text())
        asset_path(asset)
        if asset.get("kind") == "image":
            asset.update(image_geometry(asset["width"], asset["height"]))
        return asset
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError("找不到素材，請重新上傳。") from exc


def asset_path(asset):
    filename = asset["filename"]
    if not re.fullmatch(r"[a-f0-9]{32}\.(png|jpg|webp|mp4|wav|mp3|flac|m4a|ogg)", filename):
        raise ValueError("無效的素材檔名。")
    path = UPLOAD_DIR / filename
    if path.is_symlink() or not path.is_file() or path.resolve().parent != UPLOAD_DIR:
        raise ValueError("找不到素材。")
    return path


def list_assets():
    assets = []
    for metadata in UPLOAD_DIR.glob("*.json"):
        try:
            assets.append(asset_by_id(metadata.stem))
        except (ValueError, TypeError):
            continue
    return sorted(assets, key=lambda asset: asset["created_at"], reverse=True)


class MediaHandlerMixin:
    def serve_media(self, path, content_type, name=None):
        if path.is_symlink() or not path.is_file():
            self.send_json(404, {"error": "找不到檔案。"})
            return
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        byte_range = self.headers.get("Range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range)
            try:
                if not match or not any(match.groups()) or size == 0:
                    raise ValueError
                left, right = match.groups()
                if left:
                    start = int(left)
                    end = min(int(right), end) if right else end
                else:
                    suffix = int(right)
                    if suffix <= 0:
                        raise ValueError
                    start = max(0, size - suffix)
                if start > end or start >= size:
                    raise ValueError
            except ValueError:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "private, no-store")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "private, no-store")
        self.send_header("Access-Control-Allow-Origin", self.cors_origin())
        self.send_header("Vary", "Origin")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if parse_qs(urlparse(self.path).query).get("download") == ["1"]:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(name or path.name, safe='')}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as media:
                media.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = media.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def receive_asset(self, python):
        self.close_connection = True
        content_type = self.headers.get("Content-Type", "").split(";")[0].lower()
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length < 1 or length > MAX_UPLOAD:
            self.send_json(413, {"error": "單一檔案需介於 1 byte–50 MiB。"})
            return
        if content_type not in FORMATS:
            self.send_json(415, {"error": "支援 PNG/JPEG/WebP、MP4 及 WAV/MP3/FLAC/M4A/OGG 音樂。"})
            return
        if not UPLOAD_LOCK.acquire(blocking=False):
            self.send_json(409, {"error": "另一個檔案正在上傳，請稍後再試。"})
            return
        temporary = None
        try:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            used = sum(path.stat().st_size for path in UPLOAD_DIR.iterdir() if path.is_file())
            if used + length > MAX_LIBRARY or shutil.disk_usage(UPLOAD_DIR).free < length + 5 * 1024**3:
                self.send_json(507, {"error": "素材庫已達 2 GiB 或主機剩餘空間不足 5 GiB。"})
                return
            asset_id = uuid.uuid4().hex
            filename = asset_id + FORMATS[content_type]
            temporary = UPLOAD_DIR / (asset_id + ".part")
            name = parse_qs(urlparse(self.path).query).get("name", [filename])[0]
            name = re.sub(r"[\x00-\x1f\x7f/\\]", "_", name)[:180] or filename
            # Slow/partial uploads may not hold the shared upload slot indefinitely.
            self.connection.settimeout(30)
            deadline = time.monotonic() + 180
            with temporary.open("xb") as output:
                remaining = length
                while remaining:
                    if time.monotonic() > deadline:
                        raise ValueError("上傳逾時，請重試。")
                    chunk = self.rfile.read(min(256 * 1024, remaining))
                    if not chunk:
                        raise ValueError("檔案未完整上傳。")
                    output.write(chunk)
                    remaining -= len(chunk)
            kind = "audio" if content_type.startswith("audio/") else "video" if content_type == "video/mp4" else "image"
            with temporary.open("rb") as source:
                signature = source.read(16)
            valid_signature = {
                "image/png": signature.startswith(b"\x89PNG\r\n\x1a\n"),
                "image/jpeg": signature.startswith(b"\xff\xd8\xff"),
                "image/webp": signature.startswith(b"RIFF") and signature[8:12] == b"WEBP",
                "video/mp4": signature[4:8] == b"ftyp",
                "audio/wav": signature.startswith(b"RIFF") and signature[8:12] == b"WAVE",
                "audio/x-wav": signature.startswith(b"RIFF") and signature[8:12] == b"WAVE",
                "audio/mpeg": signature.startswith(b"ID3") or (len(signature) >= 2 and signature[0] == 255 and signature[1] & 224 == 224),
                "audio/flac": signature.startswith(b"fLaC"),
                "audio/x-flac": signature.startswith(b"fLaC"),
                "audio/mp4": signature[4:8] == b"ftyp",
                "audio/ogg": signature.startswith(b"OggS"),
            }[content_type]
            if not valid_signature:
                raise ValueError("檔案內容與格式不符。")
            checked = subprocess.run(
                [str(python), str(ROOT / "scripts/validate_media.py"), str(temporary), kind],
                capture_output=True, text=True, timeout=20, check=False,
            )
            if checked.returncode != 0:
                raise ValueError("無法解碼媒體，或尺寸超過 1600 萬像素。")
            asset = {"id": asset_id, "filename": filename, "name": name, "kind": kind,
                     "content_type": content_type, "size_bytes": length, "created_at": time.time(),
                     "owner_id": getattr(self, "principal", {}).get("id"),
                     "url": f"/api/assets/{asset_id}/file", **json.loads(checked.stdout)}
            if kind == "image":
                asset.update(image_geometry(asset["width"], asset["height"]))
            temporary.rename(UPLOAD_DIR / filename)
            (UPLOAD_DIR / f"{asset_id}.json").write_text(json.dumps(asset, ensure_ascii=False), encoding="utf-8")
            response = {**asset, "url": f"/api/v1/assets/{asset_id}/file"} if urlparse(self.path).path.startswith("/api/v1/") else asset
            self.send_json(201, response)
        except (ValueError, OSError, subprocess.TimeoutExpired):
            self.send_json(400, {"error": "上傳失敗：請確認檔案格式、尺寸與網路連線後重試。"})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            UPLOAD_LOCK.release()
