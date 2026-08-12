# Universal Document Converter

A FastAPI service that converts documents between formats. Its distinguishing
feature: plain-text LaTeX in the source (`$...$`, `$$...$$`, `\(...\)`, `\[...\]`)
becomes **real Word equations (OMML)** in the `.docx` output — not images, not
literal dollar-sign text. Editable in Word's equation editor.

Because equations are routed through OMML and PDFs are produced by LibreOffice,
**no TeX/LaTeX installation is required**.

---

## What it can convert

**Sources it reads:** markdown, html, latex, rst, docx, doc, odt, rtf, epub,
pptx, ppt, xlsx, xls, org, typst, ipynb, mediawiki, csv, txt, pdf

**Targets it writes:** docx *(default)*, pdf, html, markdown, latex, odt, rtf,
epub, txt

The live set depends on which engines are installed — `GET /formats` reports what
this particular host can actually do.

### How it routes

1. **Normalize** — a source pandoc can't read is converted first: legacy binary
   office (`.doc`/`.ppt`/`.xls`) → docx via LibreOffice; PDF → markdown via PyMuPDF.
2. **Produce the target** —
   - `docx` → pandoc builds it, then the OMML pass converts any literal LaTeX.
   - `pdf` → build that docx (equations and all), then LibreOffice docx → pdf.
   - anything else → pandoc straight to the target.

Format detection trusts **magic bytes** over the file extension for binary
containers, so a `.doc` mislabeled as `.docx` still routes correctly.

---

## Requirements

### Python

Python **3.10+** (developed and deployed on 3.13).

### System tools — install these separately, NOT via pip

| Tool | Needed for | Without it |
|---|---|---|
| **pandoc** | almost every conversion | only LibreOffice-native paths work |
| **LibreOffice** (`soffice`) | **all PDF output**; reading `.doc`/`.ppt`/`.xls` | no PDF target, no legacy office input |
| **libmagic** | magic-byte format detection | falls back to file extension only |
| **Bengali / Noto fonts** | Bengali text in PDF output | tofu boxes (□□□) in PDFs |

---

## Setup — Linux

### 1. System packages

**Debian / Ubuntu:**

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv curl \
                    pandoc libreoffice libmagic1 \
                    fonts-beng fonts-noto
```

> On Ubuntu 24.04 the `libmagic1` package was renamed `libmagic1t64` by the
> 64-bit `time_t` transition. The command above still works — the new package
> provides the old name — so install it exactly as written.

**Fedora / RHEL:**

```bash
sudo dnf install -y python3 python3-pip pandoc libreoffice file-libs \
                    google-noto-sans-bengali-fonts google-noto-fonts-common
```

**Arch:**

```bash
sudo pacman -S python python-pip pandoc libreoffice-fresh file noto-fonts
```

### 2. Project

```bash
git clone https://github.com/Rex-Arnab/latex-convertor.git
cd latex-convertor

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Run

```bash
uvicorn app:app --host 0.0.0.0 --port 8100
```

Open <http://localhost:8100/docs> for interactive API docs.

### 4. Verify the engines came up

```bash
curl -s localhost:8100/formats | python3 -m json.tool
```

All three engines should report `true`:

```json
{
  "engines": { "pandoc": true, "libreoffice": true, "pdf_input": true },
  "default_target": "docx"
}
```

Any `false` means that tool isn't on `PATH` — revisit step 1.

---

## Setup — Windows

### 1. System packages

Easiest via **winget**, in PowerShell:

```powershell
winget install --id JohnMacFarlane.Pandoc -e
winget install --id TheDocumentFoundation.LibreOffice -e
winget install --id Python.Python.3.13 -e
```

> `winget` ships with **Windows 10/11 desktop** only. On **Windows Server** it is
> generally absent (it depends on the Store / App Installer), so use the
> Chocolatey commands below instead — the rest of this guide is unchanged.

Or with **Chocolatey**, which works on desktop and Server alike:

```powershell
choco install pandoc libreoffice-fresh python
```

**Close and reopen PowerShell** afterwards so `PATH` changes take effect.

### 2. ⚠️ Put LibreOffice on PATH — required

This is the step that most often gets missed. The installer does **not** add
`soffice.exe` to `PATH`, and the app locates LibreOffice purely by looking for
`soffice`/`libreoffice` on `PATH`. Skip this and you silently lose **all PDF
output** and **all `.doc`/`.ppt`/`.xls` input**.

```powershell
# Permanent, current user. Adjust the path if you installed elsewhere.
[Environment]::SetEnvironmentVariable(
    "Path",
    $env:Path + ";C:\Program Files\LibreOffice\program",
    "User"
)
```

Reopen PowerShell, then confirm:

```powershell
soffice --version
pandoc --version
```

### 3. Project

```powershell
git clone https://github.com/Rex-Arnab/latex-convertor.git
cd latex-convertor

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks the activate script, run
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that session.

### 4. ⚠️ Fix `python-magic` on Windows

`requirements.txt` pins `python-magic`, which expects the `libmagic` C library —
present on Linux/macOS, **absent on Windows**. Install the bundled-DLL variant:

```powershell
pip uninstall -y python-magic
pip install python-magic-bin
```

This is optional but recommended. Without libmagic the service still runs and
falls back to extension-based detection — you just lose correct handling of files
whose extension lies about their real type.

### 5. Bengali fonts

Windows ships **Nirmala UI**, which covers Bengali, so PDF output generally works
out of the box. For wider script coverage, install
[Noto Sans Bengali](https://fonts.google.com/noto/specimen/Noto+Sans+Bengali)
(download → select all `.ttf` → right-click → *Install for all users*).

### 6. Run

```powershell
uvicorn app:app --host 0.0.0.0 --port 8100
```

Open <http://localhost:8100/docs>.

### 7. Verify

```powershell
curl.exe -s localhost:8100/formats | ConvertFrom-Json | ConvertTo-Json -Depth 5
```

Confirm `pandoc`, `libreoffice`, and `pdf_input` are all `true`.

---

## Using the API

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | liveness — `{"status":"ok"}` |
| `GET` | `/formats` | which engines are up, and readable/writable formats |
| `POST` | `/convert` | convert an uploaded file |
| `GET` | `/docs` | interactive Swagger UI |

### `POST /convert`

Send `multipart/form-data`:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `file` | file | *required* | the document to convert (max **25 MB**) |
| `target` | string | `docx` | output format |
| `math` | bool | `true` | run the LaTeX → OMML pass on docx/pdf targets |
| `pdf_input_mode` | string | `text` | PDF reading mode (only `text` is enabled) |

### Examples

**Markdown with LaTeX → Word, macOS/Linux:**

```bash
curl -X POST http://localhost:8100/convert \
     -F "file=@notes.md" \
     -F "target=docx" \
     -o notes.docx
```

**Same, Windows PowerShell:**

```powershell
curl.exe -X POST http://localhost:8100/convert `
         -F "file=@notes.md" `
         -F "target=docx" `
         -o notes.docx
```

**Legacy `.doc` → PDF:**

```bash
curl -X POST http://localhost:8100/convert \
     -F "file=@old.doc" -F "target=pdf" -o out.pdf
```

**Skip the equation pass:**

```bash
curl -X POST http://localhost:8100/convert \
     -F "file=@plain.md" -F "math=false" -o plain.docx
```

### Response headers — the conversion report

Every successful `/convert` reports what happened. Worth checking when output
looks wrong:

| Header | Meaning |
|---|---|
| `X-Source-Format` | format that was actually detected (may differ from the extension) |
| `X-Target-Format` | format produced |
| `X-Engine-Used` | engine chain, e.g. `libreoffice+pandoc+omml` |
| `X-Latex-Spans` | LaTeX spans found in the source |
| `X-Latex-Unique` | distinct expressions among them |
| `X-Equations-Converted` | spans successfully turned into Word equations |
| `X-Latex-Unparsed` | spans that could **not** be parsed — if non-zero, some math stayed literal text |

```bash
curl -D - -X POST http://localhost:8100/convert \
     -F "file=@notes.md" -o notes.docx
```

### Error codes

| Code | Meaning |
|---|---|
| `400` | empty file, or a target this host can't produce |
| `413` | over the 25 MB cap |
| `415` | unrecognized file type, or no engine can read it |
| `422` | conversion itself failed (engine error) |
| `500` | unexpected server-side failure |

---

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `API_LOG_FILE` | `./logs/access.log` | access-log path (parent dir auto-created) |

The 25 MB upload cap is `MAX_BYTES` in `app.py`.

Logging uses `WatchedFileHandler`, so an external `logrotate` can rotate the file
while workers keep appending — no restart needed.

---

## Running in production (Linux)

The reference deployment runs behind nginx + Cloudflare as a systemd unit. Client
IP resolution already prefers `CF-Connecting-IP`, then `X-Forwarded-For`, then
`X-Real-IP`.

**`/etc/systemd/system/latex-convertor.service`:**

```ini
[Unit]
Description=Universal Document Converter API
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/latex-convertor
ExecStart=/opt/latex-convertor/.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8100 --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now latex-convertor
sudo systemctl status latex-convertor
```

**`/etc/logrotate.d/latex-convertor`:**

```
/opt/latex-convertor/logs/access.log {
    weekly
    rotate 8
    compress
    delaycompress
    missingok
    notifempty
}
```

---

## Troubleshooting

**`/formats` shows `"libreoffice": false`**
`soffice` isn't on `PATH`. On Windows see step 2 above; on Linux install
`libreoffice`. Detection checks `soffice`, then `libreoffice`, then the standard
macOS app path — nothing else.

**PDF output returns 400 / "requires LibreOffice"**
Same cause. PDF is produced *only* by LibreOffice; pandoc is never used for it.

**Equations came out as literal `$x^2$` text**
Check `X-Latex-Unparsed`. Non-zero means those expressions weren't parsed. Also
confirm `math=true` (the default) and that your target is `docx` or `pdf` — the
OMML pass runs on those two only.

**Bengali renders as `□□□` in PDFs**
Missing fonts on the *server*, not the client. Install `fonts-beng`/Noto Bengali
and restart LibreOffice-backed conversions.

**`ImportError: failed to find libmagic`**
Windows — do step 4 (`python-magic-bin`). Linux — `sudo apt install libmagic1`.

**Conversions hang or time out**
pandoc is capped at 180s, LibreOffice at 240s. LibreOffice uses a throwaway
profile dir per request so concurrent calls don't deadlock on its single-instance
lock — if you've modified that, restore it.

**A `.docx` fails but the same content as `.md` works**
The upload is probably a legacy `.doc` renamed to `.docx`. Magic-byte detection
handles this — unless libmagic is missing. See step 4.

---

## Project layout

```
app.py                   FastAPI app: routes, validation, response headers
access_log.py            per-request access logging middleware
latex_to_equations.py    LaTeX -> OMML conversion; the docx post-process
converters/
  registry.py            single source of truth: formats, MIME, extensions
  detection.py           extension + magic-byte source detection
  engines.py             thin wrappers: pandoc, LibreOffice, PyMuPDF
  router.py              orchestrator: picks and composes engines
pathshala*.doc(x)        test fixtures
```

## Testing it works

### Test 1 — markdown → docx

```bash
printf 'Energy is $E = mc^2$ and area is $$A = \\pi r^2$$\n' > /tmp/test.md
curl -D - -X POST http://localhost:8100/convert \
     -F "file=@/tmp/test.md" -o /tmp/test.docx
```

Expect `200 OK` and `X-Engine-Used: pandoc+omml`.

**`X-Equations-Converted` will read `0` here — that is correct, not a failure.**
Pandoc understands `$...$` in markdown and emits Word equations itself, so by the
time the OMML pass runs there is no literal LaTeX left to convert. The counters
report only what *that pass* did.

Verify the equations really are there:

```bash
python3 -c "
import zipfile
d = zipfile.ZipFile('/tmp/test.docx').read('word/document.xml').decode('utf8')
print('equations:', d.count('<m:oMath'), '| literal \$ left:', d.count('\$'))"
```

Expect a non-zero equation count and `0` dollar signs remaining. Open the file in
Word and click an equation — it should be editable, not a picture.

### Test 2 — the OMML pass itself

The custom pass exists for LaTeX that survives as **literal text**, which is what
happens with a `.docx` where someone typed the dollar signs by hand. Build one
(run with the virtualenv active — this uses `python-docx`):

```bash
python3 -c "
from docx import Document
d = Document()
d.add_paragraph('Energy is \$E = mc^2\$ and area is \$A = \\\\pi r^2\$ here.')
d.add_paragraph('Fraction: \$\\\\frac{a}{b}\$ done.')
d.save('/tmp/literal.docx')"

curl -D - -X POST http://localhost:8100/convert \
     -F "file=@/tmp/literal.docx" -o /tmp/literal_out.docx
```

Here the counters do move — expect `X-Latex-Spans: 3`,
`X-Equations-Converted: 3`, `X-Latex-Unparsed: 0`.

### Test 3 — PDF and legacy input

```bash
curl -D - -X POST http://localhost:8100/convert \
     -F "file=@/tmp/test.md" -F "target=pdf" -o /tmp/out.pdf   # pandoc+omml+libreoffice
curl -D - -X POST http://localhost:8100/convert \
     -F "file=@old.doc" -o /tmp/out.docx                        # libreoffice+omml
```

`X-Engine-Used` should name the full chain in each case.

---

## Verified environments

The Linux instructions above were run end-to-end in a clean `ubuntu:24.04`
container (arm64): all three engines came up, and markdown→docx, literal-LaTeX
OMML, markdown→PDF, and legacy `.doc`→docx all succeeded. Bengali rendered in PDF
with the `Lohit-Bengali` font embedded, confirming `fonts-beng` does its job.

**The Windows instructions have not been executed end-to-end.** They are derived
from the code — `engines.py` locates LibreOffice via `PATH` only, and
`detection.py` guards the `magic` import — so the two ⚠️ steps are the known
failure points rather than guesses. Treat the rest as unverified until someone
runs it on a real Windows box; corrections welcome.
