# Future Improvements

This file tracks planned architectural enhancements and performance optimizations for future development cycles of **Nullify**.

---

## 🚀 Recently Completed Enhancements

The following major updates were successfully implemented and merged into the core engine on **May 24, 2026**:

1. **Item 5 — OCR Misread Tolerance:** Fuzzy character classes (`[0-9OoIliS]`) now detect numbers misread by OCR engines due to visual similarity (e.g., matching `l` as `1` or `S` as `5`). Integrates with `--ocr-tolerance` (CLI) and a GUI toggle checkbutton. Features robust post-match validation requiring $\ge 3$ true digits to eliminate false positives in natural language text.
2. **Item 6 — Scanned Page OCR Redaction:** Added graceful support for scanned/image-only PDFs using Pillow and `pytesseract`. Renders document pages at 300 DPI, runs OCR, translates pixel bounding coordinates into PDF grid space, and applies vector redact annotations. Falls back gracefully with clear, actionable environment instructions if Google Tesseract is missing.

---

## 🔮 Next-Generation Roadmap

The following list tracks planned optimizations and features for subsequent releases:

### 1. Multithreaded OCR Processing for High-Volume PDFs
* **Problem:** Running Google Tesseract OCR sequentially on scanned multi-page documents can become slow on standard machines.
* **Proposed Approach:** Implement a thread pool executor (`concurrent.futures.ThreadPoolExecutor`) to run OCR in parallel across pages. This will optimize CPU core usage and scale processing speeds linearly with local compute capacity.

### 2. Auto-Detection of Document Page Rotation
* **Problem:** Scanned pages may be loaded sideways (90°/270°) or upside-down (180°). Tesseract OCR yields degraded accuracy on misrotated pages, and coordinate translations fail if page rotation is ignored.
* **Proposed Approach:** Query `page.rotation` using PyMuPDF and automatically rotate page coordinates/matrices during coordinate mapping. Integrate Tesseract’s orientation detection (OSD mode) to automatically pre-rotate raw images before running OCR.

### 3. Customizable Redaction Appearance
* **Problem:** The tool currently hardcodes solid black blocks (`(0, 0, 0)`) for all redaction areas. Certain filing workflows prefer solid white blocks, grey textures, or transparent boundaries with customizable border guidelines.
* **Proposed Approach:** Expose a color picker in the GUI and a `--color` (or `--fill`) argument in the CLI to allow users to select from a set of standard colors (black, white, dark grey, light grey) or input a custom hex code.

---
*Last updated: May 24, 2026*
