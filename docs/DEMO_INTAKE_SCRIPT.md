# Demo script — the intake portal

**Screen:** `/submit` · **Time:** 3 minutes for the full arc, 90 seconds for the cut.

This is the screen that answers *"so what does your AI actually do?"* without a
single slide. An Implementing Agency submits evidence exactly as it would on
eSAKSHI, and eleven checks run in front of the judge.

> **Say this once, at the start:** "On the real portal, this upload is where the
> trail ends — the file is stored and a human may or may not ever open it.
> Watch what happens when it doesn't end there."

---

## Before the judges arrive

```bash
python -m uvicorn mplads.api.app:app --host 0.0.0.0 --port 8020
cd frontend && npm run demo
```

Open `/submit`. Three sample submissions are one click each — no typing, no file
picker, nothing to fumble.

**It works with OCR cold.** If the reader has not loaded, the `Read the file`
stage says so plainly and every later stage runs from the typed reference. Do not
apologise for it — it is the honest fallback and the screen says what it is.

---

## The three-act demo

### Act 1 — "Most submissions are fine, and we say so"

Click **Ordinary submission** → **Submit for assessment**.

Eleven rows fill in as each check finishes. Land on:

> "Nine of eleven checks came back clear. This is the result we want most of the
> time. A system that finds something wrong with every work is not a monitoring
> system, it is a random number generator."

**Point at `Check the photograph` → "Not seen before under any other work".**
Expand it. The explanation says re-use is only reported across *different* works
— the same work photographed twice is normal.

### Act 2 — "This work was already carrying evidence"

Click **A work already carrying evidence** → submit.

The submission itself is clean. The *work* is not:

| Stage | What lands |
|---|---|
| Compare against true peers | amount at the **100% mark** of its peer group |
| Check the lifecycle record | **2 lifecycle findings** |
| Completion risk | risk 0.441, early warning **HIGH** |
| Investigation lead | **HIGH — 4 pieces of evidence across 4 signal families** |

> "Four independent signal families agreeing is why this is a lead. Any one of
> them alone is noise."

Expand **Compare against true peers** and read the explanation aloud — it says
the clustering's silhouette is 0.050, that this is weak separation, and that it
is not accuracy. **Say it before a judge asks.** It is the single most credible
thing on the screen.

Click **Open the full case file** to land on the existing case file.

### Act 3 — the one that wins it

Click **The board and the form disagree** → submit.

Two rows go red:

```
■ Identify the work     The file reads MP3017167-W136962 but the form says MP3018356-W86316
▲ Check the photograph  This picture was already submitted for MP3017167-W136962
```

> "The agency typed one work reference. The photograph shows a different one —
> and that photograph has already been submitted for that other work.
>
> We do **not** conclude anything from this. MPLADS references run in sequence,
> so a single misread digit lands on a different real work — and two phases of
> one road genuinely look identical from the roadside. So the machine narrows
> it and a person decides. The system will not save this submission until
> someone confirms which work it belongs to."

That is the whole product in one sentence: **the machine narrows, the human
settles.**

---

## Questions you will be asked

**"Is this real or a canned animation?"**
Upload anything — a phone photo, a random PDF. Same code path. The rows fill in
as each check finishes, which is why the OCR row takes seconds and the portfolio
lookup is instant. There is no timer.

**"So it detects fraud?"**
No, and it is built so it cannot claim to. There are no fraud labels anywhere in
MPLADS data, so any model claiming to predict fraud would be fabricated. Every
lead ends in *"a human should check X"*, and a test greps the source tree to
stop the word re-entering the codebase.

**"What if the OCR is wrong?"**
That is the case the identity stage is designed around — not the unreadable
board, the *readable* one. A weathered board returns a reference at 99.6%
character confidence that is one digit off a different real work with the same
sanctioned amount. So every real reference one character away is listed, and
`needs_confirmation` is set. Show the `alternatives` list.

**"Does the submission change the score?"**
No — and that is deliberate. This reads the submission and compares it against
the portfolio; it does not retrain. Re-scoring one work against a baseline the
other 210,992 were not scored against would produce a leaderboard that means
nothing. The band shown is the band the pipeline already gave that work.

---

## If something goes wrong

| Symptom | What to say / do |
|---|---|
| Samples do not load | "Let me use my own file" — the picker works identically. |
| `Read the file` says no reader | Expected on a cold machine. Type the work reference. |
| A stage shows an error | The error reaches the screen rather than hanging it. Re-submit. |
| Assessment stops early | It stopped because it *should* — an unknown reference cannot be compared against anything. Show the near-misses. |

---

## The closing line

> "Other teams will show you a dashboard of what already happened. This is the
> moment a claim arrives — and eleven checks run before anyone has decided
> anything. It gives an investigator evidence and priorities, not accusations."
