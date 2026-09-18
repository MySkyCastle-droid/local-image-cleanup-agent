"""Pinned, local model bootstrap. Processing never downloads models."""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path

LAMA_URL = (
    "https://huggingface.co/JosephCatrambone/big-lama-torchscript/resolve/"
    "7dfbdc6dc27602d370909e8688f8f84404a1f995/lama.pt"
)
EXPECTED = {
    "big-lama.pt": "79ed9fa18680ca19a269eb88fc4f708fb6580197b2220a51d3e000eb0ffdf33b",
    "craft_mlt_25k.pth": "4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17",
    "english_g2.pth": "e2272681d9d67a04e2dff396b6e95077bc19001f8f6d3593c307b9852e1c29e8",
}


def model_dir() -> Path:
    configured = os.environ.get("LOCAL_IMAGE_CLEANUP_MODELS")
    if configured:
        return Path(configured).expanduser().resolve()
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".cache")))
    return base / "LocalImageCleanupAgent" / "models"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(path: Path, expected: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise RuntimeError(f"Missing or invalid model: {path.name}; run prepare-models")


def ensure_models(*, ocr: bool = False, lama: bool = False) -> None:
    root = model_dir()
    if ocr:
        for name in ("craft_mlt_25k.pth", "english_g2.pth"):
            _check(root / "easyocr" / name, EXPECTED[name])
    if lama:
        _check(root / "big-lama.pt", EXPECTED["big-lama.pt"])


def prepare_models() -> None:
    root = model_dir()
    root.mkdir(parents=True, exist_ok=True)
    lama = root / "big-lama.pt"
    if not lama.is_file() or sha256(lama) != EXPECTED["big-lama.pt"]:
        temporary = root / "big-lama.pt.partial"
        request = urllib.request.Request(LAMA_URL, headers={"User-Agent": "local-image-cleanup-agent/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as target:
            for block in iter(lambda: response.read(1024 * 1024), b""):
                target.write(block)
        _check(temporary, EXPECTED["big-lama.pt"])
        temporary.replace(lama)

    import easyocr

    easyocr.Reader(
        ["en"],
        gpu=False,
        model_storage_directory=str(root / "easyocr"),
        user_network_directory=str(root / "easyocr"),
        download_enabled=True,
        verbose=False,
    )
    ensure_models(ocr=True, lama=True)
