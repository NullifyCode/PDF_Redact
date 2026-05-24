"""
Generate test PDF files for the redaction test suite.
All files are created programmatically — no manual steps required.
"""

from pathlib import Path
import fitz  # PyMuPDF


TEST_DIR = Path(__file__).parent / "test_files"


def _new_doc_with_text(text: str) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), text, fontsize=11)
    return doc


def _save_doc(doc: fitz.Document, filename: str, **kw) -> None:
    doc.save(str(TEST_DIR / filename), **kw)
    doc.close()


def create_test_standard():
    """One SSN, one EIN, one ITIN, one phone, one date — all selectable text."""
    text = (
        "Tax Document\n\n"
        "SSN: 123-45-6789\n"
        "EIN: 12-3456789\n"
        "ITIN: 912-34-5678\n"
        "Phone: 713-555-1234\n"
        "Date: 12-31-2024\n"
    )
    _save_doc(_new_doc_with_text(text), "test_standard.pdf")


def create_test_multi():
    """SSN printed five times on one page."""
    lines = "\n".join([f"Record {i}: SSN 123-45-6789" for i in range(1, 6)])
    _save_doc(_new_doc_with_text(lines), "test_multi.pdf")


def create_test_clean():
    """Normal paragraph text with no sensitive numbers."""
    text = (
        "This is a clean document.\n\n"
        "It contains no Social Security Numbers, EINs, or ITINs.\n"
        "The quick brown fox jumps over the lazy dog.\n"
        "No sensitive data here at all.\n"
    )
    _save_doc(_new_doc_with_text(text), "test_clean.pdf")


def create_test_multipage():
    """SSN on page 1, plain text page 2, EIN on page 3."""
    doc = fitz.open()

    doc.new_page().insert_text((72, 100),
        "Tax Record — Page 1 of 3\nSocial Security Number: 123-45-6789\nFiler: John Doe",
        fontsize=11)

    doc.new_page().insert_text((72, 100),
        "Continuation page — Page 2 of 3\nNo sensitive information on this page.\nSee other pages.",
        fontsize=11)

    doc.new_page().insert_text((72, 100),
        "Business Record — Page 3 of 3\nEmployer Identification Number: 12-3456789\nEntity: ACME LLC",
        fontsize=11)

    _save_doc(doc, "test_multipage.pdf")


def create_test_image_only():
    """A single blank page with no text content whatsoever."""
    doc = fitz.open()
    doc.new_page()
    _save_doc(doc, "test_image_only.pdf")


def create_test_partial_mask():
    """Partially masked SSNs and EINs — various placeholder styles and masking levels."""
    text = (
        "Partially masked identifiers (all should be redacted):\n\n"
        "  SSN X-masked (dash):        328-00-XXXX\n"
        "  SSN X-masked (space):       328 00 XXXX\n"
        "  SSN X-masked (SSA-1099):    127-00-XXXX\n"
        "  SSN 0-masked, x prefix:     xxx-00-0000\n"
        "  SSN 0-masked, mixed prefix: xx5-00-0000\n"
        "  EIN 3-visible + 4-masked:   34-800XXXX\n"
        "  EIN 3-visible + 4-masked:   22-700XXXX\n"
        "  EIN 1-visible + 6-masked:   38-4XXXXXX\n"
        "  EIN 1-visible + 6-masked:   89-7XXXXXX\n"
    )
    _save_doc(_new_doc_with_text(text), "test_partial_mask.pdf")


def create_test_invalid_ssn():
    """PDF with invalid SSN ranges (must NOT be redacted) and one valid SSN."""
    text = (
        "Invalid SSN ranges — should NOT be redacted:\n"
        "  000-45-6789  (prefix 000 never issued)\n"
        "  666-45-6789  (prefix 666 never issued)\n"
        "  123-00-6789  (middle group 00 never issued)\n"
        "  123-45-0000  (suffix 0000 never issued)\n\n"
        "Valid SSN — should be redacted:\n"
        "  123-45-6789\n"
    )
    _save_doc(_new_doc_with_text(text), "test_invalid_ssn.pdf")


def create_test_acroform_ssn():
    """AcroForm PDF with SSN split across three widget fields (IRS 1040 style)."""
    doc = fitz.open()
    page = doc.new_page()

    page.insert_text((72, 100), "Your social security number", fontsize=11)

    for name, value, x0, x1 in [
        ("ssn_part1", "123",  72,  110),
        ("ssn_part2", "45",  115,  145),
        ("ssn_part3", "6789", 150, 200),
    ]:
        w = fitz.Widget()
        w.field_type  = fitz.PDF_WIDGET_TYPE_TEXT
        w.field_name  = name
        w.field_value = value
        w.rect = fitz.Rect(x0, 115, x1, 130)
        page.add_widget(w)

    page.insert_text((72, 160), "Total Income: 75000", fontsize=11)
    _save_doc(doc, "test_acroform_ssn.pdf")


def create_test_irs_format():
    """Space-separated SSNs as extracted from IRS fillable form PDFs."""
    text = (
        "Your social security number\n\n"
        "123 45 6789\n\n"
        "Spouse's social security number\n\n"
        "987 65 4321\n"
    )
    _save_doc(_new_doc_with_text(text), "test_irs_format.pdf")


def create_test_encrypted():
    """A valid PDF protected with AES-256 user password."""
    doc = _new_doc_with_text("Password-protected document.\nSSN: 123-45-6789\n")
    _save_doc(doc, "test_encrypted.pdf",
              encryption=fitz.PDF_ENCRYPT_AES_256,
              owner_pw="owner123",
              user_pw="user123")


def create_test_corrupt():
    """A .pdf file containing garbage bytes — not a valid PDF."""
    (TEST_DIR / "test_corrupt.pdf").write_bytes(
        b"NOTAPDF###\x00\xff\xfe\xfd this is not a valid PDF file"
    )


def generate_all(quiet: bool = False):
    TEST_DIR.mkdir(parents=True, exist_ok=True)
    create_test_partial_mask()
    create_test_standard()
    create_test_multi()
    create_test_clean()
    create_test_multipage()
    create_test_image_only()
    create_test_invalid_ssn()
    create_test_acroform_ssn()
    create_test_irs_format()
    create_test_encrypted()
    create_test_corrupt()
    if not quiet:
        print(f"Test files created in: {TEST_DIR}")
        for name in ("test_standard.pdf", "test_multi.pdf", "test_clean.pdf",
                     "test_multipage.pdf", "test_image_only.pdf",
                     "test_invalid_ssn.pdf", "test_acroform_ssn.pdf",
                     "test_irs_format.pdf", "test_encrypted.pdf", "test_corrupt.pdf"):
            print(f"  {name}")


if __name__ == "__main__":
    generate_all()
