"""The English source of every user-facing interface string.

One flat dictionary, translated as a unit and cached per language. Keys are stable; only
values are ever translated. Numbers and case-file content are translated separately at
request time because they change with the data.

Written for a reader with no training in statistics or auditing: a member of the public,
an officer on their first day, a school student. Where a precise technical term matters,
the page that needs it shows it in small print beside the plain words — never instead of
them. Keys are unchanged, so every translation keeps working; only the English wording moved.
"""

from __future__ import annotations

UI: dict[str, str] = {
    # navigation
    "nav.monitor": "Find problems",
    "nav.intelligence": "Clues",
    "nav.trust": "Checking the system",
    "nav.overview": "Overview",
    "nav.worklist": "Works to Check",
    "nav.trends": "Changes Over Time",
    "nav.duplicates": "Possible Duplicates",
    "nav.compliance": "Record Checks",
    "nav.archetypes": "Work Types",
    "nav.transparency": "About the Data",
    "nav.how": "How It Works",
    # shell
    "shell.brandSub": "Public Works Monitoring",
    "shell.stakeholder": "View as",
    "shell.roleSim": "See the site as a different official would — this does not sign you in",
    "shell.viewingAs": "Viewing as",
    "shell.chain": "Learn what is normal · Compare · Predict · Explain · Put in order",
    "shell.leadsNotVerdicts":
        "These are works worth checking — not proof that anyone did wrong. "
        "A person always decides what happens next.",
    # overview
    "overview.title": "Detection Centre",
    "overview.worksMonitored": "Works checked",
    "overview.totalRecommended": "Total money recommended",
    "overview.exposure": "Money at risk",
    "overview.exposureFoot": "Money in works that may not get finished — not money lost or spent",
    "overview.leads": "Works flagged for checking",
    "overview.byState": "Money at risk by state (top 10, in crore rupees)",
    "overview.bands": "How strong the clues are",
    "overview.archetypes": "Kinds of work the computer found",
    "overview.completed": "finished",
    "overview.open": "not finished yet",
    # worklist
    "worklist.title": "Works to Check",
    "worklist.sub":
        "Most worth checking first — a work comes higher the more public money a check "
        "could protect and the more clues agree",
    "worklist.search": "Search by what the work is, or who is building it",
    "worklist.allStates": "All states",
    "worklist.allBands": "All clue levels",
    "worklist.empty": "No works match these filters.",
    "worklist.work": "Work",
    "worklist.state": "State",
    "worklist.confidence": "Clue strength",
    "worklist.amount": "Amount",
    "worklist.auditRoi": "Worth checking",
    "worklist.prev": "Previous",
    "worklist.next": "Next",
    "worklist.page": "Page",
    "worklist.of": "of",
    # case file
    "case.title": "Case File",
    "case.back": "Back to the list",
    "case.evidence": "Why the computer flagged this work",
    "case.peerContext": "Compared with similar works",
    "case.nextStep": "What a person should check next",
    "case.recommended": "Recommended",
    "case.completionRisk": "Chance it may not get finished",
    "case.corroboration": "Clues that agree",
    "case.families": "kinds of clues",
    "case.earlyWarning": "Early warning",
    "case.compliance": "Problems found in the records",
    "case.duplicate": "Possible duplicate",
    "case.aiBrief": "Summary in plain words",
    "case.archetype": "Work type",
    "case.peerLevel": "Compared within",
    "case.peerSize": "Number of similar works",
    "case.amountPercentile": "Costs more than",
    # shared banners
    "banner.hitl":
        "These are works worth checking — not proof that anyone did wrong. The computer lists "
        "them by how much public money a check could protect, using clues anyone can look at. "
        "No record says which works really had problems, so a person always looks at the "
        "evidence and decides.",
    "common.loading": "Loading",
    "common.works": "works",
    "common.leads": "flagged works",
    "common.language": "Language",
    "common.generating": "Writing the summary",
    "common.exposure": "money at risk",
    "common.weight": "weight",
    "common.notFound": "Page not found",
    "common.notFoundBody": "There is nothing at this address.",
    "common.notFoundCta": "Go to the Detection Centre",
    # compliance & early warning
    "compliance.title": "Record Checks and Early Warnings",
    "compliance.sub":
        "Checking that each work's records happen in the right order, and spotting works "
        "that may never get finished",
    "compliance.authorityLead": "Where each rule comes from matters.",
    "compliance.healthIndex": "Overall health score of the scheme",
    "compliance.earlyLevels": "Early warnings for unfinished works",
    "compliance.checks": "Record checks",
    "compliance.check": "Check",
    "compliance.authority": "Based on",
    "compliance.severity": "How serious",
    "compliance.meaning": "What it means",
    # near-duplicates
    "duplicates.title": "Possible Duplicates",
    "duplicates.sub": "Works that describe the same thing — found by comparing meaning, not just words",
    "duplicates.concerningPairs": "pairs worth a look",
    "duplicates.normalLead": "Repeated descriptions are normal here",
    "duplicates.normalBody":
        "— an MP asking for forty street lights writes the same sentence forty times. So a "
        "pair only counts as worth a look when the two works read almost the same, are built "
        "by the same agency, and cost almost the same. That is what one work claimed twice "
        "would look like. It is a question for a person, never proof.",
    "duplicates.candidatesFound": "Similar pairs found",
    "duplicates.concerning": "Pairs worth a look",
    "duplicates.identicalText": "Exactly the same words",
    "duplicates.sameAgency": "Same agency building both",
    "duplicates.acrossBlocks": "compared within the same state and work type",
    "duplicates.sameAgencyAmount": "same agency, and almost the same cost",
    "duplicates.candidatePairs": "Similar pairs",
    "duplicates.workA": "Work A",
    "duplicates.workB": "Work B",
    "duplicates.similarity": "How alike",
    # temporal
    "trends.title": "Changes Over Time",
    "trends.sub": "How the scheme is changing, year by year",
    "trends.agenciesAnalysed": "agencies looked at",
    "trends.method": "How this was worked out:",
    "trends.volume": "Number of works each month (whole country)",
    "trends.median": "Typical amount per work (in thousand rupees)",
    "trends.radar": "Kinds of work that are becoming more common",
    "trends.workType": "Work type",
    "trends.status": "Status",
    "trends.recentWorks": "Recent works",
    "trends.shareChange": "Change in share",
    "trends.agenciesChanged": "Agencies that suddenly changed what they do",
    "trends.agency": "Agency",
    "trends.totalWorks": "Total works",
    "trends.whyFlagged": "Why it was flagged",
    # data transparency
    "transparency.title": "About the Data",
    "transparency.sub":
        "What we count directly, what the computer works out, and what the public data "
        "simply does not have",
    "transparency.fieldsUnavailable": "facts not available",
    "transparency.measured": "Counted directly",
    "transparency.measuredFoot": "taken straight from government records",
    "transparency.derived": "Worked out by the computer",
    "transparency.derivedFoot": "calculated, with how sure we are",
    "transparency.unavailable": "Not available",
    "transparency.unavailableFoot": "missing from public data — we do not make it up",
    "transparency.metric": "What",
    "transparency.source": "Where it comes from",
    "transparency.confidenceCol": "How sure",
    "transparency.note": "Note",
    "transparency.completeness": "How complete each fact is",
    "transparency.groundTruth": "What officers found on real visits",
    "transparency.readyFor": "Ready for more government data",
    "transparency.field": "Fact",
    "transparency.type": "Type",
    "transparency.wouldUnlock": "What it would let us do",
    "transparency.verifications": "Site visits recorded",
    "transparency.concernsConfirmed": "Problems confirmed on site",
    "transparency.stillNeeded": "Visits still needed before the scoring can be tuned",
    "transparency.outcome": "Result",
    "transparency.meaning": "Meaning",
    # archetypes
    "archetypes.title": "Work Types",
    "archetypes.sub": "Kinds of work the computer worked out on its own, just by reading the descriptions",
    "archetypes.named": "named",
    "archetypes.medianSize": "Typical cost",
    "archetypes.completedPct": "Finished",
    "archetypes.typicalDuration": "Usual time taken",
    "archetypes.flagged": "Flagged",
    "archetypes.distinctiveTerms": "Words that stand out in this group",
    "archetypes.viewFlagged": "See the flagged works",
    "archetypes.notInterpretable": "no clear meaning",
    # case file (additions)
    "case.plainSummary": "In plain words:",
    "case.auditRoiRank": "Worth-checking score",
    "case.exposureFoot": "amount × chance it may not get finished",
    "case.basis": "worked out from",
    "case.familiesFired": "different kinds of clues found",
    "case.matchedWork": "Matching work",
    "case.classification": "Type",
    "case.similarity": "How alike",
    # assistant
    "chat.assistant": "Assistant",
    "chat.open": "Ask a question",
    "chat.tools": "lookups",
    "chat.live": "live",
    "chat.offline": "offline",
    "chat.connecting": "connecting…",
    "chat.introLead":
        "I only answer by looking things up in the results the system has already worked "
        "out. I don't know anything else about this data and I don't do my own sums, so I "
        "can't make up a number — and I show you where each answer came from.",
    "chat.forThisScreen": "About this page",
    "chat.orAsk": "Or ask about",
    "chat.all": "All",
    "chat.lookedUp": "Looked up",
    "chat.working": "Looking it up…",
    "chat.placeholder": "Ask about a work, a state, or the numbers…",
    "chat.send": "Send",
    "chat.copy": "Copy",
    "chat.copied": "Copied",
    "chat.listen": "Listen",
    "chat.stop": "Stop",
    "chat.export": "Save the conversation",
    "chat.clear": "Clear the conversation",
    "chat.expand": "Make bigger",
    "chat.restore": "Make smaller",
    "chat.close": "Close",
    "chat.speak": "Ask by speaking",
    "chat.stopListening": "Stop listening",
    "chat.noVoice": "This browser cannot listen. Chrome or Edge can.",
    "chat.voiceFailed": "I could not hear that. Try again, or type it.",
    "chat.copyFailed": "The browser did not allow copying.",
    "chat.unreachable":
        "I could not reach the assistant. The system may still be starting — try again in a moment.",
}
