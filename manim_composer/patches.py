"""Monkey-patches for ManimGL compatibility with MiKTeX on Windows.

MiKTeX's `latex` command rejects the `-no-pdf` flag that manimgl
unconditionally passes.  The flag is only meaningful for `xelatex`
(which defaults to PDF output); `latex` already produces DVI.

This module replaces `full_tex_to_svg` with a version that omits
`-no-pdf` when the compiler is `latex`.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from functools import wraps
from pathlib import Path


def apply_miktex_patch() -> None:
    """Patch manimgl's tex pipeline so it works on MiKTeX."""
    import manimlib.utils.tex_file_writing as tex_mod
    from manimlib.utils.cache import cache_on_disk

    @cache_on_disk
    def _patched_full_tex_to_svg(
        full_tex: str, compiler: str = "latex", message: str = ""
    ) -> str:
        if message:
            print(message, end="\r")

        if compiler == "latex":
            dvi_ext = ".dvi"
        elif compiler == "xelatex":
            dvi_ext = ".xdv"
        else:
            raise NotImplementedError(f"Compiler '{compiler}' is not implemented")

        with tempfile.TemporaryDirectory() as temp_dir:
            tex_path = Path(temp_dir, "working").with_suffix(".tex")
            dvi_path = tex_path.with_suffix(dvi_ext)

            tex_path.write_text(full_tex)

            cmd = [compiler, "-interaction=batchmode", "-halt-on-error",
                   f"-output-directory={temp_dir}", str(tex_path)]
            # -no-pdf is only needed for xelatex (MiKTeX's latex rejects it)
            if compiler == "xelatex":
                cmd.insert(1, "-no-pdf")

            process = subprocess.run(cmd, capture_output=True, text=True)

            if process.returncode != 0:
                error_str = ""
                log_path = tex_path.with_suffix(".log")
                if log_path.exists():
                    content = log_path.read_text()
                    error_match = re.search(r"(?<=\n! ).*\n.*\n", content)
                    if error_match:
                        error_str = error_match.group()
                raise tex_mod.LatexError(error_str or "LaTeX compilation failed")

            process = subprocess.run(
                ["dvisvgm", str(dvi_path), "-n", "-v", "0", "--stdout"],
                capture_output=True,
            )
            result = process.stdout.decode("utf-8")

        if message:
            print(" " * len(message), end="\r")

        return result

    tex_mod.full_tex_to_svg = _patched_full_tex_to_svg
