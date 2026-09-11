# Reading photographs and documents — Surya, RapidOCR and Docling

An officer at a site has two kinds of evidence in hand: **a photograph of the work board**,
and often **paper** — a sanction order, a work order, a completion certificate. The case
file reads both.

| What | Reader | Why this one |
|---|---|---|
| Photograph of a site board | **Surya OCR 2** (primary) | A vision-language OCR model: reads a whole board, keeps the label next to its value, reads the "₹" sign |
| The same photograph, again | **RapidOCR** (PP-OCRv4) | An independent second reader. Two readers agreeing on a work number is evidence; one reader at "99%" is not |
| When Surya is missing or will not start | **RapidOCR** alone | The site keeps working; the screen says which reader was used |
| Documents (PDF or scan) | **Docling** | Keeps the structure — headings, tables, reading order — and runs OCR only on pages that are pictures of paper |

Everything runs **on this machine**. No photograph or document leaves it.

## What the officer sees

On the Case File, in **Site visit report**:

1. A line saying which reader will read the next photograph, and whether Surya is still
   starting.
2. After a photograph: the work number and amount read, **which reader read them**, and
   **what the second reader read** — "✓ read the same work number" or "read MP… instead".
3. If the two readers disagree, the save button stays locked until the officer ticks the box
   confirming which work the board shows. The other reading is offered as a choice.
4. **Attach a document**: the document is read, every work number in it is listed and
   checked against the records, and the screen says plainly whether *this* work is
   mentioned. The text Docling read (tables included) can be opened underneath.
5. The saved report keeps the photograph, the document, which reader read the board, and
   whether the readers agreed — kept apart from what the officer concluded.

Nothing the computer reads is ever treated as settled. It narrows; the officer confirms.

## Setting it up

```bash
# 1. Python packages (CPU PyTorch saves ~4 GB of disk)
python -m uv pip install --python .venv/Scripts/python.exe \
  --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match \
  surya-ocr docling torch torchvision

# 2. The llama.cpp server Surya runs on (official ggml-org build, Vulkan GPU support)
winget install ggml.llamacpp

# 3. Surya's model (~1.5 GB), downloaded resumably and checked against Hugging Face
.venv/Scripts/python.exe scripts/fetch_ocr_models.py
```

Optional, in `.env`:

| Variable | Default | Meaning |
|---|---|---|
| `MPLADS_OCR_ENGINES` | `surya,rapidocr` | Photograph readers in order; the first available is primary, the next checks it |
| `MPLADS_LLAMA_DEVICE` | llama.cpp's choice | e.g. `Vulkan1` for the discrete GPU (`llama-server --list-devices`) |
| `MPLADS_LLAMA_SERVER` | PATH, then the winget folder | Path to `llama-server` |
| `MPLADS_SURYA_GGUF_DIR` | `data/models/ocr/surya-ocr-2-gguf` | Where the model lives |
| `MPLADS_SURYA_STARTUP_TIMEOUT` | `300` | Seconds allowed for the model to load |

Docling's own layout models (about 400 MB) download the first time a document is read.
On a network where Hugging Face's Xet client stalls, set `HF_HUB_DISABLE_XET=1` (the API
sets it for its own downloads).

## How it behaves when something is missing

| Missing | What happens |
|---|---|
| Surya's model not downloaded, or only partly | Surya reports "not available"; RapidOCR reads photographs. A half-downloaded model is detected by `manifest.json` (written only after the size and SHA-256 match Hugging Face), so it never crashes a start |
| `llama-server` not installed | Same — RapidOCR reads |
| Surya fails to start | The failure is remembered; every later photograph goes straight to RapidOCR rather than waiting on a dead server. `GET /api/ocr/status` shows the reason |
| Surya fails on one photograph | That photograph falls to RapidOCR; the result says `fell_back_from: surya` |
| Docling not installed | Documents cannot be attached; photographs are unaffected |
| No OCR at all | The officer types the work number — verification never depends on OCR |

## API

| Route | Does |
|---|---|
| `POST /api/ocr` | Photograph → text, fields, engine, second-reader check, match against all 210,993 works, photo re-use check |
| `POST /api/ocr/document` | Document → Markdown, every work number (each checked against the records), amounts, whether this work is mentioned |
| `GET /api/document/{name}` | Serve a stored document |
| `GET /api/ocr/status` | Which readers exist here, which is primary, whether Surya is loaded, and why not |

Uploads are stored under a content hash, never the name the uploader gave; a file named
`.pdf` that is not a PDF is refused; photographs are capped at 12 MB and documents at 20 MB.

## How good is it

Measured, not assumed: `scripts/benchmark_ocr.py` draws boards for real works, damages them
the way a phone photograph is damaged, and scores each reader against the known answer.
Results: [`docs/OCR_BENCHMARK.md`](OCR_BENCHMARK.md). They are **synthetic boards** — a
sample of real photographs labelled by officers replaces them the day one exists.

Measured on 44 boards across 11 photograph conditions (seed 42), on a Quadro T1000 (4 GB):

| | Surya OCR 2 | RapidOCR |
|---|---|---|
| Work number exactly right | **93%** | 91% |
| Amount within 1% | **93%** | 73% |
| Shaking-hand (motion) blur | **50%** | 0% |
| Heavy JPEG compression | 75% | **100%** |
| Seconds per board | 20 (GPU) | 2 (CPU) |

The number that justifies running both: on one heavily compressed photograph Surya read a
**wrong but plausible** reference (MP301**58**90 for MP301**90**90). RapidOCR read it right,
the two disagreed, and the match was held for the officer. On the 40 boards where both
found a number, they **never agreed on the same wrong one**. At least one of the two read
the number right on 95% of boards.

The cost is time: a vision-language model writes its answer a token at a time, about 20
seconds a board on a 4 GB laptop GPU. The screen says so, from the last read measured.

## Tests

- `tests/test_ocr_engines.py` — the behaviour around the engines, with stand-ins (fast):
  fallback, cross-check, disagreement, half-downloaded models, documents, storage, API.
- `tests/test_ocr_real.py` — the real engines. Docling runs whenever its models are cached;
  Surya starts a GPU server, so it runs only with `MPLADS_TEST_SURYA=1`.

## Known limits

- **Surya takes a few seconds to start** (7 s measured on the T1000; longer from a cold
  disk). The API starts it in the background at launch so no officer waits for it; a model
  added while the API is running is picked up on the first photograph, which then waits.
- On Windows, Surya logs `Failed to stop llamacpp … WinError 87` at shutdown. The server
  *is* stopped — Surya's own check misreads Windows' "no such process" error.
- Surya gives no per-character confidence, so the confidence shown is RapidOCR's, and only
  when both readers agree.
- Surya is not used inside Docling: scanned documents are read by Docling's bundled
  PP-OCRv6. Documents are clean compared with weathered boards, and this keeps a document
  from waiting behind a photograph for the GPU.
