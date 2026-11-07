"""Model files for lyrics transcription and person mattes, downloaded anonymously.

Fetches the public model files with Python's standard HTTP client (plain GET requests, no extra
headers) instead of the libraries' own downloaders, and checks every file against a pinned SHA-256.

    whisper_dir()      mlx-community/whisper-large-v3-turbo (about 1.6 GB) from huggingface.co, kept in
                       ~/.cache/music-video/models/ and shared by all projects
    human_seg_path()   rembg's u2net_human_seg.onnx (about 176 MB) from github.com, put where rembg
                       looks for it first, so rembg loads it and never runs its own downloader
"""
import hashlib
import urllib.request
from pathlib import Path

CACHE = Path.home() / ".cache" / "music-video" / "models"

WHISPER_REPO = "mlx-community/whisper-large-v3-turbo"
WHISPER_REV = "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb"
WHISPER_FILES = {
    "config.json": "b34fc29e4e11e0a25e812775dd67f4dd16fc2c8eb43d28ae25ff7d660ecb6379",
    "weights.safetensors": "951ed3fc1203e6a62467abb2144a96ce7eafca8fa77e3704fdb8635ff3e7f8a6",
}

HUMAN_SEG_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
HUMAN_SEG_SHA256 = "01eb6a29a5c4d8edb30b56adad9bb3a2a0535338e480724a213e0acfd2d1c73c"


def fetch(url, out, sha256):
    """Download url to out unless it is already there; keep it only if its SHA-256 matches."""
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    h = hashlib.sha256()
    print(f"downloading {url}", flush=True)
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            h.update(chunk)
            f.write(chunk)
    if h.hexdigest() != sha256:
        tmp.unlink()
        raise SystemExit(f"checksum mismatch for {url}; the download was deleted")
    tmp.replace(out)
    return out


def whisper_dir():
    """Local folder holding the Whisper model; pass it to mlx_whisper.transcribe."""
    d = CACHE / WHISPER_REPO.replace("/", "--") / WHISPER_REV
    for name, sha in WHISPER_FILES.items():
        fetch(f"https://huggingface.co/{WHISPER_REPO}/resolve/{WHISPER_REV}/{name}", d / name, sha)
    return d


def human_seg_path():
    """u2net_human_seg.onnx in rembg's own model folder; then new_session("u2net_human_seg") loads it."""
    from rembg.sessions.u2net_human_seg import U2netHumanSegSession as S
    folder = S.model_dir() if hasattr(S, "model_dir") else S.u2net_home()  # older rembg: one flat folder
    out = Path(folder) / "u2net_human_seg.onnx"
    old = Path(S.legacy_home()) / out.name if hasattr(S, "legacy_home") else out
    return old if old.exists() and not out.exists() else fetch(HUMAN_SEG_URL, out, HUMAN_SEG_SHA256)


if __name__ == "__main__":
    print(whisper_dir())
    print(human_seg_path())
