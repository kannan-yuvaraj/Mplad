"""Assess one submitted document or photograph, stage by stage.

This is the intake path an Implementing Agency would use on eSAKSHI: a work is
marked complete and its evidence uploaded. Everything the rest of this system
does in batch across 210,993 works, this does for one submission, in order, and
narrates each step as it finishes.

**It is a reader, not a re-scorer.** The stages below read the submitted file and
compare it against the portfolio and the scored snapshot. They do **not** refit a
model, and the band reported at the end is the band the pipeline already gave
that work — plus whatever the submission itself raises. Anything else would be a
leaderboard where one row was scored against a different baseline from the rest.

Three rules carried over from the field-verification loop, because a demo that
quietly drops them is demonstrating something we did not build:

- **A match is never settled by the machine.** `ocr.match_to_work` returns every
  real reference one character away and sets `needs_confirmation`; this module
  propagates that and refuses to present an unconfirmed identity as settled.
- **A re-used photograph is a question, not a finding.**
- **No stage returns a verdict about a person or an agency.** Stages report what
  was observed and what a human should check.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Callable, Iterator

from mplads import field, ocr, photohash

LOGGER = logging.getLogger(__name__)

#: Stage outcomes. Deliberately not pass/fail — most of what this system finds is
#: "worth a look", and a red/green light would overstate every one of them.
OK = "ok"                # nothing to raise
ATTENTION = "attention"  # a human should look at this
INFO = "info"            # context, no judgement
BLOCKED = "blocked"      # cannot proceed without a human decision


@dataclass
class Stage:
    """One step of the assessment, as the UI receives it."""

    order: int
    stage: str
    title: str
    status: str
    headline: str
    explain: str
    detail: dict[str, Any] = dataclass_field(default_factory=dict)
    elapsed_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


#: The stages, in the order they run, so a UI can draw the whole pipeline before
#: any of it has finished rather than growing a list and jumping about.
STAGE_PLAN: list[tuple[str, str]] = [
    ("received", "Submission received"),
    ("read", "Read the file"),
    ("identify", "Identify the work"),
    ("photo_forensics", "Check the photograph"),
    ("cross_check", "Cross-check the amount"),
    ("record", "Pull the portfolio record"),
    ("peer", "Compare against true peers"),
    ("lifecycle", "Check the lifecycle record"),
    ("risk", "Completion risk"),
    ("duplicate", "Look for a near-duplicate"),
    ("lead", "Investigation lead"),
]


class Assessment:
    """Runs the stages for one submission.

    `case_lookup` is injected rather than imported so this module does not depend
    on the API layer — the API passes its own cached store, and tests pass a dict.
    """

    def __init__(
        self,
        *,
        known_refs: set[str],
        amounts: dict[str, float],
        case_lookup: Callable[[str], dict | None],
        actor: str = "anonymous",
    ) -> None:
        self.known_refs = known_refs
        self.amounts = amounts
        self.case_lookup = case_lookup
        self.actor = actor

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _rupees(value: Any) -> str:
        try:
            return f"Rs {float(value):,.0f}"
        except (TypeError, ValueError):
            return "not stated"

    # -- the run -----------------------------------------------------------

    def run(
        self,
        *,
        data: bytes,
        filename: str,
        kind: str,
        declared_work_ref: str = "",
        declared_amount: float | None = None,
        reader: str | None = None,
    ) -> Iterator[Stage]:
        """Yield each stage as it completes.

        `kind` is 'photo' or 'document'. `declared_work_ref` is what the agency
        typed on the form — used as a fallback when no reader is available, and
        as a second opinion when one is. `reader` names a preferred OCR engine;
        reading dominates the wall clock (measured: ~55 s cold, ~7 s warm for
        Surya against 32 ms for all ten other stages combined), so which reader
        runs is the only choice on this page that changes how it feels.
        """
        order = 0
        started = time.monotonic()

        def stage(name: str, title: str, status: str, headline: str,
                  explain: str, detail: dict[str, Any] | None = None) -> Stage:
            nonlocal order
            order += 1
            return Stage(order=order, stage=name, title=title, status=status,
                         headline=headline, explain=explain, detail=detail or {},
                         elapsed_ms=int((time.monotonic() - started) * 1000))

        # -- 1. received ---------------------------------------------------
        digest = photohash_safe_sha(data)
        stored_name = None
        try:
            stored_name = (field.save_photo(data, filename) if kind == "photo"
                           else field.save_document(data, filename))
        except ValueError as exc:
            yield stage("received", "Submission received", BLOCKED,
                        f"Rejected: {exc}",
                        "Uploads are content-addressed and extension-checked before "
                        "anything reads them.",
                        {"filename": filename, "bytes": len(data)})
            return

        yield stage("received", "Submission received", OK,
                    f"{filename} — {len(data):,} bytes",
                    "Stored under its content hash, so the same file submitted twice is "
                    "the same stored object and the original is never modified.",
                    {"filename": filename, "bytes": len(data), "sha256": digest,
                     "stored_as": stored_name, "kind": kind})

        # -- 2. read -------------------------------------------------------
        extracted: dict[str, Any] = {}
        reader_available = ocr.available() if kind == "photo" else ocr.documents_available()

        if reader_available:
            try:
                path = (field.PHOTOS if kind == "photo" else field.DOCUMENTS) / stored_name
                # `read` cross-checks with the *other* engine, so asking for the
                # fast reader while leaving that on would still invoke Surya and
                # save nothing. Choosing speed means choosing one reader — and
                # the stage below says the second reader was skipped, so nothing
                # can claim two-reader agreement that did not happen.
                single_reader = reader == "rapidocr"
                extracted = (ocr.read(path, prefer=reader, cross_check=not single_reader)
                             if kind == "photo" else ocr.read_document(path))
                lines = extracted.get("lines") or []
                fields_found = extracted.get("fields") or {}
                seconds = extracted.get("seconds")
                yield stage("read", "Read the file", OK if fields_found else INFO,
                            f"{len(lines)} lines read"
                            + (f", {len(fields_found)} fields recognised" if fields_found else "")
                            + (f" — {extracted.get('engine_label') or extracted.get('engine')}"
                               f" in {seconds}s" if seconds is not None else ""),
                            "Optical character recognition. Its confidence is confidence in "
                            "the pixels — it says how clearly the characters were seen, not "
                            "whether what they say is true. This is the only slow step: "
                            "every other check on this page finishes in milliseconds."
                            + (" Only one reader ran, so there is no second reading to "
                               "disagree with this one."
                               if single_reader else
                               " A second reader read the same photograph independently; "
                               "where the two disagree, the identity stage forces a human "
                               "to settle it."),
                            {"engine": extracted.get("engine"),
                             "engine_label": extracted.get("engine_label"),
                             "seconds": seconds,
                             "second_reader_ran": not single_reader,
                             "cross_check": extracted.get("cross_check"),
                             "fell_back_from": extracted.get("fell_back_from"),
                             "fields": fields_found,
                             "line_count": len(lines),
                             "text_preview": (extracted.get("text") or "")[:600]})
            except Exception as exc:  # a reader failing must not end the assessment
                LOGGER.warning("reader failed on %s: %s", filename, exc)
                yield stage("read", "Read the file", INFO,
                            "Reader unavailable — continuing from the typed reference",
                            "The assessment does not depend on OCR. Where no reader is "
                            "available the officer's typed reference is used, and the "
                            "identity stage says so rather than implying the machine read it.",
                            {"error": f"{type(exc).__name__}: {exc}"})
        else:
            yield stage("read", "Read the file", INFO,
                        "No reader installed on this machine — continuing from the typed reference",
                        "OCR is optional. Every later stage works from the work reference, "
                        "however it was obtained.",
                        {"ocr_status": ocr.status()})

        # -- 3. identify ---------------------------------------------------
        match = {}
        if extracted:
            match = ocr.match_to_work(extracted, self.known_refs, self.amounts)

        work_ref = match.get("work_ref") or ""
        read_ref = work_ref
        needs_confirmation = bool(match.get("needs_confirmation", True))
        alternatives = match.get("alternatives") or []

        if declared_work_ref:
            if work_ref and declared_work_ref != work_ref:
                # The two disagreeing is the most useful thing this stage can report.
                yield stage("identify", "Identify the work", BLOCKED,
                            f"The file reads {work_ref} but the form says {declared_work_ref}",
                            "MPLADS references run in sequence, so a single misread digit "
                            "lands on a different real work. The machine narrows; a human "
                            "settles it. Nothing is saved until someone confirms which.",
                            {"read_from_file": read_ref, "typed_on_form": declared_work_ref,
                             "alternatives": alternatives, "needs_confirmation": True})
                work_ref = declared_work_ref
                needs_confirmation = True
            elif not work_ref:
                work_ref = declared_work_ref
                needs_confirmation = True
                yield stage("identify", "Identify the work", ATTENTION,
                            f"Using the typed reference {work_ref} — not read from the file",
                            "The reference was not recovered from the file, so it has not "
                            "been corroborated. Treat the identity as asserted, not verified.",
                            {"typed_on_form": declared_work_ref, "needs_confirmation": True})
            else:
                needs_confirmation = bool(match.get("needs_confirmation"))
                yield stage("identify", "Identify the work", OK,
                            f"{work_ref} — the file and the form agree",
                            "Two independent sources for the identity. This is the strongest "
                            "identification this system will claim, and it still shows the "
                            "near-misses below.",
                            {"read_from_file": read_ref, "typed_on_form": declared_work_ref,
                             "alternatives": alternatives,
                             "needs_confirmation": needs_confirmation})
        elif work_ref:
            yield stage("identify", "Identify the work", ATTENTION if needs_confirmation else OK,
                        f"Read {work_ref} from the file",
                        "Every real reference one character away is listed. A weathered "
                        "board reads one digit wrong at 99.6% character confidence and lands "
                        "on a different real work — so the officer confirms.",
                        {"read_from_file": read_ref, "alternatives": alternatives,
                         "confidence": match.get("confidence"),
                         "needs_confirmation": needs_confirmation})
        else:
            yield stage("identify", "Identify the work", BLOCKED,
                        "No work reference found",
                        "Without a reference nothing can be compared. The officer can type "
                        "one and resubmit.",
                        {"reason": match.get("reason", "no reference in the file")})
            return

        known = work_ref in self.known_refs
        if not known:
            yield stage("record", "Pull the portfolio record", BLOCKED,
                        f"{work_ref} is not in this portfolio",
                        "The reference does not match any of the 210,993 works. Either it "
                        "was misread, or it belongs to a period this snapshot does not "
                        "cover. Nearby real references are listed above.",
                        {"work_ref": work_ref, "alternatives": alternatives})
            return

        # -- 4. photo forensics ---------------------------------------------
        if kind == "photo":
            reuse = field.check_photo(data, stored_name, work_ref, actor=self.actor)
            # `check_photo` returns its hits under "reuse", and reports them only
            # across *different* works — photographing one work twice is normal,
            # and flagging it would bury the case that matters.
            matches = reuse.get("reuse") or []
            if matches:
                yield stage("photo_forensics", "Check the photograph", ATTENTION,
                            f"This picture was already submitted for "
                            f"{matches[0]['work_ref']}"
                            + (f" and {len(matches) - 1} other work(s)"
                               if len(matches) > 1 else ""),
                            "Perceptual hashing catches a resized, re-compressed or "
                            "brightened copy that a checksum misses. But two phases of one "
                            "road legitimately look identical from the roadside — so this "
                            "is reported as a question, never concluded as a finding.",
                            {"matches": matches,
                             "phash": reuse.get("phash"), "dhash": reuse.get("dhash")})
            else:
                yield stage("photo_forensics", "Check the photograph", OK,
                            "Not seen before under any other work",
                            "Fingerprinted against every photograph previously submitted. "
                            "Re-use is only reported across *different* works — the same "
                            "work photographed twice is normal, and flagging that would "
                            "bury the case that matters. A new picture is the expected "
                            "result and is not evidence of anything on its own.",
                            {"phash": reuse.get("phash"), "dhash": reuse.get("dhash"),
                             "fingerprinted": reuse.get("fingerprinted")})
        else:
            refs_in_doc = extracted.get("work_refs") or []
            mentions = work_ref in refs_in_doc
            yield stage("photo_forensics", "Check the document", OK if mentions else INFO,
                        (f"The document names {work_ref}" if mentions
                         else f"{len(refs_in_doc)} reference(s) found in the document"),
                        "A sanction order often covers several works, so every reference in "
                        "it is checked against the portfolio rather than only the one this "
                        "submission is about.",
                        {"refs_in_document": refs_in_doc, "mentions_this_work": mentions})

        # -- 5. cross-check the amount ---------------------------------------
        record_amount = self.amounts.get(work_ref)
        read_amount = None
        if extracted:
            amount_field = (extracted.get("fields") or {}).get("amount")
            read_amount = amount_field.get("value") if amount_field else None
        stated = declared_amount if declared_amount is not None else read_amount

        if stated is None or record_amount is None:
            yield stage("cross_check", "Cross-check the amount", INFO,
                        "No amount to compare",
                        "Where the file or the form carries an amount it is checked against "
                        "the recorded figure. Neither was available here.",
                        {"record_amount": record_amount, "submitted_amount": stated})
        else:
            delta = float(stated) - float(record_amount)
            ratio = (float(stated) / float(record_amount)) if record_amount else None
            close = abs(delta) < max(1.0, 0.01 * float(record_amount))
            yield stage("cross_check", "Cross-check the amount",
                        OK if close else ATTENTION,
                        (f"Submitted {self._rupees(stated)} against "
                         f"{self._rupees(record_amount)} on record"
                         + ("" if close else f" — a difference of {self._rupees(abs(delta))}")),
                        "An amount that disagrees with the record is one of the few checks "
                        "here that a person could do alone — and the one they cannot do "
                        "across two lakh works.",
                        {"submitted_amount": stated, "record_amount": record_amount,
                         "difference": round(delta, 2),
                         "ratio": None if ratio is None else round(ratio, 4),
                         "source": "form" if declared_amount is not None else "read from file"})

        # -- 6..11: the portfolio's own assessment ---------------------------
        case = self.case_lookup(work_ref)
        if not case:
            yield stage("record", "Pull the portfolio record", BLOCKED,
                        f"No record could be loaded for {work_ref}",
                        "The reference is known but its record could not be read.",
                        {"work_ref": work_ref})
            return

        identity = case.get("identity") or {}
        surfaced = case.get("surfaced", True)

        yield stage("record", "Pull the portfolio record", OK,
                    f"{identity.get('implementing_agency') or 'agency not stated'}"
                    f" — {identity.get('state') or 'state not stated'}",
                    "The work as the portfolio holds it. Everything below compares this "
                    "submission against that record and against comparable works.",
                    {"identity": identity, "surfaced": surfaced})

        peer = case.get("peer_context") or {}
        archetype = case.get("archetype") or {}
        pct = peer.get("amount_percentile")
        yield stage("peer", "Compare against true peers",
                    ATTENTION if (pct is not None and (pct >= 0.99 or pct <= 0.01)) else OK,
                    (f"Amount sits at the {pct:.0%} mark of its peer group"
                     if pct is not None else "No peer percentile available"),
                    "Compared against works of the same type in comparable places, not "
                    "against the national average. The grouping comes from clustering whose "
                    "silhouette is 0.050 — that is a weak separation and it is not accuracy; "
                    "peers are a lens, not a verdict.",
                    {"peer_level": peer.get("level"), "group_size": peer.get("group_size"),
                     "amount_percentile": pct, "archetype": archetype})

        findings = case.get("compliance_findings") or []
        yield stage("lifecycle", "Check the lifecycle record",
                    ATTENTION if findings else OK,
                    (f"{len(findings)} lifecycle finding(s)" if findings
                     else "No lifecycle inconsistency recorded"),
                    "Conformance checks on the stage record: completed without a sanction "
                    "row, back-dated stages, dates outside the window. These are record "
                    "problems, not construction problems.",
                    {"findings": findings,
                     "lifecycle": case.get("lifecycle")})

        risk = case.get("risk") or {}
        warning = case.get("early_warning") or {}
        level = warning.get("level", "LOW")
        yield stage("risk", "Completion risk",
                    ATTENTION if level in {"HIGH", "CRITICAL"} else OK,
                    f"Risk {risk.get('completion_risk')} · early warning {level}",
                    "Survival analysis over every work including the ones that never "
                    "finished — which is why it differs from 'how late were the finished "
                    "ones'. Held-out C-index 0.6759: better than chance, far from certain.",
                    {"risk": risk, "early_warning": warning,
                     "exposure_rupees": case.get("exposure_rupees")})

        dup = case.get("duplicate")
        yield stage("duplicate", "Look for a near-duplicate",
                    ATTENTION if dup else OK,
                    (f"Resembles {dup['partner_work_ref']} "
                     f"({dup['similarity']:.0%} similar, {dup['classification']})"
                     if dup else "No near-duplicate partner found"),
                    "Description similarity across the portfolio. Two phases of one road "
                    "are legitimately similar, so a partner is a question for a human, not "
                    "a conclusion.",
                    {"duplicate": dup})

        # -- the lead --------------------------------------------------------
        band = case.get("confidence_band") or ("NONE" if not surfaced else "LOW")
        evidence = case.get("evidence") or []
        submission_notes = []
        if needs_confirmation:
            submission_notes.append(
                "The work identity in this submission has not been confirmed by a human.")

        yield stage("lead", "Investigation lead",
                    ATTENTION if band in {"HIGH", "MEDIUM"} else INFO,
                    (f"{band} — {len(evidence)} piece(s) of evidence across "
                     f"{case.get('n_signal_families', 0)} signal families"
                     if surfaced else "Clear record — this work was never surfaced"),
                    "An investigation lead with evidence, not a verdict. There are no fraud "
                    "labels in MPLADS data, so nothing here is a fraud score and no model "
                    "was trained to produce one. A human decides what happens next.",
                    {"band": band,
                     "surfaced": surfaced,
                     "evidence": evidence,
                     "exposure_rupees": case.get("exposure_rupees"),
                     "audit_roi": case.get("audit_roi"),
                     "priority": case.get("priority"),
                     "recommended_next_step": case.get("recommended_next_step"),
                     "suggested_actions": case.get("suggested_actions"),
                     "submission_notes": submission_notes,
                     "work_ref": work_ref,
                     "case_url": f"/case/{work_ref}",
                     "not_a_fraud_finding": True,
                     "disclaimer": case.get("disclaimer")})


def photohash_safe_sha(data: bytes) -> str:
    """SHA-256 of the payload. Named for where it is used, not what it wraps."""
    import hashlib

    return hashlib.sha256(data).hexdigest()
