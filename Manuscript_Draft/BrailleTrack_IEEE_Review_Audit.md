# Pre-Submission Audit: "A Low-Cost Conductive Grid System for Real-Time Multi-Metric Braille Reading Performance Analysis"

**OVERALL STATUS: Major revisions**

The core system (conductive grid, ESP32 scanning, multi-metric pipeline) is well-motivated and the writing is largely clean. But the audit surfaced several **verifiable, high-confidence problems**: three formulas that appear to have dropped out of the LaTeX build, a stated flagging threshold that the paper's own figure contradicts, a headline claim ("Ant" as hardest word) that undercuts another headline claim (regression/difficulty convergence), and a complete absence of sample size / variance reporting for the pilot study. None of these are fatal to the contribution, but all are the kind of thing a reviewer will catch and use to justify rejection or a hard revise-and-resubmit.

---

## A. Executive Summary (fix these first)

1. **Three missing formulas.** The raw rolling-WPM equation, the EWIQR weight function `w_i`, and the skip-rate formula are all referenced ("as expressed in Equation 2:", "Skip rate is defined as:") but never actually shown — the sentences cut straight to the next clause. This is very likely a LaTeX rendering/build error, not just a wording issue.
2. **Regression threshold contradicts Fig. 6.** Text says words are flagged at "regression count > 3"; the figure's own axis tops out at 3.0 and the highest bar (Alligator) is ~2.6. No flagged word actually exceeds 3.
3. **"Ant" undercuts the convergent-validity claim.** Ant is the single hardest word by composite difficulty (D=1.41) but doesn't appear anywhere in the regression chart (Fig. 6) — yet the text claims flagged-regression words "overlapped with high composite difficulty scores, confirming convergent validity."
4. **"Seven metrics" vs. "eight metric trackers."** Stated seven times as seven (abstract, Intro, III-A, Limitations); Fig. 3's own caption says "eight metric trackers" and lists eight items.
5. **No participant count anywhere.** The pilot study never states how many sighted participants took part, how many sessions, or gives any variance/error bars — despite the text referring to "multiple independent reading sessions."
6. **Beginner WPM benchmark is self-contradictory.** Three different beginner/novice figures appear (uncited "50-70 WPM", Fig. 4's "17 WPM (novice floor)" attributed to [6], and [6]'s own reported range of 65-185 WPM for *experienced* readers) and none of them agree.
7. **D(e) mixes unnormalized counts with bounded terms.** REV and ZC are raw, unbounded counts; VEL∈[0,1) and WREV∈{0,1}. Summing them with fixed weights (w1=1.0 etc.) without normalization undermines the meaning of the 0.50/0.90 difficulty thresholds.
8. **Full BOM isn't itemized** — three components are priced (~$5-6 total) but the stated $14-18 total isn't broken down.
9. Minor but visible LaTeX artifact: "supporting the systemś low-cost claim" (broken possessive apostrophe, p. 2).
10. Inconsistent equation cross-referencing style ("Equation 1", "the Equation 3", "(Eq. 3)") and a stray British/American spelling mix ("metre", "visualisation" vs. "visualization" elsewhere).

---

## B. Critical Issues

**[CRITICAL] Issue #1 — Missing raw-WPM formula**
- **Location:** Sec. III-D, p. 4, paragraph beginning "WPM is then computed over a 60-second rolling window:"
- **Problem:** The sentence "WPM is then computed over a 60-second rolling window: where nw(t) is the touch count within ∆T = 60 s" trails directly into the next sentence with no equation in between. Only the *smoothing* equation (Eq. 1) is shown; the underlying raw-WPM definition is never given.
- **Why it matters:** Without this, a reader cannot reproduce the metric — Eq. 1 smooths a quantity (x̃_t) that is itself never formally defined.
- **Recommended fix:** Insert the raw WPM equation (e.g., WPM_raw(t) = n_w(t)) before or as part of Eq. 1, or renumber so both are shown.

**[CRITICAL] Issue #2 — Missing EWIQR weight definition**
- **Location:** Sec. III-D, p. 4: "...is recorded with exponentially decaying weights as expressed in the Equation 2: , where clamp(x, a, b)..."
- **Problem:** There is a dangling colon-comma (": ,") exactly where the weight formula (e.g., w_i = λ^k) should appear. λ=0.95 is named as "decay factor" but the function relating w_i to λ is never written anywhere in the paper, even though w_i appears directly in Eq. 2's v̄ = Σw_i v_i / Σw_i.
- **Why it matters:** This is a core piece of the velocity-consistency metric (C_s) — without the weight formula, Eq. 2 cannot be reproduced or verified.
- **Recommended fix:** Add the explicit weight function, e.g. w_i = λ^{(t_now − t_i)} or λ^{n−i}, and confirm it against the implementation.

**[CRITICAL] Issue #3 — Missing skip-rate formula**
- **Location:** Sec. III-D, p. 4: "Considering N as the total number of mapped word regions (49 selected...), Skip rate is defined as: A BFS cluster analysis classifies skip patterns..."
- **Problem:** "Skip rate is defined as:" is immediately followed by an unrelated sentence about BFS clustering — no formula appears at all.
- **Why it matters:** Skip rate is one of the seven headline metrics; it is never mathematically defined anywhere in the paper.
- **Recommended fix:** State the formula explicitly (presumably something like skip_rate = 1 − |visited cells| / N) and clarify whether it is normalized by observation duration, as suggested later in Sec. IV-E.

**[CRITICAL] Issue #4 — Regression flag threshold contradicts Fig. 6**
- **Location:** Sec. III-D (p. 4): "Words with regression count > 3 are flagged as difficulty candidates" vs. Fig. 6 (p. 5).
- **Problem:** Fig. 6's x-axis runs 0.0–3.0, and the highest bar shown (Alligator) is visually ≈2.6 — none of the five red ("flagged") bars reach 3, let alone exceed it.
- **Why it matters:** Either the ">3" threshold in the text is wrong, or a different (unstated) threshold was actually used to generate Fig. 6. As written, the figure does not support the stated rule, and a reviewer will flag this immediately.
- **Recommended fix:** Report the actual threshold used for Fig. 6 (the caption already calls it "a configurable flag threshold" — state its value), and reconcile with the ">3" rule in Methods.

**[CRITICAL] Issue #5 — "Convergent validity" claim contradicted by its own figures**
- **Location:** Sec. IV-D, p. 5: "Words flagged by the regression tracker overlapped with high composite difficulty scores, confirming convergent validity across independent metrics."
- **Problem:** Ant is the single highest-difficulty word in the entire dataset (D = 1.41, Fig. 8) yet does not appear anywhere in Fig. 6's regression chart (13 words shown; Ant isn't one of them). Only 2 of the top-3 hardest words (Socks, Frog) show elevated regression counts — the actual hardest word does not.
- **Why it matters:** This is presented as evidence of cross-metric validity, but the strongest counter-example (the #1 hardest word) is the one that's missing from the corroborating figure.
- **Recommended fix:** Either qualify the claim ("partial overlap for 2 of the top 3 words") or explain why Ant's difficulty is driven by non-regression signals (REV/ZC/VEL) rather than WREV — which would actually be a more defensible and more interesting claim.

**[CRITICAL] Issue #6 — "Seven metrics" vs. Fig. 3's "eight metric trackers"**
- **Location:** Abstract; Sec. I; Sec. III-A ("computes seven reading performance metrics... eight-panel live visualization"); Sec. V ("seven-metric pipeline") vs. Fig. 3 caption (p. 3): "eight metric trackers (D = composite difficulty score)."
- **Problem:** The paper says "seven" five separate times but Fig. 3's own caption and its box list ("Update: WPM, vel., regr., EWIQR, Welford, skip, η, D" = 8 items) say eight.
- **Why it matters:** This is the kind of surface-level inconsistency an IEEE reviewer flags in the first pass, and it suggests the figure and prose were edited at different times.
- **Recommended fix:** The likely explanation is that Fig. 3 is counting implementation-level trackers (EWIQR and Welford are *algorithms used by* the velocity and ToT metrics, not separate metrics) rather than the seven reported metrics. State this explicitly, or recount consistently.

**[CRITICAL] Issue #7 — No sample size or variance reporting anywhere**
- **Location:** Sec. IV-A, p. 4 and throughout Sec. IV.
- **Problem:** The text says the pilot involved "multiple independent reading sessions" with sighted participants, but never states the number of participants, sessions, or session duration. All figures (7-10) are captioned "aggregated empirical data" with no indication of how many sessions were aggregated, and no error bars, confidence intervals, or variance measures appear anywhere.
- **Why it matters:** Without N, session count, and variance, none of the reported point values (D scores, dwell times, regression counts) can be assessed for reliability — this is a fundamental reproducibility and statistical-rigor gap for an empirical results section.
- **Recommended fix:** State N (participants), number of sessions per participant, and either raw per-session data or variance bars on the aggregated figures.

**[CRITICAL] Issue #8 — Composite difficulty D(e) mixes unnormalized and normalized terms**
- **Location:** Eq. 4, Sec. III-D, p. 4.
- **Problem:** REV(e) and ZC(e) are raw counts with no stated upper bound; VEL(e) ∈ [0,1); WREV(e) ∈ {0,1}. These are summed directly with fixed weights (w1=1.0, w2=0.5, w3=2.0, w4=1.5) with no normalization step described.
- **Why it matters:** A word with, say, REV(e)=3 contributes 3.0 to D from that term alone — more than double VEL's entire possible range — making the fixed color-scale thresholds in Fig. 8 (0.50, 0.90) hard to interpret or justify, since D's plausible range is not bounded or derived anywhere.
- **Recommended fix:** Either normalize REV and ZC (e.g., min-max or z-score across the session) before combining, or explicitly derive/justify D's expected range and the 0.50/0.90 thresholds from it.

---

## C. IEEE Compliance Issues

| Issue | Classification |
|---|---|
| Figures captioned below, tables captioned above, "Fig." abbreviation used consistently throughout (never "Figure") | Compliant — no action needed |
| Inconsistent equation cross-referencing: "Equation 1" / "the Equation 2" / "the Equation 3" / "(Eq. 3)" all appear | **Confirmed IEEE style issue** — standardize to "(1)" or "Eq. (1)" throughout |
| Mixed British/American spelling: "metre," "visualisation" vs. "visualization," "utilizing" elsewhere | **Likely issue** — most IEEE US-based venues (BHI included) expect American English; pick one convention |
| Article error: "renders a eight-panel live visualization suite" | **Confirmed grammar issue**, not IEEE-specific |
| No page numbers / running headers | **Venue/template-dependent** — IEEEtran conference templates typically don't require these pre-camera-ready; verify against IEEE BHI 2026's specific template instructions |
| Eq. 2 presented as a 3-line "cases" block under one number rather than (2a)/(2b)/(2c) | **Stylistic recommendation**, not a violation |
| Reference list formatting (numbering, italics, volume/no./pp./year) | Compliant — spot-checked all 24 entries, no missing fields found |

---

## D. Internal Inconsistencies

| # | Location A | Location B | Inconsistency | Recommended correction |
|---|---|---|---|---|
| 1 | Abstract / Sec. I / III-A / V ("seven...metrics") | Fig. 3 caption, p. 3 ("eight metric trackers") | Metric count differs | Reconcile terminology ("metric" vs. "tracker") or recount |
| 2 | Sec. I: "beginners typically read at only 50-70 WPM" (uncited) | Fig. 4 caption: "17 WPM (novice floor) [6]" | Two different, uncited/miscited beginner benchmarks | Cite the actual source for whichever figure is used, and reconcile 50-70 vs. 17 |
| 3 | Sec. I: ref [6] reported "range of 65–185 WPM" | Fig. 4: "novice floor [6]" = 17 WPM | [6] is cited for two contradictory numbers (65-185 for experienced readers vs. 17 as a "novice floor") | Verify what [6] actually reports for novices, if anything |
| 4 | Sec. III-D: "Words with regression count > 3 are flagged" | Fig. 6: max bar ≈2.6, axis caps at 3.0 | Stated threshold not reflected in the figure | State the actual threshold used to generate Fig. 6 |
| 5 | Sec. IV-D: regression-flagged words "overlapped with high composite difficulty scores" | Fig. 6 vs. Fig. 8: Ant (D=1.41, #1 hardest) absent from Fig. 6 | Claim not fully supported by the evidence shown | Qualify the overlap claim |
| 6 | Sec. IV-E: "this representative reading session achieved complete spatial coverage (no unvisited cells)" | Fig. 10 caption: "Grey positions denote unvisited cells" | Legend implies unvisited cells may exist in a dataset just described as having none | Clarify whether Fig. 10 uses the same session as Fig. 9, or note the legend entry is unused for this particular plot |
| 7 | Sec. III-D: Eq. 2's C_s legend says "the spread... reflects EWIQR-tracked inter-event variability" (Fig. 5) | Sec. IV-C repeats this almost verbatim | Not an error, but borderline redundant phrasing across caption and body text | Consider trimming repetition |
| 8 | Sec. IV-G: "55-60 ms" + "33 ms" hardware+software latency | Text: "combined end-to-end latency is approximately 95 ms" | 55-60 + 33 = 88-93, not 95 | Report as "≈88-93 ms" or explain the extra ~2-7 ms |

---

## E. Numerical & Mathematical Issues

- **Undefined ε** in C_s = clamp(1 − IQR/max(v̄, ε), 0, 1) (Eq. 2) — no value or description given for this small constant.
- **Undefined w_i** weight function for the EWIQR (see Critical Issue #2).
- **Missing raw-WPM and skip-rate formulas** (see Critical Issues #1, #3).
- **D(e) dimensional inconsistency** (see Critical Issue #8) — REV/ZC unbounded counts summed with bounded VEL/WREV terms.
- **Latency arithmetic**: 55-60 ms + 33 ms ≈ 88-93 ms, reported as "≈95 ms" (minor, ~2-7 ms discrepancy against the stated range).
- Hesitation rate H = r/T is defined in Methods (Sec. III-D) but **no H value is ever reported** in Results — it's the only one of the named formulas that's both defined and then dropped.

---

## F. Figures & Tables

- **Fig. 1** (breadboard photo): legible but visibly grainy at this resolution; individual copper traces are hard to distinguish. Acceptable for a prototype photo but consider a higher-resolution or annotated version.
- **Fig. 3** caption: "eight metric trackers" — see Critical Issue #6.
- **Fig. 4**: "17 WPM (novice floor) [6]" — see Critical Issue #2/internal inconsistency #2-3. Also, the EMA trend curve is still visibly rising at the right edge of the plot (touch-event index 50) rather than converging — this looks like the expected cold-start bias of a 60-second rolling window early in a session, which isn't discussed anywhere as a limitation.
- **Fig. 6**: 7 of the 21 distinct words appearing in Figs. 7–9 (Fifth, Knot, Egg, Moon, Mango, Mat, Fog) are absent from the regression chart, with no stated reason (presumably zero regressions, but this isn't confirmed in text). Also see Critical Issue #4.
- **Word label "Fifth"** (Figs. 7-9): stands out thematically against the otherwise concrete noun set (Ant, Socks, Alligator, Snail, Turtle, Frog, Cow, Hen, Elephant, etc.) — worth double-checking this isn't a typo for "Fish."
- **Fig. 8** caption states three discrete color bins (red ≥0.90, yellow 0.50–0.90, white <0.50), but the rendered heatmap appears to use a continuous gradient colormap rather than clearly banded discrete colors — verify the colormap actually implements the stated thresholds.
- **Fig. 10** caption vs. Fig. 9/Sec. IV-E text — see Internal Inconsistency #6.
- **Table I**: includes "Braille display [21],[23]" as a row in a comparison of "reading analysis systems," but the body text explicitly states these displays "provide no mechanism for capturing or analyzing how a reader interacts with the content" — several of the comparison columns (Real-Time, Vision-Free tracking, Per-word Metrics) arguably don't apply to a device that doesn't track reading at all. Consider a footnote clarifying these rows are included only as an output-cost benchmark.
- **Table II** header formatting is inconsistent: "Default (W1=1.0, W3=2.0)" lists two changed parameters while "Speed-Focused (W3=3.0)" and "Accuracy-Focused (W1=2.0)" each list only one.
- **Table II** ranking cross-checked against Fig. 8's Default D values: Ant(1.41) > Socks(1.22) > Frog(1.20) > Switch(1.04) > Cow(1.02) > {Alligator, Elephant}(0.99) — this matches the Default column exactly. Good internal consistency there.

---

## G. Citations & References

- **Uncited claim**: "beginners typically read at only 50-70 WPM" (Sec. I) has no citation attached, unlike the surrounding sentences which cite [6] and [7].
- **Uncited claim**: "$10,000 systems are prohibitively expensive" (Sec. III-B-1) — the $10,000 comparison figure is never sourced.
- **Ref [23]** (Saikot & Sanim) is cited only inside Table I and never discussed in running text — consider a sentence introducing it in Related Work, consistent with how [21] is handled.
- **Refs [8]-[10]** are cited as a group in the Introduction ("wearable sensors [8]–[10]") but never individually discussed in Sec. II's dedicated "wearable sensor systems" paragraph — that paragraph instead only discusses [15] and [16]. Since [8]-[10] appear to be prior work from the same research group (overlapping authorship with this paper — Rao), it would strengthen the related-work positioning to explicitly differentiate them there.
- Citation order, "et al." usage (3+ authors), and reference-list formatting (volume/issue/pages/year/publisher) were spot-checked across all 24 entries — no violations found.

---

## H. Language & Academic Writing

- **"supporting the systems low-cost claim"** (p. 2) — renders as "systemś" in the PDF (broken possessive apostrophe, likely a LaTeX escaping bug in the source, not just a typo). Should read "the system's low-cost claim."
- **"renders a eight-panel live visualization suite"** → "an eight-panel."
- **"as expressed in the Equation 1" / "the Equation 2" / "the Equation 3"** vs. **"(Eq. 3)"** — inconsistent equation-reference style; pick one form.
- **"metre" / "visualisation"** vs. "visualization" / "utilizing" elsewhere — inconsistent spelling convention.
- Otherwise the prose is clean, technically fluent, and largely free of the more common academic-writing problems (passive-voice overuse, ambiguous pronouns, tense drift) — this is not a heavy editing lift.

---

## I. Missing Information / Reproducibility

**Required / important:**
- Participant count (N), session count, and session duration for the pilot study.
- Variance or error bars on any of the aggregated figures (7-10) or the D-score/latency numbers.
- The three missing formulas (raw WPM, EWIQR weights, skip rate).
- Exact ESP32 board model/part number (currently just "an ESP32 microcontroller development board").
- Full itemized BOM — only copper tape (<$0.50/m), ESP32 ($4-5), and CD4051 pair ($0.80) are priced; the remaining ~$8-12 of the stated $14-18 total ("passive components, cabling, and perfboard") isn't itemized.
- How the 55-60 ms hardware latency figure was actually measured (method/instrumentation not described).

**Optional but would strengthen the paper:**
- The regression-flag threshold actually used to generate Fig. 6.
- Whether the "grey traces = past 20 events" window in Fig. 5 is a display-only choice or tied to the EWIQR's λ=0.95 decay parameter.

---

## J. Overclaims & Unsupported Statements

- **"The cost scales sub-linearly with grid size... supporting the system's low-cost claim"** (Sec. III-B-1) — asserted with no cost data across multiple grid sizes to support the sub-linearity claim. *Suggested fix:* soften to "we expect costs to scale sub-linearly..." or provide a cost projection for larger grids.
- **"Words flagged by the regression tracker overlapped with high composite difficulty scores, confirming convergent validity"** (Sec. IV-D) — contradicted by Ant's absence from Fig. 6 (see Critical Issue #5). *Suggested fix:* "partially overlapped" or specify which words.
- **"Analysis of these surface mappings confirms that the composite metric D produces stable, reproducible word-level difficulty profiles rather than transient, session-specific noise"** (Sec. IV-F) — only one aggregated dataset is shown; multi-session repeatability is explicitly named as future work elsewhere in the paper (Sec. IV-A: "multi-session variance and repeatability analysis... is planned"). "Confirms... reproducible" is stronger than what a single aggregated snapshot can support. *Suggested fix:* "is consistent with" rather than "confirms."
- **"...proving the system capable of tracking prolonged reading activity without sensor degradation or baseline drift"** (Sec. IV-F) — no longitudinal drift data or duration figures are given anywhere. *Suggested fix:* remove "proving," and either quantify session duration or drop the drift claim until measured.
- **PCA claim** ("Exploratory PCA revealed that sighted participants exhibit a tactile 'scrubbing' behavior... which inverts the kinematics of proficient blind readers," Sec. III-D) — no blind-reader data was collected in this study; the "inverts... proficient blind readers" half of the claim rests entirely on unstated PCA output plus indirect prior literature, not on any data in this paper. *Suggested fix:* clearly attribute the blind-reader-kinematics claim to prior literature (with citation) and present the PCA result (with actual loadings/variance-explained numbers) as evidence only for the sighted-participant "scrubbing" behavior.

---

## K. Page-by-Page Audit

- **p.1 (Title, Abstract, Intro):** No major issue detected, aside from the uncited "50-70 WPM" claim (see G).
- **p.2 (Related Work, Table I):** "systemś" typo (H). Table I framing issue re: Braille displays (F).
- **p.3 (Hardware, Fig. 1/2/3):** Fig. 3 "eight metric trackers" inconsistency (B-#6). BOM not fully itemized (I). Article error "a eight-panel" (H).
- **p.4 (Equations, Sec. IV start):** Three missing formulas (B-#1,#2,#3). Undefined ε (E). D(e) dimensional inconsistency (B-#8). Inconsistent "Equation X"/"Eq. X" referencing (H).
- **p.5 (Results B-E, Figs. 4-9):** "17 WPM" inconsistency (D-#2,3). Regression threshold contradiction (B-#4). Ant/convergent-validity contradiction (B-#5). Missing words in Fig. 6 (F). Fig. 4 cold-start ramp not discussed (F).
- **p.6 (Results F-H, Table II, Limitations start):** Fig. 8 color-bin/colormap mismatch (F). Fig. 10/Fig. 9 "unvisited cells" inconsistency (D-#6). Table II header inconsistency (F). Overclaim language in Sec. IV-F (J).
- **p.7 (Limitations, Conclusion, References):** No major issue detected in the prose itself; reference list is clean and well-formatted (G). PCA/blind-reader overclaim traces back to p.4 content discussed here in context.

---

## L. Final Submission Checklist

- [ ] Insert the three missing formulas (raw WPM, EWIQR weight function, skip rate)
- [ ] Reconcile "seven metrics" vs. "eight metric trackers" (Fig. 3 caption)
- [ ] Report actual participant count, session count, and variance/error bars for the pilot study
- [ ] Reconcile the three conflicting beginner/novice WPM figures (50-70, 17, and [6]'s 65-185)
- [ ] Fix the regression-flag threshold vs. Fig. 6 mismatch; state the actual threshold used
- [ ] Address the Ant/convergent-validity contradiction in Sec. IV-D
- [ ] Normalize or justify the D(e) formula's mixed unbounded/bounded terms
- [ ] Fix "systemś" → "system's" and "a eight-panel" → "an eight-panel"
- [ ] Standardize equation cross-reference style and English spelling convention throughout
- [ ] Add citations for "50-70 WPM" and "$10,000 systems" claims
- [ ] Itemize the remaining ~$8-12 of the BOM, and name the exact ESP32 board model
- [ ] Soften "confirms," "proving," and the blind-reader PCA claim per Section J
- [ ] Double-check "Fifth" as a word label — possible typo for "Fish"
- [ ] Verify latency arithmetic (88-93 ms vs. stated "≈95 ms")

---

## Confidence Assessment

**High confidence** (directly and visually verifiable from the PDF): Critical Issues #1-#6, #8; all Internal Inconsistencies except #7; the "systemś" typo; the article error; equation-reference style inconsistency; latency arithmetic; missing citations for the two flagged claims.

**Medium confidence** (strongly indicated, would benefit from author confirmation): Fig. 8's color-bin-vs-colormap mismatch (judged from a rasterized image, not the source colormap code); "Fifth" as a likely typo; the Fig. 5 "past 20 events" vs. λ=0.95 relationship; whether refs [8]-[10] are indeed the same research group.

**Low confidence** (possible, needs manual/author verification): whether the sub-linear cost-scaling claim would hold up with actual multi-size data; exact intended value of ε in Eq. 2.

---

## Top 10 Fixes Before Submission (ranked)

1. Restore the three missing formulas (raw WPM, EWIQR weights, skip rate) — these are reproducibility-critical and look like a build error, not a writing choice.
2. Report participant count, session count, and variance for the pilot study.
3. Resolve the regression-threshold-vs-Fig.6 contradiction.
4. Resolve the "seven metrics" vs. "eight metric trackers" inconsistency.
5. Fix or qualify the Ant/convergent-validity claim in Sec. IV-D.
6. Reconcile the three conflicting beginner/novice WPM numbers.
7. Normalize or justify D(e)'s mixed-scale terms and the 0.50/0.90 thresholds.
8. Soften "confirms"/"proving" language per Section J.
9. Itemize the full BOM and name the ESP32 board model.
10. Clean up the typographic/style issues (apostrophe bug, article error, equation-reference and spelling consistency).
