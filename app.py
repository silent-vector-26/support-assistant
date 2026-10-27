"""Streamlit UI for the Field Technician Copilot demo."""

from __future__ import annotations

import os

import streamlit as st

from fieldtech_assistant import (
    VisionNotConfigured,
    analyze_image,
    build_guidance,
    build_service_report,
    load_sources,
    lookup_mock_asset,
    new_case,
)


def _invalidate_report_review() -> None:
    st.session_state.report_reviewed = False


def _reconcile_report(replace_edits: bool) -> None:
    report = build_service_report(st.session_state.case)
    if replace_edits:
        st.session_state.report_editor = report
    st.session_state.report_source = report
    st.session_state.report_reviewed = False


st.set_page_config(page_title="Field Technician Copilot", page_icon="🧰", layout="wide")
st.title("🧰 Field Technician Copilot")
st.caption(
    "A simulated HVAC service assistant. Guidance is grounded in the bundled demo documents; "
    "the technician verifies observations and reviews every draft."
)

try:
    sources = load_sources()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

if "case" not in st.session_state:
    st.session_state.case = None
if "image_bytes" not in st.session_state:
    st.session_state.image_bytes = None
if "guidance" not in st.session_state:
    st.session_state.guidance = None
if "report_reviewed" not in st.session_state:
    st.session_state.report_reviewed = False

with st.sidebar:
    st.header("Service case")
    with st.form("new_case_form"):
        asset_id = st.text_input("Equipment ID", value="HVAC-RTU-104")
        symptom = st.text_area(
            "Reported symptom",
            value="Rooftop unit shows fault F07 repeatedly during startup.",
            help="Use simulated equipment and case details only.",
        )
        photo = st.file_uploader("Equipment / fault-display photo (optional)", type=["png", "jpg", "jpeg"])
        create_case = st.form_submit_button("Start / update case", type="primary")
    if create_case:
        if not symptom.strip():
            st.error("Enter the reported symptom before starting a case.")
        else:
            st.session_state.case = new_case(asset_id, symptom)
            st.session_state.image_bytes = photo.getvalue() if photo else None
            st.session_state.guidance = None
            st.session_state.report_reviewed = False
            for key in ("report_editor", "report_source", "report_last_evidence"):
                st.session_state.pop(key, None)
            st.session_state[f"confirm_{st.session_state.case['case_id']}"] = False
            st.success(f"Case {st.session_state.case['case_id']} is ready.")

    if st.session_state.case:
        st.divider()
        st.subheader("Mock asset history")
        if st.button("Look up mock asset history"):
            asset = lookup_mock_asset(st.session_state.case["asset_id"])
            if asset is None:
                st.warning("No mock asset record exists for this equipment ID.")
            else:
                st.session_state.mock_asset = asset
        mock_asset = st.session_state.get("mock_asset")
        if mock_asset and mock_asset["asset_id"] == st.session_state.case["asset_id"].upper():
            st.caption(f"**{mock_asset['equipment']}** · synthetic demo records")
            for event in mock_asset["history"]:
                st.write(f"- {event}")

case = st.session_state.case
if not case:
    st.info("Start the simulated HVAC service case from the sidebar to begin.")
    st.stop()

st.subheader(f"Case {case['case_id']} · {case['asset_id'] or 'Equipment ID not provided'}")
st.write(f"**Reported symptom:** {case['symptom']}")
st.warning("Demo only. Do not use this app to direct real repairs or replace approved safety procedures.")

intake_col, report_col = st.columns([1.25, 1])
with intake_col:
    st.markdown("### Inspect and investigate")
    if st.session_state.image_bytes:
        st.image(st.session_state.image_bytes, caption="Technician-supplied image — visual clues are not confirmed facts.")
        if st.button("Extract tentative text clues with Azure AI Vision"):
            with st.spinner("Reading visible text..."):
                try:
                    clues = analyze_image(
                        st.session_state.image_bytes,
                        os.getenv("AZURE_VISION_ENDPOINT", ""),
                        os.getenv("AZURE_VISION_KEY", ""),
                    )
                    case["image_clues"] = clues
                    if clues:
                        st.session_state[f"confirm_{case['case_id']}"] = False
                        st.success("OCR completed. Review the tentative clues below and confirm them yourself.")
                    else:
                        st.info("No readable text was detected; enter the equipment details manually.")
                except VisionNotConfigured as exc:
                    st.warning(str(exc))
                except (RuntimeError, ValueError) as exc:
                    st.error(f"Image analysis failed: {exc}")
        if case["image_clues"]:
            st.write("**Tentative OCR clues — confirm against the equipment:**")
            for clue in case["image_clues"]:
                st.code(clue)
            confirmed = st.checkbox(
                "I verified these visible details against the equipment.",
                key=f"confirm_{case['case_id']}",
            )
            if confirmed:
                for clue in case["image_clues"]:
                    observation = f"Technician-confirmed from equipment image: {clue}"
                    if observation not in case["observations"]:
                        case["observations"].append(observation)

    with st.form("investigate_form"):
        question = st.text_input(
            "Ask about the fault",
            value="What checks are documented for recurring startup fault F07?",
        )
        investigate = st.form_submit_button("Find documented checks")
    if investigate:
        result = build_guidance(question, sources)
        st.session_state.guidance = result
        case["references"] = list(
            dict.fromkeys(ref["citation"] for ref in result["evidence"])
        )
        if result["status"] in {"unsupported", "escalate"}:
            case["follow_up"] = result["message"]

    if st.session_state.guidance:
        result = st.session_state.guidance
        if result["status"] == "supported":
            st.success(result["message"])
            st.markdown("**Documented checks**")
            for index, check in enumerate(result["checks"], start=1):
                st.markdown(f"{index}. {check['text']}  \n*Source: {check['citation']}*")
            with st.expander("Evidence passages"):
                for item in result["evidence"]:
                    st.markdown(f"**{item['citation']}**")
                    st.write(item["excerpt"])
        elif result["status"] == "escalate":
            st.error(result["message"])
        else:
            st.warning(result["message"])

    st.markdown("### Record the visit")
    with st.form("record_visit_form", clear_on_submit=True):
        selected_check = st.selectbox(
            "Documented check",
            options=["(Add an observation only)"] + [
                item["text"] for item in (st.session_state.guidance or {}).get("checks", [])
            ],
        )
        outcome = st.text_input("Outcome / observation")
        save_observation = st.form_submit_button("Add to case")
    if save_observation:
        if not outcome.strip():
            st.error("Enter the observation or check outcome.")
        else:
            if selected_check == "(Add an observation only)":
                case["observations"].append(outcome.strip())
            else:
                check_data = next(
                    item for item in st.session_state.guidance["checks"]
                    if item["text"] == selected_check
                )
                case["checks"].append(
                    {
                        "check": selected_check,
                        "outcome": outcome.strip(),
                        "citation": check_data["citation"],
                    }
                )
            st.session_state.report_reviewed = False
            st.success("Added to the case evidence.")

with report_col:
    st.markdown("### Service report")
    report = build_service_report(case)
    if st.session_state.get("report_last_evidence") != report:
        st.session_state.report_reviewed = False
        st.session_state.report_last_evidence = report
    previous_source = st.session_state.get("report_source")
    if previous_source is None or st.session_state.get("report_editor") == previous_source:
        st.session_state.report_editor = report
        st.session_state.report_source = report
    report_stale = st.session_state.report_source != report
    if report_stale:
        st.warning(
            "Case evidence changed. Your edits are preserved. Reconcile the draft "
            "with the latest evidence before review or download."
        )
        with st.expander("Latest evidence-generated report", expanded=True):
            st.markdown(report)
        st.button(
            "Replace my edits with latest evidence",
            on_click=_reconcile_report,
            args=(True,),
        )
    edited_report = st.text_area(
        "Editable draft — verify before use",
        height=500,
        key="report_editor",
        on_change=_invalidate_report_review,
    )
    if report_stale:
        st.button(
            "I reconciled my edits with the latest evidence",
            on_click=_reconcile_report,
            args=(False,),
            disabled=not edited_report.strip(),
        )
    if st.button("Mark draft reviewed", disabled=report_stale):
        if not edited_report.strip():
            st.error("The report draft cannot be empty.")
        else:
            st.session_state.report_reviewed = True
    if st.session_state.report_reviewed:
        st.success("Marked reviewed in this demo session. Nothing has been submitted.")
    else:
        st.caption("Draft only · not submitted")
    st.download_button(
        "Download reviewed report" if st.session_state.report_reviewed else "Download draft report",
        data=edited_report,
        file_name=(
            f"{case['case_id'].lower()}-"
            f"{'reviewed' if st.session_state.report_reviewed else 'draft'}-service-report.md"
        ),
        mime="text/markdown",
        key="download_report",
        disabled=report_stale or not edited_report.strip(),
    )

st.divider()
st.caption("Approved demo corpus: " + " · ".join(source.source_id for source in sources))
