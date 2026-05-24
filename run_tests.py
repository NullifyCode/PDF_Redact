"""
Automated test suite for the PDF redaction engine.
Run: python run_tests.py
Exit 0 if all non-skipped tests pass; exit 1 if any fail.
"""

import sys
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))  # ensure project root is importable

import fitz
from create_test_pdfs import generate_all, TEST_DIR
from redact_ssn import process_single, process_directory


def setUpModule():
    """Generate all test PDFs once before any test class runs."""
    generate_all(quiet=True)


def _extract_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    text = "".join(page.get_text("text") for page in doc)
    doc.close()
    return text


def _cleanup(*paths):
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass


class _BaseRedactionTest(unittest.TestCase):
    """Shared setUp/tearDown for tests that process one input → one output file."""
    input_file  = ""
    output_file = ""

    def setUp(self):
        self.input  = str(TEST_DIR / self.input_file)
        self.output = str(TEST_DIR / self.output_file)
        _cleanup(self.output)

    def tearDown(self):
        _cleanup(self.output)


# ── Engine tests ──────────────────────────────────────────────────────────────

class TestPartialMask(_BaseRedactionTest):
    """Partially masked SSNs/EINs (last 4 as XXXX) must still be detected and redacted."""
    input_file  = "test_partial_mask.pdf"
    output_file = "test_partial_mask_redacted.pdf"

    def test_partial_mask_redacted(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["missed"], 0)
        self.assertGreaterEqual(result["redacted"], 9,
                                f"expected at least 9 redactions, got {result['redacted']}")
        out_text = _extract_text(self.output)
        for pattern in (
            "328-00-XXXX", "328 00 XXXX", "127-00-XXXX",   # SSN X-masked
            "xxx-00-0000", "xx5-00-0000",                    # SSN 0-masked
            "34-800XXXX",  "22-700XXXX",                     # EIN 3+4
            "38-4XXXXXX",  "89-7XXXXXX",                     # EIN 1+6
        ):
            self.assertNotIn(pattern, out_text, f"'{pattern}' still visible in output")


class TestStandardRedaction(_BaseRedactionTest):
    input_file  = "test_standard.pdf"
    output_file = "test_standard_redacted.pdf"

    def test_standard(self):
        result = process_single(self.input, self.output)

        self.assertEqual(result["status"], "success", f"status was {result['status']}")
        self.assertEqual(result["redacted"], 3, f"expected 3 redacted, got {result['redacted']}")
        self.assertEqual(result["missed"], 0, f"expected 0 missed, got {result['missed']}")

        # Phone and date must not trigger redaction
        warnings_text = " ".join(result.get("warnings", []))
        self.assertNotIn("713-555-1234", warnings_text)
        self.assertNotIn("12-31-2024", warnings_text)

        self.assertTrue(Path(self.output).exists(), "output file not created")

        out_text = _extract_text(self.output)
        for number in ("123-45-6789", "12-3456789", "912-34-5678"):
            self.assertNotIn(number, out_text, f"'{number}' still visible in output PDF")


class TestMultipleInstances(_BaseRedactionTest):
    input_file  = "test_multi.pdf"
    output_file = "test_multi_redacted.pdf"

    def test_multiple_instances(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 5, f"expected 5 redacted, got {result['redacted']}")
        self.assertEqual(result["missed"], 0)


class TestCleanFile(_BaseRedactionTest):
    input_file  = "test_clean.pdf"
    output_file = "test_clean_redacted.pdf"

    def test_clean_file(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 0)
        self.assertEqual(result["missed"], 0)

        doc = fitz.open(self.output)
        for page in doc:
            self.assertEqual(len(list(page.annots())), 0, "unexpected annotations on clean file")
        doc.close()


class TestMultiPage(_BaseRedactionTest):
    input_file  = "test_multipage.pdf"
    output_file = "test_multipage_redacted.pdf"

    def test_multipage(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 2, f"expected 2 total, got {result['redacted']}")

        pages = result.get("pages", [])
        self.assertGreaterEqual(len(pages), 3)

        # page numbers are 1-based in the result dict
        p1 = next((p for p in pages if p["page"] == 1), None)
        p2 = next((p for p in pages if p["page"] == 2), None)
        p3 = next((p for p in pages if p["page"] == 3), None)

        self.assertIsNotNone(p1)
        self.assertEqual(p1["redacted"], 1, f"p1 expected 1, got {p1['redacted']}")
        self.assertIsNotNone(p2)
        self.assertEqual(p2["redacted"], 0, f"p2 expected 0, got {p2['redacted']}")
        self.assertIsNotNone(p3)
        self.assertEqual(p3["redacted"], 1, f"p3 expected 1, got {p3['redacted']}")


class TestTargetedSSN(_BaseRedactionTest):
    """Targeted SSN lookup finds specific numbers and ignores invalid input."""
    input_file  = "test_standard.pdf"
    output_file = "test_targeted_redacted.pdf"

    def test_single_target_redacted(self):
        result = process_single(self.input, self.output, target_ssns=["123-45-6789"])
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["redacted"], 1)
        self.assertNotIn("123-45-6789", _extract_text(self.output))

    def test_up_to_six_targets(self):
        multi_out = str(TEST_DIR / "test_multi_targeted_redacted.pdf")
        _cleanup(multi_out)
        targets = [
            "123-45-6789",  # present ×5
            "912-34-5678",  # absent — must not crash
            "000-11-2222",  # invalid prefix — silently skipped
            "444-55-6666",
            "777-88-9999",
            "111-22-3333",
        ]
        try:
            result = process_single(str(TEST_DIR / "test_multi.pdf"), multi_out,
                                    target_ssns=targets)
            self.assertEqual(result["status"], "success")
            self.assertGreaterEqual(result["redacted"], 1)
            self.assertNotIn("123-45-6789", _extract_text(multi_out))
        finally:
            _cleanup(multi_out)

    def test_targeted_catches_unseparated_digits(self):
        """Targeted SSN must match raw 9-digit form — as found in IRS 1040-ES voucher bottom lines."""
        import fitz as _fitz
        tmp_in  = str(TEST_DIR / "_raw_digits_in.pdf")
        tmp_out = str(TEST_DIR / "_raw_digits_out.pdf")
        doc = _fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72),
            "Form 1040-ES Payment Voucher — Department of the Treasury Internal Revenue Service",
            fontsize=11)
        page.insert_text((72, 100),
            "4546 74 123456789 PT SMITH 30 0 202612 430",
            fontsize=11)
        doc.save(tmp_in)
        doc.close()
        try:
            result = process_single(tmp_in, tmp_out, target_ssns=["123-45-6789"])
            self.assertEqual(result["status"], "success")
            self.assertGreaterEqual(result["redacted"], 1,
                                    "unseparated 9-digit SSN not detected by targeted scan")
            self.assertNotIn("123456789", _extract_text(tmp_out),
                             "raw SSN digits still visible in output")
        finally:
            _cleanup(tmp_in, tmp_out)

    def test_invalid_format_ignored(self):
        result = process_single(self.input, self.output,
                                target_ssns=["not-an-ssn", "12345", ""])
        self.assertEqual(result["status"], "success")

    def test_none_target_preserves_existing_behavior(self):
        result = process_single(self.input, self.output, target_ssns=None)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 3)


class TestInvalidSSNs(_BaseRedactionTest):
    """SSN ranges the SSA has never issued must not be redacted."""
    input_file  = "test_invalid_ssn.pdf"
    output_file = "test_invalid_ssn_redacted.pdf"

    def test_invalid_ssns_not_redacted(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 1,
                         f"only the valid SSN should be redacted, got {result['redacted']}")
        self.assertEqual(result["missed"], 0)

        out_text = _extract_text(self.output)
        self.assertNotIn("123-45-6789", out_text, "valid SSN still present after redaction")
        for invalid in ("000-45-6789", "666-45-6789", "123-00-6789", "123-45-0000"):
            self.assertIn(invalid, out_text, f"invalid SSN '{invalid}' was incorrectly redacted")


class TestVerification(unittest.TestCase):
    """Post-redaction verification catches survivors; clean files pass with no failures."""

    def test_verification_passes_after_redaction(self):
        output = str(TEST_DIR / "test_standard_verify_check.pdf")
        _cleanup(output)
        try:
            result = process_single(str(TEST_DIR / "test_standard.pdf"), output)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result.get("verification_failures", []), [],
                             f"survivors found: {result.get('verification_failures')}")
        finally:
            _cleanup(output)

    def test_verification_no_false_alarms_on_clean_file(self):
        output = str(TEST_DIR / "test_clean_verify_check.pdf")
        _cleanup(output)
        try:
            result = process_single(str(TEST_DIR / "test_clean.pdf"), output)
            self.assertEqual(result["status"], "success")
            self.assertEqual(result.get("verification_failures", []), [])
        finally:
            _cleanup(output)


class TestAcroFormSSN(_BaseRedactionTest):
    """AcroForm PDF with SSN split across three widget fields (IRS 1040 style)."""
    input_file  = "test_acroform_ssn.pdf"
    output_file = "test_acroform_ssn_redacted.pdf"

    def test_acroform_ssn(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["redacted"], 1, "expected at least 1 redaction for split SSN")
        self.assertEqual(result["missed"], 0)

        out_text = _extract_text(self.output)
        self.assertNotRegex(out_text, r'123.{0,3}45.{0,3}6789', "SSN still readable in output")
        self.assertIn("75000", out_text, "non-sensitive content was incorrectly redacted")


class TestIRSFormat(_BaseRedactionTest):
    """Space-separated SSNs extracted from IRS fillable form PDFs."""
    input_file  = "test_irs_format.pdf"
    output_file = "test_irs_format_redacted.pdf"

    def test_irs_format(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 2, f"expected 2 redacted, got {result['redacted']}")
        self.assertEqual(result["missed"], 0)
        out_text = _extract_text(self.output)
        for number in ("123 45 6789", "987 65 4321"):
            self.assertNotIn(number, out_text, f"'{number}' still visible in output PDF")


class TestImageOnly(_BaseRedactionTest):
    input_file  = "test_image_only.pdf"
    output_file = "test_image_only_redacted.pdf"

    def test_image_only(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "image_only",
                         f"expected image_only, got {result['status']}")
        self.assertFalse(Path(self.output).exists(),
                         "output should not be created for image-only PDF")


class TestEncrypted(_BaseRedactionTest):
    input_file  = "test_encrypted.pdf"
    output_file = "test_encrypted_redacted.pdf"

    def test_encrypted(self):
        result = process_single(self.input, self.output)
        self.assertEqual(result["status"], "encrypted")
        self.assertFalse(Path(self.output).exists(),
                         "output should not be created for encrypted PDF")


class TestCorrupt(_BaseRedactionTest):
    input_file  = "test_corrupt.pdf"
    output_file = "test_corrupt_redacted.pdf"

    def test_corrupt(self):
        try:
            result = process_single(self.input, self.output)
            self.assertEqual(result["status"], "error",
                             f"expected error, got {result['status']}")
        except Exception as e:
            self.fail(f"process_single raised an exception instead of handling it: {e}")


class TestDirectoryMode(unittest.TestCase):
    def setUp(self):
        self.input_dir  = str(TEST_DIR)
        self.output_dir = str(TEST_DIR / "redacted")
        if Path(self.output_dir).exists():
            shutil.rmtree(self.output_dir)

    def test_directory_mode(self):
        results = process_directory(self.input_dir, self.output_dir)

        self.assertTrue(Path(self.output_dir).exists(), "output directory not created")

        for r in results:
            if r.get("status") == "success":
                self.assertTrue(Path(r["output"]).exists(),
                                f"missing output: {r.get('output')}")

        for r in results:
            if r.get("status") in ("image_only", "encrypted"):
                self.assertFalse(Path(r.get("output", "")).exists(),
                                 f"skipped file should not have output: {r.get('output')}")

        total_redacted = sum(r.get("redacted", 0) for r in results if r.get("status") == "success")
        total_missed   = sum(r.get("missed",   0) for r in results if r.get("status") == "success")
        self.assertGreaterEqual(total_redacted, 0)
        self.assertGreaterEqual(total_missed,   0)


class TestInputEqualsOutput(unittest.TestCase):
    def setUp(self):
        self.path = str(TEST_DIR / "test_clean.pdf")

    def test_input_equals_output(self):
        result = process_single(self.path, self.path)
        self.assertEqual(result["status"], "error",
                         "should return error when input == output")
        self.assertTrue(Path(self.path).exists(), "source file was deleted")
        self.assertIn("clean", _extract_text(self.path).lower(), "source content was altered")


class TestGUISmoke(unittest.TestCase):
    """Headless smoke test for the Tkinter GUI."""

    def test_gui_smoke(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "redact_gui",
            str(Path(__file__).parent / "redact_gui.pyw"),
        )
        mod = importlib.util.module_from_spec(spec)

        try:
            spec.loader.exec_module(mod)
        except Exception as e:
            self.fail(f"GUI module failed to import: {e}")

        try:
            app = mod.RedactApp()
        except Exception as e:
            self.fail(f"RedactApp() failed to initialize: {e}")

        self.assertIn("Nullify", app.title())
        self.assertEqual(str(app._browse_btn["state"]), "normal")
        self.assertEqual(str(app._run_btn["state"]), "normal")

        app._set_mode("dir")
        self.assertEqual(app._mode, "dir")
        app._set_mode("file")
        self.assertEqual(app._mode, "file")

        app._run_btn.configure(state="disabled")
        self.assertEqual(str(app._run_btn["state"]), "disabled")
        app._run_btn.configure(state="normal")
        self.assertEqual(str(app._run_btn["state"]), "normal")

        app._append_results("Test output line")
        app._results_text.configure(state="normal")
        content = app._results_text.get("1.0", "end").strip()
        app._results_text.configure(state="disabled")
        self.assertEqual(content, "Test output line")

        app.destroy()


class TestOCRConfusableTolerance(_BaseRedactionTest):
    input_file  = "test_ocr_confusables.pdf"
    output_file = "test_ocr_confusables_redacted.pdf"

    def test_ocr_tolerance_enabled(self):
        # ocr_tolerance=True should redact 3 matches (2 confusables + 1 normal)
        result = process_single(self.input, self.output, ocr_tolerance=True)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 3, f"expected 3 redacted, got {result['redacted']}")
        self.assertEqual(result["missed"], 0)
        
        out_text = _extract_text(self.output)
        for number in ("1l3-4S-6789", "l2-34S6789", "123-45-6789"):
            self.assertNotIn(number, out_text, f"'{number}' still visible in output PDF")

    def test_ocr_tolerance_disabled(self):
        # ocr_tolerance=False should only redact 1 match (the normal one)
        result = process_single(self.input, self.output, ocr_tolerance=False)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["redacted"], 1, f"expected 1 redacted, got {result['redacted']}")
        self.assertEqual(result["missed"], 0)
        
        out_text = _extract_text(self.output)
        self.assertNotIn("123-45-6789", out_text, "123-45-6789 should be redacted")
        self.assertIn("1l3-4S-6789", out_text, "1l3-4S-6789 should NOT be redacted")
        self.assertIn("l2-34S6789", out_text, "l2-34S6789 should NOT be redacted")


# ── Runner ────────────────────────────────────────────────────────────────────

class VerboseTestResult(unittest.TextTestResult):
    def addSuccess(self, test):
        super().addSuccess(test)
        print(f"  PASS  {test._testMethodName}")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        msg = self._exc_info_to_string(err, test).strip().splitlines()[-1]
        print(f"  FAIL  {test._testMethodName} — {msg}")

    def addError(self, test, err):
        super().addError(test, err)
        msg = self._exc_info_to_string(err, test).strip().splitlines()[-1]
        print(f"  ERROR {test._testMethodName} — {msg}")

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        print(f"  SKIP  {test._testMethodName} — {reason}")


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    test_classes = [
        TestPartialMask,
        TestStandardRedaction,
        TestMultipleInstances,
        TestCleanFile,
        TestMultiPage,
        TestTargetedSSN,
        TestInvalidSSNs,
        TestVerification,
        TestAcroFormSSN,
        TestIRSFormat,
        TestImageOnly,
        TestEncrypted,
        TestCorrupt,
        TestDirectoryMode,
        TestInputEqualsOutput,
        TestGUISmoke,
        TestOCRConfusableTolerance,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    print("Running PDF Redaction Test Suite...\n")

    runner = unittest.TextTestRunner(
        verbosity=0,
        resultclass=VerboseTestResult,
        stream=sys.stdout,
    )
    result = runner.run(suite)

    passed  = result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped)
    failed  = len(result.failures) + len(result.errors)
    skipped = len(result.skipped)

    print()
    print("==========================================")
    print(f"TEST RESULTS: {passed} passed, {failed} failed, {skipped} skipped")
    print("==========================================")

    sys.exit(0 if failed == 0 else 1)
