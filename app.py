"""
Compliance & Audit Alignment Engine - Streamlit Demonstration App
==================================================================
Interactive, enterprise-grade audit dashboard supporting:
  - Multi-Page PDF Ingestion & Automated Page-to-JSON Conversion
  - Relational JSON Input Datasets
  - Comparative compliance evaluation against strict Evaluation Criteria
  - Google Gemini, OpenAI, and Deterministic Offline engines
"""

import io
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Import core engine functions and models from compliance_engine
from compliance_engine import (
    AuditEvaluationRecord,
    AuditReport,
    ComplianceStatus,
    build_section_lookup_table,
    evaluate_alignment_with_llm,
    initialize_llm_client,
    load_json_file,
    normalize_criteria_list,
)

# Import PDF parser functions
from pdf_ingestion import (
    generate_sample_pdfs_from_json,
    parse_evaluation_criteria_pdf,
    parse_external_regulation_pdf,
    parse_internal_policy_pdf,
)

# -----------------------------------------------------------------------------
# Streamlit Page Configuration & Custom Styling
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Compliance & Audit Alignment Engine",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Premium Enterprise CSS Styles
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .block-container {
        padding-top: 1.6rem;
        padding-bottom: 3rem;
        max-width: 1400px;
    }

    /* Hero Header Banner */
    .hero-banner {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.9) 0%, rgba(15, 23, 42, 0.95) 100%);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px 30px;
        margin-bottom: 24px;
        box-shadow: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
        backdrop-filter: blur(12px);
    }

    .hero-title {
        font-size: 2.1rem;
        font-weight: 800;
        background: linear-gradient(120deg, #60a5fa 0%, #a78bfa 50%, #f472b6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 6px;
        letter-spacing: -0.02em;
    }

    .hero-subtitle {
        color: #94a3b8;
        font-size: 0.95rem;
        margin: 0;
        line-height: 1.5;
    }

    /* Metric Cards */
    .metric-card {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 18px 20px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
    }
    .metric-value {
        font-size: 2rem;
        font-weight: 800;
        margin-bottom: 2px;
    }
    .metric-label {
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
        font-weight: 600;
    }

    /* Status Badges */
    .badge-pass {
        display: inline-block;
        background: rgba(16, 185, 129, 0.15);
        color: #10b981;
        border: 1px solid rgba(16, 185, 129, 0.3);
        padding: 4px 14px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.85rem;
        letter-spacing: 0.05em;
    }
    .badge-fail {
        display: inline-block;
        background: rgba(239, 68, 68, 0.15);
        color: #ef4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
        padding: 4px 14px;
        border-radius: 9999px;
        font-weight: 700;
        font-size: 0.85rem;
        letter-spacing: 0.05em;
    }
    .badge-pdf {
        display: inline-block;
        background: rgba(59, 130, 246, 0.15);
        color: #60a5fa;
        border: 1px solid rgba(59, 130, 246, 0.3);
        padding: 3px 10px;
        border-radius: 9999px;
        font-weight: 600;
        font-size: 0.75rem;
        letter-spacing: 0.04em;
    }

    /* Audit Card */
    .audit-card {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 22px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }

    /* Document Callouts */
    .doc-callout {
        background: rgba(30, 41, 59, 0.5);
        border-radius: 10px;
        padding: 14px 16px;
        font-size: 0.88rem;
        line-height: 1.55;
        border-left: 4px solid #3b82f6;
    }
    .doc-callout-reg {
        border-left-color: #8b5cf6;
    }
    .doc-callout-crit {
        border-left-color: #f59e0b;
        background: rgba(245, 158, 11, 0.08);
    }
    .doc-callout-remed {
        border-left-color: #10b981;
        background: rgba(16, 185, 129, 0.08);
    }

    .section-tag {
        font-size: 0.75rem;
        text-transform: uppercase;
        font-weight: 700;
        letter-spacing: 0.08em;
        margin-bottom: 6px;
        color: #94a3b8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Session State & Defaults Initialization
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

DEFAULT_INTERNAL_JSON = BASE_DIR / "sample_internal_policy.json"
DEFAULT_EXTERNAL_JSON = BASE_DIR / "sample_external_regulation.json"
DEFAULT_CRITERIA_JSON = BASE_DIR / "sample_evaluation_criteria.json"

DEFAULT_INTERNAL_PDF = BASE_DIR / "sample_internal_policy.pdf"
DEFAULT_EXTERNAL_PDF = BASE_DIR / "sample_external_regulation.pdf"
DEFAULT_CRITERIA_PDF = BASE_DIR / "sample_evaluation_criteria.pdf"

# Ensure sample PDFs exist
if not DEFAULT_INTERNAL_PDF.exists():
    try:
        generate_sample_pdfs_from_json(BASE_DIR)
    except Exception:
        pass

if "audit_report" not in st.session_state:
    st.session_state.audit_report = None
if "ingestion_format" not in st.session_state:
    st.session_state.ingestion_format = "PDF Documents"

if "active_internal_json" not in st.session_state:
    if DEFAULT_INTERNAL_PDF.exists():
        st.session_state.active_internal_json = parse_internal_policy_pdf(DEFAULT_INTERNAL_PDF)
    elif DEFAULT_INTERNAL_JSON.exists():
        st.session_state.active_internal_json = load_json_file(DEFAULT_INTERNAL_JSON)
    else:
        st.session_state.active_internal_json = None

if "active_external_json" not in st.session_state:
    if DEFAULT_EXTERNAL_PDF.exists():
        st.session_state.active_external_json = parse_external_regulation_pdf(DEFAULT_EXTERNAL_PDF)
    elif DEFAULT_EXTERNAL_JSON.exists():
        st.session_state.active_external_json = load_json_file(DEFAULT_EXTERNAL_JSON)
    else:
        st.session_state.active_external_json = None

if "active_criteria_json" not in st.session_state:
    if DEFAULT_CRITERIA_PDF.exists():
        st.session_state.active_criteria_json = parse_evaluation_criteria_pdf(DEFAULT_CRITERIA_PDF)
    elif DEFAULT_CRITERIA_JSON.exists():
        st.session_state.active_criteria_json = load_json_file(DEFAULT_CRITERIA_JSON)
    else:
        st.session_state.active_criteria_json = None


# -----------------------------------------------------------------------------
# Sidebar Configuration Panel
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ Engine Configuration")

    provider_choice = st.selectbox(
        "AI Inference Provider",
        options=["Google Gemini (Recommended)", "OpenAI", "Deterministic Engine (Offline Demo)"],
        index=0,
        help="Select the LLM provider for live audit verification or choose deterministic offline rule engine.",
    )

    api_key_input = ""
    model_choice = "gemini-2.5-flash"

    if "Google Gemini" in provider_choice:
        env_gemini = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        api_key_input = st.text_input(
            "Google API Key (Gemini)",
            value=env_gemini,
            type="password",
            placeholder="AIzaSy...",
            help="Get a key from Google AI Studio: https://aistudio.google.com/app/apikey",
        )
        model_choice = st.selectbox(
            "Gemini Model",
            options=["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
            index=0,
        )
        if api_key_input:
            os.environ["GEMINI_API_KEY"] = api_key_input
            st.success("API Key detected for Gemini", icon="✅")
        else:
            st.info("No API key entered. Running in deterministic mode.", icon="ℹ️")

    elif "OpenAI" in provider_choice:
        env_openai = os.getenv("OPENAI_API_KEY") or ""
        api_key_input = st.text_input(
            "OpenAI API Key",
            value=env_openai,
            type="password",
            placeholder="sk-proj-...",
            help="Enter your OpenAI API key from platform.openai.com",
        )
        model_choice = st.selectbox(
            "OpenAI Model",
            options=["gpt-4o", "gpt-4o-mini"],
            index=0,
        )
        if api_key_input:
            os.environ["OPENAI_API_KEY"] = api_key_input
            st.success("API Key detected for OpenAI", icon="✅")
        else:
            st.info("No API key entered. Running in deterministic mode.", icon="ℹ️")
    else:
        st.info("Running deterministic rule engine without external API calls.", icon="🛡️")

    st.markdown("---")
    st.markdown("### 📄 Document Ingestion Source")

    ingestion_mode = st.radio(
        "Source Input Format",
        options=["PDF Documents (Page-to-JSON)", "JSON Relational Schemas"],
        index=0,
        help="Choose whether to ingest raw PDF documents or structured JSON files.",
    )
    st.session_state.ingestion_format = ingestion_mode

    if "PDF" in ingestion_mode:
        pdf_source = st.radio(
            "PDF Selection",
            options=["Sample Workspace PDFs", "Upload Custom PDFs"],
            index=0,
        )

        if pdf_source == "Upload Custom PDFs":
            uploaded_int_pdf = st.file_uploader("1. Internal Policy PDF", type=["pdf"])
            uploaded_ext_pdf = st.file_uploader("2. External Regulation PDF", type=["pdf"])
            uploaded_crit_pdf = st.file_uploader("3. Evaluation Criteria PDF", type=["pdf"])

            if uploaded_int_pdf:
                with st.spinner("Converting Internal Policy PDF page-by-page to JSON..."):
                    st.session_state.active_internal_json = parse_internal_policy_pdf(uploaded_int_pdf.read())
                    st.toast("Internal Policy PDF parsed!", icon="📄")

            if uploaded_ext_pdf:
                with st.spinner("Converting External Regulation PDF page-by-page to JSON..."):
                    st.session_state.active_external_json = parse_external_regulation_pdf(uploaded_ext_pdf.read())
                    st.toast("External Regulation PDF parsed!", icon="⚖️")

            if uploaded_crit_pdf:
                with st.spinner("Converting Evaluation Criteria PDF page-by-page to JSON..."):
                    st.session_state.active_criteria_json = parse_evaluation_criteria_pdf(uploaded_crit_pdf.read())
                    st.toast("Evaluation Criteria PDF parsed!", icon="📋")

        else:
            if st.button("Reload Sample PDFs", use_container_width=True):
                if not DEFAULT_INTERNAL_PDF.exists():
                    generate_sample_pdfs_from_json(BASE_DIR)
                st.session_state.active_internal_json = parse_internal_policy_pdf(DEFAULT_INTERNAL_PDF)
                st.session_state.active_external_json = parse_external_regulation_pdf(DEFAULT_EXTERNAL_PDF)
                st.session_state.active_criteria_json = parse_evaluation_criteria_pdf(DEFAULT_CRITERIA_PDF)
                st.success("Loaded & Converted Sample PDFs!")

    else:
        # JSON Mode
        json_source = st.radio(
            "JSON Selection",
            options=["Sample Workspace JSONs", "Upload Custom JSONs"],
            index=0,
        )

        if json_source == "Upload Custom JSONs":
            uploaded_internal = st.file_uploader("Upload Internal Policy JSON", type=["json"])
            uploaded_external = st.file_uploader("Upload External Regulation JSON", type=["json"])
            uploaded_criteria = st.file_uploader("Upload Evaluation Criteria JSON", type=["json"])

            if uploaded_internal:
                st.session_state.active_internal_json = json.load(uploaded_internal)
            if uploaded_external:
                st.session_state.active_external_json = json.load(uploaded_external)
            if uploaded_criteria:
                st.session_state.active_criteria_json = json.load(uploaded_criteria)
        else:
            if st.button("Reload Sample JSONs", use_container_width=True):
                st.session_state.active_internal_json = load_json_file(DEFAULT_INTERNAL_JSON)
                st.session_state.active_external_json = load_json_file(DEFAULT_EXTERNAL_JSON)
                st.session_state.active_criteria_json = load_json_file(DEFAULT_CRITERIA_JSON)
                st.success("Loaded Workspace JSONs!")

    st.markdown("---")
    run_audit_btn = st.button("🚀 Run Alignment Audit", type="primary", use_container_width=True)


# -----------------------------------------------------------------------------
# Top Hero Banner
# -----------------------------------------------------------------------------
st.markdown(
    """
    <div class="hero-banner">
        <div class="hero-title">🛡️ Compliance & Audit Alignment Engine</div>
        <div class="hero-subtitle">
            Automated verification comparing <strong>Internal Policies</strong> against 
            <strong>External Regulations</strong> under strict <strong>Evaluation Criteria</strong> statements.
            Supports <strong>Multi-Page PDF Ingestion</strong> and automated page-by-page JSON conversion.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Execution Trigger
# -----------------------------------------------------------------------------
if run_audit_btn:
    with st.spinner("Extracting sections & evaluating cross-document compliance alignment..."):
        try:
            int_data = st.session_state.active_internal_json
            ext_data = st.session_state.active_external_json
            crit_data = st.session_state.active_criteria_json

            if not int_data or not ext_data or not crit_data:
                st.error("Missing required datasets. Please load or upload all three documents.")
                st.stop()

            internal_index = build_section_lookup_table(int_data)
            external_index = build_section_lookup_table(ext_data)
            criteria_list = normalize_criteria_list(crit_data)

            if "Deterministic" in provider_choice:
                provider_key = "mock"
                client = None
                resolved_model = "rule-engine"
            elif "Google Gemini" in provider_choice:
                provider_key, client, resolved_model = initialize_llm_client(
                    google_api_key=api_key_input or None,
                    preferred_model=model_choice,
                )
            else:
                provider_key, client, resolved_model = initialize_llm_client(
                    openai_api_key=api_key_input or None,
                    preferred_model=model_choice,
                )

            eval_records: List[AuditEvaluationRecord] = []
            for node in criteria_list:
                crit_id = node.get("evaluation_criteria_id", "UNKNOWN_CRIT")
                stmt = node.get("expected_criteria_statement", "")
                aligned = node.get("aligned_sources", {})
                ext_ids = aligned.get("external_regulatory_section_ids", [])
                int_ids = aligned.get("internal_policy_section_ids", [])

                for e_id in ext_ids:
                    for i_id in int_ids:
                        int_sec = internal_index.get(i_id, {})
                        ext_sec = external_index.get(e_id, {})

                        record = evaluate_alignment_with_llm(
                            provider=provider_key,
                            client=client,
                            model_name=resolved_model,
                            criteria_id=crit_id,
                            expected_statement=stmt,
                            internal_section_id=i_id,
                            internal_heading=int_sec.get("heading", ""),
                            internal_raw_text=int_sec.get("raw_text", ""),
                            external_section_id=e_id,
                            external_heading=ext_sec.get("heading", ""),
                            external_raw_text=ext_sec.get("raw_text", ""),
                        )
                        eval_records.append(record)

            passed_count = sum(1 for r in eval_records if r.alignment_check.status == ComplianceStatus.PASS)
            failed_count = sum(1 for r in eval_records if r.alignment_check.status == ComplianceStatus.FAIL)

            report = AuditReport(
                total_criteria_evaluated=len(eval_records),
                passed_count=passed_count,
                failed_count=failed_count,
                evaluations=eval_records,
            )

            st.session_state.audit_report = report
            st.toast("Compliance Audit Complete!", icon="🎉")

        except Exception as e:
            st.error(f"Audit execution encountered an error: {e}")


# Auto-run baseline report if not yet computed
if st.session_state.audit_report is None and st.session_state.active_internal_json:
    try:
        int_data = st.session_state.active_internal_json
        ext_data = st.session_state.active_external_json
        crit_data = st.session_state.active_criteria_json
        int_idx = build_section_lookup_table(int_data)
        ext_idx = build_section_lookup_table(ext_data)
        clist = normalize_criteria_list(crit_data)

        provider_key, client, resolved_model = initialize_llm_client()
        init_records = []
        for node in clist:
            cid = node.get("evaluation_criteria_id", "UNKNOWN_CRIT")
            stmt = node.get("expected_criteria_statement", "")
            aligned = node.get("aligned_sources", {})
            for e_id in aligned.get("external_regulatory_section_ids", []):
                for i_id in aligned.get("internal_policy_section_ids", []):
                    rec = evaluate_alignment_with_llm(
                        provider=provider_key,
                        client=client,
                        model_name=resolved_model,
                        criteria_id=cid,
                        expected_statement=stmt,
                        internal_section_id=i_id,
                        internal_heading=int_idx.get(i_id, {}).get("heading", ""),
                        internal_raw_text=int_idx.get(i_id, {}).get("raw_text", ""),
                        external_section_id=e_id,
                        external_heading=ext_idx.get(e_id, {}).get("heading", ""),
                        external_raw_text=ext_idx.get(e_id, {}).get("raw_text", ""),
                    )
                    init_records.append(rec)

        p_cnt = sum(1 for r in init_records if r.alignment_check.status == ComplianceStatus.PASS)
        f_cnt = sum(1 for r in init_records if r.alignment_check.status == ComplianceStatus.FAIL)
        st.session_state.audit_report = AuditReport(
            total_criteria_evaluated=len(init_records),
            passed_count=p_cnt,
            failed_count=f_cnt,
            evaluations=init_records,
        )
    except Exception:
        pass


# -----------------------------------------------------------------------------
# Main Application Tabs
# -----------------------------------------------------------------------------
tab_dashboard, tab_simulator, tab_viewer = st.tabs([
    "📊 Executive Audit Dashboard",
    "🔄 Remediation Simulator",
    "📁 Document Repositories & PDF Ingestion",
])


# =============================================================================
# TAB 1: EXECUTIVE AUDIT DASHBOARD
# =============================================================================
with tab_dashboard:
    report: Optional[AuditReport] = st.session_state.audit_report

    if report:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        score_pct = int((report.passed_count / report.total_criteria_evaluated) * 100) if report.total_criteria_evaluated > 0 else 0

        with col_m1:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-value" style="color: #60a5fa;">{report.total_criteria_evaluated}</div>
                    <div class="metric-label">Total Evaluated</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_m2:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-value" style="color: #10b981;">{report.passed_count}</div>
                    <div class="metric-label">Compliant (PASS)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_m3:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-value" style="color: #ef4444;">{report.failed_count}</div>
                    <div class="metric-label">Gaps Detected (FAIL)</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        with col_m4:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-value" style="color: {'#10b981' if score_pct == 100 else '#f59e0b'};">{score_pct}%</div>
                    <div class="metric-label">Alignment Score</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        filter_col, export_col = st.columns([3, 1])
        with filter_col:
            status_filter = st.radio(
                "Filter Evaluations by Status:",
                options=["All Records", "FAIL Only", "PASS Only"],
                horizontal=True,
            )
        with export_col:
            report_json_str = json.dumps(report.model_dump(mode="json"), indent=2)
            st.download_button(
                label="📥 Export Report (JSON)",
                data=report_json_str,
                file_name="compliance_audit_report.json",
                mime="application/json",
                use_container_width=True,
            )

        st.markdown("---")

        for idx, evaluation in enumerate(report.evaluations, 1):
            check = evaluation.alignment_check
            is_pass = (check.status == ComplianceStatus.PASS)

            if status_filter == "FAIL Only" and is_pass:
                continue
            if status_filter == "PASS Only" and not is_pass:
                continue

            badge_html = '<span class="badge-pass">✅ PASS - FULLY ALIGNED</span>' if is_pass else '<span class="badge-fail">⚠️ FAIL - GAP DETECTED</span>'

            with st.container():
                st.markdown(
                    f"""
                    <div class="audit-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div>
                                <span style="font-size: 1.15rem; font-weight: 700; color: #f8fafc;">
                                    Evaluation Rule: <code>{evaluation.evaluation_criteria_id}</code>
                                </span>
                            </div>
                            <div>
                                {badge_html}
                            </div>
                        </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Target Criteria Statement
                st.markdown(
                    """
                    <div class="section-tag" style="color: #f59e0b;">Target Expected Criteria Statement</div>
                    """,
                    unsafe_allow_html=True,
                )
                criteria_data = st.session_state.active_criteria_json
                crit_list = normalize_criteria_list(criteria_data) if criteria_data else []
                node_match = next((n for n in crit_list if n.get("evaluation_criteria_id") == evaluation.evaluation_criteria_id), {})
                crit_stmt = node_match.get("expected_criteria_statement", "Rule verification statement.")

                st.markdown(
                    f"""
                    <div class="doc-callout doc-callout-crit" style="margin-bottom: 16px;">
                        "{crit_stmt}"
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # Comparative 2-Column Split
                col_int, col_ext = st.columns(2)

                int_idx = build_section_lookup_table(st.session_state.active_internal_json) if st.session_state.active_internal_json else {}
                ext_idx = build_section_lookup_table(st.session_state.active_external_json) if st.session_state.active_external_json else {}

                int_sec_info = int_idx.get(check.internal_section_evaluated, {})
                ext_sec_info = ext_idx.get(check.external_section_evaluated, {})

                with col_int:
                    st.markdown(
                        f"""
                        <div class="section-tag" style="color: #60a5fa;">Internal Policy: <code>{check.internal_section_evaluated}</code></div>
                        <div style="font-weight: 600; font-size: 0.92rem; margin-bottom: 6px;">
                            {int_sec_info.get("heading", "Internal Policy Section")}
                        </div>
                        <div class="doc-callout" style="min-height: 120px;">
                            "{int_sec_info.get("raw_text", "No raw text available")}"
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                with col_ext:
                    st.markdown(
                        f"""
                        <div class="section-tag" style="color: #a78bfa;">External Regulation: <code>{check.external_section_evaluated}</code></div>
                        <div style="font-weight: 600; font-size: 0.92rem; margin-bottom: 6px;">
                            {ext_sec_info.get("heading", "External Regulatory Mandate")}
                        </div>
                        <div class="doc-callout doc-callout-reg" style="min-height: 120px;">
                            "{ext_sec_info.get("raw_text", "No raw text available")}"
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown("<br>", unsafe_allow_html=True)

                with st.expander("🔍 Step-by-Step Audit Rationale & Gap Breakdown", expanded=True):
                    st.markdown(f"**Step-by-Step Comparative Rationale:**\n\n{check.rationale}")
                    st.markdown("---")
                    gap_col1, gap_col2 = st.columns(2)
                    with gap_col1:
                        st.markdown(f"**Strict Regulatory Requirement:**\n\n> {evaluation.detailed_gap_analysis.regulatory_requirement}")
                    with gap_col2:
                        st.markdown(f"**Internal Codebook Behavior:**\n\n> {evaluation.detailed_gap_analysis.internal_policy_behavior}")

                if evaluation.suggested_remediation:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(
                        f"""
                        <div class="section-tag" style="color: #10b981;">Mandatory Remediation Text Modification</div>
                        <div class="doc-callout doc-callout-remed">
                            {evaluation.suggested_remediation}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
    else:
        st.info("Click '🚀 Run Alignment Audit' in the sidebar to execute comparative compliance analysis.")


# =============================================================================
# TAB 2: INTERACTIVE REMEDIATION SIMULATOR
# =============================================================================
with tab_simulator:
    st.markdown("### 🔄 Interactive Remediation & Gap Resolution Simulator")
    st.markdown(
        "Simulate amending the Internal Policy to test whether modifying the policy text converts a "
        "**FAIL** status into a **PASS** in real time."
    )

    int_data = st.session_state.active_internal_json
    int_idx = build_section_lookup_table(int_data) if int_data else {}
    current_raw = int_idx.get("INT_SEC_4_1", {}).get("raw_text", "")

    suggested_text = (
        "Our execution desk must take all sufficient steps to obtain the best possible execution "
        "result for client orders by evaluating total consideration, including net price, transaction "
        "costs, execution speed, and likelihood of settlement across all available venues. Orders shall "
        "be dynamically routed to the venue offering the best overall economic outcome for the client. "
        "The firm strictly prohibits prioritizing internal affiliate broker networks where doing so "
        "results in higher fees, increased latency, or any adverse execution outcome for the client."
    )

    sim_col1, sim_col2 = st.columns(2)
    with sim_col1:
        st.markdown("**Original Policy Text (`INT_SEC_4_1`):**")
        st.text_area(
            "Original Text",
            value=current_raw,
            height=160,
            disabled=True,
            key="sim_orig_text",
        )

    with sim_col2:
        st.markdown("**Amended Policy Text (`INT_SEC_4_1`):**")
        edited_text = st.text_area(
            "Proposed Replacement Text",
            value=suggested_text,
            height=160,
            key="sim_edited_text",
        )

    btn_sim_apply = st.button("🧪 Simulate & Re-evaluate Compliance", type="primary")

    if btn_sim_apply:
        with st.spinner("Re-evaluating amended policy against MIFID_SEC_24_3..."):
            cloned_internal = json.loads(json.dumps(int_data))
            for page in cloned_internal.get("pages", []):
                for sec in page.get("sections", []):
                    if sec.get("section_id") == "INT_SEC_4_1":
                        sec["raw_text"] = edited_text

            ext_data = st.session_state.active_external_json
            ext_idx = build_section_lookup_table(ext_data)
            ext_sec = ext_idx.get("MIFID_SEC_24_3", {})
            crit_data = st.session_state.active_criteria_json
            crit_list = normalize_criteria_list(crit_data)
            stmt = crit_list[0].get("expected_criteria_statement", "") if crit_list else ""

            sim_provider = "mock"
            sim_client = None
            sim_model = "rule-engine"

            if "Google Gemini" in provider_choice and api_key_input:
                sim_provider, sim_client, sim_model = initialize_llm_client(google_api_key=api_key_input, preferred_model=model_choice)
            elif "OpenAI" in provider_choice and api_key_input:
                sim_provider, sim_client, sim_model = initialize_llm_client(openai_api_key=api_key_input, preferred_model=model_choice)

            sim_record = evaluate_alignment_with_llm(
                provider=sim_provider,
                client=sim_client,
                model_name=sim_model,
                criteria_id="CRIT_COMP_BEST_EXEC_01",
                expected_statement=stmt,
                internal_section_id="INT_SEC_4_1",
                internal_heading="Order Routing & Vendor Selection",
                internal_raw_text=edited_text,
                external_section_id="MIFID_SEC_24_3",
                external_heading=ext_sec.get("heading", "Best Execution Mandate to Clients"),
                external_raw_text=ext_sec.get("raw_text", ""),
            )

            st.markdown("---")
            st.markdown("#### 🏁 Simulation Audit Outcome")

            sim_status = sim_record.alignment_check.status
            if sim_status == ComplianceStatus.PASS:
                st.success("🎉 STATUS: PASS — The amended policy is fully compliant!", icon="✅")
            else:
                st.error("⚠️ STATUS: FAIL — Gaps remain in the amended policy.", icon="❌")

            st.markdown(f"**Rationale:**\n{sim_record.alignment_check.rationale}")

            if st.button("💾 Commit Remediation to Active Session"):
                st.session_state.active_internal_json = cloned_internal
                st.toast("Internal policy updated in active session! Re-run audit on Dashboard.", icon="💾")


# =============================================================================
# TAB 3: DOCUMENT REPOSITORIES & PDF INGESTION
# =============================================================================
with tab_viewer:
    st.markdown("### 📁 Document Repositories & Ingestion Architecture")
    st.markdown(
        "Inspect the converted relational JSON schemas produced from each page of the ingested PDF documents."
    )

    badge_label = "PDF Ingestion" if "PDF" in st.session_state.ingestion_format else "JSON Relational Ingestion"
    st.markdown(f'<span class="badge-pdf">⚡ Active Mode: {badge_label}</span>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    v_col1, v_col2, v_col3 = st.columns(3)

    with v_col1:
        st.markdown("#### 📄 Internal Policy")
        int_obj = st.session_state.active_internal_json
        if int_obj:
            total_p = len(int_obj.get("pages", []))
            st.caption(f"Document ID: `{int_obj.get('document_id')}` | Total Pages: {total_p}")
            st.json(int_obj, expanded=True)
        else:
            st.warning("No Internal Policy loaded.")

    with v_col2:
        st.markdown("#### ⚖️ External Regulation")
        ext_obj = st.session_state.active_external_json
        if ext_obj:
            total_p = len(ext_obj.get("pages", []))
            st.caption(f"Document ID: `{ext_obj.get('document_id')}` | Total Pages: {total_p}")
            st.json(ext_obj, expanded=True)
        else:
            st.warning("No External Regulation loaded.")

    with v_col3:
        st.markdown("#### 📋 Evaluation Criteria")
        crit_obj = st.session_state.active_criteria_json
        if crit_obj:
            st.caption(f"Rule ID: `{crit_obj.get('evaluation_criteria_id')}`")
            st.json(crit_obj, expanded=True)
        else:
            st.warning("No Evaluation Criteria loaded.")
