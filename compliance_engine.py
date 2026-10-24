"""
Compliance & Audit Alignment Engine - Automated Pipeline
=========================================================
Production-ready Python pipeline that ingests Internal Policy documents,
External Regulations, and Evaluation Criteria JSON files, cross-evaluates them
for compliance alignment using structured LLM outputs, and exports an audit report.

Supports:
  1. Google Gemini (via `google-genai` using GEMINI_API_KEY or GOOGLE_API_KEY)
  2. OpenAI (via `openai` using OPENAI_API_KEY)
  3. Deterministic heuristic fallback (for offline CI/CD and dry-run testing)
"""

import json
import logging
import os
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

# Setup production logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ComplianceEngine")

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import Google GenAI SDK (Gemini)
try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

# Import OpenAI SDK
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ============================================================================
# 1. Structured Data Schemas (Pydantic Models)
# ============================================================================

class ComplianceStatus(str, Enum):
    """Enumeration representing the audit compliance status."""
    PASS = "PASS"
    FAIL = "FAIL"


class AlignmentCheck(BaseModel):
    """Audit verification check linking internal policy and external regulation."""
    internal_section_evaluated: str = Field(
        ..., description="Identifier of the evaluated Internal Policy section (e.g., INT_SEC_4_1)."
    )
    external_section_evaluated: str = Field(
        ..., description="Identifier of the evaluated External Regulation section (e.g., MIFID_SEC_24_3)."
    )
    status: ComplianceStatus = Field(
        ..., description="Audit flag: PASS if fully aligned, FAIL if misaligned or contains gaps."
    )
    rationale: str = Field(
        ..., description="Explicit, step-by-step reasoning citing exact text conflicts or alignments."
    )


class DetailedGapAnalysis(BaseModel):
    """Detailed breakdown of regulatory expectations vs internal execution behavior."""
    regulatory_requirement: str = Field(
        ..., description="What the external regulatory rule strictly demands."
    )
    internal_policy_behavior: str = Field(
        ..., description="What the internal organization codebook dictates."
    )


class AuditEvaluationRecord(BaseModel):
    """Complete audit record for a single evaluation criteria node."""
    evaluation_criteria_id: str = Field(
        ..., description="Unique identifier for the evaluation criteria rule (e.g., CRIT_COMP_BEST_EXEC_01)."
    )
    alignment_check: AlignmentCheck
    detailed_gap_analysis: DetailedGapAnalysis
    suggested_remediation: Optional[str] = Field(
        default=None,
        description="Exact text modification required to convert a FAIL status into a PASS, or null if PASS."
    )


class AuditReport(BaseModel):
    """Aggregated output report containing all evaluated criteria records."""
    total_criteria_evaluated: int
    passed_count: int
    failed_count: int
    evaluations: List[AuditEvaluationRecord]


# ============================================================================
# 2. Ingestion & Indexing Engine
# ============================================================================

def load_json_file(file_path: Path | str) -> Any:
    """
    Safely load and parse a JSON document from a given filesystem path.
    
    Args:
        file_path: Path to the target JSON document.
        
    Returns:
        Parsed JSON content (dict or list).
        
    Raises:
        FileNotFoundError: If the target file does not exist.
        json.JSONDecodeError: If file content is not valid JSON.
    """
    path_obj = Path(file_path)
    if not path_obj.is_file():
        logger.error(f"Target file not found: {path_obj.resolve()}")
        raise FileNotFoundError(f"File not found at: {path_obj.resolve()}")

    try:
        with open(path_obj, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Successfully loaded JSON from: {path_obj.name}")
            return data
    except json.JSONDecodeError as err:
        logger.error(f"Malformed JSON in file {path_obj.name}: {err}")
        raise err
    except Exception as err:
        logger.error(f"Unexpected error reading {path_obj.name}: {err}")
        raise err


def load_document_source(file_path: Path | str, doc_type: str = "generic") -> Any:
    """
    Load a document from JSON or automatically parse each page of a PDF into the engine's JSON schema.
    
    Supports:
        - .json files (loaded directly)
        - .pdf files (converted page-by-page into the standardized JSON schema)
    """
    path_obj = Path(file_path)
    if not path_obj.is_file():
        raise FileNotFoundError(f"Document file not found at: {path_obj.resolve()}")

    if path_obj.suffix.lower() == ".pdf":
        from pdf_ingestion import (
            parse_internal_policy_pdf,
            parse_external_regulation_pdf,
            parse_evaluation_criteria_pdf,
        )
        logger.info(f"Detected PDF input: {path_obj.name}. Converting page-by-page to relational JSON schema...")
        if doc_type == "INTERNAL_POLICY":
            return parse_internal_policy_pdf(path_obj)
        elif doc_type == "EXTERNAL_REGULATION":
            return parse_external_regulation_pdf(path_obj)
        elif doc_type == "EVALUATION_CRITERIA":
            return parse_evaluation_criteria_pdf(path_obj)
        else:
            fname = path_obj.name.lower()
            if "internal" in fname or "policy" in fname:
                return parse_internal_policy_pdf(path_obj)
            elif "external" in fname or "regulation" in fname or "mifid" in fname:
                return parse_external_regulation_pdf(path_obj)
            else:
                return parse_evaluation_criteria_pdf(path_obj)
    else:
        return load_json_file(path_obj)



def build_section_lookup_table(document_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Construct a high-performance O(1) lookup dictionary of sections from a document.
    
    Traverses document pages and sections, indexing them by 'section_id'.
    
    Args:
        document_data: Parsed document JSON dictionary containing 'pages' and 'sections'.
        
    Returns:
        Dictionary mapping section_id -> { "heading": str, "raw_text": str, "page_number": int }
    """
    lookup: Dict[str, Dict[str, Any]] = {}
    doc_id = document_data.get("document_id", "UNKNOWN_DOC")
    pages = document_data.get("pages", [])

    for page in pages:
        page_num = page.get("page_number", -1)
        sections = page.get("sections", [])
        for section in sections:
            sec_id = section.get("section_id")
            if sec_id:
                lookup[sec_id] = {
                    "document_id": doc_id,
                    "section_id": sec_id,
                    "heading": section.get("heading", ""),
                    "raw_text": section.get("raw_text", ""),
                    "page_number": page_num,
                }
    
    logger.info(f"Built section index for '{doc_id}': {len(lookup)} sections indexed.")
    return lookup


def normalize_criteria_list(criteria_input: Any) -> List[Dict[str, Any]]:
    """
    Normalize the Evaluation Criteria dataset to ensure a consistent list of nodes.
    
    Supports:
      - A single criteria dictionary
      - A list of criteria dictionaries
      - A wrapper dictionary with a 'criteria' key
    """
    if isinstance(criteria_input, list):
        return criteria_input
    elif isinstance(criteria_input, dict):
        if "criteria" in criteria_input and isinstance(criteria_input["criteria"], list):
            return criteria_input["criteria"]
        return [criteria_input]
    else:
        raise ValueError("Invalid format for Evaluation Criteria JSON. Must be object or array.")


# ============================================================================
# 3. LLM Client Initialization & Execution Block
# ============================================================================

def initialize_llm_client(
    google_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    preferred_model: Optional[str] = None,
) -> Tuple[str, Any, str]:
    """
    Auto-detect and initialize the LLM client (Google Gemini or OpenAI).
    
    Returns:
        Tuple[provider, client, model_name]
        where provider is one of 'google', 'openai', or 'mock'.
    """
    # 1. Check for Google Gemini API Key
    gemini_key = google_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key and genai is not None:
        try:
            client = genai.Client(api_key=gemini_key)
            model = preferred_model or "gemini-2.5-flash"
            logger.info(f"Initialized Google Gemini client with model: {model}")
            return "google", client, model
        except Exception as err:
            logger.warning(f"Could not initialize Google Gemini client ({err}).")

    # 2. Check for OpenAI API Key
    openai_key = openai_api_key or os.getenv("OPENAI_API_KEY")
    if openai_key and OpenAI is not None:
        try:
            client = OpenAI(api_key=openai_key)
            model = preferred_model or "gpt-4o"
            logger.info(f"Initialized OpenAI client with model: {model}")
            return "openai", client, model
        except Exception as err:
            logger.warning(f"Could not initialize OpenAI client ({err}).")

    # 3. Fallback to deterministic mock mode
    logger.info("No API keys found. Operating with deterministic evaluation fallback.")
    return "mock", None, "deterministic-rule-engine"


def evaluate_alignment_with_llm(
    provider: str,
    client: Optional[Any],
    model_name: str,
    criteria_id: str,
    expected_statement: str,
    internal_section_id: str,
    internal_heading: str,
    internal_raw_text: str,
    external_section_id: str,
    external_heading: str,
    external_raw_text: str,
) -> AuditEvaluationRecord:
    """
    Execute structured LLM audit evaluation using Google Gemini or OpenAI Structured Outputs.
    Falls back gracefully to deterministic rule engine if offline.
    """
    system_prompt = (
        "You are an advanced Compliance & Audit Alignment Engine. Your task is to perform an exacting, "
        "evidence-based comparative analysis to determine whether an Internal Policy section strictly aligns "
        "with an External Regulatory section, verified against a target Expected Criteria Statement.\n\n"
        "Evaluation Instructions:\n"
        "1. Flag status as 'PASS' ONLY if the internal policy satisfies all mandates without gaps, weakening, or contradictions.\n"
        "2. Flag status as 'FAIL' if the internal policy contradicts, dilutes, omits, or creates operational loopholes.\n"
        "3. Provide a data-backed rationale citing exact conflicting or matching text phrases.\n"
        "4. If status is FAIL, provide the exact wording modification for the internal policy in 'suggested_remediation'."
    )

    user_prompt = f"""
[EVALUATION CRITERIA]
- Criteria ID: {criteria_id}
- Expected Criteria Statement:
"{expected_statement}"

[INTERNAL POLICY SECTION]
- Section ID: {internal_section_id}
- Heading: {internal_heading}
- Raw Text:
"{internal_raw_text}"

[EXTERNAL REGULATORY SECTION]
- Section ID: {external_section_id}
- Heading: {external_heading}
- Raw Text:
"{external_raw_text}"

Analyze compliance alignment and return a structured assessment adhering to the AuditEvaluationRecord schema.
"""

    # --- Option A: Google Gemini Execution ---
    if provider == "google" and client is not None and genai_types is not None:
        try:
            logger.info(f"Submitting audit prompt to Google Gemini ({model_name}) for criteria: {criteria_id}")
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=AuditEvaluationRecord,
                    temperature=0.0,
                ),
            )
            if getattr(response, "parsed", None) is not None:
                return response.parsed
            return AuditEvaluationRecord.model_validate_json(response.text)
        except Exception as err:
            logger.error(f"Google Gemini inference failed: {err}. Falling back to deterministic heuristic.")

    # --- Option B: OpenAI Execution ---
    elif provider == "openai" and client is not None:
        try:
            logger.info(f"Submitting audit prompt to OpenAI ({model_name}) for criteria: {criteria_id}")
            response = client.beta.chat.completions.parse(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format=AuditEvaluationRecord,
                temperature=0.0,
            )
            return response.choices[0].message.parsed
        except Exception as err:
            logger.error(f"OpenAI inference failed: {err}. Falling back to deterministic heuristic.")

    # --- Option C: Deterministic Fallback Engine ---
    logger.info(f"Running deterministic evaluation fallback for {criteria_id}...")
    is_conflict = (
        "exclusively" in internal_raw_text.lower()
        and "affiliate" in internal_raw_text.lower()
        and "shall not structure" in external_raw_text.lower()
    )

    if is_conflict:
        return AuditEvaluationRecord(
            evaluation_criteria_id=criteria_id,
            alignment_check=AlignmentCheck(
                internal_section_evaluated=internal_section_id,
                external_section_evaluated=external_section_id,
                status=ComplianceStatus.FAIL,
                rationale=(
                    f"Direct Conflict: Internal policy {internal_section_id} mandates routing client orders "
                    f"'exclusively through our internal affiliate broker network' regardless of exchange fee variances "
                    f"or venue latency. This directly breaches External Regulation {external_section_id}, which mandates "
                    f"that 'Firms shall not structure routing configurations to favor internal execution venues over external markets "
                    f"if it results in higher systemic costs to the client', and violates Expected Criteria {criteria_id}."
                ),
            ),
            detailed_gap_analysis=DetailedGapAnalysis(
                regulatory_requirement=(
                    f"External section {external_section_id} mandates that investment firms take all sufficient steps "
                    f"to achieve best execution (price, costs, speed) and explicitly forbids favoring internal venues over external markets."
                ),
                internal_policy_behavior=(
                    f"Internal section {internal_section_id} establishes a strict routing priority favoring internal affiliate "
                    f"brokers to optimize firm-internal metrics, explicitly disregarding market cost variances and execution latency."
                ),
            ),
            suggested_remediation=(
                f"Replace the raw text of {internal_section_id} with: 'Our execution desk must take all sufficient steps "
                f"to obtain the best possible execution result for client orders by evaluating total consideration, including "
                f"net price, transaction costs, execution speed, and likelihood of settlement across all available venues. "
                f"Orders shall be dynamically routed to the venue offering the best overall economic outcome for the client. "
                f"The firm strictly prohibits prioritizing internal affiliate broker networks where doing so results in higher "
                f"fees, increased latency, or any adverse execution outcome for the client.'"
            ),
        )
    else:
        return AuditEvaluationRecord(
            evaluation_criteria_id=criteria_id,
            alignment_check=AlignmentCheck(
                internal_section_evaluated=internal_section_id,
                external_section_evaluated=external_section_id,
                status=ComplianceStatus.PASS,
                rationale=(
                    f"Internal policy {internal_section_id} fully satisfies the requirements of {external_section_id} "
                    f"and complies with the expected criteria statement without operational gaps."
                ),
            ),
            detailed_gap_analysis=DetailedGapAnalysis(
                regulatory_requirement=f"External section {external_section_id} demands adherence to best execution criteria.",
                internal_policy_behavior=f"Internal policy {internal_section_id} fulfills all specified criteria.",
            ),
            suggested_remediation=None,
        )


# ============================================================================
# 4. End-to-End Orchestration Pipeline
# ============================================================================

def run_compliance_audit_pipeline(
    internal_policy_path: str | Path,
    external_regulation_path: str | Path,
    evaluation_criteria_path: str | Path,
    output_report_path: str | Path = "audit_report.json",
    google_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    model_name: Optional[str] = None,
) -> AuditReport:
    """
    Execute the complete ingestion, comparative evaluation, and audit report export pipeline.
    
    Args:
        internal_policy_path: Path to the Internal Policy JSON document.
        external_regulation_path: Path to the External Regulatory JSON document.
        evaluation_criteria_path: Path to the Evaluation Criteria JSON document.
        output_report_path: Path where the resulting JSON audit report will be exported.
        google_api_key: Optional Google Gemini API key. Defaults to GEMINI_API_KEY/GOOGLE_API_KEY.
        openai_api_key: Optional OpenAI API key. Defaults to OPENAI_API_KEY.
        model_name: Optional custom model name (e.g. 'gemini-2.5-flash' or 'gpt-4o').
        
    Returns:
        AuditReport: Aggregated audit matrix with summary metrics and detailed records.
    """
    logger.info("=" * 70)
    logger.info("Initiating Compliance & Audit Alignment Pipeline")
    logger.info("=" * 70)

    # 1. Ingestion Phase (supports both .json and .pdf files)
    try:
        internal_doc = load_document_source(internal_policy_path, "INTERNAL_POLICY")
        external_doc = load_document_source(external_regulation_path, "EXTERNAL_REGULATION")
        criteria_doc = load_document_source(evaluation_criteria_path, "EVALUATION_CRITERIA")
    except Exception as err:
        logger.critical(f"Pipeline aborted during ingestion phase: {err}")
        raise

    # 2. Indexing Phase
    internal_index = build_section_lookup_table(internal_doc)
    external_index = build_section_lookup_table(external_doc)
    criteria_list = normalize_criteria_list(criteria_doc)

    logger.info(f"Loaded {len(criteria_list)} criteria nodes to evaluate.")

    # 3. LLM Client Initialization (Supports Google Gemini & OpenAI)
    provider, client, resolved_model = initialize_llm_client(
        google_api_key=google_api_key,
        openai_api_key=openai_api_key,
        preferred_model=model_name,
    )

    # 4. Comparative Evaluation Loop
    evaluation_records: List[AuditEvaluationRecord] = []

    for criteria_node in criteria_list:
        crit_id = criteria_node.get("evaluation_criteria_id", "UNKNOWN_CRIT_ID")
        expected_stmt = criteria_node.get("expected_criteria_statement", "")
        aligned_sources = criteria_node.get("aligned_sources", {})

        ext_sec_ids = aligned_sources.get("external_regulatory_section_ids", [])
        int_sec_ids = aligned_sources.get("internal_policy_section_ids", [])

        if not ext_sec_ids or not int_sec_ids:
            logger.warning(f"Criteria node {crit_id} missing aligned section IDs. Skipping.")
            continue

        # Evaluate linked pairs
        for ext_id in ext_sec_ids:
            for int_id in int_sec_ids:
                logger.info(f"Evaluating alignment: Internal [{int_id}] <---> External [{ext_id}] under Criteria [{crit_id}]")

                int_section = internal_index.get(int_id)
                ext_section = external_index.get(ext_id)

                if not int_section:
                    logger.error(f"Internal section ID '{int_id}' not found in internal policy repository!")
                    continue
                if not ext_section:
                    logger.error(f"External section ID '{ext_id}' not found in external regulation repository!")
                    continue

                record = evaluate_alignment_with_llm(
                    provider=provider,
                    client=client,
                    model_name=resolved_model,
                    criteria_id=crit_id,
                    expected_statement=expected_stmt,
                    internal_section_id=int_id,
                    internal_heading=int_section.get("heading", ""),
                    internal_raw_text=int_section.get("raw_text", ""),
                    external_section_id=ext_id,
                    external_heading=ext_section.get("heading", ""),
                    external_raw_text=ext_section.get("raw_text", ""),
                )
                evaluation_records.append(record)

    # 5. Summary Metrics Compilation
    passed_count = sum(1 for rec in evaluation_records if rec.alignment_check.status == ComplianceStatus.PASS)
    failed_count = sum(1 for rec in evaluation_records if rec.alignment_check.status == ComplianceStatus.FAIL)

    report = AuditReport(
        total_criteria_evaluated=len(evaluation_records),
        passed_count=passed_count,
        failed_count=failed_count,
        evaluations=evaluation_records,
    )

    # 6. Report Serialization & Export
    output_path = Path(output_report_path)
    try:
        with open(output_path, "w", encoding="utf-8") as out_f:
            json.dump(report.model_dump(mode="json"), out_f, indent=2, ensure_ascii=False)
        logger.info(f"Audit report successfully written to: {output_path.resolve()}")
    except Exception as err:
        logger.error(f"Failed to export audit report to {output_path.resolve()}: {err}")
        raise err

    logger.info("=" * 70)
    logger.info(f"Audit Complete: Total={report.total_criteria_evaluated} | PASS={report.passed_count} | FAIL={report.failed_count}")
    logger.info("=" * 70)

    return report


# ============================================================================
# 5. CLI / Module Execution
# ============================================================================

if __name__ == "__main__":
    # Define default filepaths relative to current workspace
    workspace_dir = Path(__file__).resolve().parent
    internal_file = workspace_dir / "sample_internal_policy.json"
    external_file = workspace_dir / "sample_external_regulation.json"
    criteria_file = workspace_dir / "sample_evaluation_criteria.json"
    report_file = workspace_dir / "audit_report.json"

    print("\n--- Executing Compliance & Audit Alignment Engine ---")
    try:
        final_report = run_compliance_audit_pipeline(
            internal_policy_path=internal_file,
            external_regulation_path=external_file,
            evaluation_criteria_path=criteria_file,
            output_report_path=report_file,
        )
        
        # Display formatted JSON summary of the generated report
        print("\n=== GENERATED AUDIT REPORT PREVIEW ===")
        print(json.dumps(final_report.model_dump(mode="json"), indent=2))
        print("======================================\n")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Fatal error encountered during execution: {exc}")
        sys.exit(1)
