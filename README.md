# SSN / EIN Redaction Tool

## What this program does

This tool scans PDF files and **permanently redacts** Social Security Numbers (SSNs),
Individual Taxpayer Identification Numbers (ITINs), and Employer Identification Numbers (EINs).
Matched numbers are replaced with solid black rectangles — not hidden behind a layer, but
physically removed from the file so they cannot be recovered by selecting text, searching,
or stripping annotations.

**How detection works — three passes per page:**
1. **Text layer** — regex on extracted text, then `search_for()` to place the redaction rectangle.
2. **AcroForm widgets** — reads every form field value directly; handles IRS 1040-style SSNs
   that are split across three separate boxes (###, ##, ####).
3. **Word proximity** — reassembles adjacent numeric word tokens on the same baseline;
   catches SSNs rendered as individually-positioned characters where `search_for()` fails.

**What formats are detected:**
- Standard dash-separated: `123-45-6789`
- Space-separated (IRS fillable forms): `123 45 6789`
- EINs: `12-3456789` and `12 3456789`
- ITINs (900-series): same pattern as SSNs

**What is not detected by design:**
- Unseparated 9-digit strings like `123456789` — too many innocent matches
- Invalid SSN ranges that the SSA has never issued (prefix `000`/`666`, middle `00`, suffix `0000`)

**Limitation:** Detection works only on PDFs where numbers exist as selectable text.
Pages with zero selectable characters (pure scans) are detected and skipped with a warning — use OCR software on those first.

---

## Requirements

- Windows PC
- Python 3.8 or higher
- PyMuPDF (installed via `requirements_redact.txt`)

---

## First-time setup

1. **Install Python** — download from [python.org](https://python.org) and run the installer.
   Check **Add Python to PATH** during setup.
2. **Open a Command Prompt** in the `pdf_redactor` folder (Shift + right-click inside the
   folder → "Open PowerShell window here").
3. **Install dependencies:**
   ```
   pip install -r requirements_redact.txt
   ```
4. **Create a desktop shortcut** for the GUI:
   - Right-click `redact_gui.pyw` → Send to → Desktop (create shortcut).
   - The `.pyw` extension makes Windows run it without a console window.

---

## How to use — Desktop (GUI)

1. Double-click the **SSN / EIN Redaction Tool** shortcut (or `redact_gui.pyw` directly).
2. Choose **Single PDF file** or **All PDFs in folder**.
3. Click **Browse** and select your file or folder.
4. The output path fills in automatically. Click **Change** to override it.
5. *(Optional)* Enter up to **6 specific SSNs** in the TARGET section to hunt for those
   numbers in addition to the standard sweep. Fields are masked and cleared from memory
   immediately after redaction begins.
6. Click **Run Redaction**.
7. Read the Results panel. If the status bar shows a warning, read those lines before
   distributing the output file.

---

## How to use — Command Line

Redact a single file (output saved next to original with `_redacted` appended):
```
python redact_ssn.py "C:\path\to\mydoc.pdf"
```

Redact all PDFs in a folder (output saved to a `redacted\` subfolder):
```
python redact_ssn.py "C:\path\to\documents\"
```

Specify a custom output path:
```
python redact_ssn.py "C:\path\to\mydoc.pdf" --output "C:\Users\Me\Desktop\mydoc_clean.pdf"
```

---

## Understanding the summary output

```
=== REDACTION SUMMARY ===
mydoc.pdf                 -> mydoc_redacted.pdf           [3 redacted | 0 missed]

Total files processed:   1
Total matches redacted:  3
Total matches MISSED:    0
Verification:            PASSED
Files with matches:      1
Files skipped/errors:    0
```

| Line | Meaning |
|------|---------|
| `[N redacted]` | Black rectangles written to the output file. |
| `[N missed]` | Matches found in text extraction that could not be visually located — see below. |
| `Verification: PASSED` | Output file was re-opened after save; no patterns survived. |
| `Verification FAILURES` | A pattern was still found after redaction — manual review required. |
| `SKIPPED: all pages image-only` | Every page is a scanned image — no text to redact. |
| `SKIPPED: password-protected` | File is encrypted; remove the password first. |
| `ERROR: …` | File could not be opened (corrupt, wrong format). |

### Non-zero MISSED count — what to do

The tool found a sensitive number in the text layer but could not place a redaction rectangle
on the page. This happens when text rendering and text extraction disagree on character positions.
**Do not treat the output as fully redacted.** Open the output PDF, search for the number shown
in the warning (masked to last 4 digits), and redact it manually with a PDF editor.

---

## Security measures

- **Permanent redaction of text, images, and vector graphics** — `apply_redactions()` is called
  with `PDF_REDACT_IMAGE_PIXELS` and `PDF_REDACT_LINE_ART_REMOVE_IF_COVERED`. This physically
  destroys the underlying pixels and vector paths inside the redaction area — not just an overlay
  annotation that could be stripped by a recipient. Saved with `garbage=4` to remove all orphaned
  PDF objects.
- **Metadata stripped** — document info dict (`/Producer`, `/Author`, etc.) and XMP stream
  cleared before save.
- **Embedded files removed** — any file attachments embedded in the PDF are deleted before save.
- **Form field values cleared** — `widget.field_value = ""` zeroes AcroForm fields before
  the visual redaction is applied.
- **Post-save verification** — the output file is re-opened and re-scanned; survivors are
  flagged as `VERIFY FAIL` in the summary.
- **Targeted SSN memory safety** — entered SSNs are held only in `bytearray` objects that are
  explicitly overwritten with null bytes after redaction completes; the Python regex cache is
  purged (`re.purge()`) so compiled patterns do not linger in memory; GUI fields are cleared
  before the worker thread launches; clipboard is cleared on Run.
- **No logging of sensitive values** — warning messages use masked form `[***-**-XXXX]`;
  the logger never receives raw SSN digits.

---

## Known limitations

- **Scanned / image-only pages** — pages with zero selectable text are warned and skipped; use OCR first. Pages that are sparse (a cover sheet or signature page with a few lines of real text) are processed normally.
- **Password-protected PDFs** — skipped entirely. Remove the password with a PDF editor first.
- **Unseparated 9-digit strings** (`123456789`) — not detected by design to avoid false positives
  on account numbers, phone extensions, etc.
- **Not a substitute for certified redaction workflows** — for legal filings, court submissions,
  or HIPAA-covered documents use a certified product and have results verified by a professional.

---

## File descriptions

| File | Description |
|------|-------------|
| `redact_ssn.py` | Redaction engine — all detection logic, three-pass architecture, CLI entry point. **Do not delete.** |
| `redact_gui.pyw` | Tkinter GUI — calls the engine. Double-click to launch. **Do not delete.** |
| `requirements_redact.txt` | Python package list. Used by `pip install -r requirements_redact.txt`. **Do not delete.** |
| `FUTURE_IMPROVEMENTS.md` | Planned enhancements (OCR tolerance, Tesseract integration). |
| `run_tests.py` | Automated test suite (19 tests). Run `python run_tests.py` to verify everything works. |
| `create_test_pdfs.py` | Generates test PDFs used by the suite. Called automatically by `run_tests.py`. |
| `test_files\` | Generated test PDFs. Safe to delete — `run_tests.py` recreates them. |
