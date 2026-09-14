# Putting the site online, free, on Render

The whole product — the React screens, the API, the 210,993 works and everything computed
from them — runs as **one container at one address**. This is how to get that address.

It costs nothing and needs no card. It takes about twenty minutes, most of which is
waiting for a build.

---

## Before you start

You need:

* a **GitHub account** — you have one: the project is at `kannan-yuvaraj/Mplad`;
* a **Render account** — sign up at [render.com](https://render.com) with "Sign in with
  GitHub". That is the only account to create.

Nothing has to be installed on your computer.

---

## The five steps

1. Go to **[dashboard.render.com/blueprints](https://dashboard.render.com/blueprints)** and
   click **New Blueprint Instance**.
2. Choose the repository **`kannan-yuvaraj/Mplad`**. If Render does not list it, click
   *Configure account* and give Render permission to see it.
3. Render finds [`render.yaml`](../render.yaml) in the repository and shows you what it is
   about to create: one web service called **thadam**, on the **free** plan. Everything it
   needs — which port, which settings, how it checks the service is alive — is already in
   that file, so **there is nothing to fill in**.
4. Give the blueprint a name (anything) and click **Apply**.
5. Wait. The first build takes **10–20 minutes**, because it installs Python, builds the
   React app and copies the artifacts. You can watch the log; you do not have to.

When it finishes, the service page shows an address like
`https://thadam.onrender.com`. **That is the site.** Open it, and sign in with
`auditor` / `mplads2026` if you want to record a site verification.

Every time you push to `main`, Render rebuilds and redeploys on its own.

---

## What "free" actually means here

Say these out loud before a judge rather than being caught by them.

**It sleeps.** After 15 minutes with no visitor, Render stops the container. The next
visitor waits **about a minute** while it starts again. The link never breaks — it is just
slow to answer the first time. If you are presenting, **open the site five minutes
beforehand** and it will be awake and instant.

**It forgets what people type into it.** The free plan has no disk. The artifacts are baked
into the image and are read-only, so the site always comes back exactly as deployed — but a
site verification recorded *through* the live site, and the audit-chain entry for it, are
gone at the next restart. That is fine for a demonstration and not fine for a pilot; a
pilot needs a paid disk, which is a setting, not a code change.

**It has 512 MB of memory.** Fully warmed the service is about **430 MB**, so it fits — but
it fits because it was made to. Two consequences are visible on the site and are stated on
the screens themselves:

* **Photographs are read by RapidOCR, not Surya.** Surya is the better reader (93% against
  91% on our benchmark, and it survives motion blur where RapidOCR does not) but it needs a
  GPU and a 1.5 GB model. The Camera panel names the reader it used.
* **Documents cannot be read at all.** Docling needs PyTorch, which is 300 MB the moment a
  PDF arrives — the container would be killed mid-upload. The Documents panel says it is
  unavailable instead, which is the honest failure: refusing a PDF beats accepting one and
  dying.

Both are settings in [`render.yaml`](../render.yaml), not missing code. On a host with 2 GB
they switch back on with no change to the program.

---

## If something goes wrong

**The build fails on the PyTorch step.** `MPLADS_DOCUMENT_OCR=0` is meant to keep PyTorch
out of the image entirely — Render supplies a service's environment variables to the build
as arguments, which the `ARG` of the same name in the [`Dockerfile`](../Dockerfile) picks
up. If your build log shows it downloading torch anyway, that mechanism did not fire: add
`MPLADS_DOCUMENT_OCR=0` under *Settings → Build → Docker Build Arguments* and deploy again.
The site is correct either way; this only decides how big the image is.

**The deploy is marked "live" but the page is blank.** The React app is built inside the
image, so this normally means the frontend build stage failed. Search the build log for
`npm run build`.

**"Service Unavailable" a minute after it was fine.** That is the container sleeping.
Refresh and wait.

**It was killed with "out of memory".** Look at what was being done. The two known ways to
exceed 512 MB are uploading a document (which should be refused — check
`/api/ocr/status` reports `documents.available: false`) and a runaway crawl of the budget
slider. Report the second one; it is a bug, not a limit.

---

## Where else this could live

| Host | Memory | Always on | Card needed | Verdict |
|---|---|---|---|---|
| **Render free** | 512 MB | no — sleeps after 15 min | no | **what this file describes** |
| Hugging Face Space | 16 GB | yes (sleeps after 48 h) | no | **blocked**: the account shows `limit=0` for free CPU Spaces, which is an account restriction, not something the code can fix |
| Google Colab | 12 GB | no — dies with the tab | no | good for a live demonstration: [`notebooks/MPLADS_run_in_colab.ipynb`](../notebooks/MPLADS_run_in_colab.ipynb) |
| Render paid | 2 GB | yes | yes, $7/mo | Surya and document reading both switch back on |

The Hugging Face route is worth retrying if that quota ever clears: 16 GB would run the
whole thing — Surya included — with nothing turned off.
