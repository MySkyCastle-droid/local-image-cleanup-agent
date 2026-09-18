"""Durable batch state, review decisions, and local audit artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from .engine import load_image, process, save_clean_image, save_comparison
from .models import sha256

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}
QA_STATUSES = {"completed_manual", "needs_review", "imperfect"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def item_id(relative: str) -> str:
    return hashlib.sha256(relative.encode("utf-8")).hexdigest()[:16]


def load_report(output: Path) -> dict[str, Any]:
    path = output / "report.json"
    if not path.is_file():
        return {"schema_version": 1, "records": {}, "generated_at": None}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or not isinstance(payload.get("records"), dict):
        raise ValueError("Unsupported report format")
    return payload


def audit_path(output: Path, relative: str) -> Path:
    """Resolve a report artifact without allowing it outside the local audit folder."""
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Invalid audit artifact path")
    root = output.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ValueError("Audit artifact escapes output folder")
    return target


def summary(records: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {
        "total": len(records),
        "completed_auto": 0,
        "completed_manual": 0,
        "needs_review": 0,
        "imperfect": 0,
        "failed": 0,
    }
    for record in records.values():
        status = record.get("qa_status", "needs_review")
        if status in counts:
            counts[status] += 1
        if record.get("processing_status") in {"failed", "missing_source"}:
            counts["failed"] += 1
    return counts


def write_report(output: Path, payload: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    payload["generated_at"] = _now()
    payload["summary"] = summary(payload["records"])
    temporary = output / ".report.json.partial"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output / "report.json")
    fields = (
        "id", "source_rel", "source_sha256", "processing_status", "qa_status",
        "qa_origin", "warnings", "confidence", "original", "mask", "cleaned", "comparison",
    )
    csv_temporary = output / ".report.csv.partial"
    with csv_temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in sorted(payload["records"].values(), key=lambda value: value["source_rel"]):
            artifacts = record.get("artifacts", {})
            writer.writerow({
                "id": record["id"],
                "source_rel": record["source_rel"],
                "source_sha256": record.get("source_sha256", ""),
                "processing_status": record.get("processing_status", ""),
                "qa_status": record.get("qa_status", ""),
                "qa_origin": record.get("qa_origin", ""),
                "warnings": ";".join(record.get("warnings", [])),
                "confidence": "" if record.get("confidence") is None else record["confidence"],
                **{name: artifacts.get(name, "") for name in ("original", "mask", "cleaned", "comparison")},
            })
    csv_temporary.replace(output / "report.csv")


def _source_files(source: Path) -> list[Path]:
    return sorted(
        (
            path for path in source.rglob("*")
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in SUPPORTED
            and source.resolve() in path.resolve().parents
        ),
        key=lambda path: path.relative_to(source).as_posix().casefold(),
    )


def _paths(identifier: str, suffix: str) -> dict[str, str]:
    return {
        "original": f"audit/originals/{identifier}{suffix}",
        "mask": f"audit/masks/{identifier}.png",
        "cleaned": f"audit/cleaned/{identifier}{suffix}",
        "comparison": f"audit/comparisons/{identifier}.jpg",
    }


def process_batch(
    source: Path,
    output: Path,
    *,
    authorized: bool,
    detector: str = "ocr",
    method: str = "lama",
    gpu: bool = False,
    only_id: str | None = None,
    max_new: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if not authorized:
        raise ValueError("Confirm authorization with --authorized")
    if max_new is not None and max_new < 0:
        raise ValueError("--max-new must be nonnegative")
    source, output = source.resolve(), output.resolve()
    if not source.is_dir():
        raise FileNotFoundError("Source folder does not exist")
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Source and output folders must not overlap")
    paths = _source_files(source)
    payload = load_report(output)
    if not paths and not payload["records"]:
        raise ValueError("No supported images found")
    count = 0
    seen_ids: set[str] = set()
    for source_path in paths:
        relative = source_path.relative_to(source).as_posix()
        identifier = item_id(relative)
        seen_ids.add(identifier)
        if only_id is not None and identifier != only_id:
            continue
        current = payload["records"].get(identifier, {})
        digest = sha256(source_path)
        artifacts = _paths(identifier, source_path.suffix.lower())
        same_input = current.get("source_sha256") == digest
        same_options = current.get("detector") == detector and current.get("method") == method
        same_marks = current.get("processed_marks_revision") == current.get("marks_revision", 0)
        present = all(audit_path(output, path).is_file() for path in artifacts.values())
        if same_input and same_options and same_marks and present and not force:
            continue
        if max_new is not None and count >= max_new:
            break
        record: dict[str, Any] = {
            "id": identifier,
            "source_rel": relative,
            "source_sha256": digest,
            "detector": detector,
            "method": method,
            "manual_boxes": current.get("manual_boxes", []),
            "manual_mask": current.get("manual_mask"),
            "marks_revision": current.get("marks_revision", 0),
            "processed_marks_revision": current.get("marks_revision", 0),
            "manual_qa": current.get("manual_qa"),
            "qa_history": current.get("qa_history", []),
            "artifacts": artifacts,
            "warnings": [],
            "qa_status": "needs_review",
            "qa_origin": "automatic",
            "processing_status": "failed",
            "updated_at": _now(),
        }
        try:
            image = load_image(source_path)
            record["width"], record["height"] = image.size
            supplied = audit_path(output, record["manual_mask"]) if record["manual_mask"] else None
            result = process(
                image, detector=detector, method=method,
                manual_boxes=record["manual_boxes"], supplied_mask=supplied, gpu=gpu,
            )
            for path in artifacts.values():
                (output / path).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, output / artifacts["original"])
            result.mask.save(output / artifacts["mask"], format="PNG")
            cleaned_for_file = result.cleaned
            if source_path.suffix.lower() in {".png", ".webp"}:
                with Image.open(source_path) as opened:
                    oriented = ImageOps.exif_transpose(opened)
                    if "A" in oriented.getbands():
                        cleaned_for_file = result.cleaned.convert("RGBA")
                        cleaned_for_file.putalpha(oriented.getchannel("A"))
            save_clean_image(cleaned_for_file, output / artifacts["cleaned"])
            save_comparison(image, result.mask, result.cleaned, output / artifacts["comparison"])
            record["processing_status"] = "cleaned" if result.detected else "no_change"
            record["warnings"] = result.warnings
            record["confidence"] = result.confidence
            record["mask_pixels"] = int(np.count_nonzero(result.mask))
            record["boxes"] = result.boxes
            if result.warnings or (current.get("manual_qa") and (force or not same_input or not same_marks)):
                record["qa_status"] = "needs_review"
            elif current.get("manual_qa") and same_input:
                record["qa_status"] = current["manual_qa"]["status"]
                record["qa_origin"] = "manual"
            else:
                record["qa_status"] = "completed_auto"
        except Exception as exc:
            record["warnings"] = ["processing_failed"]
            record["error_type"] = type(exc).__name__
        payload["records"][identifier] = record
        write_report(output, payload)
        count += 1
    if only_id is None:
        for identifier, record in payload["records"].items():
            if identifier not in seen_ids and record.get("processing_status") != "missing_source":
                record["processing_status"] = "missing_source"
                record["qa_status"] = "needs_review"
                record["qa_origin"] = "automatic"
                record["warnings"] = ["missing_source"]
    if only_id is not None and only_id not in seen_ids:
        raise KeyError("Image ID not found in source folder")
    write_report(output, payload)
    return payload


def mark_box(output: Path, identifier: str, box: list[int], *, remove: bool = False) -> dict[str, Any]:
    payload = load_report(output)
    record = payload["records"].get(identifier)
    if record is None:
        raise KeyError("Unknown image ID")
    from .engine import _validated_box

    _validated_box(box, (record["width"], record["height"]))
    boxes = record.setdefault("manual_boxes", [])
    if remove:
        boxes.remove(box)
    elif box not in boxes:
        boxes.append(box)
    record["marks_revision"] = int(record.get("marks_revision", 0)) + 1
    record["qa_status"] = "needs_review"
    record["qa_origin"] = "automatic"
    write_report(output, payload)
    return record


def mark_mask(output: Path, identifier: str, mask_file: Path) -> dict[str, Any]:
    payload = load_report(output)
    record = payload["records"].get(identifier)
    if record is None:
        raise KeyError("Unknown image ID")
    from PIL import Image

    with Image.open(mask_file) as opened:
        if opened.size != (record["width"], record["height"]):
            raise ValueError("Mask dimensions do not match the oriented image")
        mask = opened.convert("L")
    target = f"audit/manual_masks/{identifier}.png"
    (output / target).parent.mkdir(parents=True, exist_ok=True)
    mask.save(output / target, format="PNG")
    record["manual_mask"] = target
    record["marks_revision"] = int(record.get("marks_revision", 0)) + 1
    record["qa_status"] = "needs_review"
    record["qa_origin"] = "automatic"
    write_report(output, payload)
    return record


def set_qa(output: Path, identifier: str, status: str, note: str = "") -> dict[str, Any]:
    if status not in QA_STATUSES:
        raise ValueError("Invalid QA status")
    payload = load_report(output)
    record = payload["records"].get(identifier)
    if record is None:
        raise KeyError("Unknown image ID")
    if record.get("processed_marks_revision") != record.get("marks_revision", 0):
        raise ValueError("Reprocess marked regions before QA")
    if status == "completed_manual" and record.get("processing_status") not in {"cleaned", "no_change"}:
        raise ValueError("Only successfully processed images can be approved")
    decision = {"status": status, "note": note, "at": _now()}
    record.setdefault("qa_history", []).append(decision)
    record["manual_qa"] = decision
    record["qa_status"] = status
    record["qa_origin"] = "manual"
    write_report(output, payload)
    return record
