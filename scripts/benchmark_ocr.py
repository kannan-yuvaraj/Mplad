"""Measure how well each OCR reader reads MPLADS site boards — before trusting any of them.

    .venv/Scripts/python.exe scripts/benchmark_ocr.py              # 60 boards, every reader
    .venv/Scripts/python.exe scripts/benchmark_ocr.py --boards 200 --engines rapidocr

No dataset of real board photographs with known answers exists, so this makes one: boards
drawn from **real works in the portfolio** (real references, amounts, agencies), then put
through what a phone at a site does to a picture — tilt, perspective, blur, a shaking hand,
fading, low light, sensor noise, heavy JPEG compression, a board far away in a wider photo,
and all of them at once. Because the board was drawn from
a known work, the right answer is known exactly.

For every reader it reports, per condition:

* **exact reference** — the work number read exactly right (the one that matters: a single
  wrong digit is a different real work);
* **reference found** — any work number found at all;
* **amount** — the sanctioned amount read to within 1%;
* **seconds per board**.

and, where two readers ran, how often they agree, and how often they agree *and are wrong*
— the case a cross-check cannot catch. Results go to `docs/OCR_BENCHMARK.md` and
`data/artifacts/ocr_benchmark.json`.

These are synthetic boards: they measure the readers against the *kinds* of damage a real
photograph suffers, not against real photographs. A real sample, labelled by officers,
replaces this the day one exists.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mplads import config, ocr  # noqa: E402

FONTS = [Path(p) for p in (
    "C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/verdana.ttf", "C:/Windows/Fonts/tahoma.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
) if Path(p).exists()]

#: Board colour schemes seen on MPLADS and PWD sign boards.
SCHEMES = [("#f2f0e8", "#1d4a2f", "#171310"), ("#ffffff", "#0e2a47", "#111111"),
           ("#fff6d6", "#8a1c1c", "#1a1a1a"), ("#e8f0f7", "#14406e", "#0b0b0b")]

CONDITIONS = ["clean", "tilt", "perspective", "blur", "motion", "faded", "dim", "noise", "jpeg",
              "distant", "harsh"]


def _font(size: int, rng: random.Random):
    path = rng.choice(FONTS) if FONTS else None
    return ImageFont.truetype(str(path), size) if path else ImageFont.load_default()


def draw_board(work: pd.Series, rng: random.Random) -> Image.Image:
    """A display board for a real work, laid out the way MPLADS boards are."""
    width, height = 1100, 700
    ground, band, ink = rng.choice(SCHEMES)
    image = Image.new("RGB", (width, height), ground)
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 96], fill=band)
    draw.text((40, 30), "MEMBER OF PARLIAMENT LOCAL AREA DEVELOPMENT SCHEME",
              font=_font(26, rng), fill="white")
    draw.rectangle([24, 120, width - 24, height - 24], outline=band, width=3)
    amount = float(work["recommended_amount"] or 0)
    amount_text = rng.choice(["Rs {:,.0f}", "Rs. {:,.0f}", "₹ {:,.0f}"]).format(amount)
    rows = [
        ("Work No.", work["work_ref"]),
        ("Description", str(work["work_description"])[:48]),
        ("Sanctioned Amount", amount_text),
        ("Implementing Agency", str(work["implementing_agency"])[:40]),
        ("Constituency", f"{work['constituency']}, {work['state_name']}"[:40]),
        ("Recommended On", str(work["recommendation_date"])[:10]),
    ]
    y = 160
    for label, value in rows:
        draw.text((56, y), label + ":", font=_font(24, rng), fill="#5c5346")
        draw.text((370, y), str(value), font=_font(28, rng), fill=ink)
        y += 78
    return image


def _perspective(image: Image.Image, rng: random.Random, strength: float) -> Image.Image:
    w, h = image.size
    d = lambda: rng.uniform(0, strength) * min(w, h)  # noqa: E731
    src = [(d(), d()), (w - d(), d()), (w - d(), h - d()), (d(), h - d())]
    dst = [(0, 0), (w, 0), (w, h), (0, h)]
    matrix = []
    for (x, y), (u, v) in zip(dst, src):
        matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
    coeffs = np.linalg.solve(np.array(matrix, float), np.array(src, float).reshape(8))
    return image.transform((w, h), Image.PERSPECTIVE, coeffs, Image.BICUBIC, fillcolor="#6b6b5e")


def degrade(image: Image.Image, condition: str, rng: random.Random) -> Image.Image:
    """What a phone at a site does to a picture of a board."""
    def jpeg(img, quality):
        buffer = BytesIO()
        img.save(buffer, "JPEG", quality=quality)
        return Image.open(BytesIO(buffer.getvalue())).convert("RGB")

    def noise(img, sigma):
        array = np.asarray(img).astype(np.float32)
        array += np.random.default_rng(rng.randrange(1 << 30)).normal(0, sigma, array.shape)
        return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))

    if condition == "clean":
        return image
    if condition == "tilt":
        return image.rotate(rng.uniform(-7, 7), expand=True, fillcolor="#6b6b5e")
    if condition == "perspective":
        return _perspective(image, rng, 0.09)
    if condition == "blur":
        return image.filter(ImageFilter.GaussianBlur(rng.uniform(2.2, 3.2)))
    if condition == "motion":  # a hand that moved while the shutter was open
        from scipy.ndimage import uniform_filter1d

        array = np.asarray(image).astype(np.float32)
        smeared = uniform_filter1d(array, size=rng.choice([9, 11, 13]), axis=1)
        return Image.fromarray(np.clip(smeared, 0, 255).astype(np.uint8))
    if condition == "distant":  # the board is a small part of a wider photograph
        scene = Image.new("RGB", (1600, 1200), rng.choice(["#7d7a6a", "#6f7f5f", "#8a8377"]))
        scene = noise(scene, 18)
        board = image.resize((int(image.width * 0.52), int(image.height * 0.52)))
        scene.paste(board, (rng.randint(60, 600), rng.randint(60, 700)))
        return jpeg(scene, 60)
    if condition == "faded":
        faded = ImageEnhance.Contrast(image).enhance(rng.uniform(0.3, 0.45))
        return ImageEnhance.Brightness(faded).enhance(rng.uniform(1.2, 1.35))
    if condition == "dim":
        return noise(ImageEnhance.Brightness(image).enhance(rng.uniform(0.22, 0.32)), 8)
    if condition == "noise":
        return noise(image, rng.uniform(26, 36))
    if condition == "jpeg":
        small = image.resize((image.width * 2 // 5, image.height * 2 // 5))
        return jpeg(small, rng.randint(12, 20))
    if condition == "harsh":  # everything at once, mildly: a real afternoon photograph
        out = _perspective(image.rotate(rng.uniform(-6, 6), expand=True, fillcolor="#6b6b5e"),
                           rng, 0.07)
        out = ImageEnhance.Contrast(out.filter(ImageFilter.GaussianBlur(1.8))).enhance(0.55)
        out = noise(ImageEnhance.Brightness(out).enhance(0.7), 14)
        return jpeg(out.resize((out.width // 2, out.height // 2)), 30)
    raise ValueError(condition)


def run(boards: int, engines: list[str], seed: int, out_dir: Path) -> dict:
    works = pd.read_parquet(
        config.ARTIFACTS / "works_scored.parquet",
        columns=["work_ref", "recommended_amount", "work_description", "implementing_agency",
                 "constituency", "state_name", "recommendation_date"],
    ).dropna(subset=["work_ref"])
    sample = works.sample(boards, random_state=seed).reset_index(drop=True)
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    readers = {name: ocr.ENGINES[name] for name in engines
               if name in ocr.ENGINES and ocr.ENGINES[name].available()}
    skipped = sorted(set(engines) - set(readers))
    if skipped:
        print("not available here, skipped:", ", ".join(skipped))
    for reader in readers.values():
        if hasattr(reader, "start"):
            began = time.time()
            reader.start()
            print(f"{reader.name} started in {time.time() - began:.1f}s")

    rows = []
    for i, work in sample.iterrows():
        condition = CONDITIONS[i % len(CONDITIONS)]
        image = degrade(draw_board(work, rng), condition, rng)
        if i < len(CONDITIONS):
            image.save(out_dir / f"{i:02d}-{condition}.jpg", quality=90)
        row = {"work_ref": work["work_ref"], "amount": float(work["recommended_amount"]),
               "condition": condition}
        for name, reader in readers.items():
            began = time.time()
            try:
                lines = reader.lines(image)
                error = None
            except Exception as exc:  # a reader crashing is a result, not an abort
                lines, error = [], str(exc)[:120]
            seconds = time.time() - began
            fields = ocr._extract_fields(lines)
            read_ref = (fields.get("work_ref") or {}).get("value")
            read_amount = (fields.get("amount") or {}).get("value")
            row[name] = {
                "read": read_ref,
                "exact": read_ref == work["work_ref"],
                "found": read_ref is not None,
                "amount_ok": bool(read_amount) and abs(read_amount - row["amount"])
                             <= max(row["amount"] * 0.01, 1.0),
                "seconds": round(seconds, 3),
                "error": error,
            }
        rows.append(row)
        marks = "  ".join(f"{n}={'OK ' if row[n]['exact'] else 'X  '}" for n in readers)
        print(f"[{i + 1:>3}/{boards}] {condition:<11} {work['work_ref']:<20} {marks}", flush=True)
    return {"rows": rows, "engines": list(readers), "skipped": skipped,
            "boards": boards, "seed": seed}


def summarise(result: dict) -> dict:
    rows, engines = result["rows"], result["engines"]
    summary: dict = {"overall": {}, "by_condition": {}, "agreement": None}
    for name in engines:
        cells = [r[name] for r in rows]
        summary["overall"][name] = {
            "exact_reference": float(np.mean([c["exact"] for c in cells])),
            "reference_found": float(np.mean([c["found"] for c in cells])),
            "amount_within_1pct": float(np.mean([c["amount_ok"] for c in cells])),
            "seconds_per_board": float(np.median([c["seconds"] for c in cells])),
            "errors": sum(1 for c in cells if c["error"]),
        }
        for condition in CONDITIONS:
            subset = [r[name] for r in rows if r["condition"] == condition]
            if subset:
                summary["by_condition"].setdefault(condition, {})[name] = float(
                    np.mean([c["exact"] for c in subset]))
    if len(engines) >= 2:
        a, b = engines[:2]
        both = [r for r in rows if r[a]["read"] and r[b]["read"]]
        agree = [r for r in both if r[a]["read"] == r[b]["read"]]
        summary["agreement"] = {
            "pair": [a, b],
            "both_found": len(both),
            "agree": len(agree),
            # The dangerous cell: both readers say the same wrong reference.
            "agree_and_wrong": sum(1 for r in agree if not r[a]["exact"]),
            "disagree": len(both) - len(agree),
            "either_exact": float(np.mean([r[a]["exact"] or r[b]["exact"] for r in rows])),
        }
    return summary


def write_report(result: dict, summary: dict, path: Path) -> None:
    engines = result["engines"]
    pct = lambda v: f"{v * 100:.0f}%"  # noqa: E731
    lines = [
        "# OCR benchmark — reading MPLADS site boards",
        "",
        f"{result['boards']} boards drawn from real works in the portfolio, each put through one "
        "of eleven photograph conditions. The right answer is known exactly because each board "
        "was drawn from a known work. Generated by `scripts/benchmark_ocr.py` "
        f"(seed {result['seed']}).",
        "",
        "**These are synthetic boards.** They measure the readers against the *kinds* of damage "
        "a phone photograph suffers — tilt, blur, fading, low light, noise, compression — not "
        "against real photographs. A sample of real boards, labelled by officers, replaces "
        "this the day one exists.",
        "",
        "## Overall",
        "",
        "| Reader | Work number exactly right | Any work number found | Amount within 1% "
        "| Seconds per board |",
        "|---|---|---|---|---|",
    ]
    for name in engines:
        o = summary["overall"][name]
        lines.append(f"| {ocr.ENGINES[name].label} | **{pct(o['exact_reference'])}** | "
                     f"{pct(o['reference_found'])} | {pct(o['amount_within_1pct'])} | "
                     f"{o['seconds_per_board']:.1f} |")
    lines += ["", "## Work number exactly right, by photograph condition", "",
              "| Condition | " + " | ".join(ocr.ENGINES[n].label for n in engines) + " |",
              "|---|" + "---|" * len(engines)]
    for condition, cells in summary["by_condition"].items():
        lines.append(f"| {condition} | " + " | ".join(pct(cells[n]) for n in engines) + " |")
    if summary["agreement"]:
        g = summary["agreement"]
        a, b = (ocr.ENGINES[n].label for n in g["pair"])
        lines += [
            "", "## Two readers on the same photograph", "",
            f"Both found a work number on {g['both_found']} boards. They agreed on "
            f"{g['agree']} and disagreed on {g['disagree']}. **They agreed on the same wrong "
            f"number {g['agree_and_wrong']} time(s)** — the only case a cross-check cannot "
            "catch, and the reason every match is still confirmed by the officer.",
            "",
            f"At least one of {a} and {b} read the number exactly right on "
            f"{pct(g['either_exact'])} of boards.",
        ]
    if result["skipped"]:
        lines += ["", f"Not available on the machine that ran this: {', '.join(result['skipped'])}."]
    lines += ["", "Sample boards, one per condition: `data/artifacts/ocr_benchmark/`.", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--boards", type=int, default=60)
    parser.add_argument("--engines", default=",".join(config.OCR_IMAGE_ENGINES))
    parser.add_argument("--seed", type=int, default=config.RANDOM_SEED)
    args = parser.parse_args()

    result = run(args.boards, [e.strip() for e in args.engines.split(",") if e.strip()],
                 args.seed, config.ARTIFACTS / "ocr_benchmark")
    if not result["engines"]:
        raise SystemExit("no OCR reader is available on this machine")
    summary = summarise(result)
    (config.ARTIFACTS / "ocr_benchmark.json").write_text(
        json.dumps({"summary": summary, **result}, indent=2), encoding="utf-8")
    write_report(result, summary, config.DOCS / "OCR_BENCHMARK.md")
    print(json.dumps(summary["overall"], indent=2))
    print("wrote docs/OCR_BENCHMARK.md")
    ocr.shutdown()


if __name__ == "__main__":
    main()
