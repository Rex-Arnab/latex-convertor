#!/usr/bin/env python3
"""Universal document converter API.

POST any supported document (multipart/form-data) and a target format; get back
the converted file. Default target is .docx, where plain-text LaTeX
($...$, $$...$$, \\(...\\), \\[...\\]) becomes real Word equations (OMML).

Run:  uvicorn app:app --host 0.0.0.0 --port 8100
Docs: /docs   |   Capabilities: /formats
"""
from __future__ import annotations

import os
import shutil
import tempfile
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from access_log import log_requests
from converters import Format, router
from converters.detection import detect
from converters.registry import media_type, output_ext, source_ext
from latex_to_equations import ConversionError

MAX_BYTES = 25 * 1024 * 1024  # 25 MB upload cap

app = FastAPI(
    title="Universal Document Converter",
    version="2.0.0",
    description="Convert between document formats; LaTeX becomes real Word equations.",
)

# Log every request to a file (./logs/access.log, rotated by logrotate).
app.middleware("http")(log_requests)


class ConvertOptions(BaseModel):
    target: Format = Format.docx
    math: bool = True  # run the LaTeX->OMML post-process on docx/pdf targets
    pdf_input_mode: Literal["text"] = "text"  # "math" = pluggable, not enabled yet


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/formats")
def formats() -> dict:
    """Live capability view: which engines are up and which conversions we serve."""
    caps = router.discover()
    targets = [t.value for t in router.supported_targets()]
    sources = [f.value for f in Format if router.can_read(f)]
    return {
        "engines": caps,
        "default_target": Format.docx.value,
        "sources": sources,
        "targets": targets,
    }


async def validated_upload(
    request: Request, file: UploadFile = File(...)
) -> tuple[str, Format, bytes]:
    """Validate the multipart upload and detect its format. Keeps request-shape
    validation out of the route body (validate -> service -> response)."""
    name = file.filename or "upload"
    request.state.upload_name = name  # picked up by the access-log middleware
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {MAX_BYTES // (1024 * 1024)} MB).",
        )
    try:
        src_fmt = detect(name, data)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    if not router.can_read(src_fmt):
        raise HTTPException(
            status_code=415,
            detail=f"No engine available to read '{src_fmt.value}' on this server.",
        )
    return name, src_fmt, data


@app.post("/convert")
def convert_endpoint(
    upload: tuple[str, Format, bytes] = Depends(validated_upload),
    target: Annotated[Format, Form()] = Format.docx,
    math: Annotated[bool, Form()] = True,
    pdf_input_mode: Annotated[Literal["text"], Form()] = "text",
) -> FileResponse:
    """Convert an uploaded document to `target` and stream it back.

    Sync `def` so FastAPI runs the blocking work (pandoc / LibreOffice
    subprocesses) in a threadpool rather than on the event loop.
    """
    opts = ConvertOptions(target=target, math=math, pdf_input_mode=pdf_input_mode)
    name, src_fmt, data = upload
    if target not in router.supported_targets():
        raise HTTPException(
            status_code=400,
            detail=f"Target '{target.value}' is not available. See /formats.",
        )

    workdir = tempfile.mkdtemp(prefix="convapi-")
    cleanup = BackgroundTask(shutil.rmtree, workdir, ignore_errors=True)
    src_path = os.path.join(workdir, f"input.{source_ext(src_fmt)}")
    with open(src_path, "wb") as fh:
        fh.write(data)

    try:
        outcome = router.convert(src_path, src_fmt, target, opts, workdir)
    except ConversionError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:  # defensive: no stack traces, no leaked temp dirs
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Conversion failed: {exc}")

    stem = os.path.splitext(os.path.basename(name))[0] or "document"
    download_name = f"{stem}.{output_ext(target)}"
    omml = outcome.omml
    headers = {
        "X-Source-Format": src_fmt.value,
        "X-Target-Format": target.value,
        "X-Engine-Used": "+".join(outcome.engines) or "none",
        "X-Latex-Spans": str(omml.spans if omml else 0),
        "X-Latex-Unique": str(omml.unique if omml else 0),
        "X-Equations-Converted": str(omml.converted if omml else 0),
        "X-Latex-Unparsed": str(len(omml.missing) if omml else 0),
    }
    return FileResponse(
        outcome.out_path,
        media_type=media_type(target),
        filename=download_name,
        headers=headers,
        background=cleanup,
    )
