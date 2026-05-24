# Nullify — Advanced PDF Redaction Tool

Nullify is a professional, high-performance desktop utility designed to scan PDF files and **permanently redact** Social Security Numbers (SSNs), Individual Taxpayer Identification Numbers (ITINs), and Employer Identification Numbers (EINs). 

Sensitive numbers are physically erased from the PDF structures—not merely covered with a black block—rendering them 100% unrecoverable by text selection, copy-pasting, visual extraction, or metadata parsing.

---

## Key Features

- **🖥️ High-DPI Windows Support:** Includes crisp, multi-size high-DPI desktop assets and High-DPI Windows awareness for razor-sharp rendering across high-resolution displays.
- **🔍 Multi-Pass Engine:** Detects sensitive data across three comprehensive layers:
  1. **Selectable Text Layer:** Executes high-speed regex queries on PDF text objects.
  2. **AcroForm Fields:** Reads and cleans active form elements directly, including split-digit forms (e.g., IRS Form 1040 layout where SSNs span three separate widget boxes).
  3. **Word Proximity Reassembly:** Finds numbers that are broken into individual characters or sparse adjacent word tokens on a line.
- **👁️ OCR Confusable Misread Tolerance:** Identifies and redacts numbers misread by OCR engines due to visual lookalikes (e.g. `1l3-4S-6789` using lowercase `l` for `1` and uppercase `S` for `5`). Includes intelligent post-match validation to avoid false positives in ordinary text.
- **⚡ Graceful Tesseract OCR Support:** Automatically detects scanned/image-only PDF pages. Renders pages at 300 DPI, runs Google Tesseract OCR, translates coordinates, and redacts. If Tesseract is not installed, the tool gracefully alerts the user with easy-to-follow setup logs and continues.
- **🔒 Absolute Security & Memory Safety:**
  - **Irreversible Pixels:** Redacts by physically stripping underneath graphics and pixels via `apply_redactions()` using PyMuPDF vector path pruning and pixel-purging.
  - **Metadata Strip:** Clears the PDF Info dictionary, XMP metadata stream, and embedded attachments.
  - **Memory Erasure:** Entered targeted search numbers are held in mutable structures and explicitly zeroed out with null bytes after processing. The Python regex engine cache is immediately purged, and garbage collection is requested to keep RAM clean.
  - **Privacy First:** No sensitive digits are ever written to logs or warning terminals (sensitive values are masked, e.g. `[***-**-6789]`).

---

## Requirements

- **Operating System:** Windows PC (7, 8, 10, or 11)
- **Python Runtime:** Python 3.8 or higher
- **Dependencies:** Listed in [requirements_redact.txt](file:///C:/Claude_Git/nullify_public/requirements_redact.txt) (primarily PyMuPDF)
- **Optional OCR Support:** [Google Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (highly recommended for scanned documents)

---

## First-Time Setup

1. **Install Python:** Download Python from [python.org](https://python.org). Ensure you check the box **"Add Python to PATH"** during setup.
2. **Install Dependencies:** Open a Command Prompt or PowerShell window in the project folder and run:
   ```bash
   pip install -r requirements_redact.txt
   ```
3. **Configure Desktop Shortcut:** Double-click the helper script [setup_shortcut.py](file:///C:/Claude_Git/nullify_public/setup_shortcut.py) (or run `python setup_shortcut.py` in your shell) to automatically generate a premium **Nullify** shortcut with its custom branded icon directly on your Desktop!

*(Optional) For Image-Only Scanned PDFs:*
- Install Google Tesseract OCR for Windows from [here](https://github.com/UB-Mannheim/tesseract/wiki).
- Add Tesseract to your Windows Environment Variables PATH so the system can run it.
- Run `pip install pytesseract` in your terminal.

---

## How to Use — Desktop (GUI)

1. Double-click the **Nullify** desktop shortcut (or run `redact_gui.pyw` directly).
2. Select your redaction target: **Single PDF file** or **All PDFs in folder**.
3. Click **Browse** to select your input file/folder. Output paths are suggested automatically.
4. **Configure Advanced Options:**
   - **OCR Misread Tolerance:** Check this box to enable lookalike confusable matching (`[0-9OoIliS]`).
   - **Targeted Redaction:** Input up to 6 specific SSNs/EINs to explicitly hunt down and redact.
5. Click **Run Redaction**.
6. Review the logs in the interactive Results panel. If warning markers appear, read them before sharing the output document.

---

## How to Use — Command Line

Nullify is fully operational from the terminal.

Redact a single file (creates `*_redacted.pdf`):
```bash
python redact_ssn.py "C:\path\to\document.pdf"
```

Redact a directory of files (outputs to a `redacted\` folder):
```bash
python redact_ssn.py "C:\path\to\documents\"
```

Specify custom output destinations:
```bash
python redact_ssn.py "C:\path\to\document.pdf" --output "C:\path\to\redacted_document.pdf"
```

Enable OCR confusable misread tolerance:
```bash
python redact_ssn.py "C:\path\to\document.pdf" --ocr-tolerance
```

---

## File Structure

| File / Folder | Purpose |
| :--- | :--- |
| **[redact_ssn.py](file:///C:/Claude_Git/nullify_public/redact_ssn.py)** | Core redaction engine, detection passes, and CLI command router. |
| **[redact_gui.pyw](file:///C:/Claude_Git/nullify_public/redact_gui.pyw)** | Sleek Navy/Crimson Tkinter desktop user interface. |
| **[setup_shortcut.py](file:///C:/Claude_Git/nullify_public/setup_shortcut.py)** | Desktop shortcut provisioner with WScript shell triggers. |
| **[run_tests.py](file:///C:/Claude_Git/nullify_public/run_tests.py)** | Comprehensive test suite of **23 automated tests**. |
| **[create_test_pdfs.py](file:///C:/Claude_Git/nullify_public/create_test_pdfs.py)** | Programmatic creator of anonymous synthetic test PDFs. |
| **[nullify.ico](file:///C:/Claude_Git/nullify_public/nullify.ico)** | Premium multi-resolution branded Windows icon asset. |
| **[nullify.png](file:///C:/Claude_Git/nullify_public/nullify.png)** | High-contrast application logo. |
| **[FUTURE_IMPROVEMENTS.md](file:///C:/Claude_Git/nullify_public/FUTURE_IMPROVEMENTS.md)** | Documented architectural enhancements for future development. |

---

## Verification & Trust

Nullify is designed to be fully self-validating. To run the full verification test suite:
```bash
python run_tests.py
```
This automatically generates 12 synthetic PDF test cases representing different layouts, encryption states, and OCR errors, executes 23 targeted tests on the redaction engine, and cleans up after completion.
