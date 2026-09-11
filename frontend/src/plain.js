/**
 * Plain words for what the engine says.
 *
 * The engine stores a short sentence with every clue it finds on a work, and those
 * sentences are written for analysts: "Recommended amount at the 100th percentile of 144
 * comparable works (robust z 115.3)". They are part of the stored results, so they are not
 * rewritten at the source — that would change the data. They are re-worded here, as they
 * are shown, into words a school student can follow.
 *
 * Every rewrite keeps the same facts and the same numbers. A sentence this file does not
 * recognise is shown exactly as the engine wrote it rather than guessed at, and every
 * caller keeps the original available as a tooltip so the exact figures are never lost.
 *
 * The templates matched here are the ones in src/mplads/pipeline.py (evidence) and
 * src/mplads/intelligence/early_warning.py (reasons). If those templates change, the
 * rewrite simply stops matching and the original sentence shows — it never breaks.
 */

/** Each kind of clue, named the way a person would say it. */
export const CLUE_NAME = {
  "Peer amount": "Costs much more than similar works",
  "Peer duration": "Taking much longer than similar works",
  "Completion risk": "Might never get finished",
  "Lifecycle conformance": "Records don't add up",
  "Behavioural change": "Agency suddenly changed",
  "Statistical outlier": "Unusual numbers",
  "Near-duplicate work": "Might be a repeat of another work",
};

/** Short forms for tight spaces such as chips. */
export const CLUE_SHORT = {
  "Peer amount": "High cost",
  "Peer duration": "Long delay",
  "Completion risk": "May not finish",
  "Lifecycle conformance": "Records",
  "Behavioural change": "Agency changed",
  "Statistical outlier": "Unusual numbers",
  "Near-duplicate work": "Possible repeat",
};

/** The engine's family keys, in words. */
export const FAMILY_NAME = {
  amount: "cost",
  duration: "time taken",
  lifecycle: "records",
  behaviour: "agency behaviour",
  multivariate: "unusual numbers",
  duplication: "possible repeat",
};

export const clueName = (s) => CLUE_NAME[s] || s;
export const familyName = (f) => FAMILY_NAME[f] || f;

/** The eight record checks, named plainly. */
export const CHECK_NAME = {
  "Amount outlier vs peers": "Costs far more than similar works",
  "Stalled beyond peer norm": "Stuck much longer than similar works",
  "Completion before recommendation": "Finished before it was even asked for",
  "Missing description": "No description written",
  "Missing recommendation record": "No record of who asked for it",
  "Completed without sanction": "Finished without an approval on record",
  "Completion beyond snapshot": "Finish date is in the future",
  "Non positive amount": "Amount is zero or less",
};
export const checkName = (n) => CHECK_NAME[n] || n;

/** What each record check means, for someone who has never seen a sanction order. */
export const CHECK_MEANING = {
  "Completed without sanction":
    "It is marked as finished, but there is no record that it was ever approved. Every other work goes: asked for → approved → finished.",
  "Completion before recommendation":
    "The finish date is earlier than the date it was asked for — that cannot really happen, so the dates are wrong somewhere.",
  "Completion beyond snapshot":
    "The finish date is after the date these records were taken, sometimes years later. It is most likely a typing mistake.",
  "Missing recommendation record":
    "It shows up as approved or finished, but there is no record of anyone asking for it, so we cannot tell where it came from.",
  "Non positive amount":
    "The amount is zero or less than zero, so its money cannot be checked.",
  "Missing description":
    "Nobody wrote down what the work is, so it cannot be grouped or compared with similar works.",
  "Stalled beyond peer norm":
    "It has been waiting far longer than similar works in the same state.",
  "Amount outlier vs peers":
    "It asks for far more money than similar works in the same state.",
};
export const checkMeaning = (name, fallback) => CHECK_MEANING[name] || fallback;

/** Which group of similar works a work was compared with. */
export const PEER_LEVEL = {
  cat_state: "Same kind of work, same state",
  cat: "Same kind of work, all of India",
  state: "All works in the same state",
  global: "All works in India",
};

/** How the "may not get finished" chance was worked out. */
export const RISK_BASIS = {
  cox_model: "learned from how long similar works took",
};

/** The engine's four next-step sentences, said plainly. Unknown ones come back unchanged. */
export function plainNextStep(text) {
  if (!text) return text;
  if (text.startsWith("A human should check the lifecycle record")) {
    return "A person should ask the District Authority to check this work's records — its dates do not add up.";
  }
  if (text.startsWith("A human should verify the scope and estimate")) {
    return "A person should ask the agency building it why it costs so much more than similar works, and check what exactly is being built.";
  }
  if (text.startsWith("A human should request a progress update")) {
    return "A person should ask the agency building it how far the work has got, because it has been going on for a long time.";
  }
  if (text.startsWith("A human should review this work's evidence")) {
    return "A person should read the clues above and decide whether someone needs to visit the site.";
  }
  if (text.startsWith("No signal fired on this work")) {
    return "No check raised a concern — this work is normal for its kind on everything we measure. Nobody needs to review it. It can still be visited, and a visit that finds it fine is just as useful as one that finds a problem.";
  }
  return text;
}

/** The change-over-time labels, said plainly. */
export const TREND_NAME = {
  NORMAL: "Normal",
  STABLE: "Steady",
  GROWING: "Growing",
  DECLINING: "Shrinking",
  EMERGING: "New and growing",
  PERSISTENT_CHANGE: "Changed and stayed",
  SUDDEN_CHANGE: "Sudden jump",
  INSUFFICIENT_HISTORY: "Too new to tell",
};

/** Rephrase a change-over-time explanation (intelligence/temporal.py). Unknown ones come back unchanged. */
export function plainTrend(text) {
  if (!text) return text;
  if (text === "Within the usual range for this series.") return "Nothing unusual — about the same as usual.";
  let m = text.match(/^The recent level is (\d+)% (higher|lower) than the historical average and has stayed there for three periods\.$/);
  if (m) return `Lately it has been ${m[1]}% ${m[2]} than it used to be, and it has stayed that way for three periods in a row.`;
  m = text.match(/^The latest period is a (spike|drop|dip) of ([\d.]+) standard deviations against this series' own history\.$/);
  if (m) {
    const up = m[1] === "spike";
    return `The latest period suddenly jumped ${up ? "up" : "down"} — far ${up ? "above" : "below"} anything normal for it (${m[2]} times its usual ups and downs).`;
  }
  m = text.match(/^Growing steadily from a small base \(\+(\d+)%\)\.$/);
  if (m) return `Started small and is growing steadily (up ${m[1]}%).`;
  m = text.match(/^Only (\d+) periods of history available\.$/);
  if (m) return `Only ${m[1]} periods of history so far — too few to tell.`;
  return text;
}

/** What an officer can record after a visit. */
export const OUTCOME = {
  VERIFIED_COMPLETE: ["Finished, as recorded", "Visited. The work is there and finished, just as the record says."],
  VERIFIED_IN_PROGRESS: ["Being built", "Visited. The work is there and really is being built."],
  NOT_STARTED: ["Not started", "Visited. No work has started at this place."],
  NOT_FOUND: ["Not found", "Visited. Nothing at this place matches the record."],
  RECORD_MISMATCH: ["Different from the record", "The work is there, but it is different from the record (size, what it is, or where)."],
  NO_ACCESS: ["Could not check", "Could not check — the place could not be reached or found."],
};

/** What an officer does at each of the five steps, said plainly. Keyed by the engine's stage. */
export const STAGE_HELP = {
  New: "The computer flagged this case and no person has looked at it yet. Read the clues before deciding whether someone should visit.",
  Assigned: "An officer is now in charge of this case. The review date is a promise, not a suggestion.",
  "In Progress": "Papers have been asked for or a site visit is arranged. Write down what you find as you go (in Chatter), so the next person can follow the case.",
  Verified: "Someone has really gone and looked. Write down what they found — even \"nothing wrong\", which helps the system just as much as a real problem.",
  Closed: "What was found is written down and the case is done. It now helps the computer learn — the only way its scoring stops being an educated guess.",
};

/** The engine's suggested actions, said plainly. */
export const ACTION = {
  "Review the lifecycle history and sanction record": "Look at every step in its records, and at its approval",
  "Compare scope and estimate with peer works": "Compare what is being built, and its cost, with similar works",
  "Request a progress update from the implementing agency": "Ask the agency building it how far the work has got",
  "Verify supporting documents and field evidence": "Check the papers, and what can be seen at the site",
};
export const plainAction = (a) => ACTION[a] || a;
export const plainGuidance = (stage, text) => STAGE_HELP[stage] || text;

/** Clue-strength labels that come from the engine as words. */
export const BAND_LABEL = { "NOT SURFACED": "Not flagged" };

/**
 * The English template briefing (llm.py's fallback), with its analyst words swapped for
 * plain ones. Only applied to the English template — a model-written or translated
 * briefing is shown exactly as it came.
 */
const BRIEF_SWAPS = [
  ["placed on the audit list", "put on the list to check"],
  ["independent kinds of evidence", "different kinds of clue"],
  ["peer amount", "costs much more than similar works"],
  ["peer duration", "taking much longer than similar works"],
  ["behavioural change", "agency suddenly changed"],
  ["statistical outlier", "unusual numbers"],
  ["near-duplicate work", "might be listed twice"],
  ["lifecycle conformance", "records don't add up"],
  ["completion risk", "might never get finished"],
  ["may be tied up if it does not finish", "could be stuck if it never gets finished"],
  ["the model estimates may not finish on time", "the computer thinks may not get finished on time"],
  ["The portfolio holds", "The scheme has"],
  ["still in progress", "not finished yet"],
];
export function plainBrief(text) {
  if (!text) return text;
  let t = text;
  for (const [a, b] of BRIEF_SWAPS) t = t.split(a).join(b);
  for (const key of [
    "A human should check the lifecycle record with the District Authority — the stage dates are inconsistent.",
    "A human should verify the scope and estimate for this work against its peers via the Implementing Agency.",
    "A human should request a progress update from the Implementing Agency on this long-running work.",
    "A human should review this work's evidence and decide whether a site verification is warranted.",
  ]) t = t.split(key).join(plainNextStep(key));
  return t;
}

export const DISCLAIMER =
  "This system only points out works a person should look at. It never decides that anything is fraud.";

/** Rephrase one stored evidence sentence. Unknown sentences come back unchanged. */
export function plainEvidence(text) {
  if (!text) return text;
  let m;

  m = text.match(/^Recommended amount at the (\d+)th percentile of ([\d,]+) comparable works \(robust z (-?[\d.]+)\)\.$/);
  if (m) {
    const p = Number(m[1]);
    return p >= 100
      ? `It costs more than all ${m[2]} similar works in the same state.`
      : `It costs more than ${p} out of every 100 similar works in the same state (${m[2]} works compared).`;
  }

  m = text.match(/^Open for longer than (\d+)% of comparable works still in progress\.$/);
  if (m) {
    return Number(m[1]) >= 100
      ? "It has been waiting longer than every similar unfinished work."
      : `It has been waiting longer than ${m[1]} out of every 100 similar unfinished works.`;
  }

  m = text.match(/^Survival model: (\d+)% of comparable works have not completed within (\d+) days\.$/);
  if (m) return `Out of every 100 similar works, about ${m[1]} were still not finished after ${m[2]} days.`;

  m = text.match(/^Lifecycle inconsistency: (.+)\.$/);
  if (m) return `The dates or steps in its records do not add up: ${m[1]}.`;

  if (text.startsWith("Implementing agency's recommendation pattern shifted year-on-year")) {
    const mag = text.match(/\(magnitude (\d+)%\)/);
    return "The agency building it suddenly changed the size or kind of work it takes on"
      + (mag ? ` (a change of about ${mag[1]}%)` : "")
      + ". This can have an innocent reason, such as a new officer or a new rule.";
  }

  if (text.startsWith("A trained anomaly detector (IsolationForest)")) {
    return "A computer model that has learned what normal works look like says this work's "
      + "cost and age are unusual compared with works across India.";
  }

  m = text.match(/^A work in the same state and archetype is ([\d.]+)% semantically similar \(([^)]*)\)/);
  if (m) {
    return `Another work of the same type in the same state (${m[2]}) is described in almost `
      + `the same way — ${Math.round(Number(m[1]))}% alike. The same words are often used for `
      + "different works, so a person should check they really are separate.";
  }

  return text;
}

/** Rephrase an early-warning reason. Unknown sentences come back unchanged. */
export function plainReason(text) {
  if (!text) return text;
  if (text === "No stalling indicators; the work is progressing within normal ranges.") {
    return "Nothing suggests this work is stuck — it is moving along normally.";
  }
  if (text === "Work is recorded as completed; no early warning applies.") {
    return "This work is marked as finished, so there is nothing to warn about.";
  }
  let t = text.replace(/^(CRITICAL|HIGH|MEDIUM|LOW) — /, "");
  const before = t;
  t = t.replace(
    /open ([\d.]+)x longer than the typical completed work of this type in (.+?) \((\d+) days\)/,
    (_, r, s, d) => `it has been open ${r} times longer than similar finished works in ${s} usually take (${d} days)`,
  );
  t = t.replace(
    /the survival model puts a (\d+)% chance it will not complete within (\d+) days/,
    (_, p, d) => `there is about a ${p}% chance it will not be finished within ${d === "365" ? "a year" : `${d} days`}`,
  );
  if (t === before) return text; // nothing recognised — show the engine's own words
  t = t.replace("; and ", ", and ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/**
 * The guarantee behind the Field Rota, computed rather than quoted. Handing out the
 * longest trips first to whoever has least work is proven (Graham, 1969) never to leave
 * the busiest person with more than (4/3 − 1/(3m)) times the best possible load.
 */
export const rotaBound = (auditors) => {
  const m = Math.max(1, Number(auditors) || 1);
  return 4 / 3 - 1 / (3 * m);
};
