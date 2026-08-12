"""The orchestrator. Picks engines per (source -> target) pair and composes them
into a small pipeline, with the LaTeX->OMML post-process hooked in for docx/pdf.

Pipeline shape:
  1. Normalize any non-pandoc source (legacy office -> docx via LibreOffice;
     pdf -> markdown via PyMuPDF) into something pandoc can read.
  2. Produce the target:
       - docx : (pandoc ->)docx, then OMML post-process for any literal $...$.
       - pdf  : build that docx (with equations), then LibreOffice docx -> pdf.
       - else : pandoc straight to the target.
This routes math + Bengali through OMML/LibreOffice and avoids needing a TeX
install on the server.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from latex_to_equations import ConversionError, ConversionResult, apply_omml_to_docx

from .engines import LibreOfficeEngine, PandocEngine, PdfInputEngine
from .registry import (
    Format,
    LIBREOFFICE_READ,
    PANDOC_READ,
    PANDOC_WRITE,
    TARGETS,
    output_ext,
)


@dataclass
class ConvertOutcome:
    out_path: str
    source: Format
    target: Format
    engines: list[str]
    omml: ConversionResult | None = None


class Router:
    def __init__(self) -> None:
        self.pandoc = PandocEngine()
        self.libre = LibreOfficeEngine()
        self.pdf_in = PdfInputEngine()
        self._caps: dict[str, bool] | None = None

    def discover(self) -> dict[str, bool]:
        if self._caps is None:
            self._caps = {
                "pandoc": self.pandoc.available(),
                "libreoffice": self.libre.available(),
                "pdf_input": self.pdf_in.available(),
            }
        return self._caps

    def can_read(self, fmt: Format) -> bool:
        caps = self.discover()
        return (
            (fmt in PANDOC_READ and caps["pandoc"])
            or (fmt in LIBREOFFICE_READ and caps["libreoffice"])
            or (fmt == Format.pdf and caps["pdf_input"])
        )

    def supported_targets(self) -> list[Format]:
        caps = self.discover()
        out: list[Format] = []
        for t in TARGETS:
            if t == Format.pdf:
                if caps["libreoffice"]:
                    out.append(t)
            elif t == Format.docx:
                if caps["pandoc"] or caps["libreoffice"]:
                    out.append(t)
            elif t in PANDOC_WRITE and caps["pandoc"]:
                out.append(t)
        return out

    def convert(self, src_path, src_fmt, dst_fmt, opts, workdir) -> ConvertOutcome:
        caps = self.discover()
        engines: list[str] = []

        # 1. Normalize non-pandoc sources into a pandoc-readable form.
        cur_path, cur_fmt = src_path, src_fmt
        if src_fmt not in PANDOC_READ:
            if src_fmt in LIBREOFFICE_READ and caps["libreoffice"]:
                cur_path = self.libre.convert(src_path, "docx", workdir)
                cur_fmt = Format.docx
                engines.append("libreoffice")
            elif src_fmt == Format.pdf and caps["pdf_input"]:
                cur_path = self.pdf_in.to_markdown(
                    src_path, workdir, opts.pdf_input_mode
                )
                cur_fmt = Format.markdown
                engines.append("pdf_input")
            else:
                raise ConversionError(f"No engine available to read '{src_fmt.value}'.")

        # 2. Produce the requested target.
        omml: ConversionResult | None = None
        if dst_fmt in (Format.docx, Format.pdf):
            docx_path = self._to_docx(cur_path, cur_fmt, workdir, engines)
            if opts.math:
                out_docx = os.path.join(workdir, "with_math.docx")
                omml = apply_omml_to_docx(docx_path, out_docx)
                docx_path = out_docx
                engines.append("omml")
            if dst_fmt == Format.docx:
                out_path = docx_path
            else:
                if not caps["libreoffice"]:
                    raise ConversionError("PDF output requires LibreOffice.")
                out_path = self.libre.convert(docx_path, "pdf", workdir)
                engines.append("libreoffice")
        else:
            if not caps["pandoc"]:
                raise ConversionError("pandoc is required for this target format.")
            out_path = os.path.join(workdir, f"out.{output_ext(dst_fmt)}")
            self.pandoc.run(cur_path, cur_fmt, out_path, dst_fmt)
            engines.append("pandoc")

        return ConvertOutcome(out_path, src_fmt, dst_fmt, engines, omml)

    def _to_docx(self, cur_path, cur_fmt, workdir, engines) -> str:
        if cur_fmt == Format.docx:
            return cur_path
        if not self.discover()["pandoc"]:
            raise ConversionError("pandoc is required to build a docx.")
        out = os.path.join(workdir, "from_pandoc.docx")
        self.pandoc.run(cur_path, cur_fmt, out, Format.docx)
        engines.append("pandoc")
        return out


router = Router()
