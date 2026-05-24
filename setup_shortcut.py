"""
setup_shortcut.py — Create a Desktop shortcut for the SSN/EIN Redaction Tool
                    with a custom application icon.

Steps:
  1. Save your icon image as  app_icon.png  in this folder.
  2. Run:  python setup_shortcut.py
  3. A shortcut with the custom icon appears on your Desktop.
"""

import sys
import subprocess
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent.resolve()
ICON_PNG    = PROJECT_DIR / "nullify.png"
ICON_ICO    = PROJECT_DIR / "nullify.ico"
SCRIPT      = PROJECT_DIR / "redact_gui.pyw"
DESKTOP     = Path.home() / "Desktop"
SHORTCUT    = DESKTOP / "Nullify.lnk"

# Derive pythonw.exe from the currently running Python interpreter.
_pythonw = Path(sys.executable).parent / "pythonw.exe"
PYTHONW  = _pythonw if _pythonw.exists() else Path(sys.executable)


def make_ico() -> None:
    """Convert app_icon.png to a multi-size Windows .ico file."""
    if ICON_ICO.exists():
        print(f"  Icon exists  : {ICON_ICO} (skipping generation)")
        return
    try:
        from PIL import Image
    except ImportError:
        print("ERROR: Pillow is required for icon conversion.")
        print("       Run:  pip install Pillow")
        sys.exit(1)

    if not ICON_PNG.exists():
        print(f"ERROR: {ICON_PNG} not found.")
        print("       Save your icon image as app_icon.png in the project folder first.")
        sys.exit(1)

    img = Image.open(ICON_PNG).convert("RGBA")

    # Center-crop to square so the icon is never distorted on resize.
    w, h  = img.size
    side  = min(w, h)
    left  = (w - side) // 2
    top   = (h - side) // 2
    img   = img.crop((left, top, left + side, top + side))

    # Pillow's ICO plugin resizes from the source automatically when sizes= is given.
    # append_images is an APNG/GIF parameter and has no effect on ICO output.
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(str(ICON_ICO), format="ICO", sizes=sizes)

    # Verify all sizes were embedded.
    from PIL import IcoImagePlugin  # noqa: F401 — side-effect: registers the plugin
    check = Image.open(ICON_ICO)
    embedded = check.info.get("sizes", set())
    print(f"  Icon written : {ICON_ICO}  ({side}×{side} px source, {len(embedded)} sizes embedded)")


def make_shortcut() -> None:
    """Create (or replace) the Desktop shortcut using PowerShell + WScript.Shell.
    Uses SpecialFolders('Desktop') so OneDrive-redirected Desktops are found correctly.
    """
    # Escape single quotes in paths for PowerShell
    pythonw_esc = str(PYTHONW).replace("'", "''")
    script_esc  = str(SCRIPT).replace("'", "''")
    icon_esc    = str(ICON_ICO).replace("'", "''")
    project_esc = str(PROJECT_DIR).replace("'", "''")

    ps_script = f"""
$ws      = New-Object -ComObject WScript.Shell
$desktop = $ws.SpecialFolders('Desktop')
$lnk     = Join-Path $desktop 'Nullify.lnk'
$s       = $ws.CreateShortcut($lnk)
$s.TargetPath       = '{pythonw_esc}'
$s.Arguments        = '"{script_esc}"'
$s.IconLocation     = '{icon_esc}'
$s.WorkingDirectory = '{project_esc}'
$s.Description      = 'Nullify Redaction Tool'
$s.Save()
Write-Output $lnk
"""
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        check=True, capture_output=True, text=True,
    )
    lnk_path = result.stdout.strip()
    print(f"  Shortcut     : {lnk_path}")

    # Force Windows to rebuild the icon cache so the new icon appears immediately.
    refresh = r"""
$cache = "$env:LOCALAPPDATA\IconCache.db"
if (Test-Path $cache) { Remove-Item $cache -Force }
$cacheDir = "$env:LOCALAPPDATA\Microsoft\Windows\Explorer"
if (Test-Path $cacheDir) {
    Get-ChildItem $cacheDir -Filter "iconcache_*.db" |
        Remove-Item -Force -ErrorAction SilentlyContinue
}
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Start-Process explorer
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", refresh],
        capture_output=True,
    )
    print("  Icon cache   : refreshed (Explorer restarted)")


if __name__ == "__main__":
    print("Building icon and desktop shortcut…")
    make_ico()
    make_shortcut()
    print("\nDone. Double-click the shortcut on your Desktop to launch the tool.")
