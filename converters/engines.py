"""Conversion engines: thin wrappers over the external tools the router drives.

Each engine reports whether it is `available()` on this host (so the same code
runs on the Mac and the Linux server, lighting up whatever is installed) and
exposes purpose-specific methods the router composes into a pipeline.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from latex_to_equations import ConversionError

from .registry import Format, pandoc_name


def _run(cmd: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        raise ConversionError(
            f"{cmd[0]} failed (exit {proc.returncode}): {' | '.join(tail)}"
        )
    return proc


class PandocEngine:
    name = "pandoc"

    def available(self) -> bool:
        return shutil.which("pandoc") is not None

    def run(self, src: str, src_fmt: Format, dst: str, dst_fmt: Format) -> str:
        """Convert a pandoc-readable file to a pandoc-writable target."""
        cmd = [
            "pandoc",
            src,
            "-f",
            pandoc_name(src_fmt),
            "-t",
            pandoc_name(dst_fmt),
            "--standalone",
            "-o",
            dst,
        ]
        _run(cmd)
        return dst


class LibreOfficeEngine:
    name = "libreoffice"

    def __init__(self) -> None:
        self._bin = (
            shutil.which("soffice")
            or shutil.which("libreoffice")
            or (
                "/Applications/LibreOffice.app/Contents/MacOS/soffice"
                if os.path.exists(
                    "/Applications/LibreOffice.app/Contents/MacOS/soffice"
                )
                else None
            )
        )

    def available(self) -> bool:
        return self._bin is not None

    def convert(self, src: str, target_ext: str, outdir: str) -> str:
        """Convert `src` to `target_ext` (e.g. 'docx', 'pdf') inside `outdir`.

        Uses a throwaway profile dir so concurrent requests don't fight over
        LibreOffice's single-instance lock.
        """
        profile = os.path.join(outdir, "_loprofile")
        cmd = [
            self._bin,
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to",
            target_ext,
            "--outdir",
            outdir,
            src,
        ]
        _run(cmd, timeout=240)
        produced = os.path.join(
            outdir,
            os.path.splitext(os.path.basename(src))[0] + "." + target_ext.split(":")[0],
        )
        if not os.path.exists(produced):
            raise ConversionError(
                f"LibreOffice produced no {target_ext} for {os.path.basename(src)}"
            )
        return produced


class PdfInputEngine:
    """Reads PDFs. Text mode (PyMuPDF) is the basic, installed path; the math
    mode is a pluggable slot (Docling/Marker/Mathpix) that is not enabled yet."""

    name = "pdf_input"

    def available(self) -> bool:
        try:
            import fitz  # noqa: F401  (PyMuPDF)

            return True
        except Exception:
            return False

    def to_markdown(self, src: str, outdir: str, mode: str = "text") -> str:
        if mode != "text":
            raise ConversionError(
                f"PDF math-recovery mode '{mode}' is not enabled on this server "
                "(install a math backend: docling / marker / mathpix)."
            )
        md = self._extract_text(src)
        out = os.path.join(outdir, "from_pdf.md")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(md)
        return out

    @staticmethod
    def _extract_text(src: str) -> str:
        try:  # prefer pymupdf4llm: better paragraph/table structure
            import pymupdf4llm

            return pymupdf4llm.to_markdown(src)
        except Exception:
            pass
        import fitz  # PyMuPDF text fallback

        doc = fitz.open(src)
        try:
            return "\n\n".join(page.get_text("text") for page in doc)
        finally:
            doc.close()
