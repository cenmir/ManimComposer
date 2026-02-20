"""LaTeX distribution detection and TinyTeX auto-installation."""

import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QWidget

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INSTALL_BASE = Path(os.environ.get("LOCALAPPDATA", "")) / "ManimComposer"
_INSTALL_DIR = _INSTALL_BASE / "TinyTeX"
_BIN_DIR = _INSTALL_DIR / "bin" / "windows"

_TINYTEX_URL = "https://yihui.org/tinytex/TinyTeX-0.zip"

_REQUIRED_PACKAGES = [
    "dvipng",       # DVI → PNG  (canvas rendering)
    "dvisvgm",      # DVI → SVG  (ManimGL preview)
    "standalone",   # \documentclass[standalone]
    "preview",      # \usepackage{preview}
    "amsmath",      # \usepackage{amsmath}
    "amssymb",      # \usepackage{amssymb}
]

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

SYSTEM = "system"
TINYTEX = "tinytex"
NONE = "none"


def detect() -> str:
    """Return SYSTEM, TINYTEX, or NONE depending on LaTeX availability."""
    if shutil.which("latex"):
        return SYSTEM
    if (_BIN_DIR / "latex.exe").is_file():
        return TINYTEX
    return NONE


def is_complete() -> bool:
    """Check whether the local TinyTeX has all required executables."""
    for name in ("latex.exe", "dvipng.exe", "dvisvgm.exe"):
        if not (_BIN_DIR / name).is_file():
            return False
    return True


# ---------------------------------------------------------------------------
# PATH management
# ---------------------------------------------------------------------------

def ensure_path() -> None:
    """Prepend TinyTeX bin dir to os.environ['PATH'] if TinyTeX is active.

    Call once at startup so every subprocess.run() inherits the correct PATH.
    """
    if detect() == TINYTEX:
        bin_dir = str(_BIN_DIR)
        if bin_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")


def get_latex_env() -> dict | None:
    """Return env dict with TinyTeX on PATH, or None if system LaTeX is used."""
    status = detect()
    if status == SYSTEM:
        return None
    if status == TINYTEX:
        env = os.environ.copy()
        bin_dir = str(_BIN_DIR)
        if bin_dir not in env.get("PATH", ""):
            env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
        return env
    return None


# ---------------------------------------------------------------------------
# Install worker (runs in QThread)
# ---------------------------------------------------------------------------

class TinyTeXInstallWorker(QThread):
    """Downloads, extracts, and configures TinyTeX in a background thread."""

    progress = pyqtSignal(int, int)       # (bytes_received, total_bytes)
    phase_changed = pyqtSignal(str)       # status label text
    finished_ok = pyqtSignal()
    error = pyqtSignal(str)

    def run(self):
        try:
            self._download_and_extract()
            self._install_packages()
            self.finished_ok.emit()
        except Exception as exc:
            self.error.emit(str(exc))

    # -- phases --

    def _download_and_extract(self):
        self.phase_changed.emit("Downloading TinyTeX…")
        zip_path = Path(tempfile.gettempdir()) / "TinyTeX-0.zip"

        def _reporthook(block_num, block_size, total_size):
            self.progress.emit(block_num * block_size, max(total_size, 1))

        urlretrieve(_TINYTEX_URL, str(zip_path), reporthook=_reporthook)

        self.phase_changed.emit("Extracting…")
        _INSTALL_BASE.mkdir(parents=True, exist_ok=True)
        # Remove old install if present so we get a clean state
        if _INSTALL_DIR.exists():
            shutil.rmtree(_INSTALL_DIR, ignore_errors=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(_INSTALL_BASE)

        zip_path.unlink(missing_ok=True)

        if not (_BIN_DIR / "latex.exe").is_file():
            raise RuntimeError(
                f"Extraction failed — latex.exe not found at {_BIN_DIR}"
            )

    def _install_packages(self):
        self.phase_changed.emit("Installing LaTeX packages…")
        tlmgr = str(_BIN_DIR / "tlmgr.bat")
        result = subprocess.run(
            [tlmgr, "install"] + _REQUIRED_PACKAGES,
            capture_output=True, text=True, timeout=300,
            creationflags=_CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tlmgr install failed (exit {result.returncode}):\n"
                f"{result.stderr or result.stdout}"
            )


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

def offer_install(parent: QWidget) -> bool:
    """Ask the user whether to install TinyTeX. Returns True if accepted."""
    answer = QMessageBox.question(
        parent,
        "LaTeX Not Found",
        "LaTeX is not installed on this system.\n\n"
        "Manim Composer can automatically install TinyTeX,\n"
        "a lightweight LaTeX distribution (~45 MB download).\n\n"
        "Install now?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes,
    )
    return answer == QMessageBox.StandardButton.Yes


def run_install(parent: QWidget) -> bool:
    """Run the TinyTeX install with a progress dialog. Returns True on success."""
    dlg = QProgressDialog("Preparing…", "Cancel", 0, 100, parent)
    dlg.setWindowTitle("Installing TinyTeX")
    dlg.setMinimumDuration(0)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setValue(0)

    worker = TinyTeXInstallWorker()
    success = False
    error_msg = ""

    def on_progress(received, total):
        if total > 0:
            dlg.setMaximum(total)
            dlg.setValue(min(received, total))

    def on_phase(text):
        dlg.setLabelText(text)
        # Switch to indeterminate for the package-install phase
        if "packages" in text.lower():
            dlg.setMaximum(0)

    def on_ok():
        nonlocal success
        success = True
        dlg.close()

    def on_error(msg):
        nonlocal error_msg
        error_msg = msg
        dlg.close()

    worker.progress.connect(on_progress)
    worker.phase_changed.connect(on_phase)
    worker.finished_ok.connect(on_ok)
    worker.error.connect(on_error)
    dlg.canceled.connect(worker.terminate)

    worker.start()
    dlg.exec()  # blocks until dialog is closed
    worker.wait()

    if success:
        ensure_path()
        QMessageBox.information(
            parent, "Success",
            "TinyTeX installed successfully.\n"
            "LaTeX rendering is now available."
        )
        return True

    if error_msg:
        QMessageBox.critical(
            parent, "Installation Failed",
            f"TinyTeX installation failed:\n\n{error_msg}"
        )
    return False
