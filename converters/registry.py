"""Format registry: the canonical set of formats, how to detect them by
extension/MIME, how to name them for pandoc, and how to serve them back.

This is the single source of truth the router and the API both read from.
"""

from __future__ import annotations

from enum import Enum


class Format(str, Enum):
    markdown = "markdown"
    html = "html"
    latex = "latex"
    rst = "rst"
    docx = "docx"
    doc = "doc"
    odt = "odt"
    rtf = "rtf"
    epub = "epub"
    pptx = "pptx"
    ppt = "ppt"
    xlsx = "xlsx"
    xls = "xls"
    org = "org"
    typst = "typst"
    ipynb = "ipynb"
    mediawiki = "mediawiki"
    csv = "csv"
    txt = "txt"
    pdf = "pdf"


# Extension -> Format (lowercased, with leading dot).
EXT_TO_FORMAT: dict[str, Format] = {
    ".md": Format.markdown,
    ".markdown": Format.markdown,
    ".mdown": Format.markdown,
    ".html": Format.html,
    ".htm": Format.html,
    ".tex": Format.latex,
    ".latex": Format.latex,
    ".rst": Format.rst,
    ".docx": Format.docx,
    ".doc": Format.doc,
    ".odt": Format.odt,
    ".rtf": Format.rtf,
    ".epub": Format.epub,
    ".pptx": Format.pptx,
    ".ppt": Format.ppt,
    ".xlsx": Format.xlsx,
    ".xls": Format.xls,
    ".org": Format.org,
    ".typ": Format.typst,
    ".typst": Format.typst,
    ".ipynb": Format.ipynb,
    ".wiki": Format.mediawiki,
    ".csv": Format.csv,
    ".txt": Format.txt,
    ".text": Format.txt,
    ".pdf": Format.pdf,
}

# A few MIME types (from libmagic) -> Format, for detection fallback.
MIME_TO_FORMAT: dict[str, Format] = {
    "application/pdf": Format.pdf,
    "application/msword": Format.doc,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": Format.docx,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": Format.pptx,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": Format.xlsx,
    "application/vnd.ms-powerpoint": Format.ppt,
    "application/vnd.ms-excel": Format.xls,
    "application/vnd.oasis.opendocument.text": Format.odt,
    "application/rtf": Format.rtf,
    "text/rtf": Format.rtf,
    "application/epub+zip": Format.epub,
    "text/html": Format.html,
    "text/x-tex": Format.latex,
    "application/x-tex": Format.latex,
    "text/markdown": Format.markdown,
    "text/plain": Format.txt,
    "text/csv": Format.csv,
}

# Media type + output extension to serve each target with.
MEDIA_TYPE: dict[Format, str] = {
    Format.docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    Format.pdf: "application/pdf",
    Format.html: "text/html",
    Format.markdown: "text/markdown",
    Format.latex: "application/x-tex",
    Format.odt: "application/vnd.oasis.opendocument.text",
    Format.rtf: "application/rtf",
    Format.epub: "application/epub+zip",
    Format.pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    Format.rst: "text/x-rst",
    Format.org: "text/plain",
    Format.typst: "text/plain",
    Format.txt: "text/plain",
}
OUTPUT_EXT: dict[Format, str] = {
    Format.docx: "docx",
    Format.pdf: "pdf",
    Format.html: "html",
    Format.markdown: "md",
    Format.latex: "tex",
    Format.odt: "odt",
    Format.rtf: "rtf",
    Format.epub: "epub",
    Format.pptx: "pptx",
    Format.rst: "rst",
    Format.org: "org",
    Format.typst: "typ",
    Format.txt: "txt",
}

# Pandoc reader/writer names. Most match the enum value; the exceptions live here.
PANDOC_NAME: dict[Format, str] = {Format.txt: "plain"}

# What pandoc can read / write natively (NOT pdf, NOT legacy binary office).
PANDOC_READ: set[Format] = {
    Format.markdown,
    Format.html,
    Format.latex,
    Format.rst,
    Format.docx,
    Format.odt,
    Format.rtf,
    Format.epub,
    Format.org,
    Format.typst,
    Format.ipynb,
    Format.mediawiki,
    Format.csv,
    Format.txt,
}
PANDOC_WRITE: set[Format] = {
    Format.markdown,
    Format.html,
    Format.latex,
    Format.rst,
    Format.docx,
    Format.odt,
    Format.rtf,
    Format.epub,
    Format.org,
    Format.typst,
    Format.pptx,
    Format.txt,
}

# Formats LibreOffice can open (used to normalize non-pandoc sources to docx,
# and as the engine for any -> pdf).
LIBREOFFICE_READ: set[Format] = {
    Format.doc,
    Format.docx,
    Format.odt,
    Format.rtf,
    Format.ppt,
    Format.pptx,
    Format.xls,
    Format.xlsx,
    Format.html,
    Format.txt,
    Format.csv,
}

# Targets the service advertises.
TARGETS: list[Format] = [
    Format.docx,
    Format.pdf,
    Format.html,
    Format.markdown,
    Format.latex,
    Format.odt,
    Format.rtf,
    Format.epub,
    Format.txt,
]


# Canonical extension to give a saved INPUT file, keyed by its detected format
# (so a mislabeled upload is handed to engines with the right extension).
SOURCE_EXT: dict[Format, str] = {
    Format.markdown: "md",
    Format.html: "html",
    Format.latex: "tex",
    Format.rst: "rst",
    Format.docx: "docx",
    Format.doc: "doc",
    Format.odt: "odt",
    Format.rtf: "rtf",
    Format.epub: "epub",
    Format.pptx: "pptx",
    Format.ppt: "ppt",
    Format.xlsx: "xlsx",
    Format.xls: "xls",
    Format.org: "org",
    Format.typst: "typ",
    Format.ipynb: "ipynb",
    Format.mediawiki: "wiki",
    Format.csv: "csv",
    Format.txt: "txt",
    Format.pdf: "pdf",
}


def source_ext(fmt: Format) -> str:
    return SOURCE_EXT.get(fmt, fmt.value)


def pandoc_name(fmt: Format) -> str:
    return PANDOC_NAME.get(fmt, fmt.value)


def media_type(fmt: Format) -> str:
    return MEDIA_TYPE.get(fmt, "application/octet-stream")


def output_ext(fmt: Format) -> str:
    return OUTPUT_EXT.get(fmt, fmt.value)
