"""Near-duplicate / repeated-work detection over the 384-d description embeddings.

Semantic, not string matching: two works phrased completely differently but describing the
same thing will still be caught, and two works sharing boilerplate but describing different
locations will not be over-weighted.

Efficiency: a global O(N^2) comparison over 210k works is 4.4e10 pairs and is not attempted.
Instead candidates are generated inside *blocks* — works sharing a state and an archetype —
which is also the only comparison that is administratively meaningful: two identical
descriptions in different states are usually a common civic template, not a repeat claim.

Output is an investigation lead. Identical descriptions are routine in this scheme (one MP
recommending 40 street lights writes the same sentence 40 times), so a match is a question
for a human, never proof of a duplicate claim.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from mplads import config

LOGGER = logging.getLogger(__name__)

#: Cosine-similarity bands. Calibrated by inspecting real pairs at each level.
EXACT = 0.995
NEAR_EXACT = 0.97
HIGH = 0.92
POSSIBLE = 0.86

#: Blocks larger than this are sub-sampled for neighbour search to bound runtime.
MAX_BLOCK = 6_000
NEIGHBOURS = 6


def classify(score: float) -> str:
    if score >= EXACT:
        return "EXACT"
    if score >= NEAR_EXACT:
        return "NEAR_EXACT"
    if score >= HIGH:
        return "HIGH_SIMILARITY"
    if score >= POSSIBLE:
        return "POSSIBLE_REPEAT"
    return "NORMAL"


def _load_vectors() -> tuple[dict[str, int], np.ndarray]:
    """Description text -> row index, and the L2-normalised embedding matrix."""
    cache = np.load(
        config.REFERENCE / "models" / "archetype" / "desc_embeddings.npz", allow_pickle=True
    )
    texts = cache["texts"]
    vectors = cache["vectors"].astype("float32")
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / np.clip(norms, 1e-9, None)
    return {t: i for i, t in enumerate(texts)}, vectors


def detect(works: pd.DataFrame) -> pd.DataFrame:
    """Find near-duplicate work pairs within (state, archetype) blocks.

    Returns one row per candidate pair with a similarity score, the administrative
    relationship between the two works, and a plain-English explanation.
    """
    index, vectors = _load_vectors()
    frame = works[
        works["work_description"].notna() & works["archetype_id"].notna()
    ].copy()
    frame["_row"] = frame["work_description"].map(index)
    frame = frame[frame["_row"].notna()]
    frame["_row"] = frame["_row"].astype(int)
    LOGGER.info("duplicates: %s works carry an embedding", f"{len(frame):,}")

    rng = np.random.default_rng(config.RANDOM_SEED)
    pairs: list[dict] = []

    blocks = frame.groupby(["state_name", "archetype_id"], observed=True)
    LOGGER.info("duplicates: scanning %s (state x archetype) blocks", f"{blocks.ngroups:,}")

    for (state, archetype), block in blocks:
        if len(block) < 2:
            continue
        if len(block) > MAX_BLOCK:
            block = block.iloc[rng.choice(len(block), MAX_BLOCK, replace=False)]

        matrix = vectors[block["_row"].to_numpy()]
        k = min(NEIGHBOURS, len(block))
        # Imported here, not at the top: this module is also imported by the API, which
        # only ever reads the pairs the pipeline already found. Loading scikit-learn to do
        # that costs 70 MB of a server's memory to fit nothing.
        from sklearn.neighbors import NearestNeighbors

        nn = NearestNeighbors(n_neighbors=k, metric="cosine").fit(matrix)
        distances, indices = nn.kneighbors(matrix)

        refs = block["work_ref"].to_numpy()
        agencies = block["implementing_agency"].to_numpy()
        constituencies = block["constituency"].to_numpy()
        amounts = block["recommended_amount"].to_numpy()
        descriptions = block["work_description"].to_numpy()
        mps = block["mp_name"].to_numpy()

        for i in range(len(block)):
            for slot in range(1, k):  # slot 0 is the work itself
                j = indices[i, slot]
                similarity = 1.0 - float(distances[i, slot])
                if similarity < POSSIBLE:
                    continue
                if refs[i] >= refs[j]:  # emit each unordered pair once
                    continue
                same_agency = agencies[i] == agencies[j]
                same_constituency = constituencies[i] == constituencies[j]
                pairs.append(
                    {
                        "work_ref_a": refs[i],
                        "work_ref_b": refs[j],
                        "similarity": round(similarity, 4),
                        "classification": classify(similarity),
                        "state_name": state,
                        "archetype_id": int(archetype),
                        "same_implementing_agency": bool(same_agency),
                        "same_constituency": bool(same_constituency),
                        "identical_text": bool(descriptions[i] == descriptions[j]),
                        "amount_a": float(amounts[i]) if pd.notna(amounts[i]) else None,
                        "amount_b": float(amounts[j]) if pd.notna(amounts[j]) else None,
                        "mp_a": mps[i],
                        "mp_b": mps[j],
                        "description_a": str(descriptions[i])[:200],
                        "description_b": str(descriptions[j])[:200],
                    }
                )

    result = pd.DataFrame(pairs)
    if result.empty:
        LOGGER.warning("duplicates: no candidate pairs found")
        return result

    result["explanation"] = result.apply(_explain, axis=1)
    # Concentration matters more than any single pair: rank by how tightly the match sits.
    result = result.sort_values(
        ["similarity", "same_implementing_agency", "same_constituency"], ascending=False
    ).reset_index(drop=True)

    LOGGER.info(
        "duplicates: %s candidate pairs (%s)",
        f"{len(result):,}",
        result["classification"].value_counts().to_dict(),
    )
    return result


def _explain(row: pd.Series) -> str:
    bits = [f"Descriptions are {row['similarity'] * 100:.1f}% semantically similar"]
    if row["identical_text"]:
        bits.append("the text is character-for-character identical")
    bits.append(f"both in {row['state_name']}")
    if row["same_constituency"]:
        bits.append("the same constituency")
    if row["same_implementing_agency"]:
        bits.append("the same implementing agency")
    if row["mp_a"] == row["mp_b"]:
        bits.append("recommended by the same MP")
    return (
        ", ".join(bits)
        + ". Repeated descriptions are common and legitimate in this scheme; a human should "
        "confirm whether these are genuinely separate works."
    )


def concerning(pairs: pd.DataFrame) -> pd.DataFrame:
    """The subset of pairs whose *administrative* pattern is worth a human's time.

    Semantic similarity alone is not concerning: one MP recommending forty street lights
    writes the same sentence forty times, and that is exactly how the scheme works. What is
    worth asking about is a near-identical description **from the same implementing agency
    for a near-identical amount** — the shape a repeated claim would take.
    """
    if pairs.empty:
        return pairs
    amounts_close = (
        (pairs["amount_a"] - pairs["amount_b"]).abs()
        / pairs[["amount_a", "amount_b"]].max(axis=1).clip(lower=1)
    ) <= 0.02
    return pairs[
        (pairs["similarity"] >= NEAR_EXACT)
        & pairs["same_implementing_agency"]
        & amounts_close.fillna(False)
    ].copy()


def per_work_signal(pairs: pd.DataFrame, works: pd.DataFrame) -> pd.DataFrame:
    """Collapse the *concerning* pairs to a per-work duplicate signal for fusion."""
    columns = ["work_ref", "duplicate_similarity", "duplicate_partner"]
    focus = concerning(pairs)
    if focus.empty:
        return pd.DataFrame({c: [] for c in columns})

    stacked = pd.concat(
        [
            focus[["work_ref_a", "work_ref_b", "similarity"]].rename(
                columns={"work_ref_a": "work_ref", "work_ref_b": "partner"}
            ),
            focus[["work_ref_b", "work_ref_a", "similarity"]].rename(
                columns={"work_ref_b": "work_ref", "work_ref_a": "partner"}
            ),
        ]
    )
    best = stacked.sort_values("similarity", ascending=False).drop_duplicates("work_ref")
    LOGGER.info(
        "duplicates: %s pairs are administratively concerning (same agency, near-identical "
        "amount) covering %s works",
        f"{len(focus):,}",
        f"{len(best):,}",
    )
    return best.rename(
        columns={"similarity": "duplicate_similarity", "partner": "duplicate_partner"}
    )[columns]
