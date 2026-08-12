#!/usr/bin/env python3
"""Convert plain-text LaTeX expressions inside a Word .doc/.docx into real
Word equations (OMML), so Word renders them as math instead of raw `$...$` text.

Supported delimiters:  $...$   $$...$$   \\(...\\)   \\[...\\]

Pipeline:
  .doc  --(textutil/soffice)-->  .docx
  document.xml  --per paragraph-->  find LaTeX spans
  unique LaTeX  --(one pandoc call)-->  OMML <m:oMath> elements
  rebuild each paragraph, keeping original per-run formatting for the text and
  splicing the equation elements inline where the LaTeX used to be.

Requires: pandoc on PATH, python lxml. On macOS, textutil handles .doc; elsewhere
LibreOffice (soffice) is used if present.
"""
from __future__ import annotations

import argparse
import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass

from lxml import etree


class ConversionError(Exception):
    """Raised when a document cannot be converted (bad input, missing tools)."""


@dataclass
class ConversionResult:
    spans: int  # total LaTeX spans found in the document
    unique: int  # distinct LaTeX expressions
    converted: int  # equations actually inserted
    missing: list[str]  # expressions pandoc could not parse (left as text)


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
XML = "http://www.w3.org/XML/1998/namespace"
NS = {"w": W, "m": M}

W_P = f"{{{W}}}p"
W_R = f"{{{W}}}r"
W_T = f"{{{W}}}t"
W_RPR = f"{{{W}}}rPr"
M_OMATH = f"{{{M}}}oMath"

# Math spans, longest delimiter first so $$ wins over $. Inner LaTeX is whichever
# group matched. `$...$` forbids an inner `$` so an unmatched dollar stays literal.
TOKEN = re.compile(
    r"\$\$(.+?)\$\$"  # $$ display $$
    r"|\\\[(.+?)\\\]"  # \[ display \]
    r"|\$([^$]+?)\$"  # $ inline $
    r"|\\\((.+?)\\\)",  # \( inline \)
    re.S,
)


def inner_latex(match: re.Match) -> str:
    """Return the captured LaTeX from whichever alternative matched."""
    return next(g for g in match.groups() if g is not None)


# --------------------------------------------------------------------------- #
# .doc -> .docx
# --------------------------------------------------------------------------- #
def ensure_docx(src: str, workdir: str) -> str:
    """Return a path to a .docx for `src`, converting from legacy .doc if needed."""
    if src.lower().endswith(".docx"):
        return src
    if not src.lower().endswith(".doc"):
        raise ConversionError(f"Unsupported input (need .doc or .docx): {src}")

    out = os.path.join(workdir, "input.docx")
    if shutil.which("textutil"):  # macOS
        subprocess.run(
            ["textutil", "-convert", "docx", src, "-output", out], check=True
        )
        return out
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if soffice:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", workdir, src],
            check=True,
        )
        produced = os.path.join(
            workdir, os.path.splitext(os.path.basename(src))[0] + ".docx"
        )
        if not os.path.exists(produced):
            raise ConversionError("LibreOffice did not produce a .docx")
        return produced
    raise ConversionError(
        "Cannot convert .doc: need `textutil` (macOS) or `soffice` (LibreOffice)."
    )


# --------------------------------------------------------------------------- #
# LaTeX -> OMML (single batched pandoc call)
# --------------------------------------------------------------------------- #
def latex_to_omml(expressions: list[str], workdir: str) -> dict[str, etree._Element]:
    """Convert each unique LaTeX expression to an <m:oMath> element.

    Everything goes through one pandoc invocation. Each expression is tagged with
    an alphanumeric marker so results stay aligned even if one fails to parse, and
    a leading plain line prevents pandoc's `%`-title-block from eating the first.
    """
    pandoc = shutil.which("pandoc")
    if not pandoc:
        raise ConversionError("pandoc not found on PATH (brew install pandoc).")

    mark = lambda i: f"MQX{i}QXM"
    md = "BATCHSTART\n\n" + "\n\n".join(
        f"{mark(i)} ${e}$" for i, e in enumerate(expressions)
    )
    md_path = os.path.join(workdir, "batch.md")
    docx_path = os.path.join(workdir, "batch.docx")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    subprocess.run([pandoc, md_path, "-o", docx_path], check=True)

    with zipfile.ZipFile(docx_path) as zf:
        tree = etree.fromstring(zf.read("word/document.xml"))

    marker_re = re.compile(r"MQX(\d+)QXM")
    result: dict[str, etree._Element] = {}
    for p in tree.iter(W_P):
        text = "".join(t.text or "" for t in p.iter(W_T))
        omaths = p.findall(f".//{M_OMATH}")
        if not omaths:
            continue
        for m in marker_re.finditer(text):
            idx = int(m.group(1))
            if 0 <= idx < len(expressions):
                result[expressions[idx]] = omaths[0]
    return result


# --------------------------------------------------------------------------- #
# Paragraph rewriting
# --------------------------------------------------------------------------- #
def make_text_run(rpr: etree._Element | None, text: str) -> etree._Element:
    r = etree.Element(W_R)
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = etree.SubElement(r, W_T)
    t.set(f"{{{XML}}}space", "preserve")
    t.text = text
    return r


def text_pieces(pieces, start, end):
    """Yield (rPr, substring) for char range [start,end), split at run boundaries
    so each fragment keeps the formatting of the run it came from."""
    offset = 0
    for rpr, txt in pieces:
        a, b = offset, offset + len(txt)
        offset = b
        if b <= start or a >= end:
            continue
        sub = txt[max(start, a) - a : min(end, b) - a]
        if sub:
            yield rpr, sub


def collect_paragraph(p):
    """Return (full_text, pieces, text_runs) for a paragraph.
    pieces is [(rPr, text), ...] over the text-bearing runs, in order."""
    pieces, text_runs = [], []
    for r in p.findall(W_R):
        ts = r.findall(W_T)
        if not ts:
            continue
        text_runs.append(r)
        pieces.append((r.find(W_RPR), "".join(t.text or "" for t in ts)))
    return "".join(t for _, t in pieces), pieces, text_runs


def rewrite_paragraph(p, omml_map) -> int:
    """Replace LaTeX spans in paragraph `p` with equations. Returns # converted."""
    full, pieces, text_runs = collect_paragraph(p)
    if not text_runs:
        return 0
    matches = list(TOKEN.finditer(full))
    if not matches:
        return 0

    nodes, pos, converted = [], 0, 0
    for m in matches:
        if m.start() > pos:  # plain text before this equation
            nodes += [
                make_text_run(r, s) for r, s in text_pieces(pieces, pos, m.start())
            ]
        omath = omml_map.get(inner_latex(m))
        if omath is not None:
            nodes.append(copy.deepcopy(omath))
            converted += 1
        else:  # conversion failed -> leave the literal text untouched
            nodes += [
                make_text_run(r, s) for r, s in text_pieces(pieces, m.start(), m.end())
            ]
        pos = m.end()
    if pos < len(full):  # trailing text
        nodes += [make_text_run(r, s) for r, s in text_pieces(pieces, pos, len(full))]

    anchor = text_runs[0].getprevious()  # usually w:pPr
    for r in text_runs:
        p.remove(r)
    ref = anchor
    for node in nodes:
        if ref is None:
            p.insert(0, node)
        else:
            ref.addnext(node)
        ref = node
    return converted


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def apply_omml_to_docx(in_docx: str, out_docx: str) -> ConversionResult:
    """Rewrite plain-text LaTeX spans inside `in_docx` as OMML equations, writing
    the result to `out_docx`. All other docx parts and per-run formatting are
    preserved. A docx with no LaTeX is written through unchanged (converted=0).

    This is the reusable core: the router calls it on ANY docx it produces
    (md→docx, html→docx, pdf→docx, …), and `convert()` calls it for the CLI.
    """
    try:
        with zipfile.ZipFile(in_docx) as zf:
            names = zf.namelist()
            doc_xml = zf.read("word/document.xml")
            members = {n: zf.read(n) for n in names}
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ConversionError(f"Not a valid .docx (Office Open XML) file: {exc}")

    tree = etree.fromstring(doc_xml)
    paragraphs = list(tree.iter(W_P))

    # pass 1: gather every unique LaTeX expression
    seen = []
    for p in paragraphs:
        full, _, _ = collect_paragraph(p)
        for m in TOKEN.finditer(full):
            seen.append(inner_latex(m))
    uniq = list(dict.fromkeys(seen))

    with tempfile.TemporaryDirectory() as workdir:
        omml_map = latex_to_omml(uniq, workdir) if uniq else {}
    missing = [e for e in uniq if e not in omml_map]

    # pass 2: rewrite paragraphs
    total = sum(rewrite_paragraph(p, omml_map) for p in paragraphs)

    new_xml = etree.tostring(
        tree, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    members["word/document.xml"] = new_xml
    with zipfile.ZipFile(out_docx, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:  # preserve original member order
            zf.writestr(name, members[name])

    return ConversionResult(
        spans=len(seen), unique=len(uniq), converted=total, missing=missing
    )


def convert(src: str, dst: str) -> ConversionResult:
    """Convert LaTeX in `src` (.doc/.docx) to equations, writing a .docx to `dst`.

    Raises ConversionError on unrecoverable problems (bad input type, missing
    tools). A document with no LaTeX is not an error: a .doc is still upgraded
    to .docx (converted=0).
    """
    with tempfile.TemporaryDirectory() as workdir:
        docx = ensure_docx(src, workdir)
        return apply_omml_to_docx(docx, dst)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("input", help="Path to the source .doc or .docx file")
    ap.add_argument(
        "-o", "--output", help="Output .docx path (default: <input>_math.docx)"
    )
    args = ap.parse_args()

    if not os.path.isfile(args.input):
        sys.exit(f"No such file: {args.input}")
    out = args.output or os.path.splitext(args.input)[0] + "_math.docx"
    try:
        result = convert(args.input, out)
    except ConversionError as exc:
        sys.exit(str(exc))

    if result.spans == 0:
        print(f"No LaTeX expressions found; wrote unchanged copy -> {out}")
    else:
        print(
            f"Found {result.spans} LaTeX spans ({result.unique} unique); "
            f"converted {result.converted} equation(s) -> {out}"
        )
    if result.missing:
        print(
            f"WARNING: {len(result.missing)} expression(s) could not be parsed and "
            f"were left as text:\n  " + "\n  ".join(repr(e) for e in result.missing)
        )


if __name__ == "__main__":
    main()
