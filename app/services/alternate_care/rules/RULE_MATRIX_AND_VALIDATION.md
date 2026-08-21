# Care-Destination Rule Engine — V1 Draft

Rule version: `routing_rules_v0.1.0-draft`
Derived from: `synthetic_avoidable_ed_data.csv` (20,000 rows) + the two design docs.

## Scope

This engine only ever sees patients where an **upstream model** has already
set `avoidable_ed == 1` and where **no red-flag symptom is active**
(`flag_*` columns all 0). That's 12,093 / 20,000 rows in the synthetic set.
No red-flag/ER logic is implemented here — that's deliberately out of scope,
matching both design docs.

## Rule matrix

| Rule ID | Symptom category | Key conditions | Destination | Status |
|---|---|---|---|---|
| SAFETY-000 | chest_pain / severe_breathing_difficulty / severe_abdominal_pain_or_trauma / neuro_deficit | any occurrence | URGENT_CARE (defensive) | Requires validation |
| SPEC-002-PULM | mild_breathing_difficulty | copd_asthma_flag=1 AND chronic_condition_count≥2 | SPECIALIST (Pulmonology) | Requires validation |
| SPEC-003-ORTHO | back_pain | gradual onset AND trend∈{same,worsening} AND ed_visits_past_year≥3 | SPECIALIST (Orthopedics) | Requires validation |
| SPEC-001-FLAREUP | chronic_disease_flareup | trend=worsening AND CCI≥7 | SPECIALIST (unnamed — see gap below) | Requires validation |
| TELE-001-FLAREUP | chronic_disease_flareup | trend∈{same,improving} AND pain≤3 | TELEHEALTH | Requires validation |
| PCP-001-FLAREUP | chronic_disease_flareup | (default) | PCP | Document-supported |
| TELE-002-INFECTION | minor_infection | trend=improving AND pain≤3 | TELEHEALTH | Requires validation |
| UC-001-INFECTION | minor_infection | (default) | URGENT_CARE | Document-supported |
| UC-002-BREATHING | mild_breathing_difficulty | duration=hours | URGENT_CARE | Document-supported |
| TELE-005-BREATHING | mild_breathing_difficulty | duration=days AND trend∈{same,improving} AND pain≤3 | TELEHEALTH | Requires validation |
| PCP-002-BREATHING | mild_breathing_difficulty | (default) | PCP | Document-supported |
| UC-003-BACKPAIN | back_pain | onset=sudden | URGENT_CARE | Document-supported |
| TELE-004-BACKPAIN | back_pain | onset=gradual AND trend∈{same,improving} AND pain≤3 | TELEHEALTH | Requires validation |
| PCP-003-BACKPAIN | back_pain | (default) | PCP | Document-supported |
| TELE-003-GENERAL | mild_general_symptom | trend=improving AND pain≤3 | TELEHEALTH | Document-supported |
| PCP-004-GENERAL | mild_general_symptom | (default) | PCP | Document-supported |
| UC-004-DENTAL | dental_pain | (default) | URGENT_CARE (stopgap) | Requires product decision |
| FALLBACK-999 | — | no match | PCP | Safety fallback |

Rules are evaluated **highest priority first, first match wins** (see YAML
`priority` field). Full conditions and citations to the source docs are in
`rules/care_destination_rules.yaml`.

## Validation run (full in-scope population, n=12,093)

**Destination distribution:**

| Destination | Count | % |
|---|---|---|
| URGENT_CARE | 4,673 | 38.6% |
| PCP | 4,087 | 33.8% |
| TELEHEALTH | 1,845 | 15.3% |
| SPECIALIST | 1,488 | 12.3% |

**Sanity check — every `primary_symptom_category` maps cleanly and
exclusively into the expected destinations** (see full crosstab in
`validate_against_data.py` output). E.g. `minor_infection` → 100%
URGENT_CARE/TELEHEALTH, `dental_pain` → 100% URGENT_CARE, no
cross-contamination.

> **STALE — re-run needed.** The distribution above predates
> `TELE-004-BACKPAIN` and `TELE-005-BREATHING` (added to extend the
> low-pain/stable-or-improving telehealth pattern to `back_pain` and
> `mild_breathing_difficulty`, mirroring TELE-001/002/003). These will
> shift some share of `PCP` (back_pain default) and `URGENT_CARE`
> (breathing default) into `TELEHEALTH`. Re-run
> `validate_against_data.py` against the source CSV to get the real
> updated counts rather than estimating — do not publish new
> percentages until that's done.

`SAFETY-000` fired 6 times — all from label noise where a severe
symptom category slipped through the red-flag filter (≤0.05% of in-scope
rows). This is expected and confirms the defensive rule is doing its job
rather than never firing at all.

## Known gaps — need clinical/product input before production

1. **No dedicated dental pathway.** `dental_pain` is 12% of the in-scope
   population but doesn't cleanly belong in PCP/UC/Specialist/Telehealth.
   Currently stopgapped to URGENT_CARE, which is clinically wrong (most
   urgent-care clinics don't treat dental pain). **Recommend adding a
   5th destination or an explicit referral branch.**

2. **`chronic_disease_flareup` has no body-system signal.** All seven
   chronic-condition flags (diabetes, HTN, cardiac, COPD/asthma, CKD,
   cancer, immunocompromised) sit at ~52–55% prevalence *within this
   category*, evenly — meaning the synthetic data doesn't tell us which
   organ system is flaring up. `SPEC-001-FLAREUP` can only flag "needs
   specialist-level review," not name a specialty. **A body-system-specific
   symptom field or "dominant condition" field is needed to route to a
   named specialty for this ~20% of the specialist-eligible population.**

3. **New:** `TELE-004-BACKPAIN` and `TELE-005-BREATHING` extend the
   pain≤3/stable-or-improving telehealth pattern beyond the three
   symptom categories the pattern was originally observed in
   (mild_general_symptom, minor_infection, chronic_disease_flareup).
   For back pain, doc 1 explicitly found no discriminative signal on
   this split, so this is an engineering extrapolation, not a
   dataset-confirmed pattern. For breathing difficulty, using
   self-reported pain as a severity proxy is weaker clinical grounding
   than for the other categories, since breathing complaints are
   conventionally triaged by auscultation/SpO2 rather than pain score.
   Both need clinical sign-off before activation, and the sign-off
   should separately cover (a) the threshold and (b) whether pain is
   an acceptable proxy at all for breathing severity.

4. **All thresholds (CCI≥7, ed_visits≥3, pain≤3, etc.) are derived by
   pattern-matching the synthetic distributions, not clinical guidelines.**
   Every rule tagged `RECOMMENDED_REQUIRES_VALIDATION` needs sign-off from
   a clinical reviewer before this goes near real patients — per doc 2's
   explicit requirement, engineering-derived thresholds are not the same
   as clinically validated ones.

5. **`has_pcp_flag` was not used** as a routing feature. It showed near-zero
   correlation with `avoidable_ed` in the exploratory pass and no clear
   signal within any symptom category. It may still matter for continuity
   scoring at the provider-ranking stage (right destination, which provider)
   rather than the destination decision itself.
