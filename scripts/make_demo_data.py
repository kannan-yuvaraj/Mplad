"""Generate the sample data used to demonstrate the field-verification loop.

Nothing here is invented government data. The works are real rows from the portfolio; what
is generated is the *photograph an officer would take* of a board that already exists at
every MPLADS site, plus a small set of verification records marked as demonstration data
so they can never be mistaken for real site visits.

Run:

    .venv/Scripts/python.exe scripts/make_demo_data.py

Writes `demo/photos/*.png|jpg` and `demo/WALKTHROUGH.md`, and seeds the verification store.
"""

from __future__ import annotations

import hashlib
import random
import sys
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mplads import config, field  # noqa: E402

DEMO = config.REPO_ROOT / "demo"
PHOTOS = DEMO / "photos"

#: Windows first because that is where this is demonstrated, then the usual Linux paths.
FONT_CANDIDATES = [
    Path("C:/Windows/Fonts/arialbd.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]

BOARD = (1100, 700)


def _font(size: int):
    for path in FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_board(work: pd.Series, *, weathered: bool = False) -> Image.Image:
    """Draw the display board that MPLADS requires at every work site."""
    image = Image.new("RGB", BOARD, "#f2f0e8")
    draw = ImageDraw.Draw(image)

    draw.rectangle([0, 0, BOARD[0], 96], fill="#1d4a2f")
    draw.text((40, 30), "MEMBER OF PARLIAMENT LOCAL AREA DEVELOPMENT SCHEME",
              font=_font(26), fill="white")
    draw.rectangle([24, 120, BOARD[0] - 24, BOARD[1] - 24], outline="#1d4a2f", width=3)

    amount = float(work["recommended_amount"] or 0)
    rows = [
        ("Work No.", work["work_ref"]),
        ("Description", str(work["work_description"])[:52]),
        ("Sanctioned Amount", "Rs {:,.0f}".format(amount)),
        ("Implementing Agency", str(work["implementing_agency"])[:44]),
        ("Constituency", "{}, {}".format(work["constituency"], work["state_name"])),
        ("Recommended On", str(work["recommendation_date"])[:10]),
    ]
    y = 160
    for label, value in rows:
        draw.text((56, y), label + ":", font=_font(24), fill="#5c5346")
        draw.text((360, y), str(value), font=_font(28), fill="#171310")
        y += 78

    if weathered:
        # A real board photographed at a real site: sun-faded, slightly out of focus.
        image = image.filter(ImageFilter.GaussianBlur(1.4))
        image = ImageEnhance.Contrast(image).enhance(0.72)
        image = ImageEnhance.Brightness(image).enhance(1.18)
    return image


def in_scene(board: Image.Image, work_ref: str) -> Image.Image:
    """Stand the board at its own roadside, the way an officer's photograph shows it.

    A bare board is a flat template: every work's board has the same layout and
    differs only in small text, which a perceptual hash cannot see. Uploaded one
    after another, five different works all "matched" each other, so the demo
    reported a re-used photograph that never existed. Real photographs differ in
    sky, ground, framing and what stands behind the board — so these do too.
    The scene is seeded by the work reference, so the same work always gets the
    same scene and `reshoot` of it still matches, which is the point of that demo.
    """
    rng = random.Random(int(hashlib.sha256(work_ref.encode()).hexdigest()[:12], 16))
    width, height = 1600, 1100
    horizon = rng.randint(330, 720)
    sky_top = rng.randint(90, 235)
    scene = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(scene)
    for y in range(horizon):  # sky, darker or lighter per site
        shade = int(sky_top + (255 - sky_top) * y / max(horizon, 1) * 0.6)
        draw.line([(0, y), (width, y)], fill=(shade - 20, shade, min(255, shade + 25)))
    ground = rng.choice([(96, 84, 60), (60, 92, 48), (140, 120, 90), (48, 48, 44)])
    draw.rectangle([0, horizon, width, height], fill=ground)
    for _ in range(rng.randint(3, 9)):  # trees, buildings, a wall — whatever is there
        x = rng.randint(-100, width)
        w = rng.randint(80, 420)
        top = horizon - rng.randint(60, 360)
        tone = rng.randint(20, 120)
        if rng.random() < 0.5:
            draw.ellipse([x, top, x + w, horizon + 40], fill=(tone, tone + 30, tone))
        else:
            draw.rectangle([x, top, x + w, horizon + 10], fill=(tone + 60, tone + 50, tone + 40))

    scale = rng.uniform(0.62, 0.88)
    placed = board.resize((int(board.width * scale), int(board.height * scale)))
    placed = placed.rotate(rng.uniform(-4, 4), expand=True, fillcolor=ground)
    x = rng.randint(40, width - placed.width - 40)
    y = rng.randint(60, height - placed.height - 40)
    post = (x + placed.width // 2 - 12, y + placed.height - 10)
    draw.rectangle([post[0], post[1], post[0] + 24, height], fill=(70, 70, 70))
    scene.paste(placed, (x, y))
    return scene


def reshoot(image: Image.Image) -> bytes:
    """The same picture, sent again the way a re-used photo actually arrives.

    Resized, re-compressed and brightened. Its SHA-256 is completely different; the
    perceptual hash is not. That gap is the whole demonstration.
    """
    smaller = image.resize((int(image.width * 0.78), int(image.height * 0.78)))
    brighter = ImageEnhance.Brightness(smaller).enhance(1.09)
    buffer = BytesIO()
    brighter.save(buffer, "JPEG", quality=72)
    return buffer.getvalue()


def as_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def pick_works() -> pd.DataFrame:
    """Four real works: two top leads, and two ordinary ones."""
    frame = pd.read_parquet(
        config.ARTIFACTS / "works_scored.parquet",
        columns=["work_ref", "work_description", "recommended_amount", "state_name",
                 "constituency", "implementing_agency", "recommendation_date", "band",
                 "audit_roi", "is_completed"],
    )
    leads = frame[frame["band"] == "HIGH"].sort_values(
        ["audit_roi", "work_ref"], ascending=[False, True]
    )
    ordinary = frame[frame["band"] == "NONE"].sort_values("work_ref")
    return pd.concat([leads.head(2), ordinary.head(2)]).reset_index(drop=True)


def main() -> None:
    PHOTOS.mkdir(parents=True, exist_ok=True)
    works = pick_works()
    lead, second_lead, ordinary_a, ordinary_b = (works.iloc[i] for i in range(4))

    written: list[tuple[str, str]] = []

    def save(name: str, data: bytes, caption: str) -> None:
        (PHOTOS / name).write_bytes(data)
        written.append((name, caption))

    def photo(work, **kw):
        return in_scene(render_board(work, **kw), str(work["work_ref"]))

    save("01-board-matches.png", as_png(photo(lead)),
         "A clean board for {}. It reads, and it matches the case file you are "
         "standing in.".format(lead["work_ref"]))

    save("02-board-different-work.png", as_png(photo(second_lead)),
         "A board for {}. Upload it on {}'s case file and the reader says so instead "
         "of accepting it.".format(second_lead["work_ref"], lead["work_ref"]))

    save("03-photo-first-submission.png", as_png(photo(ordinary_a)),
         "Submitted first, for {}.".format(ordinary_a["work_ref"]))

    save("04-photo-resubmitted.jpg", reshoot(photo(ordinary_a)),
         "The same photograph resized, re-compressed and brightened, then submitted for "
         "{}. A different file; the same picture.".format(ordinary_b["work_ref"]))

    save("05-board-weathered.png", as_png(photo(ordinary_b, weathered=True)),
         "Faded and out of focus, the way boards actually look. Shows what the reader "
         "does when it is unsure rather than pretending it is not.")

    # The public copy the Submit page loads its samples from.
    public = config.REPO_ROOT / "frontend" / "public" / "demo" / "photos"
    public.mkdir(parents=True, exist_ok=True)
    for name, _ in written:
        (public / name).write_bytes((PHOTOS / name).read_bytes())

    if "--photos-only" in sys.argv:
        print("photographs only: no records seeded, walkthrough unchanged")
    else:
        seed_records(lead, second_lead, ordinary_a)
        write_walkthrough(works, written)

    print("wrote {} photographs to {}".format(len(written), PHOTOS))
    for name, caption in written:
        print("  {:34s} {}".format(name, caption[:70]))
    print("\nwalkthrough: {}".format(DEMO / "WALKTHROUGH.md"))


def seed_records(lead, second_lead, ordinary) -> None:
    """A little history, so the screens are not empty. Marked as demonstration data."""
    seeds = [
        (lead["work_ref"], "VERIFIED_IN_PROGRESS", "demo.nodal.bihar", "state",
         "Site visited with the block engineer. Foundation work under way; the board "
         "matches the sanction."),
        (second_lead["work_ref"], "RECORD_MISMATCH", "demo.audit.cag", "auditor",
         "Work exists but covers 3 locations, not the 7 named in the recommendation. "
         "Referred to the implementing agency for a written explanation."),
        (ordinary["work_ref"], "VERIFIED_COMPLETE", "demo.nodal.bihar", "state",
         "Complete and in use. Nothing to raise."),
    ]
    existing = {v["work_ref"] for v in field.recent(200)}
    added = 0
    for work_ref, outcome, actor, role, notes in seeds:
        if work_ref in existing:
            continue
        field.record(work_ref=work_ref, outcome=outcome, actor=actor, role=role,
                     notes=notes, demo=True)
        added += 1
    print("seeded {} demonstration verification records "
          "(excluded from the label count)".format(added))


def write_walkthrough(works: pd.DataFrame, written: list[tuple[str, str]]) -> None:
    lead = works.iloc[0]
    ordinary_a, ordinary_b = works.iloc[2], works.iloc[3]
    lines = [
        "# Field verification - demonstration walkthrough",
        "",
        "Everything below runs on real portfolio rows. The photographs are generated "
        "renderings of the display board MPLADS already requires at every work site; the "
        "verification records are marked as demonstration data and are excluded from the "
        "label count on the Data Transparency screen.",
        "",
        "## Before you start",
        "",
        "1. Sign in at `/login` as **auditor** (password `mplads2026`).",
        "2. Open the case file for `{}`.".format(lead["work_ref"]),
        "3. Scroll to **Field verification**.",
        "",
        "## The four things to show",
        "",
        "### 1. It reads the board",
        "",
        "Upload `demo/photos/01-board-matches.png`. The reader pulls the work reference "
        "and the sanctioned amount off the board and confirms it matches `{}` - nobody "
        "types a reference number standing in a field.".format(lead["work_ref"]),
        "",
        "### 2. It notices when the board is for a different work",
        "",
        "Upload `demo/photos/02-board-different-work.png` on the same case file. The "
        "reference read from the board is shown against the one you are on, and they do "
        "not agree. The officer sees the disagreement before saving, not after.",
        "",
        "### 3. It catches a recycled photograph - the one a human cannot do at scale",
        "",
        "Upload `demo/photos/03-photo-first-submission.png` on `{}` and record any "
        "outcome. Then open `{}` and upload `demo/photos/04-photo-resubmitted.jpg`."
        .format(ordinary_a["work_ref"], ordinary_b["work_ref"]),
        "",
        "It is a different file - different name, different format, different size, "
        "different SHA-256. The perceptual hash matches anyway, and the screen says which "
        "work the picture was already submitted for, by whom, and when.",
        "",
        "Say this out loud: **it is a question, not a finding.** Two phases of one road "
        "legitimately look identical from the roadside. The system asks; a human answers.",
        "",
        "### 4. It admits when it cannot read",
        "",
        "Upload `demo/photos/05-board-weathered.png`. Faded and out of focus, the way "
        "boards actually look. Confidence drops and the fields come back partial or empty "
        "- shown as such, for the officer to correct, never quietly guessed.",
        "",
        "## The closing line",
        "",
        "Everything else in this product ends at *a human should check X*. This is the "
        "only screen that records what the human found - and those records are the only "
        "ground truth this system can ever obtain. The Data Transparency screen counts how "
        "far off that is instead of implying it has already happened.",
        "",
        "## The files",
        "",
        "| File | What it shows |",
        "| --- | --- |",
    ]
    lines += ["| `{}` | {} |".format(name, caption) for name, caption in written]
    lines.append("")
    (DEMO / "WALKTHROUGH.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
