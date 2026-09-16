# The live eSAKSHI feed

Keeps this product's view of MPLADS in step with the portal, continuously,
instead of depending on a scrape someone ran once.

---

## Start here: what "live" can and cannot mean

**The portal offers no push.** Verified against every public endpoint:

| We looked for | Present? |
|---|---|
| Webhook / callback registration | **No** |
| Change feed or event stream | **No** |
| `modified_since` / `updated_after` parameter | **No** |
| `ETag` or `If-None-Match` | **No** |
| `Last-Modified` header | **No** |
| Any cursor over changes | **No** |

So a real MPLADS integration is **polling with change detection**, and the
honest statement of freshness is *"bounded by the poll interval"*, never *"real
time"*. `/api/live/status` returns that sentence as `latency_contract` so a
screen cannot quietly promise more than the source can give.

If MoSPI later grants authenticated access with a proper delta API, only
`sync.py` changes — the store, the change feed and the API stay as they are.

---

## What makes continuous polling affordable

The portal will tell us **where** something moved for about 450 bytes:

```
POST /rest/PreLoginDashboardData/getTilesData  {"uname": "<state>,0,0,<house>,<tenure>"}
  -> counts AND rupees-to-the-paisa for that whole scope
```

So a cycle is:

```
144 aggregate calls (36 states x 2 houses x 2 tenures)     ~3 min
     │
     ├─ fingerprint each, compare to the stored watermark
     │
     └─ for ONLY the scopes that moved:
            fetch their 4 tile reports  ->  diff every work and payment
                                        ->  write the change feed
```

**Measured, not estimated.** First cycle over 4 scopes: 20 requests. Second
cycle, nothing changed upstream: **4 requests.** The saving grows with scope
size — a big state costs one small tile call instead of five heavy report calls.

Scopes that have not moved for `COLD_AFTER_UNCHANGED` checks are polled one
cycle in `COLD_POLL_EVERY` rather than every cycle. Retired Rajya Sabha tenures
do not change; spending the same attention on them as on an active Lok Sabha
state wastes requests an active state could have had. They are polled **less
often, never dropped** — `/api/live/scopes` shows `consecutive_unchanged` so a
scope that stopped being watched cannot hide.

### The limitation, stated rather than buried

A change that leaves **both** the count and the total rupees identical is
invisible to the fingerprint — a work cancelled and another added for exactly
the same amount in the same scope, or a description corrected. That is what the
**nightly full sweep** is for. Aggregate polling is the fast path, not the only
path.

---

## The change feed is the point

A dashboard that overwrites yesterday's number can say what is true now. It
cannot say:

> `MP3018937-W49384` — `work_stage`: *Pending for Sanction* → *Work Completed*
> `MP3018937-W49384` — `sanction_amount`: *111111* → *4855264*

Those are real rows this pipeline produced. Nothing is overwritten without first
being diffed, so `change_log` is an append-only record of what actually moved,
when we saw it move, and what it was before.

Two deliberate quietenings, because a feed full of noise stops being read:

- **`Sno` is not tracked.** It is a row number that shifts whenever anything is
  inserted above it; tracking it would make one new work report thousands of
  spurious changes.
- **`2999928.0` and `2999928` are the same number.** So are `None` and `""`.
  Both are pinned by tests.

A change is an **observation, not a finding**. `/api/live/changes` says so in
its own response. Nothing in the feed is an assessment of a work or an agency.

---

## Running it

```bash
# one cycle, all scopes
python -m ingestion.cli live-sync

# one cycle, ignoring fingerprints (the nightly safety net)
python -m ingestion.cli live-sync --full

# the service: incremental every 15 min, full sweep nightly
python -m ingestion.cli live-run

# freshness + change-feed summary
python -m ingestion.cli live-status
```

Tuning:

```bash
python -m ingestion.cli live-run --interval 300 --full-every 43200
MPLADS_REQUEST_DELAY=3 python -m ingestion.cli live-run     # gentler on the portal
```

`enumerate` must have been run once first — the scope list comes from the stored
reference data, not from a hardcoded table of states.

**One instance only.** A PID lock file refuses a second scheduler, because a
politeness budget is not enforceable if any number of copies can run.

---

## API

| Route | What it answers |
|---|---|
| `GET /api/live/status` | Is the feed alive, how fresh, and how far has it drifted from the scored snapshot |
| `GET /api/live/changes` | What actually moved, most recent first (`?entity=work&field=work_stage`) |
| `GET /api/live/scopes` | Per-scope freshness, including which have gone cold |
| `GET /api/live/work/{work_ref}` | One work as the portal has it now, its payments, and its full change history |

All four are **additive** and mounted in a `try/except` — if the ingestion
package or the live database is absent, the API still boots and these routes
report `available: false` with instructions. A deployment without the feed
degrades to the snapshot; it does not fail.

### The two ages, kept apart on purpose

| | Source | Moves when |
|---|---|---|
| **Scored snapshot** — leads, bands, audit plan, every screen | `data/artifacts/works_scored.parquet` | the pipeline is re-run |
| **Live mirror** — the portal as of the last sync | `data/portal/live/mplads_live.sqlite` | every sync cycle |

`/api/live/status` returns **both** ages (`scored_snapshot_age_seconds` and
`seconds_since_last_sync`) so a screen can show the gap. Averaging them, or
labelling a snapshot figure "live", would be a lie the UI tells on the
pipeline's behalf — and the risk band beside a freshly-synced amount is still
the band the model gave the *snapshot*.

---

## Layout

```
ingestion/live/
  store.py     SQLite warehouse + the diffing upserts + the change feed
  sync.py      one cycle: fingerprint -> refresh only what moved
  service.py   the loop: backoff, PID lock, heartbeat, graceful stop
src/mplads/api/live.py    the four routes
tests/test_live_pipeline.py   19 tests, no network
```

Storage: `data/portal/live/mplads_live.sqlite` (WAL). Tens of MB at national
scale — the live mirror is text and numbers, not files.

---

## What is not built

- **No file syncing.** The feed tracks works and payments. New photographs and
  PDFs are found by `ingestion.cli attachments`, which is a separate, far more
  expensive job (~84 GB nationally) and is deliberately not wired into the
  cycle.
- **No automatic re-scoring.** A sync updates the mirror; it does not re-run the
  models, so leads and bands do not move until `mplads.cli pipeline` runs. That
  is a deliberate seam — re-scoring 210,993 works on every cycle would be waste,
  and re-scoring *some* of them would produce a leaderboard where different rows
  were scored against different national baselines.
- **No alerting.** The change feed is queryable but nothing watches it for you.
- **The service has not been run for a sustained period.** It is proven over
  single cycles and the diff path is tested; a multi-day soak has not been done.
