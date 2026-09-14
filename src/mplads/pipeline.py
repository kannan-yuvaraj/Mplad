"""End-to-end intelligence pipeline: Learn -> Compare -> Predict -> Explain -> Prioritise.

Runs over data/interim/works.parquet (Phase 1 output) and writes every artifact the API
serves into data/artifacts/. Transparent and rule-based throughout: there is no supervised
fraud model, no fraud label, and no output is a probability of wrongdoing. Every surfaced
work carries the evidence that surfaced it and one recommended action for a human.

    python -m mplads.pipeline
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from mplads import config
from mplads.intelligence import compliance, duplicates, early_warning, temporal, transparency

LOGGER = logging.getLogger(__name__)
SNAPSHOT = pd.Timestamp(config.SNAPSHOT_DATE)

ACTIVITY_RE = re.compile(r"^WS/MP\d+/\d{4}-\d{4}/\d+-(?P<category>.+)$", re.S)


# --------------------------------------------------------------------------- Learn


def add_activity_category(works: pd.DataFrame) -> pd.DataFrame:
    """Parse the official permissible-works category out of ACTIVITY_NAME (93% coverage)."""
    cat = works["activity_name"].str.extract(ACTIVITY_RE)["category"].str.strip()
    works["activity_category"] = cat.fillna("Uncategorised")
    LOGGER.info(
        "activity_category: %s distinct, %.1f%% parsed",
        works["activity_category"].nunique(),
        100 * (works["activity_category"] != "Uncategorised").mean(),
    )
    return works


def add_archetypes(works: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attach the trained archetype cluster and its label to each work.

    Membership comes from our own MiniBatchKMeans model (see mplads.train); labels are the
    c-TF-IDF distinctive terms produced during training. Run `mplads train` first.
    """
    models = config.ARTIFACTS / "models"
    assign = pd.read_parquet(models / "archetype_assignment.parquet")
    catalog = pd.read_parquet(models / "archetype_catalog.parquet")

    works = works.merge(assign, on="work_description", how="left")
    works["archetype_id"] = works["archetype_id"].astype("Int64")
    labels = dict(zip(catalog["archetype_id"], catalog["label"]))
    works["archetype_label"] = works["archetype_id"].map(labels).fillna("unassigned")
    for src, dst, default in [
        ("interpretable", "archetype_interpretable", True),
        ("note", "archetype_note", ""),
        ("top_terms", "archetype_top_terms", ""),
    ]:
        if src in catalog.columns:
            works[dst] = works["archetype_id"].map(
                dict(zip(catalog["archetype_id"], catalog[src]))
            )
            works[dst] = works[dst].fillna(default)
        else:
            works[dst] = default

    catalog = catalog.rename(columns={"n_descriptions": "n_works"})
    LOGGER.info("archetypes: %s of %s works assigned (trained KMeans)",
                f"{int(works['archetype_id'].notna().sum()):,}", f"{len(works):,}")
    return works, catalog


# ------------------------------------------------------------------------- features


def add_features(works: pd.DataFrame, stages: pd.DataFrame) -> pd.DataFrame:
    """Lifecycle features with correct right-censoring at the snapshot date."""
    rec = works["recommendation_date"]
    comp = works["completion_date"]

    valid_dates = works["is_backdated"].eq(False) & works["is_future_dated"].eq(False)
    works["event_observed"] = (works["is_completed"] & valid_dates).astype(int)

    duration = np.where(
        works["is_completed"] & valid_dates,
        (comp - rec).dt.days,
        (SNAPSHOT - rec).dt.days,
    )
    works["duration_days"] = pd.to_numeric(duration, errors="coerce")
    # Orphans (no recommendation date) and anomalies cannot enter the survival fit.
    works.loc[works["duration_days"] < 0, "duration_days"] = np.nan
    works["log_amount"] = np.log1p(works["recommended_amount"].astype("float"))
    works["is_open"] = ~works["is_completed"]
    return works


# ------------------------------------------------------------------------- Compare


def _robust_z(values: pd.Series) -> pd.Series:
    """Median/MAD z-score with an IQR fallback for round-number-bunched groups."""
    med = values.median()
    mad = (values - med).abs().median()
    scale = 1.4826 * mad
    if scale <= 0:
        iqr = values.quantile(0.75) - values.quantile(0.25)
        scale = iqr / 1.349
    if scale <= 0:
        return pd.Series(0.0, index=values.index)
    return (values - med) / scale


def _loo_percentile(values: pd.Series) -> pd.Series:
    """Leave-one-out percentile rank: each work ranked against its peers, not itself."""
    n = len(values)
    if n <= 1:
        return pd.Series(np.nan, index=values.index)
    ranks = values.rank(method="average")
    return (ranks - 1) / (n - 1)


def add_peer_comparison(works: pd.DataFrame) -> pd.DataFrame:
    """Score each work against genuinely comparable works via hierarchical back-off.

    Levels: activity_category x state -> activity_category -> state -> global. The first
    level with at least MIN_PEERS works is used, and the level is recorded per work.
    """
    works = works.copy()
    works["peer_level"] = "global"
    works["peer_group_id"] = "GLOBAL"
    works["peer_group_size"] = len(works)

    levels = [
        ("cat_state", ["activity_category", "state_name"]),
        ("cat", ["activity_category"]),
        ("state", ["state_name"]),
    ]
    assigned = pd.Series(False, index=works.index)
    for level_name, keys in levels:
        sizes = works.groupby(keys)["work_ref"].transform("size")
        take = (sizes >= config.MIN_PEERS) & (~assigned)
        gid = works[keys].astype(str).agg("|".join, axis=1)
        works.loc[take, "peer_level"] = level_name
        works.loc[take, "peer_group_id"] = level_name + ":" + gid[take]
        works.loc[take, "peer_group_size"] = sizes[take]
        assigned |= take

    LOGGER.info("peer levels: %s", works["peer_level"].value_counts().to_dict())

    # Amount and open-duration scores computed within the assigned peer group.
    works["amount_pct"] = np.nan
    works["amount_z"] = np.nan
    works["open_duration_pct"] = np.nan
    for _, idx in works.groupby("peer_group_id").groups.items():
        grp = works.loc[idx]
        amt = grp["recommended_amount"].astype("float")
        works.loc[idx, "amount_pct"] = _loo_percentile(amt)
        works.loc[idx, "amount_z"] = _robust_z(amt)
        open_grp = grp[grp["is_open"]]
        if len(open_grp) > 1:
            works.loc[open_grp.index, "open_duration_pct"] = _loo_percentile(
                open_grp["duration_days"]
            )
    return works


# ------------------------------------------------------------------------- Predict


def add_completion_risk(works: pd.DataFrame) -> pd.DataFrame:
    """Attach the trained Cox model's completion-risk score. Not a score of wrongdoing.

    risk_score = 1 - S_i(horizon): the model's estimated chance this work has NOT completed
    within the horizon, given its amount, sanction status, state and archetype. Completed
    works carry 0. Run `mplads train` first.
    """
    works = works.copy()
    risk = pd.read_parquet(config.ARTIFACTS / "models" / "risk_scores.parquet")
    works = works.merge(risk, on="work_ref", how="left")

    works["risk_score"] = works["cox_risk"].fillna(0.0).clip(0, 1)
    works.loc[works["is_completed"], "risk_score"] = 0.0
    works["risk_level_used"] = np.where(works["cox_risk"].notna(), "cox_model", "unscored")
    LOGGER.info(
        "completion risk: Cox scores attached to %s works (open, scored)",
        f"{int((works['risk_score'] > 0).sum()):,}",
    )
    return works


# ------------------------------------------------------ behaviour (light change-point)


def add_change_points(works: pd.DataFrame) -> pd.DataFrame:
    """Flag implementing agencies whose recommendation behaviour shifted between years.

    Deliberately uses recommendation-time volume and median amount only — completion-based
    series are censoring-contaminated and would make every recent period look 'changed'.
    A change point is a lead ('behaviour changed'), never 'misconduct occurred'.
    """
    works = works.copy()
    works["change_point"] = 0.0
    df = works.dropna(subset=["recommendation_date", "implementing_agency"]).copy()
    df["year"] = df["recommendation_date"].dt.year

    agg = (
        df.groupby(["implementing_agency", "year"])
        .agg(n=("work_ref", "size"), med_amt=("recommended_amount", "median"))
        .reset_index()
    )
    agg = agg[agg["n"] >= 5]
    shifted: dict[str, float] = {}
    evidence: dict[str, str] = {}
    for agency, g in agg.groupby("implementing_agency"):
        if len(g) < 2:
            continue
        g = g.sort_values("year")
        amt = g["med_amt"].to_numpy()
        rel = np.abs(np.diff(amt)) / (amt[:-1] + 1e-9)
        if rel.size and rel.max() > 0.5:  # >50% median-amount shift year on year
            shifted[agency] = float(min(1.0, rel.max()))
            # Before/after evidence, as the deck promises: the reviewer sees the two
            # periods being compared, not just a magnitude.
            at = int(np.argmax(rel))
            before, after = g.iloc[at], g.iloc[at + 1]
            evidence[agency] = (
                f"{int(before['year'])}: {int(before['n'])} works at a median of "
                f"Rs {before['med_amt']:,.0f} -> {int(after['year'])}: {int(after['n'])} "
                f"works at a median of Rs {after['med_amt']:,.0f}"
            )

    mask = works["implementing_agency"].isin(shifted)
    works.loc[mask, "change_point"] = works.loc[mask, "implementing_agency"].map(shifted)
    works["change_point_evidence"] = works["implementing_agency"].map(evidence).fillna("")
    LOGGER.info("change points: %s agencies flagged", len(shifted))
    return works


# ------------------------------------------------------------ Explain & Prioritise


def add_anomaly(works: pd.DataFrame) -> pd.DataFrame:
    """Attach the trained IsolationForest multivariate outlier flag as one signal."""
    works = works.copy()
    iso = joblib.load(config.ARTIFACTS / "models" / "isolation_forest.joblib")
    snap = SNAPSHOT
    feats = pd.DataFrame({
        "log_amount": np.log1p(works["recommended_amount"].fillna(0)),
        "age_days": (snap - works["recommendation_date"]).dt.days.fillna(0).clip(lower=0),
    })
    feats = (feats - feats.mean()) / (feats.std() + 1e-9)
    works["anomaly_flag"] = (iso.predict(feats.values) == -1).astype(float)
    LOGGER.info("anomaly: %s works flagged by trained IsolationForest",
                f"{int(works['anomaly_flag'].sum()):,}")
    return works


def _sigmoid(x: pd.Series) -> pd.Series:
    return 1 / (1 + np.exp(-x))


def add_fusion(works: pd.DataFrame) -> pd.DataFrame:
    """Combine signals into a transparent priority, exposure and audit-ROI ranking."""
    works = works.copy()

    # Normalise each raw signal into [0,1]. Each has a plain-English meaning.
    gate = config.PEER_PERCENTILE_GATE
    works["sig_peer_amount"] = np.where(
        works["amount_pct"] >= gate, _sigmoid((works["amount_z"] - 2).clip(-6, 6)), 0.0
    )
    works["sig_peer_duration"] = np.where(
        works["open_duration_pct"] >= gate, works["open_duration_pct"].fillna(0.0), 0.0
    )
    works["sig_completion_risk"] = np.where(works["risk_score"] >= 0.60, works["risk_score"], 0.0)
    conf = (
        works["is_backdated"].astype(float)
        + works["completed_without_sanction"].astype(float)
        + works["is_future_dated"].astype(float)
        + works["is_orphan"].astype(float)
    ).clip(0, 1)
    works["sig_conformance"] = conf * 0.9
    works["sig_change_point"] = works["change_point"].fillna(0.0)
    works["sig_anomaly"] = works.get("anomaly_flag", pd.Series(0.0, index=works.index)).fillna(0.0)

    dup = works.get("duplicate_similarity", pd.Series(np.nan, index=works.index)).fillna(0.0)
    works["sig_duplicate"] = np.where(dup >= config.DUPLICATE_SIGNAL_THRESHOLD, dup, 0.0)

    signal_cols = {
        "peer_amount": "sig_peer_amount",
        "peer_duration": "sig_peer_duration",
        "completion_risk": "sig_completion_risk",
        "conformance": "sig_conformance",
        "change_point": "sig_change_point",
        "anomaly": "sig_anomaly",
        "duplicate": "sig_duplicate",
    }

    # Noisy-OR fusion with configured weights. Priority in [0,1).
    one_minus = pd.Series(1.0, index=works.index)
    for name, col in signal_cols.items():
        one_minus *= 1 - config.SIGNAL_WEIGHTS[name] * works[col].clip(0, 1)
    works["priority"] = 1 - one_minus

    # Confidence = number of independent signal FAMILIES firing (>0), not signals.
    fired = pd.DataFrame(index=works.index)
    for name, col in signal_cols.items():
        fired[config.SIGNAL_FAMILY[name]] = fired.get(
            config.SIGNAL_FAMILY[name], 0
        ) + (works[col] > 0).astype(int)
    families = (fired > 0).sum(axis=1)
    works["n_families"] = families

    works["band"] = pd.cut(
        families, bins=[-1, 0, 1, 2, 99], labels=["NONE", "LOW", "MEDIUM", "HIGH"]
    ).astype(str)

    # Exposure at risk (NOT loss, NOT spend): recommended amount weighted by completion risk.
    works["rs_exposure"] = works["recommended_amount"].astype("float").fillna(0.0) * works[
        "risk_score"
    ].clip(0, 1)
    # Audit-ROI: priority x exposure x corroboration. Each factor is traceable.
    works["audit_roi"] = works["priority"] * works["rs_exposure"] * (1 + works["n_families"])

    LOGGER.info("fusion bands: %s", works["band"].value_counts().to_dict())
    return works


# ----------------------------------------------------------------- case files & stats


def _evidence(row: pd.Series) -> list[dict]:
    ev = []
    if row["sig_peer_amount"] > 0:
        ev.append({
            "signal": "Peer amount", "family": "amount",
            "detail": f"Recommended amount at the {row['amount_pct']*100:.0f}th percentile of "
                      f"{int(row['peer_group_size'])} comparable works (robust z {row['amount_z']:.1f}).",
        })
    if row["sig_peer_duration"] > 0:
        ev.append({
            "signal": "Peer duration", "family": "duration",
            "detail": f"Open for longer than {row['open_duration_pct']*100:.0f}% of comparable "
                      f"works still in progress.",
        })
    if row["sig_completion_risk"] > 0:
        ev.append({
            "signal": "Completion risk", "family": "duration",
            "detail": f"Survival model: {row['risk_score']*100:.0f}% of comparable works have not "
                      f"completed within {config.RISK_HORIZON_DAYS} days.",
        })
    if row["sig_conformance"] > 0:
        flags = [n for n, f in [
            ("back-dated completion", row["is_backdated"]),
            ("completed without a sanction record", row["completed_without_sanction"]),
            ("completion date beyond the snapshot", row["is_future_dated"]),
            ("no recommendation record", row["is_orphan"]),
        ] if f]
        ev.append({"signal": "Lifecycle conformance", "family": "lifecycle",
                   "detail": "Lifecycle inconsistency: " + "; ".join(flags) + "."})
    if row["sig_change_point"] > 0:
        ev.append({"signal": "Behavioural change", "family": "behaviour",
                   "detail": f"Implementing agency's recommendation pattern shifted year-on-year "
                             f"(magnitude {row['change_point']:.0%}). "
                             + (f"Before/after — {row['change_point_evidence']}. "
                                if row.get('change_point_evidence') else "")
                             + "A change point is a lead, not a finding: a new officer or a "
                               "revised guideline produces one too."})
    if row.get("sig_anomaly", 0) > 0:
        ev.append({"signal": "Statistical outlier", "family": "multivariate",
                   "detail": "A trained anomaly detector (IsolationForest) flags this work's "
                             "amount-and-age profile as unusual against the national portfolio."})
    if row.get("sig_duplicate", 0) > 0:
        partner = row.get("duplicate_partner")
        ev.append({"signal": "Near-duplicate work", "family": "duplication",
                   "detail": f"A work in the same state and archetype is "
                             f"{row['duplicate_similarity'] * 100:.1f}% semantically similar "
                             f"({partner}). Repeated descriptions are common in this scheme, "
                             f"so a human should confirm these are genuinely separate works."})
    return ev


def build_case_file(row: pd.Series) -> dict:
    amt = None if pd.isna(row["recommended_amount"]) else float(row["recommended_amount"])
    return {
        "work_ref": row["work_ref"],
        "identity": {
            "work_ref": row["work_ref"],
            "description": (row["work_description"] or "")[:300] if isinstance(row["work_description"], str) else None,
            "state": row["state_name"],
            "constituency": row["constituency"],
            "implementing_agency": row["implementing_agency"],
            "mp_name": row["mp_name"],
            "recommended_amount": amt,
            "recommendation_date": None if pd.isna(row["recommendation_date"]) else row["recommendation_date"].date().isoformat(),
            "status": "Completed" if row["is_completed"] else ("Sanctioned" if row["is_sanctioned"] else "Recommended"),
        },
        "archetype": {"id": None if pd.isna(row["archetype_id"]) else int(row["archetype_id"]),
                      "label": row["archetype_label"]},
        "peer_context": {"level": row["peer_level"], "group_size": int(row["peer_group_size"]),
                         "amount_percentile": None if pd.isna(row["amount_pct"]) else round(float(row["amount_pct"]), 3)},
        "risk": {"completion_risk": round(float(row["risk_score"]), 3), "basis": row["risk_level_used"]},
        "exposure_rupees": round(float(row["rs_exposure"]), 0),
        "priority": round(float(row["priority"]), 4),
        "confidence_band": row["band"],
        "n_signal_families": int(row["n_families"]),
        "audit_roi": round(float(row["audit_roi"]), 0),
        "evidence": _evidence(row),
        "compliance_findings": compliance.findings_for(row),
        "early_warning": {
            "level": row.get("early_warning_level", "LOW"),
            "score": round(float(row.get("early_warning_score", 0.0)), 3),
            "reason": row.get("early_warning_reason", ""),
            "stall_ratio": None if pd.isna(row.get("stall_ratio")) else round(float(row["stall_ratio"]), 2),
            "peer_median_days": None if pd.isna(row.get("peer_median_days")) else int(row["peer_median_days"]),
        },
        "duplicate": None if not row.get("duplicate_partner") or pd.isna(row.get("duplicate_similarity")) else {
            "partner_work_ref": row["duplicate_partner"],
            "similarity": round(float(row["duplicate_similarity"]), 4),
            "classification": duplicates.classify(float(row["duplicate_similarity"])),
        },
        "lifecycle": {
            "stage": "Completed" if row["is_completed"] else ("Sanctioned" if row["is_sanctioned"] else "Recommended"),
            "days_open": None if pd.isna(row.get("duration_days")) else int(row["duration_days"]),
            "note": "Administrative lifecycle stage, not physical construction progress.",
        },
        "recommended_next_step": _recommend(row),
        "suggested_actions": _actions(row),
        "not_a_fraud_finding": True,
        "disclaimer": "This system identifies patterns warranting human investigation; "
                      "it does not determine fraud.",
    }


def _actions(row: pd.Series) -> list[str]:
    """Concrete things an officer can do, driven by which signals actually fired."""
    actions = []
    if row.get("sig_duplicate", 0) > 0:
        actions.append("Check duplicate possibility against the matched work")
    if row.get("compliance_flags", 0) > 0:
        actions.append("Review the lifecycle history and sanction record")
    if row.get("sig_peer_amount", 0) > 0:
        actions.append("Compare scope and estimate with peer works")
    if row.get("early_warning_level") in {"HIGH", "CRITICAL"}:
        actions.append("Request a progress update from the implementing agency")
    actions.append("Verify supporting documents and field evidence")
    return actions


def _recommend(row: pd.Series) -> str:
    if row["is_backdated"] or row["completed_without_sanction"] or row["is_future_dated"]:
        return "A human should check the lifecycle record with the District Authority — the stage dates are inconsistent."
    if row["sig_peer_amount"] > 0:
        return "A human should verify the scope and estimate for this work against its peers via the Implementing Agency."
    if row["sig_completion_risk"] > 0 or row["sig_peer_duration"] > 0:
        return "A human should request a progress update from the Implementing Agency on this long-running work."
    return "A human should review this work's evidence and decide whether a site verification is warranted."


def build_stats(works: pd.DataFrame, catalog: pd.DataFrame) -> dict:
    surfaced = works[works["band"].isin(["MEDIUM", "HIGH"])]
    national = {
        "total_works": int(len(works)),
        "completed": int(works["is_completed"].sum()),
        "open": int(works["is_open"].sum()),
        "states": int(works["state_name"].nunique()),
        "constituencies": int(works["constituency"].nunique()),
        "implementing_agencies": int(works["implementing_agency"].nunique()),
        "total_recommended_rupees": float(works["recommended_amount"].sum()),
        "total_exposure_rupees": float(works["rs_exposure"].sum()),
        "surfaced_leads": int(len(surfaced)),
        "bands": works["band"].value_counts().to_dict(),
    }
    by_state = (
        works.groupby("state_name")
        .agg(
            works=("work_ref", "size"),
            exposure=("rs_exposure", "sum"),
            leads=("band", lambda s: int(s.isin(["MEDIUM", "HIGH"]).sum())),
        )
        .reset_index()
        .sort_values("exposure", ascending=False)
    )
    archetypes = catalog.head(20).to_dict("records")
    return {"national": national, "by_state": by_state.to_dict("records"), "archetypes": archetypes}


# --------------------------------------------------------------------------- run


def run(artifacts_dir: Path | None = None) -> pd.DataFrame:
    out = config.ARTIFACTS if artifacts_dir is None else artifacts_dir
    out.mkdir(parents=True, exist_ok=True)

    works = pd.read_parquet(config.DATA_INTERIM / "works.parquet")
    stages = pd.read_parquet(config.DATA_INTERIM / "stages.parquet")
    LOGGER.info("loaded %s works", f"{len(works):,}")

    works = add_activity_category(works)
    works, catalog = add_archetypes(works)
    works = add_features(works, stages)
    works = add_peer_comparison(works)
    works = add_completion_risk(works)
    works = add_change_points(works)
    works = add_anomaly(works)

    # --- intelligence engines -------------------------------------------------
    pairs = duplicates.detect(works)
    if not pairs.empty:
        works = works.merge(
            duplicates.per_work_signal(pairs, works), on="work_ref", how="left"
        )
        # Row groups, because the API streams this file rather than loading it: one group
        # of 223,407 rows is read all-or-nothing and costs 250 MB to touch at all.
        pairs.to_parquet(out / "duplicate_pairs.parquet", index=False, row_group_size=20_000)

    works = compliance.evaluate(works)
    works = add_fusion(works)
    works = early_warning.score(works)

    # Worklist: everything with >=2 families (the corroboration rule), ranked by audit-ROI.
    worklist = works[works["band"].isin(["MEDIUM", "HIGH"])].sort_values(
        "audit_roi", ascending=False
    )
    case_files = [build_case_file(r) for _, r in worklist.iterrows()]

    # Row groups for the same reason as the pairs file: the API reads 22 of these 82
    # columns and should never have to touch the whole thing at once to do it.
    works.to_parquet(out / "works_scored.parquet", index=False, row_group_size=25_000)
    (out / "case_files.json").write_text(json.dumps(case_files, default=str), encoding="utf-8")
    catalog.to_parquet(out / "archetypes.parquet", index=False)

    stats = build_stats(works, catalog)
    stats["compliance"] = compliance.summary(works)
    stats["early_warning"] = early_warning.summary(works)
    stats["duplicates"] = _duplicate_summary(pairs)
    stats["archetype_intelligence"] = _archetype_intelligence(works)
    stats["health_index"] = _health_index(works, pairs)
    (out / "stats.json").write_text(json.dumps(stats, default=str), encoding="utf-8")

    (out / "temporal.json").write_text(
        json.dumps(temporal.build(works), default=str), encoding="utf-8"
    )
    (out / "transparency.json").write_text(
        json.dumps(transparency.build(works), default=str), encoding="utf-8"
    )
    LOGGER.info("wrote %s case files; artifacts in %s", f"{len(case_files):,}", out)
    return works


def _duplicate_summary(pairs: pd.DataFrame) -> dict:
    if pairs.empty:
        return {"total_pairs": 0, "by_classification": {}, "top": []}
    focus = duplicates.concerning(pairs)
    return {
        "total_pairs": int(len(pairs)),
        "concerning_pairs": int(len(focus)),
        "by_classification": pairs["classification"].value_counts().to_dict(),
        "same_agency_pairs": int(pairs["same_implementing_agency"].sum()),
        "identical_text_pairs": int(pairs["identical_text"].sum()),
        "top": focus.head(100).to_dict("records"),
        "method_note": "Semantic similarity over 384-d embeddings within state x archetype "
                       "blocks. Repeated descriptions are normal in this scheme, so only "
                       "pairs from the same implementing agency for a near-identical amount "
                       "are treated as concerning. An investigation lead, never proof.",
    }


def _archetype_intelligence(works: pd.DataFrame) -> list[dict]:
    """Per-archetype profile: size, geography, lifecycle, completion and risk."""
    frame = works.dropna(subset=["archetype_id"])
    rows = []
    for aid, group in frame.groupby("archetype_id"):
        completed = group[group["is_completed"]]
        rows.append({
            "archetype_id": int(aid),
            "label": group["archetype_label"].iloc[0],
            "n_works": int(len(group)),
            "states": int(group["state_name"].nunique()),
            "agencies": int(group["implementing_agency"].nunique()),
            "median_amount": float(group["recommended_amount"].median() or 0),
            "completion_rate": round(float(group["is_completed"].mean()), 3),
            "median_days_to_complete": None if completed.empty else float(completed["duration_days"].median()),
            "lead_rate": round(float(group["band"].isin(["MEDIUM", "HIGH"]).mean()), 3),
            "interpretable": bool(group["archetype_interpretable"].iloc[0]),
            "note": group["archetype_note"].iloc[0],
            "top_terms": group["archetype_top_terms"].iloc[0],
            "total_exposure": float(group["rs_exposure"].sum()),
            "top_state": group["state_name"].mode().iloc[0] if not group["state_name"].mode().empty else None,
        })
    return sorted(rows, key=lambda r: -r["n_works"])


def _health_index(works: pd.DataFrame, pairs: pd.DataFrame) -> dict:
    """MPLADS Operational Health Index — a derived analytical index,every component explained."""
    total = len(works)
    completion = float(works["is_completed"].mean())
    compliance_clean = 1 - float((works["compliance_flags"] > 0).mean())
    lead_free = 1 - float(works["band"].isin(["MEDIUM", "HIGH"]).mean())
    dup_rate = 0.0 if pairs.empty else min(1.0, len(pairs) / max(total, 1))
    dup_clean = 1 - dup_rate
    completeness = float(works["work_description"].notna().mean())

    components = [
        {"name": "Completion performance", "value": round(completion, 3), "weight": 0.30,
         "explanation": f"{completion * 100:.1f}% of works have a completion record."},
        {"name": "Record compliance", "value": round(compliance_clean, 3), "weight": 0.25,
         "explanation": f"{(1 - compliance_clean) * 100:.1f}% of works carry at least one "
                        f"lifecycle-consistency flag."},
        {"name": "Investigation-lead rate", "value": round(lead_free, 3), "weight": 0.20,
         "explanation": f"{(1 - lead_free) * 100:.1f}% of works were surfaced as leads."},
        {"name": "Duplicate-candidate rate", "value": round(dup_clean, 3), "weight": 0.15,
         "explanation": f"{dup_rate * 100:.2f}% of works have a near-duplicate candidate."},
        {"name": "Data completeness", "value": round(completeness, 3), "weight": 0.10,
         "explanation": f"{completeness * 100:.1f}% of works carry a usable description."},
    ]
    score = sum(c["value"] * c["weight"] for c in components)
    return {
        "score": round(100 * score, 1),
        "components": components,
        "note": "A derived analytical index, not an official government measure. Each "
                "component is measured and explained; the weights are set in code and "
                "visible here.",
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    run()
