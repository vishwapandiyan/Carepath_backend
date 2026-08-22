# Alternate Care Navigation — Routing Rule Matrix (V1)
**Derived from `synthetic_avoidable_ed_data.csv` (20,000 rows, 57 features)**
Population scope: this agent only ever sees rows where the upstream ML model has set `avoidable_ed = 1` (n = 12,214 / 61%).

---

## 0. Data-quality finding: the upstream label leaks 77 true emergencies

Before building any rule, we checked whether `avoidable_ed = 1` can be trusted at face value. It mostly can — but not entirely:

| `primary_symptom_category` (within avoidable_ed=1) | n | `any_red_flag` rate | `pqe_category` |
|---|---|---|---|
| chest_pain | 28 | 89.3% | 100% NonPQE_TrueEmergency |
| severe_breathing_difficulty | 20 | 90.0% | 100% NonPQE_TrueEmergency |
| severe_abdominal_pain_or_trauma | 13 | 92.3% | 100% NonPQE_TrueEmergency |
| neuro_deficit | 16 | 100.0% | 100% NonPQE_TrueEmergency |

These 77 rows (0.6% of the navigator population) are true emergencies that the upstream model mislabeled as avoidable. Every one of them still carries a clinical red flag (chest pain + sweating/nausea, stroke signs, LOC, etc.) even though `avoidable_ed = 1`.

> **RULE SAFETY-000 (mandatory, not optional)**
> ```
> IF any(flag_*) == true
> THEN destination = ESCALATE_TO_ED  (bypass all other rules)
> ```
> This is a defense-in-depth check, not new ER-triage logic — it does not re-diagnose anything. It simply refuses to route a red-flagged patient into a non-emergency pathway even if an upstream model said to. This must run **first**, before care-type classification, regardless of `avoidable_ed`.

After this filter, **99.4% of the navigator population (12,137 rows) falls into 6 clean categories.** Everything below is built from those 6.

---

## 1. Care-Type Classification — the 6 core categories

| `primary_symptom_category` | n | Dominant `pqe_category` | Match rate |
|---|---|---|---|
| mild_general_symptom | 3,033 | NonPQE_FollowUp | 99.6% |
| minor_infection | 2,683 | PQE03_AcuteACSC | 99.4% |
| chronic_disease_flareup | 2,287 | PQE02_ChronicACSC | 98.9% |
| back_pain | 1,556 | PQE05_BackPain | 99.0% |
| dental_pain | 1,454 | PQE01_Dental | 99.9% |
| mild_breathing_difficulty | 1,124 | PQE04_Asthma | 98.3% |

`primary_symptom_category` is a near-perfect proxy for `pqe_category` once red flags are excluded. This is the primary routing key — everything else (duration, trend, chronic flags, `has_pcp_flag`, utilization) is a **modifier**, per the original design doc's guidance not to build single-feature rules.

### Destinations (V1 — 4 destinations)

```
PCP
URGENT_CARE
SPECIALIST
TELEHEALTH
```

`dental_pain` routes to `SPECIALIST` with `specialty = DENTISTRY` (see Section 4 — this was
revised from an earlier "5th destination" design; kept here as SPECIALIST to match the
original 4-destination architecture, with the caveat below about network/billing implications).

### RULE CT-001 — mild_general_symptom → PCP
```
IF primary_symptom_category == mild_general_symptom
THEN care_type = PCP
REASON: 99.6% NonPQE_FollowUp. Low severity (mean pain 2.4/10),
        60% improving trend, 72.5% already have a PCP,
        mean 4.5 ED visits/year -> high-utilizer, continuity-of-care
        priority over one-off UC visit.
PRIORITY: 10
EVIDENCE: DOCUMENT-SUPPORTED (derived from dataset)
```

### RULE TC-001 — mild_general_symptom, delivery-mode suitability (TELEHEALTH candidate)
```
IF primary_symptom_category == mild_general_symptom
   AND pain_level_self_reported <= 3
   AND symptom_trend in [same, improving]
THEN delivery_mode_candidate = TELEHEALTH
     (else IN_PERSON)
REASON: 68.0% of mild_general_symptom rows meet this low-severity /
        stable-or-improving profile -- the only proxy this dataset
        supports for telehealth suitability.
PRIORITY: 15
EVIDENCE: RECOMMENDED — REQUIRES CLINICAL VALIDATION.
CORRECTION NOTE: an earlier version of this rule referenced a
  `patient_preference` field. That field does not exist anywhere in
  the 57-column dataset -- it was an unverified assumption, not a
  derived rule, and has been removed. See Section 1a below.
```

### RULE CT-002 — minor_infection → URGENT_CARE
```
IF primary_symptom_category == minor_infection
THEN care_type = URGENT_CARE
REASON: 99.4% PQE03_AcuteACSC (acute, ambulatory-care-sensitive —
        clinically meant for outpatient treatment, not ED).
        pain_duration = 100% "days" but symptom is acute-onset
        infection needing same-day exam; temp ~37.8-37.9°C and
        WBC ~11.4-11.6 are mildly elevated but uniform across
        sub-locations (skin/pelvis/abdomen) — no signal to
        differentiate telehealth-suitability from UC-necessity
        in this dataset, so default to UC (physical exam needed
        for infection source assessment).
PRIORITY: 10
EVIDENCE: DOCUMENT-SUPPORTED
NOTE: pain_location (skin_soft_tissue / pelvis / abdomen) is carried
      forward as a specialist-candidate tag for cases where the UC
      visit results in a referral — see Section 3.
```

### RULE CT-003 — chronic_disease_flareup → PCP (+ review flag)
```
IF primary_symptom_category == chronic_disease_flareup
THEN care_type = PCP
     specialist_review_candidate = true
     named_specialty = null   <-- see Section 5 for why
REASON: 98.9% PQE02_ChronicACSC (chronic ambulatory-care-sensitive
        condition -- textbook PCP management). 59% stable/"same"
        trend, moderate pain (mean 3.5-3.7/10). PCP is both the
        clinically correct first stop for chronic flare
        management AND the only destination this dataset can
        safely support, since no body-system signal exists to
        name a specialty (Section 5).
PRIORITY: 10
EVIDENCE: DOCUMENT-SUPPORTED
```

### RULE CT-004 — back_pain → PCP (primary), Orthopedics candidate (recurrent)
```
IF primary_symptom_category == back_pain
THEN care_type = PCP
     specialist_candidate = ORTHOPEDICS if ed_visits_past_year >= 2
                              OR chronic_condition_count >= 2
                             else null
REASON: 99.0% PQE05_BackPain. duration/trend split (days vs hours,
        same vs improving) does NOT correlate with chronic_condition_
        count (1.05 vs 1.06 — no signal), so duration/trend cannot be
        used to separate PCP-manageable vs specialist-needed back pain
        in this dataset. Falls back to standard clinical practice:
        most acute low back pain is PCP-first; recurrence/complexity
        (utilization + comorbidity count) is the only available proxy
        for escalation.
PRIORITY: 10
EVIDENCE: PARTIALLY DOCUMENT-SUPPORTED — the ed_visits/comorbidity
          escalation threshold is a RECOMMENDED RULE REQUIRING
          CLINICAL VALIDATION, not derived from an observed
          discriminative pattern (none existed in the data).
```

### RULE CT-005 — mild_breathing_difficulty → PCP / Specialist(Pulmonology) candidate
```
IF primary_symptom_category == mild_breathing_difficulty
THEN care_type = PCP
     specialist_candidate = PULMONOLOGY if copd_asthma_flag == 1
                              AND (ed_visits_past_year >= 2
                                   OR admissions_past_year >= 1)
                             else null
REASON: 98.3% PQE04_Asthma. copd_asthma_flag present in 85% of this
        category (vs 27% population baseline) — strong specialty
        signal. SpO2 (~95.6-95.7%) and respiratory rate (~19.3-19.4)
        are statistically identical regardless of copd_asthma_flag,
        so vitals don't add discrimination here; the flag itself plus
        recurrence is the workable escalation signal.
PRIORITY: 10
EVIDENCE: DOCUMENT-SUPPORTED (copd_asthma_flag correlation);
          escalation threshold (>=2 ED visits) is RECOMMENDED —
          REQUIRES CLINICAL VALIDATION.
```

### RULE CT-006 — dental_pain → DENTAL_CARE
See Section 4.

---

## 1a. Honest Status: TELEHEALTH Is Not a Data-Derived Destination

Unlike PCP / URGENT_CARE / SPECIALIST, **TELEHEALTH has no dedicated column or clean mapping
in this dataset.** There is no `patient_preference`, `modality`, `telehealth_suitable`, or
equivalent field among the 57 columns. `pqe_category` doesn't split by delivery mode either.

What exists instead is `TC-001` above: a proxy heuristic (low pain + stable/improving trend)
applied only within `mild_general_symptom`, covering 68% of that category. This is the
**only** telehealth signal the data can support, and it is explicitly a **modifier on PCP**
(`delivery_mode_candidate`), not a standalone `care_type = TELEHEALTH` destination rule with
independent evidence.

**What this means for your team:**
- Do not treat TELEHEALTH as "done" alongside the other three destinations — it isn't, and
  claiming otherwise would misrepresent what this dataset can support.
- Two real paths forward: (a) add a `patient_preference` / `modality_suitability` field to the
  intake schema so this can be data-driven like the others, or (b) accept `TC-001` as a
  clinically-reviewed proxy rule for the one category it applies to, and leave TELEHEALTH
  unavailable (in-person only) for every other category until better signal exists.
- I did **not** originally apply the same TC-001 logic to `chronic_disease_flareup` or
  `mild_breathing_difficulty` even though their low-severity+stable rates are 19.7% and 81.8%
  respectively — flareup follow-ups and breathing complaints plausibly need a physical
  exam/auscultation that pain-level and trend alone don't capture, and deciding that is a
  clinical call, not an engineering one.

**UPDATE — extended to back_pain and mild_breathing_difficulty (see `rules/care_destination_rules.yaml`
`TELE-004-BACKPAIN`, `TELE-005-BREATHING`):** on request, the same low-pain (≤3)/stable-or-improving
proxy heuristic was added for these two categories, following the exact TC-001/TELE-003 pattern —
**as proposed candidate rules, not as validated ones.** Both are tagged
`RECOMMENDED_REQUIRES_VALIDATION` in the rule file, same tier as `TELE-001-FLAREUP` and
`TELE-002-INFECTION`, not `DOCUMENT_SUPPORTED` like `TELE-003-GENERAL`. Two caveats specific to
each, beyond the usual threshold-needs-validation note:
- **back_pain**: this doc already established (RULE CT-004 above) that duration/trend has *no*
  measured correlation with chronic_condition_count for this category — so `TELE-004-BACKPAIN`
  is an engineering extrapolation of the general pattern, not a dataset-confirmed one, more so
  than TELE-001/002/003 were.
- **mild_breathing_difficulty**: this is the case the caution above was specifically written
  about — breathing complaints conventionally need auscultation/SpO2 to assess, not just a pain
  score. `TELE-005-BREATHING` is scoped to `pain_duration=days` only (never competes with the
  hours/acute UC rule) and sits below the Pulmonology escalation, but the clinical reviewer
  should sign off separately on (a) the pain≤3 threshold and (b) whether pain is an acceptable
  severity proxy for breathing complaints *at all* — those are two different questions.

Recommend these two new rules stay disabled (or routed to a human-review queue) until a
clinician has reviewed both, exactly as already planned for `TELE-001-FLAREUP` /
`TELE-002-INFECTION`.

## 2. Conflict Resolution / Priority

```
SAFETY-000 (red flag)         >  all other rules   [ESCALATE_TO_ED]
CT-006 (dental -> SPECIALIST) >  everything else   [category is exclusive]
CT-002 (UC / infection)       >  CT-003/004/005    [acute > chronic/routine]
CT-001, CT-003, CT-004, CT-005 (PCP variants)      [category-exclusive, no overlap in this dataset]
```

Because `primary_symptom_category` is single-valued per patient in this dataset, there is currently **no observed multi-category conflict** (e.g., a patient who is simultaneously `back_pain` and `chest_pain`). The rule engine should still be built to handle multi-symptom input defensively — treat it as **RECOMMENDED, REQUIRES CLINICAL VALIDATION**: when multiple symptom categories are reported, take the highest-priority category using clinical acuity ordering (infection/acute > chronic flare > routine > dental), not first-in-list.

**Availability vs. clinical destination:** per the original design doc, provider unavailability must never silently change `care_type`. If no PCP slot exists, offer telehealth-PCP or a later date — never re-route to UC to fill the gap.

---

## 3. Specialist Candidate Tagging (from UC/infection track)

`minor_infection` doesn't route to Specialist directly in V1 (it's UC-first), but `pain_location` gives a real, evidence-based specialty tag for **if/when a UC visit results in a referral**:

| `pain_location` | n | Candidate specialty if referred | Evidence |
|---|---|---|---|
| skin_soft_tissue | 923 | Dermatology / Wound Care | pain_location is 100% consistent within this bucket |
| pelvis | 893 | Urology (male) / Gynecology (female) — split on `gender` | pain_location is 100% consistent within this bucket |
| abdomen | 867 | Gastroenterology | pain_location is 100% consistent within this bucket |

Temperature (~37.8–37.9°C) and WBC (~11.4–11.6) are uniform across all three buckets — they signal "infection present," not which specialty, so they aren't used as a splitter here.

---

## 4. Gap Resolution: dental_pain → SPECIALIST (specialty = DENTISTRY)

**Revised decision:** dental_pain routes to `SPECIALIST` with `specialty = DENTISTRY`, keeping the
architecture at 4 destinations rather than introducing a 5th. Practically this means the
Specialty Router must accept `DENTISTRY` as a valid specialty value, and downstream Provider
Discovery must be able to filter/search a dental provider network the same way it filters a
medical one.

**Carried-forward caveat (worth flagging to the team, not a blocker):** dental provider
networks are frequently contracted, credentialed, and adjudicated separately from medical
specialist networks in US care-navigation systems (separate NPI taxonomy codes, separate
payer contracts, sometimes a completely separate provider directory/API). If your Provider
Discovery service is built against a single medical-provider data source, `DENTISTRY` may need
its own connector even though it's modeled as just another specialty in the routing layer.
That's a Provider Discovery implementation detail, not a routing-rule problem, so it doesn't
block this decision — just don't assume "specialty" implies "same provider search backend"
everywhere downstream.

### RULE CT-006 — dental_pain → SPECIALIST (DENTISTRY)
```
IF primary_symptom_category == dental_pain
   AND any(flag_*) == false
THEN care_type = SPECIALIST
     specialty = DENTISTRY
     urgency = ROUTINE if pain_level_self_reported < 7
               else PRIORITY  (worsening trend + high pain -> sooner slot)
REASON: 99.9% PQE01_Dental. pain_location = 100% jaw_tooth,
        pain_duration = 100% days. Pain is meaningful (median 5.9/10,
        never below 3/10) but non-emergent absent red flags.
PRIORITY: 20 (evaluated before the 6 core PCP/UC/Specialist rules —
             dental is a distinct category, must not be caught by
             general symptom rules)
EVIDENCE: DOCUMENT-SUPPORTED
```

### RULE CT-006b — dental_pain escalation
```
IF primary_symptom_category == dental_pain
   AND any(flag_severe_dehydration, flag_uncontrolled_bleeding,
           flag_chest_pain_sweating_nausea, flag_shortness_of_breath,
           flag_severe_allergic_reaction, flag_high_fever_stiff_neck_rash)
THEN care_type = ESCALATE_TO_ED  (or same-day Oral & Maxillofacial
                                   Surgery / urgent DENTISTRY slot if
                                   that pathway exists in the provider
                                   network)
REASON: 9.7% of all dental_pain rows (158/1,633, population-wide —
        not just the avoidable_ed=1 subset) carry a red flag,
        consistent with a dental abscess with systemic infection
        signs (facial cellulitis + fever, uncontrolled post-
        extraction bleeding, etc.) — a genuine escalation, not a
        routine toothache.
PRIORITY: 5 (runs before CT-006; effectively an extension of
             SAFETY-000 scoped to dental presentations)
EVIDENCE: DOCUMENT-SUPPORTED
```

---

## 5. Gap Resolution: `chronic_disease_flareup` has no body-system signal

**Confirmed empirically, not assumed.** Within `chronic_disease_flareup`, isolating the 116 patients who have **exactly one** chronic-disease flag set (removing multimorbidity noise), `pain_location` was `generalized` and `pain_character` was `dull` for **100% of every single-flag subgroup** — diabetes, hypertension, cardiac, COPD/asthma, CKD, cancer, and immunocompromised patients are indistinguishable on every available symptom feature. This is a data-generation gap, not a rule-design failure — no rule can recover a signal that was never encoded.

**Decision:** Route to PCP with a `specialist_review_candidate = true` flag and no named specialty (Rule CT-003 above). This is the only option that doesn't fabricate clinical certainty.

**Documented but NOT implemented in V1 — requires clinical validation:**
```
RULE SPEC-FLAREUP-FALLBACK (do not activate without clinical sign-off)

IF specialist_review_candidate == true
   AND named_specialty == null
   AND [forced to pick one specialty]
THEN apply priority order across the patient's own TRUE flags:
     cardiac_history_flag       (highest acuity)
     > copd_asthma_flag
     > ckd_flag
     > diabetes_flag
     > immunocompromised_flag
     > cancer_flag
     > hypertension_flag        (lowest, usually asymptomatic-driver)

STATUS: RECOMMENDED — REQUIRES CLINICAL VALIDATION.
This ordering is an engineering guess at acuity, not derived from
outcome data. It should not go live until a clinician confirms both
the ordering and whether guessing a specialty from comorbidity flags
alone (without symptom specificity) is safe at all.
```
**Recommended real fix (preferred over the fallback above):** request one additional feature from the data/clinical team — e.g. `flareup_type` (categorical: cardiac / respiratory / renal / endocrine / other) or free-text chief complaint for this category specifically. This is the honest long-term solution; the fallback above is a stopgap only.

---

## 6. Specialist Rule Matrix (full — includes non-dataset-derived candidates flagged as such)

| Rule ID | Feature Pattern | Specialty | Priority | Evidence |
|---|---|---|---|---|
| CT-006 | `primary_symptom_category=dental_pain` + no red flags | Dentistry | 20 | DOCUMENT-SUPPORTED |
| CT-006b | `primary_symptom_category=dental_pain` + red flag present | Dentistry (urgent) or ED escalation | 5 | DOCUMENT-SUPPORTED |
| SPEC-001 | `primary_symptom_category=minor_infection` + `pain_location=skin_soft_tissue`, on UC referral | Dermatology / Wound Care | 40 | DOCUMENT-SUPPORTED |
| SPEC-002 | `primary_symptom_category=minor_infection` + `pain_location=pelvis` + `gender=male`, on UC referral | Urology | 40 | DOCUMENT-SUPPORTED |
| SPEC-003 | `primary_symptom_category=minor_infection` + `pain_location=pelvis` + `gender=female`, on UC referral | Gynecology | 40 | DOCUMENT-SUPPORTED |
| SPEC-004 | `primary_symptom_category=minor_infection` + `pain_location=abdomen`, on UC referral | Gastroenterology | 40 | DOCUMENT-SUPPORTED |
| SPEC-005 | `primary_symptom_category=mild_breathing_difficulty` + `copd_asthma_flag=1` + (`ed_visits_past_year>=2` OR `admissions_past_year>=1`) | Pulmonology | 30 | DOCUMENT-SUPPORTED (flag correlation) / threshold RECOMMENDED |
| SPEC-006 | `primary_symptom_category=back_pain` + (`ed_visits_past_year>=2` OR `chronic_condition_count>=2`) | Orthopedics | 30 | RECOMMENDED — REQUIRES CLINICAL VALIDATION (no discriminative signal found; fallback heuristic) |
| SPEC-007 | `primary_symptom_category=chronic_disease_flareup` + `cardiac_history_flag=1` (fallback ordering, see Sec. 5) | Cardiology | 50 (lowest confidence tier) | RECOMMENDED — DO NOT ACTIVATE without clinical sign-off |
| SPEC-008 | `primary_symptom_category=chronic_disease_flareup` + `copd_asthma_flag=1` (fallback ordering) | Pulmonology | 50 | RECOMMENDED — DO NOT ACTIVATE |
| SPEC-009 | `primary_symptom_category=chronic_disease_flareup` + `ckd_flag=1` (fallback ordering) | Nephrology | 50 | RECOMMENDED — DO NOT ACTIVATE |
| SPEC-010 | `primary_symptom_category=chronic_disease_flareup` + `diabetes_flag=1` (fallback ordering) | Endocrinology | 50 | RECOMMENDED — DO NOT ACTIVATE |
| SPEC-011 | `primary_symptom_category=chronic_disease_flareup` + `immunocompromised_flag=1` (fallback ordering) | Infectious Disease / Immunology | 50 | RECOMMENDED — DO NOT ACTIVATE |
| SPEC-012 | `primary_symptom_category=chronic_disease_flareup` + `cancer_flag=1` (fallback ordering) | Oncology | 50 | RECOMMENDED — DO NOT ACTIVATE |
| SPEC-013 | `primary_symptom_category=chronic_disease_flareup` + `hypertension_flag=1` only, no other flags | Cardiology (secondary) | 50 | RECOMMENDED — DO NOT ACTIVATE |

**Confidence tiers, not fabricated probabilities** (per original design doc — no invented 97.3%-style numbers):
- **Tier 1 (0.85+)**: CT-006, SPEC-001–004 — direct symptom-location match, uniform within bucket (dental is 99.9% consistent, the cleanest signal in the whole dataset)
- **Tier 2 (0.60–0.85)**: SPEC-005 — flag correlation is strong (85% vs 27% baseline) but threshold unvalidated
- **Tier 3 (below activation threshold)**: SPEC-006 — no real signal, heuristic only
- **Tier 0 (do not activate)**: SPEC-007–013 — fallback-of-last-resort, explicitly gated behind clinical approval

---

## 7. What Still Needs Clinical Validation (consolidated)

1. Back-pain escalation threshold (`ed_visits_past_year >= 2` / `chronic_condition_count >= 2`) — engineering heuristic, no discriminative pattern in data.
2. Pulmonology escalation threshold for `mild_breathing_difficulty` — flag correlation is real, the specific visit-count cutoff is not validated.
3. Whether comorbidity-flag priority ordering (Section 5 fallback) is acceptable at all as a specialty-naming method, or should be blocked entirely pending a `flareup_type` feature.
4. Multi-symptom-category conflict ordering (Section 2) — untestable in this dataset since it's single-category per row; needs either synthetic multi-symptom test cases or real intake data.
5. Dental escalation destination: same-day OMFS vs. ED — needs confirmation of what's actually available in the provider network.
6. **New:** `TELE-004-BACKPAIN` pain≤3/stable-or-improving threshold — extrapolated from the
   TELE-003 pattern into a category (back_pain) where this doc found no discriminative signal
   on duration/trend at all.
7. **New:** `TELE-005-BREATHING` — needs sign-off on both the threshold *and* whether
   self-reported pain is an acceptable proxy for breathing-complaint severity in the first
   place (see Section 1a addendum). This is the least data-grounded telehealth rule in the set.

---

## 8. Summary: Destinations and Population Share

| Destination | Rule(s) | Share of navigator population |
|---|---|---|
| PCP | CT-001, CT-003, CT-004 (default), CT-005 (default) | ~73% (mild_general_symptom + chronic_flareup + back_pain + breathing without specialist trigger) |
| URGENT_CARE | CT-002 | ~22% (minor_infection) |
| SPECIALIST — immediate route (Dentistry) | CT-006, CT-006b | ~12% (dental_pain) |
| SPECIALIST — candidate flag, not immediate route (Dermatology/Urology/Gyn/GI/Pulm/Ortho) | SPEC-001–006 | subset of UC/back_pain/breathing referrals |
| ESCALATE_TO_ED | SAFETY-000, CT-006b | 0.6%+ safety net |

*Note: percentages don't sum to 100 due to specialist-candidate overlap within PCP/UC-routed categories, and dental now counting as an immediate-route Specialist share rather than a separate bucket.*

**STALE — pending re-run.** This table predates `TELE-004-BACKPAIN` / `TELE-005-BREATHING`
(see Section 1a addendum and `RULE_MATRIX_AND_VALIDATION.md`). Once active, some share of the
PCP row (back_pain default) and URGENT_CARE row (breathing default) will move to a TELEHEALTH
row. Re-run `validate_against_data.py` for real numbers rather than estimating here.
