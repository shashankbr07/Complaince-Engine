"""
PDF Ingestion & Multi-Page Document Parser
===========================================
Converts multi-page PDF documents into the relational JSON document schemas
required by the Compliance & Audit Alignment Engine:
  - Internal Policy JSON
  - External Regulation JSON
  - Evaluation Criteria JSON
"""

import io
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pymupdf  # Modern PyMuPDF import
from pypdf import PdfReader
from pydantic import BaseModel, Field

logger = logging.getLogger("PDFIngestion")


# ============================================================================
# PDF Text Extraction (Page by Page)
# ============================================================================

def extract_pages_from_pdf(pdf_source: Union[str, Path, bytes, io.BytesIO]) -> List[Dict[str, Any]]:
    """
    Extract text page-by-page from a PDF file path or byte stream.
    
    Returns:
        List of dicts: [ {"page_number": int, "text": str}, ... ]
    """
    pages_data = []

    if isinstance(pdf_source, (str, Path)):
        doc = pymupdf.open(str(pdf_source))
    elif isinstance(pdf_source, io.BytesIO):
        doc = pymupdf.open(stream=pdf_source.getvalue(), filetype="pdf")
    elif isinstance(pdf_source, bytes):
        doc = pymupdf.open(stream=pdf_source, filetype="pdf")
    else:
        raise ValueError(f"Unsupported PDF source type: {type(pdf_source)}")

    try:
        for idx, page in enumerate(doc):
            text = page.get_text("text").strip()
            pages_data.append({
                "page_number": idx + 1,
                "text": text,
            })
    finally:
        doc.close()

    return pages_data


# ============================================================================
# Robust Page-to-Section Parsers
# ============================================================================

def parse_internal_policy_pdf(
    pdf_source: Union[str, Path, bytes, io.BytesIO],
    doc_id: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse an Internal Policy PDF into the exact JSON schema expected by the compliance engine.
    """
    raw_pages = extract_pages_from_pdf(pdf_source)
    pages_list = []

    detected_title = title
    detected_id = doc_id

    for p in raw_pages:
        page_num = p["page_number"]
        page_text = p["text"]

        # Detect document title and ID from page 1 metadata lines if available
        if not detected_title:
            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            if lines:
                detected_title = lines[0]
        
        doc_id_match = re.search(r"DOCUMENT\s+ID:\s*([A-Z0-9_\-]+)", page_text, re.IGNORECASE)
        if doc_id_match and not detected_id:
            detected_id = doc_id_match.group(1)

        sections = []

        # Target explicit section patterns: e.g. "Section INT_SEC_4_1: Order Routing..." or "INT_SEC_4_1"
        explicit_pattern = re.compile(
            r"(?:Section\s+)?(INT_SEC_[A-Z0-9_]+|(?:\d+\.\d+))\s*[:–\-]?\s*([^\n]+)\n(.*?)(?=(?:(?:Section\s+)?(?:INT_SEC_|\d+\.\d+)|\Z))",
            re.DOTALL | re.IGNORECASE,
        )

        matches = list(explicit_pattern.finditer(page_text))
        if matches:
            for match in matches:
                sec_id_raw = match.group(1).strip()
                heading = match.group(2).strip()
                body = match.group(3).strip()

                if not sec_id_raw.startswith("INT_SEC_"):
                    sec_id = f"INT_SEC_{sec_id_raw.replace('.', '_')}"
                else:
                    sec_id = sec_id_raw

                # Clean heading
                heading = re.sub(r"^[–\-:\s]+", "", heading).strip()

                sections.append({
                    "section_id": sec_id,
                    "heading": heading,
                    "raw_text": body if body else page_text,
                })
        else:
            # Fallback if no explicit regex matches
            sec_tag = re.search(r"INT_SEC_[A-Z0-9_]+", page_text)
            sec_id = sec_tag.group(0) if sec_tag else f"INT_SEC_P{page_num}_1"
            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            heading = lines[0] if lines else f"Policy Section {page_num}"
            sections.append({
                "section_id": sec_id,
                "heading": heading,
                "raw_text": page_text,
            })

        pages_list.append({
            "page_number": page_num,
            "sections": sections,
        })

    return {
        "document_id": detected_id or "INT-POL-PDF",
        "document_type": "INTERNAL_POLICY",
        "title": detected_title or "Internal Policy Manual",
        "pages": pages_list,
    }


def parse_external_regulation_pdf(
    pdf_source: Union[str, Path, bytes, io.BytesIO],
    doc_id: Optional[str] = None,
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse an External Regulation PDF into the exact JSON schema expected by the engine.
    """
    raw_pages = extract_pages_from_pdf(pdf_source)
    pages_list = []

    detected_title = title
    detected_id = doc_id

    for p in raw_pages:
        page_num = p["page_number"]
        page_text = p["text"]

        if not detected_title:
            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            if lines:
                detected_title = lines[0]

        doc_id_match = re.search(r"DOCUMENT\s+ID:\s*([A-Z0-9_\-]+)", page_text, re.IGNORECASE)
        if doc_id_match and not detected_id:
            detected_id = doc_id_match.group(1)

        sections = []

        # Target explicit regulatory sections like "Section MIFID_SEC_24_3: Best Execution Mandate..."
        pattern = re.compile(
            r"(?:Section\s+)?(MIFID_SEC_[A-Z0-9_]+|Article\s+\d+(?:\(\d+\))?)\s*[:–\-]?\s*([^\n]+)\n(.*?)(?=(?:(?:Section\s+)?(?:MIFID_SEC_|Article\s+\d+)|\Z))",
            re.DOTALL | re.IGNORECASE,
        )

        matches = list(pattern.finditer(page_text))
        if matches:
            for match in matches:
                sec_id_raw = match.group(1).strip()
                heading = match.group(2).strip()
                body = match.group(3).strip()

                if not sec_id_raw.startswith("MIFID_SEC_"):
                    # normalize Article 24(3) -> MIFID_SEC_24_3
                    digits = re.findall(r"\d+", sec_id_raw)
                    sec_id = f"MIFID_SEC_{'_'.join(digits)}"
                else:
                    sec_id = sec_id_raw

                heading = re.sub(r"^[–\-:\s]+", "", heading).strip()

                sections.append({
                    "section_id": sec_id,
                    "heading": heading,
                    "raw_text": body if body else page_text,
                })
        else:
            # Fallback
            sec_tag = re.search(r"MIFID_SEC_[A-Z0-9_]+", page_text)
            sec_id = sec_tag.group(0) if sec_tag else f"MIFID_SEC_P{page_num}_1"
            lines = [l.strip() for l in page_text.splitlines() if l.strip()]
            heading = lines[0] if lines else f"Regulatory Mandate Page {page_num}"
            sections.append({
                "section_id": sec_id,
                "heading": heading,
                "raw_text": page_text,
            })

        pages_list.append({
            "page_number": page_num,
            "sections": sections,
        })

    return {
        "document_id": detected_id or "REG-MIFIDII-PDF",
        "document_type": "EXTERNAL_REGULATION",
        "title": detected_title or "Markets in Financial Instruments Directive",
        "pages": pages_list,
    }


def parse_evaluation_criteria_pdf(
    pdf_source: Union[str, Path, bytes, io.BytesIO],
    crit_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Parse an Evaluation Criteria PDF into the expected Evaluation Criteria JSON format.
    """
    raw_pages = extract_pages_from_pdf(pdf_source)
    full_text = "\n\n".join(p["text"] for p in raw_pages)

    # Detect Criteria ID (e.g. CRIT_COMP_BEST_EXEC_01)
    crit_id_match = re.search(r"CRIT_[A-Z0-9_]+", full_text)
    detected_crit_id = crit_id or (crit_id_match.group(0) if crit_id_match else "CRIT_COMP_BEST_EXEC_01")

    # Detect domain
    domain_match = re.search(r"DOMAIN:\s*([^\n|]+)", full_text, re.IGNORECASE)
    domain = domain_match.group(1).strip() if domain_match else "Investor Protection & Best Execution"

    # Detect aligned internal and external section IDs
    ext_ids = re.findall(r"MIFID_SEC_[A-Z0-9_]+", full_text)
    int_ids = re.findall(r"INT_SEC_[A-Z0-9_]+", full_text)

    if not ext_ids:
        ext_ids = ["MIFID_SEC_24_3"]
    if not int_ids:
        int_ids = ["INT_SEC_4_1"]

    # Extract Statement (between "Expected Compliance Statement:" and "Aligned Source Mappings:")
    stmt_pattern = re.search(
        r"Expected Compliance Statement:\s*(.*?)(?=\n\s*(?:Aligned Source Mappings|Aligned Sources|\Z))",
        full_text,
        re.DOTALL | re.IGNORECASE,
    )
    if stmt_pattern:
        statement = stmt_pattern.group(1).strip()
    else:
        # Fallback regex
        stmt_alt = re.search(r'(?:Statement|Rule):\s*"?([^"\n]+(?:\n[^"\n]+)*)"?', full_text, re.IGNORECASE)
        statement = stmt_alt.group(1).strip() if stmt_alt else full_text.strip()

    return {
        "evaluation_criteria_id": detected_crit_id,
        "criteria_metadata": {
            "domain": domain,
            "risk_level": "Critical",
        },
        "expected_criteria_statement": statement,
        "aligned_sources": {
            "external_regulatory_section_ids": sorted(list(set(ext_ids))),
            "internal_policy_section_ids": sorted(list(set(int_ids))),
        },
    }


# ============================================================================
# Synthetic PDF Sample Generator (Using ReportLab)
# ============================================================================

def generate_sample_pdfs_from_json(output_dir: Union[str, Path]) -> Dict[str, Path]:
    """
    Creates realistic sample PDF files from the existing sample JSON datasets
    so the user can immediately test PDF uploads and conversions.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=12,
    )
    meta_style = ParagraphStyle(
        'DocMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=15,
    )
    heading_style = ParagraphStyle(
        'SecHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#1e40af'),
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        'SecBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=16,
        textColor=colors.HexColor('#334155'),
        spaceAfter=12,
    )

    pdf_files = {}

    # 1. Internal Policy PDF
    int_pdf_path = out_path / "sample_internal_policy.pdf"
    doc_int = SimpleDocTemplate(str(int_pdf_path), pagesize=letter)
    story_int = [
        Paragraph("Global Wealth Management Operations Codebook", title_style),
        Paragraph("DOCUMENT ID: INT-POL-2026-EXEC | PAGE 1", meta_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=15),
        Paragraph("Section INT_SEC_4_1: Order Routing &amp; Vendor Selection", heading_style),
        Paragraph(
            "Our execution desk prioritizes routing client equity orders exclusively through our internal "
            "affiliate broker network. This strategy maximizes internal routing efficiency and maintains "
            "centralized volume metrics, regardless of real-time exchange fee variances or external venue "
            "latency fluctuations.",
            body_style,
        ),
    ]
    doc_int.build(story_int)
    pdf_files["internal_policy_pdf"] = int_pdf_path

    # 2. External Regulation PDF
    ext_pdf_path = out_path / "sample_external_regulation.pdf"
    doc_ext = SimpleDocTemplate(str(ext_pdf_path), pagesize=letter)
    story_ext = [
        Paragraph("Markets in Financial Instruments Directive II - Article 24", title_style),
        Paragraph("DOCUMENT ID: REG-MIFIDII-CH24 | OFFICIAL REGULATORY TEXT | PAGE 14", meta_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=15),
        Paragraph("Section MIFID_SEC_24_3: Best Execution Mandate to Clients", heading_style),
        Paragraph(
            "Investment firms must take all sufficient steps to obtain, when executing orders, the best possible "
            "result for their clients taking into account price, costs, speed, likelihood of execution and "
            "settlement, size, nature or any other consideration relevant to the execution of the order. "
            "Firms shall not structure routing configurations to favor internal execution venues over external "
            "markets if it results in higher systemic costs to the client.",
            body_style,
        ),
    ]
    doc_ext.build(story_ext)
    pdf_files["external_regulation_pdf"] = ext_pdf_path

    # 3. Evaluation Criteria PDF
    crit_pdf_path = out_path / "sample_evaluation_criteria.pdf"
    doc_crit = SimpleDocTemplate(str(crit_pdf_path), pagesize=letter)
    story_crit = [
        Paragraph("Compliance Evaluation Criteria Specification", title_style),
        Paragraph("EVALUATION CRITERIA ID: CRIT_COMP_BEST_EXEC_01 | DOMAIN: Investor Protection", meta_style),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor('#cbd5e1'), spaceAfter=15),
        Paragraph("Expected Compliance Statement:", heading_style),
        Paragraph(
            "The internal policy must explicitly enforce that client orders are routed to venues offering the best "
            "net price, lowest transaction costs, and fastest execution speed. It is strictly prohibited to prioritize "
            "internal routing networks or affiliate brokers if doing so conflicts with obtaining the absolute best "
            "economic outcome for the client.",
            body_style,
        ),
        Spacer(1, 10),
        Paragraph("Aligned Source Mappings:", heading_style),
        Paragraph("• External Regulatory Section ID: MIFID_SEC_24_3", body_style),
        Paragraph("• Internal Policy Section ID: INT_SEC_4_1", body_style),
    ]
    doc_crit.build(story_crit)
    pdf_files["evaluation_criteria_pdf"] = crit_pdf_path

    logger.info(f"Generated sample PDFs in: {out_path.resolve()}")
    return pdf_files


if __name__ == "__main__":
    current_dir = Path(__file__).resolve().parent
    generated = generate_sample_pdfs_from_json(current_dir)
    print("Generated PDFs:", generated)
