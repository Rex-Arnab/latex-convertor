"""Source-format detection: trust the extension first, fall back to magic bytes.

The magic-byte fallback matters because pandoc cannot read a legacy binary .doc
(OLE) and would fail confusingly if a .doc were mislabeled .docx. libmagic tells
the two apart (OLE compound document vs PK zip), so we route correctly.
"""

from __future__ import annotations

import os

from .registry import EXT_TO_FORMAT, MIME_TO_FORMAT, Format

try:  # optional; detection still works on extension alone without it
    import magic as _libmagic
except Exception:  # pragma: no cover - import guard
    _libmagic = None


def _from_magic(data: bytes) -> Format | None:
    if not _libmagic or not data:
        return None
    try:
        mime = _libmagic.from_buffer(data, mime=True)
    except Exception:
        mime = ""
    if mime in MIME_TO_FORMAT:
        return MIME_TO_FORMAT[mime]
    # Legacy OLE containers (old .doc/.xls/.ppt) report a generic mime like
    # application/x-ole-storage or CDFV2; disambiguate via the text description.
    try:
        desc = _libmagic.from_buffer(data).lower()
    except Exception:
        desc = ""
    if "composite document" in desc or "cdfv2" in desc or "ole2" in desc:
        if "excel" in desc or "spreadsheet" in desc:
            return Format.xls
        if "powerpoint" in desc or "presentation" in desc:
            return Format.ppt
        return Format.doc  # default OLE office document
    return None


def detect(filename: str, data: bytes) -> Format:
    """Return the best-guess source Format for an upload.

    Strategy: magic-bytes wins for the formats it identifies confidently
    (binary containers), otherwise the extension decides. This keeps text
    formats (md/html/latex) on the extension (libmagic just says text/plain)
    while catching spoofed/binary mismatches.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    by_ext = EXT_TO_FORMAT.get(ext)
    by_magic = _from_magic(data)

    # Binary containers: trust magic over a possibly-wrong extension.
    BINARY = {
        Format.pdf,
        Format.doc,
        Format.docx,
        Format.ppt,
        Format.pptx,
        Format.xls,
        Format.xlsx,
        Format.odt,
        Format.epub,
        Format.rtf,
    }
    if by_magic in BINARY:
        return by_magic
    if by_ext is not None:
        return by_ext
    if by_magic is not None:
        return by_magic
    raise ValueError(f"Unrecognized file type for '{filename}' (ext='{ext}').")
