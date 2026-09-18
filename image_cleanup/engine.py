"""Conservative local detection and masked inpainting."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .models import ensure_models, model_dir

_WATERMARK_TEXT = re.compile(
    r"(?:\bwatermark\b|\bcopyright\b|©|\bwww\.|https?://|@[a-z0-9_.-]{2,})",
    re.IGNORECASE,
)


@dataclass
class Result:
    cleaned: Image.Image
    mask: Image.Image
    boxes: list[list[int]]
    warnings: list[str]
    confidence: float | None
    detected: bool


def load_image(path: Path) -> Image.Image:
    with Image.open(path) as opened:
        opened.load()
        if opened.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Supported formats are JPEG, PNG and WebP")
        return ImageOps.exif_transpose(opened).convert("RGB")


def save_clean_image(image: Image.Image, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.partial")
    suffix = destination.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        image.convert("RGB").save(temporary, format="JPEG", quality=95, subsampling=0)
    elif suffix == ".png":
        image.save(temporary, format="PNG")
    elif suffix == ".webp":
        image.save(temporary, format="WEBP", quality=95)
    else:
        raise ValueError(f"Unsupported output extension: {suffix}")
    temporary.replace(destination)


@lru_cache(maxsize=2)
def _reader(*, gpu: bool):
    ensure_models(ocr=True)
    import easyocr

    root = model_dir() / "easyocr"
    return easyocr.Reader(
        ["en"],
        gpu=gpu,
        model_storage_directory=str(root),
        user_network_directory=str(root),
        download_enabled=False,
        verbose=False,
    )


def detect_text(image: Image.Image, *, gpu: bool = False) -> list[tuple[list[int], float]]:
    matches: list[tuple[list[int], float]] = []
    for polygon, text, confidence in _reader(gpu=gpu).readtext(
        np.asarray(image), detail=1, paragraph=False
    ):
        if not _WATERMARK_TEXT.search(str(text)):
            continue
        points = np.asarray(polygon, dtype=np.float64)
        x0, y0 = np.floor(points.min(axis=0)).astype(int)
        x1, y1 = np.ceil(points.max(axis=0)).astype(int)
        matches.append(([int(x0), int(y0), int(x1 - x0), int(y1 - y0)], float(confidence)))
    return matches


def _validated_box(box: list[int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    if len(box) != 4:
        raise ValueError("A box needs x,y,width,height")
    x, y, width, height = (int(value) for value in box)
    if width <= 0 or height <= 0:
        raise ValueError("Box width and height must be positive")
    if x < 0 or y < 0 or x + width > size[0] or y + height > size[1]:
        raise ValueError("Box must fit inside the image")
    return x, y, width, height


def _mask_for(
    size: tuple[int, int], boxes: list[list[int]], supplied: Path | None
) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        x, y, width, height = _validated_box(box, size)
        draw.rectangle((x, y, x + width - 1, y + height - 1), fill=255)
    if supplied is not None:
        with Image.open(supplied) as opened:
            if opened.size != size:
                raise ValueError("Manual mask dimensions must match the oriented image")
            supplied_mask = opened.convert("L")
        mask = Image.fromarray(
            np.maximum(np.asarray(mask), np.asarray(supplied_mask)).astype(np.uint8), mode="L"
        )
    return mask


@lru_cache(maxsize=2)
def _lama_model(gpu: bool):
    ensure_models(lama=True)
    os.environ["LAMA_MODEL"] = str(model_dir() / "big-lama.pt")
    import torch
    from simple_lama_inpainting import SimpleLama

    device = torch.device("cuda" if gpu and torch.cuda.is_available() else "cpu")
    return SimpleLama(device=device)


def _inpaint(image: Image.Image, mask: Image.Image, method: str, gpu: bool) -> Image.Image:
    mask_array = np.asarray(mask)
    if not np.any(mask_array):
        return image.copy()
    if method == "telea":
        bgr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        repaired = cv2.inpaint(bgr, mask_array, 3, cv2.INPAINT_TELEA)
        candidate = Image.fromarray(cv2.cvtColor(repaired, cv2.COLOR_BGR2RGB))
    elif method == "lama":
        candidate = _lama_model(gpu)(image, mask).convert("RGB")
    else:
        raise ValueError(f"Unknown inpaint method: {method}")
    return Image.composite(candidate, image, mask)


def process(
    image: Image.Image,
    *,
    detector: str = "ocr",
    method: str = "lama",
    manual_boxes: list[list[int]] | None = None,
    supplied_mask: Path | None = None,
    gpu: bool = False,
) -> Result:
    if detector not in {"ocr", "none"}:
        raise ValueError(f"Unknown detector: {detector}")
    manual_boxes = manual_boxes or []
    detections = detect_text(image, gpu=gpu) if detector == "ocr" else []
    auto_boxes = []
    for box, _confidence in detections:
        x, y, width, height = box
        x0, y0 = max(0, x - 3), max(0, y - 3)
        x1, y1 = min(image.width, x + width + 3), min(image.height, y + height + 3)
        if x1 > x0 and y1 > y0:
            auto_boxes.append([x0, y0, x1 - x0, y1 - y0])
    boxes = auto_boxes + manual_boxes
    mask = _mask_for(image.size, boxes, supplied_mask)
    cleaned = _inpaint(image, mask, method, gpu)
    mask_pixels = int(np.count_nonzero(np.asarray(mask)))
    warnings: list[str] = []
    confidence = min((value for _box, value in detections), default=None)
    if manual_boxes or supplied_mask is not None:
        warnings.append("manual_region_requires_review")
    if not mask_pixels:
        warnings.append("empty_mask")
    if mask_pixels / (image.width * image.height) > 0.06:
        warnings.append("large_mask")
    if confidence is not None and confidence < 0.6:
        warnings.append("low_detection_confidence")
    if mask_pixels and detector == "ocr" and detect_text(cleaned, gpu=gpu):
        warnings.append("possible_residual")
    return Result(cleaned, mask, boxes, warnings, confidence, bool(mask_pixels))


def save_comparison(
    original: Image.Image, mask: Image.Image, cleaned: Image.Image, destination: Path
) -> None:
    panel_size = (600, 500)
    preview = Image.new("RGB", (panel_size[0] * 3, panel_size[1] + 34), "white")
    image = ImageOps.contain(original, panel_size)
    mask_overlay = original.copy()
    tint = Image.new("RGB", original.size, (238, 48, 96))
    mask_overlay.paste(Image.blend(original, tint, 0.65), mask=mask)
    for index, (label, panel) in enumerate(
        (("Original", image), ("Mask", mask_overlay), ("Cleaned", cleaned))
    ):
        fitted = ImageOps.contain(panel, panel_size)
        x = index * panel_size[0] + (panel_size[0] - fitted.width) // 2
        y = 34 + (panel_size[1] - fitted.height) // 2
        preview.paste(fitted, (x, y))
        ImageDraw.Draw(preview).text((index * panel_size[0] + 12, 9), label, fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    preview.save(destination, format="JPEG", quality=88)
