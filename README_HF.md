---
title: MPLADS AI Forensic Monitoring
emoji: 🏛️
colorFrom: red
colorTo: green
sdk: docker
app_port: 8080
pinned: false
license: mit
short_description: Leads over 2.1 lakh MPLADS works, never fraud verdicts
---

# MPLADS AI Forensic Monitoring & Decision Support

**Team Morior Invictus · Smart India Hackathon 2026 · PS SIH26102 (MoSPI)**

The complete product — dashboard, API and assistant — in one container.

## What this is

An AI-assisted monitoring layer over India's MPLADS scheme. It learns what normal public work
looks like, compares each work against its **true peers**, estimates completion risk and the
rupee exposure attached to it, detects when an implementing agency's behaviour changes, and
ranks what deserves an officer's attention.

**It produces investigation leads with evidence. It never produces fraud verdicts.** There are
no fraud labels in this data, so any model claiming to predict fraud would be fabricated.

## Screens

**1 · Find** — Detection Centre · Works to Check · Possible Duplicates · Record Checks ·
Changes Over Time · Work Types · Case File
**2 · Act** — Visit Plan · Who Goes Where · Agency Profile · Case Tracking (Salesforce)
**3 · Check** — Step by Step · Was It Right? · About the Data · How It Works

Every screen is written in plain words a member of the public can follow.

Plus a data-grounded assistant on every screen that shows which lookup produced each figure.

## Verified numbers

| Measure | Value |
|---|---|
| Works | 210,993 (85,773 completed · 125,220 open) |
| Recommended / exposure | ₹11,565 Cr / ₹1,302 Cr |
| Investigation leads | 37,705 — 4,478 HIGH · 33,227 MEDIUM |
| Coverage | 36 states · 545 constituencies · 778 agencies |
| Archetypes | 50, silhouette **0.050** *(separation, never accuracy)* |
| Completion risk | Cox PH held-out **C-index 0.6759** |
| Synthetic validation | **69.25%** detection over 904 planted anomalies |
| Tests | **300 passing** |

## Honest limitations

- **No fraud labels exist**, so nothing here is validated against a real fraud outcome.
- **`ACTUAL_AMOUNT` is not expenditure** — it equals the recommended amount on 98.35% of
  completed works. No cost-overrun signal exists in this data.
- **Silhouette 0.050 is not accuracy.** It measures cluster separation; real-world text
  clusters overlap heavily.
- **No official rules are asserted.** No statutory threshold ships with this public data, so
  calling a statistical outlier a legal breach would be inventing law.

## Reading photographs and documents

On a case file, an officer can photograph the work board and attach a document (a sanction
order, work order or certificate, as a PDF or a photo).

- **Photographs** are read by **RapidOCR** on this Space. The full system reads them with
  **Surya OCR 2** on a GPU and uses RapidOCR as an independent second reader; Surya needs a
  GPU and a 1.5 GB model, so it is not part of this free CPU deployment — the screen says so.
- **Documents** are read by **Docling**, which keeps tables and finds every work number in
  the document, each checked against all 210,993 works. The first document after a restart
  takes a minute while Docling fetches its layout model.
- Nothing read by the computer is ever treated as settled: the officer confirms it.

## Notes on this deployment

Frontend and API are served by one process, so there is no CORS and no separate API host.
Artifacts are baked into the image — nothing to upload, and the container serves exactly what
was tested.

Free-tier storage is not persistent: the hash-chained audit log, field verification records
and uploaded photos and documents reset when the Space restarts. Everything else is read-only.

**This is a demonstration.** The sign-in page lists shared demo accounts on purpose, so
evaluators can try every role; anyone who opens the Space can sign in with them. Sign-in
tokens are signed with a secret held by the Space, not the development default.
