"""
PDF SSN/EIN Redaction Engine
Usage: python redact_ssn.py <input_pdf_or_dir> [--output <path>]
"""

import io
import gc
import re
import argparse
import logging
from pathlib import Path
import fitz  # PyMuPDF

# Optional Tesseract OCR Support
try:
    import pytesseract
    from PIL import Image
    pytesseract.get_tesseract_version()
    HAS_TESSERACT = True
except Exception:
    HAS_TESSERACT = False

# Library-safe: callers configure logging; CLI entry point sets up handlers in main().
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# Negative lookaheads exclude ranges the SSA has never issued:
#   prefix 000/666, middle group 00, suffix 0000
SSN_PATTERN = r'\b(?!000|666)\d{3}[- ](?!00)\d{2}[- ](?!0000)\d{4}\b'
EIN_PATTERN  = r'\b\d{2}[- ]\d{7}\b'

# Partially masked identifiers — some of the 9 digit positions replaced by a
# placeholder character.  Common placeholder chars: X x * #
# Some government forms (e.g. SSA-1099) also use 0 (zero) as a placeholder.
_MASK_CHARS  = r'Xx*#'
_DM          = rf'[\d{_MASK_CHARS}]'       # digit or mask char — one position
_MASK_OR_ZERO = rf'[{_MASK_CHARS}0]'       # mask char or zero-as-placeholder

# Separator used between SSN/EIN groups in PDFs — covers hyphen, space,
# non-breaking space (U+00A0), non-breaking hyphen (U+2011), and en-dash (U+2013).
_SEP = '[- ‑– ]'

# SSN/ITIN partial A: last 4 positions are standard mask chars (X x * #).
# First 5 positions may be any digit or mask char — no invalid-range exclusions
# so that 127-00-XXXX (middle group 00 is technically invalid but appears in
# real partially-masked SSA forms) is still caught.
SSN_PARTIAL_PATTERN = rf'\b{_DM}{{3}}{_SEP}{_DM}{{2}}{_SEP}[{_MASK_CHARS}]{{4}}\b'

# SSN/ITIN partial B: for forms that use 0 as a placeholder digit (e.g. SSA-1099
# renders xxx-00-0000 or xx5-00-0000).  Requires the first group to contain at
# least one mask char (proving intent to mask) so that plain invalid-range SSNs
# such as 000-xx-xxxx are not caught here — those remain excluded by SSN_PATTERN.
_SSN_PARTIAL_ZERO = (
    rf'\b(?!\d{{3}}{_SEP})'          # first group must NOT be all pure digits
    rf'{_DM}{{3}}{_SEP}'              # first group: digit or mask chars
    rf'{_DM}{{2}}{_SEP}'             # middle group: digit or mask chars
    rf'{_MASK_OR_ZERO}{{4}}\b'        # last group: mask char or zero placeholder
)

# EIN partial: 2-digit prefix stays as pure digits; the 7-digit body accepts any
# combination of digits and mask chars across all 7 positions.
# e.g. 38-4XXXXXX (1+6), 34-800XXXX (3+4), 89-7XXXXXX (1+6), 34-XXXXXXX (0+7)
EIN_PARTIAL_PATTERN = rf'\b\d{{2}}{_SEP}{_DM}{{7}}\b'

FILL_COLOR   = (0, 0, 0)
REDACTED_SUFFIX = "_redacted"
WIDGET_ROW_BUCKET = 8   # vertical tolerance (points) for grouping widgets on the same row


def compile_patterns(ocr_tolerance: bool = False) -> dict:
    d_class = r'0-9OoIliS' if ocr_tolerance else r'0-9'
    d = rf'[{d_class}]'
    mask_chars = r'Xx*#'
    dm = rf'[{d_class}{mask_chars}]'
    mask_or_zero = rf'[{mask_chars}0]'
    sep = '[- ‑– ]'
    
    ssn_pat = rf'\b(?!000|666){d}{{3}}{sep}(?!00){d}{{2}}{sep}(?!0000){d}{{4}}\b'
    ein_pat = rf'\b{d}{{2}}{sep}{d}{{7}}\b'
    
    ssn_partial_pat = rf'\b{dm}{{3}}{sep}{dm}{{2}}{sep}[{mask_chars}]{{4}}\b'
    
    ssn_partial_zero_pat = (
        rf'\b(?!{d}{{3}}{sep})'
        rf'{dm}{{3}}{sep}'
        rf'{dm}{{2}}{sep}'
        rf'{mask_or_zero}{{4}}\b'
    )
    
    ein_partial_pat = rf'\b{d}{{2}}{sep}{dm}{{7}}\b'

    return {
        "SSN/ITIN":                    re.compile(ssn_pat),
        "SSN/ITIN (partial)":          re.compile(ssn_partial_pat),
        "SSN/ITIN (partial, 0-masked)": re.compile(ssn_partial_zero_pat),
        "EIN":                         re.compile(ein_pat),
        "EIN (partial)":               re.compile(ein_partial_pat),
    }



def _mask_value(s: str) -> str:
    """Return a masked form showing only the last 4 digits, e.g. [***-**-6789]."""
    digits = re.sub(r'\D', '', s)
    return f"[***-**-{digits[-4:]}]" if len(digits) >= 4 else "[***]"


def find_sensitive_matches(text: str, compiled_patterns: dict, ocr_tolerance: bool = False) -> list:
    matches = []
    for type_name, pattern in compiled_patterns.items():
        for m in pattern.finditer(text):
            match_str = m.group()
            # If ocr_tolerance is True, enforce that the match contains at least 3 true digits
            if ocr_tolerance and sum(c.isdigit() for c in match_str) < 3:
                continue
            matches.append((type_name, match_str))
    return matches


def _any_pattern_matches(parts: list, compiled_patterns: dict) -> bool:
    """Return True if joining parts with any separator matches at least one pattern."""
    return any(
        pat.search(sep.join(parts))
        for sep in (" ", "-", "")
        for pat in compiled_patterns.values()
    )


def is_likely_image_only(page, page_text: str = None) -> bool:
    text = page_text if page_text is not None else page.get_text("text")
    return len(text.strip()) == 0


def _redact_widgets(page, compiled_patterns: dict) -> int:
    """Pass 2: scan AcroForm widget fields — handles IRS-style split SSN fields."""
    widget_data = []
    for w in page.widgets():
        val = (w.field_value or "").strip()
        if val:
            widget_data.append((val, w.rect, w))
    if not widget_data:
        return 0

    widget_data.sort(key=lambda x: (round(x[1].y0 / WIDGET_ROW_BUCKET) * WIDGET_ROW_BUCKET,
                                     x[1].x0))
    redacted = 0
    used = set()

    def _redact_widget(widget, rect):
        try:
            widget.field_value = ""
            widget.update()
        except Exception:
            pass  # read-only or non-text widget — still redact visually
        page.add_redact_annot(rect, fill=FILL_COLOR, text="", cross_out=False)

    for i, (val, rect, widget) in enumerate(widget_data):
        if _any_pattern_matches([val], compiled_patterns):
            _redact_widget(widget, rect)
            redacted += 1
            used.add(i)

    for window in (3, 2):
        for i in range(len(widget_data) - window + 1):
            if any(i + j in used for j in range(window)):
                continue
            group = widget_data[i:i + window]
            ys = [item[1].y0 for item in group]
            if max(ys) - min(ys) > WIDGET_ROW_BUCKET * 2:
                continue
            if _any_pattern_matches([item[0] for item in group], compiled_patterns):
                for _, rect, widget in group:
                    _redact_widget(widget, rect)
                    redacted += 1
                for j in range(window):
                    used.add(i + j)

    return redacted


def _redact_word_proximity(page, compiled_patterns: dict, skip_normalized: set) -> int:
    """Pass 3: find SSN/EIN patterns spanning adjacent text fragments.

    skip_normalized: digit-only strings already successfully redacted by Pass 1,
    so we don't double-count when the same SSN is found as contiguous text.
    """
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    if not words:
        return 0

    rows: dict = {}
    for idx, w in enumerate(words):
        key = round(w[1] / 5) * 5
        rows.setdefault(key, []).append((idx, w))

    redacted = 0
    used_indices: set = set()

    for row_items in rows.values():
        row_items.sort(key=lambda x: x[1][0])
        for window in range(2, 5):
            for i in range(len(row_items) - window + 1):
                group_items = row_items[i:i + window]
                indices = [x[0] for x in group_items]
                if any(idx in used_indices for idx in indices):
                    continue
                group = [x[1] for x in group_items]
                texts = [g[4] for g in group]
                if not all(re.fullmatch(r'[\d\- ]+', t) for t in texts):
                    continue
                # sep-independent normalization: joining then stripping gives same result for any sep
                if re.sub(r'\D', '', "".join(texts)) in skip_normalized:
                    continue  # Pass 1 already handled this exact match
                if _any_pattern_matches(texts, compiled_patterns):
                    for g in group:
                        page.add_redact_annot(fitz.Rect(g[0], g[1], g[2], g[3]),
                                              fill=FILL_COLOR, text="", cross_out=False)
                    redacted += 1
                    used_indices.update(indices)

    return redacted


def redact_page(page, compiled_patterns: dict, page_text: str = None,
                ocr_tolerance: bool = False) -> dict:
    redacted_count = 0
    missed_count = 0
    warnings = []
    p1_found_normalized: set = set()

    text = page_text if page_text is not None else page.get_text("text")
    matches = find_sensitive_matches(text, compiled_patterns, ocr_tolerance=ocr_tolerance)
    str_to_type = {m[1]: m[0] for m in matches}

    for match_str, type_name in str_to_type.items():
        rects = page.search_for(match_str)
        if not rects:
            # Log without the SSN value — logger output may reach log files.
            logger.warning("1 %s match found in text layer but could not be visually located",
                           type_name)
            # User-facing warning uses masked form only.
            warnings.append(
                f"1 {type_name} match {_mask_value(match_str)} found in text but not "
                f"visually locatable — check output file manually"
            )
            missed_count += 1
            continue
        p1_found_normalized.add(re.sub(r'[-\s]', '', match_str))
        for rect in rects:
            page.add_redact_annot(rect, fill=FILL_COLOR, text="", cross_out=False)
            redacted_count += 1

    redacted_count += _redact_widgets(page, compiled_patterns)
    redacted_count += _redact_word_proximity(page, compiled_patterns, p1_found_normalized)

    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_PIXELS,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
    )

    return {"redacted": redacted_count, "missed": missed_count, "warnings": warnings}


def _strip_metadata(doc) -> None:
    """Remove info dict, XMP stream, and embedded file attachments."""
    doc.set_metadata({})
    try:
        doc.del_xml_metadata()
    except Exception:
        pass
    # Remove embedded file attachments — these survive text redaction unexamined.
    try:
        for i in range(doc.embfile_count() - 1, -1, -1):
            doc.embfile_del(i)
    except Exception:
        pass


def verify_redaction(output_path: str, compiled_patterns: dict) -> list:
    """Re-open the saved file and confirm no SSN/EIN patterns survived."""
    failures = []
    try:
        doc = fitz.open(output_path)
        for page_num, page in enumerate(doc, start=1):
            text = page.get_text("text")
            for type_name, pattern in compiled_patterns.items():
                for m in pattern.finditer(text):
                    # Never echo raw digits for targeted entries; mask general matches.
                    if type_name.startswith("Targeted"):
                        display = "[redacted]"
                    else:
                        display = _mask_value(m.group())
                    failures.append(
                        f"p.{page_num}: {type_name} {display} still present in text layer"
                    )
            for w in page.widgets():
                val = (w.field_value or "").strip()
                if val:
                    for type_name, pattern in compiled_patterns.items():
                        if pattern.search(val):
                            failures.append(
                                f"p.{page_num}: {type_name} still present in form field value"
                            )
        doc.close()
    except Exception as e:
        failures.append(f"Verification error: {e}")
    return failures


def redact_scanned_page(page, compiled_patterns: dict, ocr_tolerance: bool = False) -> dict:
    """Redact an image-only page using Pytesseract OCR."""
    redacted_count = 0
    # 1. Render page at 300 DPI
    pix = page.get_pixmap(dpi=300)
    img_data = pix.tobytes("png")
    pil_img = Image.open(io.BytesIO(img_data))
    
    # 2. Get OCR data
    ocr_data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT)
    n_boxes = len(ocr_data['text'])
    
    # 3. Group words by line
    lines = {}
    for i in range(n_boxes):
        t = ocr_data['text'][i].strip()
        if not t:
            continue
        key = (ocr_data['block_num'][i], ocr_data['line_num'][i])
        lines.setdefault(key, []).append({
            "text": t,
            "left": ocr_data['left'][i],
            "top": ocr_data['top'][i],
            "width": ocr_data['width'][i],
            "height": ocr_data['height'][i]
        })
        
    used_coords = set()
    
    def to_pdf_rect(l, t, w, h):
        return fitz.Rect(l * 72.0 / 300.0, t * 72.0 / 300.0, 
                         (l + w) * 72.0 / 300.0, (t + h) * 72.0 / 300.0)
    
    for line_words in lines.values():
        line_words.sort(key=lambda x: x['left'])
        
        # Pass A: Single word match
        for idx, w in enumerate(line_words):
            if _any_pattern_matches([w['text']], compiled_patterns):
                if ocr_tolerance and sum(c.isdigit() for c in w['text']) < 3:
                    continue
                rect = to_pdf_rect(w['left'], w['top'], w['width'], w['height'])
                page.add_redact_annot(rect, fill=FILL_COLOR, text="", cross_out=False)
                redacted_count += 1
                used_coords.add(idx)
        
        # Pass B: Proximity sliding window (sizes 2 to 4)
        for window in range(2, 5):
            for idx in range(len(line_words) - window + 1):
                if any((idx + j) in used_coords for j in range(window)):
                    continue
                group = line_words[idx : idx + window]
                texts = [w['text'] for w in group]
                
                if _any_pattern_matches(texts, compiled_patterns):
                    if ocr_tolerance and sum(c.isdigit() for c in "".join(texts)) < 3:
                        continue
                    for w in group:
                        rect = to_pdf_rect(w['left'], w['top'], w['width'], w['height'])
                        page.add_redact_annot(rect, fill=FILL_COLOR, text="", cross_out=False)
                    redacted_count += 1
                    for j in range(window):
                        used_coords.add(idx + j)
                        
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_PIXELS,
        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
    )
    return {"redacted": redacted_count, "missed": 0, "warnings": []}


def redact_pdf(input_path: str, output_path: str, target_ssns: list = None,
               ocr_tolerance: bool = False) -> dict:
    try:
        doc = fitz.open(input_path)
    except fitz.FileDataError as e:
        logger.error("Could not open '%s': %s", input_path, type(e).__name__)
        return {"status": "error", "error": str(e)}

    if doc.needs_pass:
        doc.close()
        return {"status": "encrypted"}

    compiled_patterns = compile_patterns(ocr_tolerance=ocr_tolerance)

    if target_ssns:
        for i, ssn in enumerate(target_ssns, 1):
            digits = re.sub(r'\D', '', ssn)
            if len(digits) == 9:
                compiled_patterns[f"Targeted-{i}"] = re.compile(
                    rf'\b(?:{digits[:3]}{_SEP}{digits[3:5]}{_SEP}{digits[5:]}|{digits})\b'
                )

    total_redacted = 0
    total_missed = 0
    all_warnings = []
    page_results = []
    image_only_pages = 0

    for page_num, page in enumerate(doc, start=1):
        page_text = page.get_text("text")          # single extraction per page
        if is_likely_image_only(page, page_text=page_text):
            if HAS_TESSERACT:
                logger.warning("p.%d: Page is image-only. Running OCR redaction...", page_num)
                result = redact_scanned_page(page, compiled_patterns, ocr_tolerance=ocr_tolerance)
                total_redacted += result["redacted"]
                page_results.append({
                    "page": page_num,
                    "redacted": result["redacted"],
                    "missed": 0,
                    "skipped": False,
                    "ocr_applied": True
                })
            else:
                msg = "Page skipped — likely image-only (Tesseract OCR required for automatic scan redaction)"
                logger.warning("p.%d: %s", page_num, msg)
                all_warnings.append(
                    f"WARNING p.{page_num}: {msg}. "
                    f"To enable automatic scanned page redaction, please install Google Tesseract OCR "
                    f"and 'pytesseract' (pip install pytesseract)."
                )
                image_only_pages += 1
                page_results.append({"page": page_num, "redacted": 0, "missed": 0, "skipped": True})
            continue

        result = redact_page(page, compiled_patterns, page_text, ocr_tolerance=ocr_tolerance)
        for w in result["warnings"]:
            all_warnings.append(f"WARNING p.{page_num}: {w}")
        total_redacted += result["redacted"]
        total_missed += result["missed"]
        page_results.append({
            "page": page_num,
            "redacted": result["redacted"],
            "missed": result["missed"],
            "skipped": False,
        })

    if image_only_pages == len(doc):
        doc.close()
        return {"status": "image_only"}

    _strip_metadata(doc)
    doc.save(output_path, garbage=4, deflate=True, clean=True)
    doc.close()

    verification_failures = verify_redaction(output_path, compiled_patterns)

    # Explicit cleanup: remove references to compiled patterns (which contain
    # targeted SSN digit strings), purge the re cache, and request immediate GC.
    del compiled_patterns
    re.purge()
    gc.collect()

    return {
        "status": "success",
        "output": output_path,
        "redacted": total_redacted,
        "missed": total_missed,
        "warnings": all_warnings,
        "pages": page_results,
        "verification_failures": verification_failures,
    }


def process_single(input_path: str, output_path: str = None,
                   target_ssns: list = None, ocr_tolerance: bool = False) -> dict:
    input_p = Path(input_path)

    if output_path is None:
        output_path = str(input_p.parent / (input_p.stem + REDACTED_SUFFIX + input_p.suffix))

    if str(Path(input_path).resolve()) == str(Path(output_path).resolve()):
        return {"status": "error", "error": "Input and output paths are the same — refusing to overwrite source"}

    result = redact_pdf(input_path, output_path, target_ssns=target_ssns, ocr_tolerance=ocr_tolerance)
    result["input"] = input_path
    if "output" not in result:
        result["output"] = output_path
    return result


def process_directory(input_dir: str, output_dir: str = None,
                      target_ssns: list = None, ocr_tolerance: bool = False) -> list:
    input_p = Path(input_dir)

    if output_dir is None:
        output_p = input_p / "redacted"
    else:
        output_p = Path(output_dir)

    output_p.mkdir(parents=True, exist_ok=True)

    pdf_files = list(input_p.glob("*.pdf"))
    results = []

    for pdf_file in pdf_files:
        out_file = output_p / (pdf_file.stem + REDACTED_SUFFIX + pdf_file.suffix)
        result = process_single(str(pdf_file), str(out_file), target_ssns=target_ssns, ocr_tolerance=ocr_tolerance)
        result["filename"] = pdf_file.name
        results.append(result)

    return results


def format_summary(results: list) -> str:
    lines = ["=== REDACTION SUMMARY ==="]
    total_redacted = 0
    total_missed = 0
    files_with_matches = 0
    files_skipped = 0

    for r in results:
        filename = r.get("filename") or Path(r.get("input", "unknown")).name
        output = r.get("output", "")
        out_name = Path(output).name if output else ""
        status = r.get("status", "unknown")

        if status == "success":
            redacted = r.get("redacted", 0)
            missed = r.get("missed", 0)
            total_redacted += redacted
            total_missed += missed
            if redacted > 0:
                files_with_matches += 1
            missed_note = f" | {missed} missed — see warnings" if missed > 0 else " | 0 missed"
            lines.append(f"{filename:<25} -> {out_name:<35} [{redacted} redacted{missed_note}]")
            pages = r.get("pages", [])
            impacted = [str(p["page"]) for p in pages if p.get("redacted", 0) > 0]
            if impacted:
                lines.append(f"  Redacted on pages: {', '.join(impacted)}")
            for w in r.get("warnings", []):
                lines.append(f"  {w}")
            for vf in r.get("verification_failures", []):
                lines.append(f"  *** VERIFY FAIL: {vf}")
            if pages:
                lines.append("")
                lines.append("  Page  Redacted")
                lines.append("  ----  --------")
                for p in pages:
                    if p.get("skipped"):
                        lines.append(f"  {p['page']:>4}         —  (image-only, skipped)")
                    elif p["redacted"] > 0:
                        n = p["redacted"]
                        word = "match" if n == 1 else "matches"
                        lines.append(f"  {p['page']:>4}  {n:>8}  ** {n} {word} redacted")
                    else:
                        lines.append(f"  {p['page']:>4}         0")
                lines.append("")
        elif status == "image_only":
            files_skipped += 1
            lines.append(f"{filename:<25} -> SKIPPED: all pages image-only (OCR required)")
        elif status == "encrypted":
            files_skipped += 1
            lines.append(f"{filename:<25} -> SKIPPED: password-protected")
        elif status == "error":
            files_skipped += 1
            lines.append(f"{filename:<25} -> ERROR: {r.get('error', 'unknown error')}")

    total_vf = sum(
        len(r.get("verification_failures", []))
        for r in results if r.get("status") == "success"
    )

    lines.append("")
    lines.append(f"Total files processed:   {len(results)}")
    lines.append(f"Total matches redacted:  {total_redacted}")
    if total_missed > 0:
        lines.append(f"*** Total matches MISSED:    {total_missed} *** <-- REVIEW WARNINGS ABOVE")
    else:
        lines.append(f"Total matches MISSED:    {total_missed}")
    if total_vf > 0:
        lines.append(f"*** Verification FAILURES:   {total_vf} *** MANUAL REVIEW REQUIRED")
    else:
        lines.append(f"Verification:            PASSED")
    lines.append(f"Files with matches:      {files_with_matches}")
    lines.append(f"Files skipped/errors:    {files_skipped}")
    return "\n".join(lines)


def print_summary(results: list) -> None:
    print("\n" + format_summary(results))


def main():
    # Configure logging only when running as a CLI tool, not when used as a library.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Redact SSNs and EINs from PDF files")
    parser.add_argument("input", help="Path to a PDF file or directory of PDFs")
    parser.add_argument("--output", help="Custom output path (file or directory)", default=None)
    parser.add_argument("--ocr-tolerance", action="store_true", help="Enable OCR confusable misread tolerance")
    args = parser.parse_args()

    input_p = Path(args.input)

    if input_p.is_dir():
        results = process_directory(str(input_p), args.output, ocr_tolerance=args.ocr_tolerance)
        for r in results:
            if "filename" not in r:
                r["filename"] = Path(r.get("input", "unknown")).name
    elif input_p.is_file():
        result = process_single(str(input_p), args.output, ocr_tolerance=args.ocr_tolerance)
        result["filename"] = input_p.name
        results = [result]
    else:
        print(f"Error: '{args.input}' is not a valid file or directory.")
        raise SystemExit(1)

    print_summary(results)


if __name__ == "__main__":
    main()
