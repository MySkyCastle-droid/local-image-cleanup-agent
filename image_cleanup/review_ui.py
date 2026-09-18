"""Local-only Streamlit QA surface."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import streamlit as st

from image_cleanup.delivery import export_delivery
from image_cleanup.workspace import audit_path, load_report, mark_box, mark_mask, process_batch, set_qa


def _args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(sys.argv[1:])


args = _args()
st.set_page_config(page_title="Image Cleanup QA", layout="wide")
st.title("Image Cleanup QA")
payload = load_report(args.output)
records = payload["records"]
if not records:
    st.info("No processed images")
    st.stop()

counts = payload.get("summary", {})
metrics = st.columns(5)
for column, (label, key) in zip(
    metrics,
    (("Total", "total"), ("Automatic", "completed_auto"),
     ("Approved", "completed_manual"), ("Review", "needs_review"),
     ("Imperfect", "imperfect")),
):
    column.metric(label, counts.get(key, 0))

filter_choice = st.segmented_control(
    "Status", ["All", "Needs review", "Imperfect", "Completed", "Failed"], default="Needs review"
)


def _show(record: dict) -> bool:
    status = record.get("qa_status")
    return (
        filter_choice == "All"
        or (filter_choice == "Needs review" and status == "needs_review")
        or (filter_choice == "Imperfect" and status == "imperfect")
        or (filter_choice == "Completed" and status in {"completed_auto", "completed_manual"})
        or (filter_choice == "Failed" and record.get("processing_status") == "failed")
    )


visible = sorted((record for record in records.values() if _show(record)), key=lambda row: row["source_rel"])
if not visible:
    st.info("No images in this view")
else:
    chosen = st.selectbox(
        "Image", visible, format_func=lambda row: f"{row['id']}  {row['source_rel']}"
    )
    left, right = st.columns([3, 2], gap="large")
    with left:
        tabs = st.tabs(["Comparison", "Original", "Mask", "Cleaned"])
        for tab, key in zip(tabs, ("comparison", "original", "mask", "cleaned")):
            with tab:
                try:
                    artifact = audit_path(args.output, chosen.get("artifacts", {}).get(key, ""))
                except ValueError:
                    artifact = None
                if artifact is not None and artifact.is_file():
                    st.image(str(artifact), width="stretch")
                else:
                    st.warning(f"{key.capitalize()} unavailable")
        st.caption(
            f"{chosen.get('processing_status', 'failed')} / {chosen.get('qa_status', 'needs_review')}"
            f" / {'Automatically judged' if chosen.get('qa_origin') == 'automatic' else 'Human reviewed'}"
        )
        if chosen.get("warnings"):
            st.warning(", ".join(chosen["warnings"]))
        if chosen.get("error_type"):
            st.error(chosen["error_type"])
        if chosen.get("qa_history"):
            with st.expander("QA history"):
                for decision in reversed(chosen["qa_history"]):
                    st.text(f"{decision['at']}  {decision['status']}")
                    if decision.get("note"):
                        st.write(decision["note"])

    with right:
        st.subheader("QA")
        note = st.text_area("Note", key=f"note_{chosen['id']}")
        qa_cols = st.columns(3)
        if qa_cols[0].button("Approve", width="stretch"):
            set_qa(args.output, chosen["id"], "completed_manual", note)
            st.rerun()
        if qa_cols[1].button("Review", width="stretch"):
            set_qa(args.output, chosen["id"], "needs_review", note)
            st.rerun()
        if qa_cols[2].button("Imperfect", width="stretch"):
            set_qa(args.output, chosen["id"], "imperfect", note)
            st.rerun()

        st.subheader("Repair region")
        width, height = int(chosen.get("width") or 0), int(chosen.get("height") or 0)
        if width and height:
            with st.form("box_form"):
                x = st.number_input("X", min_value=0, max_value=width - 1, value=0)
                y = st.number_input("Y", min_value=0, max_value=height - 1, value=0)
                w = st.number_input("Width", min_value=1, max_value=width, value=min(100, width))
                h = st.number_input("Height", min_value=1, max_value=height, value=min(50, height))
                submitted = st.form_submit_button("Add region")
            if submitted:
                try:
                    mark_box(args.output, chosen["id"], [int(x), int(y), int(w), int(h)])
                    process_batch(
                        args.source, args.output, authorized=True, only_id=chosen["id"],
                        detector=chosen.get("detector", "ocr"), method=chosen.get("method", "lama"),
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")
            boxes = chosen.get("manual_boxes", [])
            if boxes:
                selected_box = st.selectbox("Marked regions", boxes, format_func=lambda box: ", ".join(map(str, box)))
                if st.button("Remove region", icon=":material/delete:"):
                    mark_box(args.output, chosen["id"], selected_box, remove=True)
                    process_batch(
                        args.source, args.output, authorized=True, only_id=chosen["id"],
                        detector=chosen.get("detector", "ocr"), method=chosen.get("method", "lama"),
                    )
                    st.rerun()
            uploaded_mask = st.file_uploader("Mask PNG", type=["png"])
            if uploaded_mask is not None and st.button("Apply mask"):
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temporary:
                    temporary.write(uploaded_mask.getvalue())
                    temporary_path = Path(temporary.name)
                try:
                    mark_mask(args.output, chosen["id"], temporary_path)
                    process_batch(
                        args.source, args.output, authorized=True, only_id=chosen["id"],
                        detector=chosen.get("detector", "ocr"), method=chosen.get("method", "lama"),
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"{type(exc).__name__}: {exc}")
                finally:
                    temporary_path.unlink(missing_ok=True)

st.divider()
if st.button("Build client delivery", icon=":material/archive:"):
    try:
        result = export_delivery(args.output)
        st.session_state["delivery"] = str(result)
    except Exception as exc:
        st.error(f"{type(exc).__name__}: {exc}")
if st.session_state.get("delivery"):
    delivery = Path(st.session_state["delivery"])
    if delivery.is_file():
        st.download_button(
            "Download client delivery", delivery.read_bytes(),
            file_name="client_delivery.zip", mime="application/zip",
            icon=":material/download:",
        )
