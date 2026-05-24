# Future Improvements

This file tracks planned enhancements that are out of scope for the current release.
Items are ordered by implementation priority.

---

## Item 5 — OCR misread tolerance in pattern matching

**Problem:** Optical character recognition (OCR) and some low-quality PDF generators
confuse visually similar characters: the letter O for digit 0, lowercase l or uppercase
I for digit 1, S for 5. A scanned SSN `1l3-4S-6789` would pass through undetected
because the current patterns only match `\d` (true digit characters).

**Proposed approach:** Replace `\d` with a character class that includes OCR confusables,
following the technique used by [JoshData/pdf-redactor](https://github.com/JoshData/pdf-redactor):

```python
DIGIT_OR_OCR = r'[0-9OoIliS]'
SSN_PATTERN  = rf'\b(?!000|666){DIGIT_OR_OCR}{{3}}[- ](?!00){DIGIT_OR_OCR}{{2}}[- ](?!0000){DIGIT_OR_OCR}{{4}}\b'
```

**Considerations:**
- Increases false-positive risk on text that contains runs of these letters (e.g. `Oil-lo-IlOI`).
- Only meaningful on PDFs that went through OCR before reaching this tool.
- Should be offered as an opt-in flag (`--ocr-tolerance`) rather than the default.

---

## Item 6 — OCR support for image-only pages

**Problem:** The tool currently detects image-only pages (pages with fewer than 50
extractable text characters) and skips them with a warning. Any SSNs printed on a
scanned or photographed page are invisible to the engine.

**Proposed approach:** Integrate [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
via `pytesseract` as an optional dependency, following the render-then-OCR strategy
used by [SpectrePDF](https://github.com/udiram/SpectrePDF):

1. Detect image-only page (existing logic).
2. Render page to high-resolution raster via `page.get_pixmap(dpi=300)`.
3. Pass image to Tesseract with `--psm 6` (uniform block of text).
4. Receive word-level bounding boxes (`image_to_data()` with `Output.DICT`).
5. Match SSN/EIN patterns against the OCR text.
6. Map word coordinates back to PDF points (`pixel / dpi * 72`).
7. Draw solid black rectangles over matched regions on the raster image.
8. Re-embed the modified raster as the page image.

**Considerations:**
- Requires `pytesseract` and a local Tesseract installation — non-trivial first-time setup.
- Rasterised output loses text searchability (acceptable trade-off for scanned source material).
- Coordinate mapping between raster pixels and PDF points must account for page rotation.
- Accuracy depends on scan quality; low-DPI inputs (below 150 DPI) give unreliable results.
- Should degrade gracefully: if `pytesseract` is not installed, fall back to the current
  skip-with-warning behaviour and print an install hint.
- Suggested install guard:

```python
try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
```

**Estimated effort:** Large — 2–3 days including coordinate mapping, tests with real
scanned PDFs, and graceful fallback handling.

---

*Last updated: 2026-05-22*
*Improvements 1–4 were implemented in commit history — see git log for details.*
