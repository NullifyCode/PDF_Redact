# Nullify — Advanced PDF Redaction Tool (GUI)
# Copyright (C) 2026 Nullify Code
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# Desktop shortcut provisioner: run setup_shortcut.py to generate a crisp Desktop link.

import os
import ctypes
import tkinter as tk
from tkinter import filedialog
import threading
from pathlib import Path

# Enable High-DPI awareness on Windows to ensure crisp fonts and sharp image rendering
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from redact_ssn import process_single, process_directory, REDACTED_SUFFIX, format_summary

# ── Design tokens (Nullify Palette) ────────────────────────────────
BG         = "#F5F6F7"   # navy/grey window background
PANEL      = "#F5F6F7"   # panel/header background
ACCENT     = "#1B2E4B"   # primary navy
ACCENT_HOV = "#112035"   # primary hover (darker navy)
CRIMSON    = "#C0392B"   # crimson accent
OPEN_CLR   = "#2563EB"   # blue — Open button
OPEN_HOV   = "#1D4ED8"   # blue hover / pressed
CARD_BG    = "#FFFFFF"   # surface/card background
TEXT       = "#1A1A1A"   # primary text
TEXT_DIM   = "#666666"   # secondary labels
BORDER     = "#E0E2E6"   # subtle dividers
WHITE      = "#FFFFFF"
TERM_BG    = "#1E1E1E"   # dark terminal background
TERM_FG    = "#E8E6E1"   # default terminal text
TERM_OK    = "#4ADE80"   # green — success
TERM_WARN  = "#FBBF24"   # amber — warning / skipped
TERM_ERR   = "#F87171"   # red — error / missed
TERM_DIM   = "#6B7280"   # dim grey — header / info

FONT_TITLE   = ("Segoe UI", 18, "bold")
FONT_SUB     = ("Segoe UI", 10)
FONT_SECTION = ("Segoe UI",  9, "bold")
FONT_BODY    = ("Segoe UI", 10)
FONT_BTN_LG  = ("Segoe UI", 11, "bold")
FONT_BTN_SM  = ("Segoe UI",  9)
FONT_ENTRY   = ("Segoe UI", 10)
FONT_MONO    = ("Consolas",  9)
FONT_STATUS  = ("Segoe UI",  9)


# ── Mode-selection card ───────────────────────────────────────────────────────

class _ModeCard(tk.Frame):
    """Clickable card widget for file / folder mode selection."""

    def __init__(self, parent, label: str, icon: str, value: str, on_select):
        super().__init__(parent, bg=CARD_BG, cursor="hand2",
                         highlightthickness=2, highlightbackground=BORDER,
                         highlightcolor=BORDER)
        self._value = value
        self._on_select = on_select
        self._widgets: list = [self]

        inner = tk.Frame(self, bg=CARD_BG, padx=20, pady=14)
        self._widgets.append(inner)
        inner.pack(fill="both", expand=True)

        icon_lbl = tk.Label(inner, text=icon, bg=CARD_BG,
                            font=("Segoe UI Emoji", 22), fg=ACCENT)
        self._widgets.append(icon_lbl)
        icon_lbl.pack()

        text_lbl = tk.Label(inner, text=label, bg=CARD_BG, font=FONT_BODY, fg=TEXT)
        self._widgets.append(text_lbl)
        text_lbl.pack(pady=(6, 0))

        for w in self._widgets:
            w.bind("<Button-1>", self._click)

    def _click(self, _=None):
        self._on_select(self._value)

    def set_active(self, active: bool):
        border = CRIMSON if active else BORDER
        bg     = "#F0F4F8" if active else CARD_BG   # faint navy/blue-grey tint when selected
        self.configure(highlightbackground=border, highlightcolor=border)
        for w in self._widgets:
            w.configure(bg=bg)


# ── Main application ──────────────────────────────────────────────────────────

class RedactApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Nullify")
        try:
            self.iconbitmap(str(Path(__file__).parent / "nullify.ico"))
        except Exception:
            pass
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(700, 640)

        self._mode           = "file"
        self._input_var       = tk.StringVar()
        self._output_var      = tk.StringVar()
        self._status_var      = tk.StringVar(value="Ready")
        self._target_ssn_vars = [tk.StringVar() for _ in range(6)]
        self._ocr_tolerance_var = tk.BooleanVar(value=False)
        self._last_output     = None   # path shown by the Open button after a successful run

        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_body()
        self._build_status_bar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=PANEL)
        hdr.pack(fill="x")

        inner = tk.Frame(hdr, bg=PANEL, padx=26, pady=20)
        inner.pack(fill="x")

        row = tk.Frame(inner, bg=PANEL)
        row.pack(anchor="w")

        logo_path = Path(__file__).parent / "nullify.png"
        has_logo = False
        if logo_path.exists():
            try:
                self._logo_image = tk.PhotoImage(file=str(logo_path))
                has_logo = True
            except Exception:
                pass

        if has_logo:
            tk.Label(row, image=self._logo_image, bg=PANEL).pack(side="left", padx=(0, 14))
        else:
            tk.Label(row, text="🛡", bg=PANEL,
                     font=("Segoe UI Emoji", 28), fg=ACCENT).pack(side="left", padx=(0, 14))

        col = tk.Frame(row, bg=PANEL)
        col.pack(side="left")
        tk.Label(col, text="Nullify",
                 bg=PANEL, font=FONT_TITLE, fg=TEXT).pack(anchor="w")
        tk.Label(col,
                 text="Permanently removes SSNs and Tax IDs from PDF files",
                 bg=PANEL, font=FONT_SUB, fg=TEXT_DIM).pack(anchor="w", pady=(2, 0))

        # Accent stripe
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")

    def _build_body(self):
        body = tk.Frame(self, bg=BG, padx=28, pady=22)
        body.pack(fill="both", expand=True)

        self._build_mode_cards(body)
        self._build_file_rows(body)
        self._build_target_ssns(body)
        self._build_options(body)
        self._build_run_button(body)
        self._build_results_panel(body)

    def _build_mode_cards(self, parent):
        self._section_label(parent, "WHAT DO YOU WANT TO REDACT?")

        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(8, 20))

        self._card_file = _ModeCard(row, "Single PDF File",    "📄", "file", self._set_mode)
        self._card_file.pack(side="left", expand=True, fill="both", padx=(0, 10))

        self._card_dir  = _ModeCard(row, "All PDFs in Folder", "📁", "dir",  self._set_mode)
        self._card_dir.pack(side="left", expand=True, fill="both")

        self._set_mode("file")

    def _build_file_rows(self, parent):
        self._section_label(parent, "SOURCE")

        src = tk.Frame(parent, bg=BG)
        src.pack(fill="x", pady=(6, 16))
        src.columnconfigure(0, weight=1)

        self._input_entry = self._entry(src, self._input_var)
        self._input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._browse_btn = self._outline_btn(src, "Browse…", self._browse_input)
        self._browse_btn.grid(row=0, column=1)

        self._section_label(parent, "SAVE TO")

        out = tk.Frame(parent, bg=BG)
        out.pack(fill="x", pady=(6, 22))
        out.columnconfigure(0, weight=1)

        self._entry(out, self._output_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._outline_btn(out, "Change…", self._browse_output).grid(row=0, column=1)

    def _build_target_ssns(self, parent):
        self._section_label(parent, "TARGET SPECIFIC SSNs  (optional — leave blank to skip)")

        tk.Label(parent,
                 text="Enter up to 6 SSNs to hunt for specifically. All fields are cleared from memory after redaction.",
                 bg=BG, font=("Segoe UI", 8), fg=TEXT_DIM).pack(anchor="w", pady=(0, 8))

        grid = tk.Frame(parent, bg=BG)
        grid.pack(fill="x", pady=(0, 20))
        COLS = 3
        for col in range(COLS):
            grid.columnconfigure(col, weight=1)

        self._target_entries = []
        for i in range(6):
            r, c = divmod(i, COLS)
            cell = tk.Frame(grid, bg=BG)
            cell.grid(row=r, column=c,
                      padx=(0, 12) if c < COLS - 1 else 0,
                      pady=(0, 6), sticky="ew")
            tk.Label(cell, text=f"SSN {i + 1}", bg=BG,
                     font=FONT_SECTION, fg=TEXT_DIM).pack(anchor="w")
            entry = self._entry(cell, self._target_ssn_vars[i])
            entry.configure(show="●")
            # Prevent clipboard copy/cut — show="●" masks display but not clipboard.
            entry.bind("<<Copy>>",  lambda e: "break")
            entry.bind("<<Cut>>",   lambda e: "break")
            entry.pack(fill="x", pady=(2, 0))
            self._target_entries.append(entry)

    def _build_options(self, parent):
        self._section_label(parent, "SETTINGS")
        
        opt_frame = tk.Frame(parent, bg=BG)
        opt_frame.pack(fill="x", pady=(6, 16))
        
        cb = tk.Checkbutton(
            opt_frame,
            text="Enable OCR Misread Tolerance (matches O for 0, I for 1, S for 5)",
            variable=self._ocr_tolerance_var,
            font=FONT_BODY,
            bg=BG, fg=TEXT,
            activebackground=BG, activeforeground=TEXT,
            selectcolor=WHITE,
            relief="flat", bd=0,
            cursor="hand2"
        )
        cb.pack(anchor="w")

    def _build_run_button(self, parent):
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(pady=(0, 22))

        self._run_btn = tk.Button(
            wrap,
            text="▶   Run Redaction",
            font=FONT_BTN_LG,
            bg=ACCENT, fg=WHITE,
            activebackground=ACCENT_HOV, activeforeground=WHITE,
            relief="flat", bd=0,
            padx=38, pady=12,
            cursor="hand2",
            command=self._run,
        )
        self._run_btn.pack(side="left")
        self._run_btn.bind("<Enter>", lambda _: self._run_btn.configure(bg=ACCENT_HOV))
        self._run_btn.bind("<Leave>", lambda _: self._run_btn.configure(bg=ACCENT))

        # Open button — hidden until a successful run produces an output file/folder.
        self._open_btn = tk.Button(
            wrap,
            text="",
            font=FONT_BTN_LG,
            bg=OPEN_CLR, fg=WHITE,
            activebackground=OPEN_HOV, activeforeground=WHITE,
            relief="flat", bd=0,
            padx=28, pady=12,
            cursor="hand2",
            command=self._open_last_output,
        )
        self._open_btn.bind("<Enter>", lambda _: self._open_btn.configure(bg=OPEN_HOV))
        self._open_btn.bind("<Leave>", lambda _: self._open_btn.configure(bg=OPEN_CLR))

    def _build_results_panel(self, parent):
        self._section_label(parent, "RESULTS")

        shell = tk.Frame(parent, bg=TERM_BG,
                         highlightbackground=BORDER, highlightthickness=1)
        shell.pack(fill="both", expand=True, pady=(6, 0))

        self._results_text = tk.Text(
            shell,
            font=FONT_MONO,
            bg=TERM_BG, fg=TERM_FG,
            insertbackground=TERM_FG,
            selectbackground=ACCENT,
            relief="flat", bd=10,
            wrap="word",
            state="disabled",
            height=12,
        )
        sb = tk.Scrollbar(shell, command=self._results_text.yview,
                          bg=TERM_BG, troughcolor="#2A2A2A",
                          highlightthickness=0, bd=0)
        self._results_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._results_text.pack(side="left", fill="both", expand=True)

        self._results_text.tag_configure("header", foreground=TERM_DIM)
        self._results_text.tag_configure("ok",     foreground=TERM_OK)
        self._results_text.tag_configure("warn",   foreground=CRIMSON)
        self._results_text.tag_configure("err",    foreground=CRIMSON)
        self._results_text.tag_configure("dim",    foreground=TERM_DIM)
        self._results_text.tag_configure("total",  foreground=TERM_FG)
        self._results_text.tag_configure("success_passed", background="#EAF7F2", foreground="#0F6E56")

    def _build_status_bar(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        bar = tk.Frame(self, bg=PANEL, padx=18, pady=7)
        bar.pack(fill="x")

        self._status_dot = tk.Label(bar, text="●", bg=PANEL,
                                    font=FONT_STATUS, fg=TEXT_DIM)
        self._status_dot.pack(side="left")
        self._status_lbl = tk.Label(bar, textvariable=self._status_var,
                                    bg=PANEL, font=FONT_STATUS, fg=TEXT_DIM)
        self._status_lbl.pack(side="left", padx=(5, 0))

        license_lbl = tk.Label(bar, text="GNU GPL v3", bg=PANEL,
                               font=FONT_STATUS, fg=TEXT_DIM)
        license_lbl.pack(side="right")

    # ── Widget factories ──────────────────────────────────────────────────────

    def _section_label(self, parent, text: str):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(0, 2))
        tk.Label(row, text=text, bg=BG,
                 font=FONT_SECTION, fg=TEXT_DIM).pack(side="left")
        tk.Frame(row, bg=BORDER, height=1).pack(
            side="left", fill="x", expand=True, padx=(10, 0), pady=1)

    def _entry(self, parent, textvariable) -> tk.Entry:
        return tk.Entry(
            parent,
            textvariable=textvariable,
            font=FONT_ENTRY,
            bg=WHITE, fg=TEXT,
            relief="flat",
            highlightbackground=BORDER,
            highlightcolor=ACCENT,
            highlightthickness=1,
            insertbackground=ACCENT,
        )

    def _outline_btn(self, parent, text: str, command) -> tk.Button:
        btn = tk.Button(
            parent,
            text=text,
            font=FONT_BTN_SM,
            bg=PANEL, fg=TEXT,
            activebackground=BORDER, activeforeground=TEXT,
            relief="flat", bd=0,
            padx=12, pady=5,
            cursor="hand2",
            highlightbackground=BORDER,
            highlightthickness=1,
            command=command,
        )
        btn.bind("<Enter>", lambda _: btn.configure(bg=BORDER))
        btn.bind("<Leave>", lambda _: btn.configure(bg=PANEL))
        return btn

    # ── Event handlers ────────────────────────────────────────────────────────

    def _set_mode(self, mode: str):
        self._mode = mode
        self._card_file.set_active(mode == "file")
        self._card_dir.set_active(mode == "dir")
        current = self._input_var.get()
        if current:
            self._output_var.set(_derive_output_path(current, mode))

    def _browse_input(self):
        if self._mode == "file":
            path = filedialog.askopenfilename(
                title="Select PDF file",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            )
        else:
            path = filedialog.askdirectory(title="Select folder containing PDFs")
        if path:
            self._input_var.set(path)
            self._output_var.set(_derive_output_path(path, self._mode))

    def _browse_output(self):
        if self._mode == "file":
            path = filedialog.asksaveasfilename(
                title="Save redacted PDF as",
                defaultextension=".pdf",
                filetypes=[("PDF files", "*.pdf")],
            )
        else:
            path = filedialog.askdirectory(title="Select output folder")
        if path:
            self._output_var.set(path)

    def _open_last_output(self):
        if self._last_output and Path(self._last_output).exists():
            os.startfile(self._last_output)

    def _set_status(self, msg: str, color: str = TEXT_DIM):
        self._status_var.set(msg)
        self._status_dot.configure(fg=color)
        self._status_lbl.configure(fg=color)

    def _append_results(self, text: str):
        self._results_text.configure(state="normal")
        self._results_text.delete("1.0", "end")
        for line in text.splitlines():
            self._results_text.insert("end", line + "\n", _classify_line(line))
        self._results_text.configure(state="disabled")
        self._results_text.see("1.0")   # position at top so user reads from the beginning

    def _run(self):
        input_path  = self._input_var.get().strip()
        output_path = self._output_var.get().strip()
        ocr_tolerance = self._ocr_tolerance_var.get()

        if not input_path:
            self._set_status("Error: no input selected.", TERM_ERR)
            return

        # Collect targeted SSNs into bytearrays, then immediately wipe the fields.
        # The bytearray gives us an explicit zero-on-completion guarantee that
        # Python str cannot provide.
        target_bufs = []
        for var, entry in zip(self._target_ssn_vars, self._target_entries):
            val = var.get().strip()
            if val:
                target_bufs.append(bytearray(val.encode("utf-8")))
            var.set("")
            entry.delete(0, "end")
        try:
            self.clipboard_clear()   # ensure no SSN digits linger on the system clipboard
        except Exception:
            pass

        self._open_btn.pack_forget()   # hide until the new run completes
        self._last_output = None
        self._run_btn.configure(state="disabled", bg=TEXT_DIM)
        self._set_status("Redacting…", ACCENT)
        self._append_results("Running redaction…")

        def worker():
            try:
                target_ssns = [b.decode("utf-8") for b in target_bufs] or None

                if self._mode == "file":
                    result = process_single(input_path, output_path or None,
                                            target_ssns=target_ssns, ocr_tolerance=ocr_tolerance)
                    result["filename"] = Path(input_path).name
                    results = [result]
                else:
                    results = process_directory(input_path, output_path or None,
                                                target_ssns=target_ssns, ocr_tolerance=ocr_tolerance)
                    for r in results:
                        if "filename" not in r:
                            r["filename"] = Path(r.get("input", "unknown")).name

                summary      = format_summary(results)
                total_missed = sum(r.get("missed",   0) for r in results if r.get("status") == "success")
                total_ok     = sum(r.get("redacted", 0) for r in results if r.get("status") == "success")

                def finish():
                    self._append_results(summary)
                    if total_missed > 0:
                        self._set_status(
                            f"Done — {total_missed} match(es) could not be located. Review warnings.",
                            TERM_WARN)
                    else:
                        self._set_status(
                            f"Done — {total_ok} match(es) redacted successfully.", TERM_OK)
                    self._run_btn.configure(state="normal", bg=ACCENT)

                    # Show the open button when there is a usable output to open.
                    if self._mode == "file":
                        out = results[0].get("output", "") if results else ""
                        if out and Path(out).exists():
                            self._last_output = out
                            self._open_btn.configure(text="Open Redacted PDF")
                            self._open_btn.pack(side="left", padx=(14, 0))
                    else:
                        # For directory mode open the output folder itself.
                        out = results[0].get("output", "") if results else ""
                        out_dir = str(Path(out).parent) if out else ""
                        if out_dir and Path(out_dir).exists():
                            self._last_output = out_dir
                            self._open_btn.configure(text="Open Output Folder")
                            self._open_btn.pack(side="left", padx=(14, 0))

                self.after(0, finish)

            except Exception as exc:
                def on_error():
                    self._append_results(f"Unexpected error:\n  {exc}")
                    self._set_status(f"Error: {exc}", TERM_ERR)
                    self._run_btn.configure(state="normal", bg=ACCENT)
                self.after(0, on_error)
            finally:
                # Zero every targeted SSN buffer so the digits do not linger in heap memory.
                import gc, re as _re
                for buf in target_bufs:
                    buf[:] = b"\x00" * len(buf)
                _re.purge()
                gc.collect()

        threading.Thread(target=worker, daemon=True).start()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _derive_output_path(input_path: str, mode: str) -> str:
    p = Path(input_path)
    return str(p.parent / (p.stem + REDACTED_SUFFIX + p.suffix)) \
        if mode == "file" else str(p / "redacted")


def _classify_line(line: str) -> str:
    stripped = line.strip()
    if "Verification:            PASSED" in line:
        return "success_passed"
    if line.startswith("==="):
        return "header"
    if stripped.startswith("Page") or stripped.startswith("----"):
        return "header"
    if "** " in line or "Redacted on pages:" in line:
        return "ok"
    if "image-only, skipped" in line:
        return "warn"
    if "MISSED" in line or "ERROR" in line or "VERIFY FAIL" in line or "Verification FAILURES" in line:
        return "err"
    if "WARNING" in line or "SKIPPED" in line:
        return "warn"
    if "redacted" in line and "0 missed" in line:
        return "ok"
    if line.startswith("Total") or line.startswith("Verification") or line.startswith("Files"):
        return "total"
    return "dim"


if __name__ == "__main__":
    app = RedactApp()
    app.mainloop()
