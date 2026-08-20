# ED Avoidable Model - Quick Integration Summary

## 🎯 Goal
Integrate the ED Avoidable ML model into the existing chatbot flow to predict whether an emergency department visit is necessary after safety screening.

---

## 📊 Current vs Required Data

### What We Have:
| Source | Fields | Count |
|--------|--------|-------|
| **Chatbot Intake** | chief_complaint, symptom_onset, pain_scale, location | 4 |
| **Safety Screening** | 10 YES/NO red flag questions | 10 |
| **EHR Database** | Demographics, vitals, labs, medications, chronic conditions, utilization history | 50+ |
| **Total Available** | | **64+** |

### What ML Model Needs:
| Category | Fields Needed | Count |
|----------|---------------|-------|
| **Symptom Details** | primary_symptom_category, pain_level, onset, duration, location, character, radiating, trend | 9 |
| **Red Flags** | 10 emergency indicators | 10 |
| **Vital Signs** | BP, HR, RR, temp, SpO2, pain_score | 7 |
| **Lab Values** | WBC, Hgb, platelets, sodium, potassium, creatinine, glucose, troponin, BNP, lactate, INR | 13 |
| **Chronic Conditions** | Diabetes, HTN, cardiac, COPD, CKD, cancer, immunocompromised flags | 9 |
| **Comorbidity Scores** | Condition count, Charlson index | 2 |
| **Medications** | Count, anticoagulants, insulin flags | 4 |
| **Utilization History** | Days since last ED, ED visits, admissions, has PCP | 5 |
| **Demographics** | Age, gender | 3 |
| **Total Required** | | **95** |

---

## 🚨 Critical Gaps

### 1. Missing Intake Questions (Need to Add)
Currently collecting 4 fields, need **4 more**:
- ❌ `pain_duration` - "How long have you had these symptoms?"
- ❌ `pain_character` - "Sharp, dull, throbbing, burning, cramping, or pressure?"
- ❌ `pain_radiating` - "Does the pain spread to other areas?"
- ❌ `symptom_trend` - "Are symptoms getting better, worse, or staying the same?"

**Action**: Extend chatbot to ask **8 questions total** (currently 4)

### 2. Missing Red Flag Questions (Need to Add)
Currently have 10 flags, ML model expects 2 more:
- ❌ `flag_vomiting_blood_or_blood_in_stool`
- ❌ `flag_severe_dehydration`

**Action**: Add to safety screening (**12 questions total** instead of 10)

### 3. EHR Field Name Mismatches
| ML Model Expects | EHR Has | Solution |
|------------------|---------|----------|
| `wbc` | `wbc_count` | Map in code |
| `ed_visits_past_year` | `previous_er_visits_12m` | Map in code |
| `admissions_past_year` | `previous_admissions_12m` | Map in code |
| `pain_score_clinical` | ❌ Missing | Add to EHR OR use defaults |
| `has_pcp_flag` | ❌ Missing | Add to EHR OR use defaults |

### 4. New Patients Without EHR
What if patient has no existing EHR record?

**Solution**: Use population defaults (normal vital signs, no chronic conditions, etc.)

---

## 🔧 Technical Implementation

### New Files to Create:

1. **`app/services/ed_feature_mapper.py`**
   - Maps Intake + Safety + EHR → 95 ML features
   - Handles missing data with defaults
   - Classifies symptom categories

2. **`app/services/ed_prediction_service.py`**
   - Loads `best_avoidable_ed_model.pkl`
   - Makes predictions
   - Returns YES/NO + probability + confidence

3. **API Endpoint**: `POST /api/v1/patient/ed-prediction`
   - Input: intake_data, safety_flags, patient_mrn (optional)
   - Output: avoidable_ed (YES/NO), probability, confidence, recommendation

### Files to Modify:

1. **`app/services/vocabulary.py`**
   - Add 4 new questions to `QUESTION_TEMPLATES`
   - Update `REQUIRED_FIELD_ORDER`

2. **`chatbot_ui.py`**
   - Add 2 new red flag questions in safety screening
   - Call `/patient/ed-prediction` after safety verdict = NO
   - Display ED avoidable result with recommendation

3. **`app/api/v1/endpoints/patient.py`**
   - Add new ED prediction endpoint

4. **`app/models/ehr.py`** (Optional)
   - Add `pain_score_clinical` field
   - Add `has_pcp_flag` field

---

## 🔄 Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER ENTERS CHATBOT                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: INTAKE (8 Questions)                                   │
│  ✓ Chief complaint                                               │
│  ✓ Symptom onset                                                 │
│  ✓ Pain scale                                                    │
│  ✓ Location                                                      │
│  ✓ Pain duration          ← NEW                                 │
│  ✓ Pain character         ← NEW                                 │
│  ✓ Pain radiating         ← NEW                                 │
│  ✓ Symptom trend          ← NEW                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: SAFETY SCREENING (12 Red Flags)                       │
│  ✓ Chest pain                                                    │
│  ✓ Difficulty breathing                                          │
│  ✓ Altered consciousness                                         │
│  ✓ Severe bleeding                                               │
│  ✓ Stroke symptoms                                               │
│  ✓ Suicidal ideation                                             │
│  ✓ Anaphylaxis                                                   │
│  ✓ High fever                                                    │
│  ✓ Unable to walk                                                │
│  ✓ Severe abdominal pain                                         │
│  ✓ Vomiting blood        ← NEW                                  │
│  ✓ Severe dehydration    ← NEW                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │  Safety Result  │
                    └─────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
    ┌──────────────────┐          ┌──────────────────┐
    │   YES - EMERGENCY │          │  NO - NOT        │
    │                   │          │  EMERGENCY       │
    └──────────────────┘          └──────────────────┘
              ↓                               ↓
    ┌──────────────────┐          ┌──────────────────┐
    │ GO TO EMERGENCY  │          │  CALL ED AVOIDABLE│
    │ ROOM IMMEDIATELY │          │  ML MODEL        │
    │                  │          │                  │
    │ END FLOW         │          └──────────────────┘
    └──────────────────┘                      ↓
                                  ┌──────────────────────────┐
                                  │ EDFeatureMapper          │
                                  │ - Map intake data        │
                                  │ - Map safety flags       │
                                  │ - Fetch EHR (if exists)  │
                                  │ - Apply defaults         │
                                  │ → 95 features            │
                                  └──────────────────────────┘
                                              ↓
                                  ┌──────────────────────────┐
                                  │ EDPredictionService      │
                                  │ - Load ML model          │
                                  │ - Apply encoders         │
                                  │ - Make prediction        │
                                  │ → YES or NO + confidence │
                                  └──────────────────────────┘
                                              ↓
                              ┌───────────────┴───────────────┐
                              ↓                               ↓
                    ┌──────────────────┐          ┌──────────────────┐
                    │ ED AVOIDABLE:    │          │ ED AVOIDABLE:    │
                    │ YES              │          │ NO               │
                    └──────────────────┘          └──────────────────┘
                              ↓                               ↓
                    ┌──────────────────┐          ┌──────────────────┐
                    │ Recommend:       │          │ Recommend:       │
                    │ - Telemedicine   │          │ - Go to ED       │
                    │ - Urgent Care    │          │ - Get evaluation │
                    │ - PCP Follow-up  │          │                  │
                    └──────────────────┘          └──────────────────┘
```

---

## 📋 Quick Start Checklist

### Before Implementation - Answer These:

1. ✅ **Extend intake to 8 questions?** (adds 4 symptom detail questions)
   - [ ] YES - More comprehensive
   - [ ] NO - Keep at 4 questions

2. ✅ **Add 2 more red flag questions?** (vomiting blood, dehydration)
   - [ ] YES - Add to screening
   - [ ] NO - Use defaults (False)

3. ✅ **Add new EHR fields?** (pain_score_clinical, has_pcp_flag)
   - [ ] YES - Update schema
   - [ ] NO - Use defaults

4. ✅ **Handle patients without EHR?**
   - [ ] Use population defaults (recommended)
   - [ ] Require EHR creation first
   - [ ] Collect basic info during intake

5. ✅ **Where to place model file?**
   - [ ] Keep in ML_Complete_Package/
   - [ ] Move to app/ml_models/
   - [ ] Use absolute path

6. ✅ **How to display results?**
   - [ ] Show both safety + ED results separately
   - [ ] Combine into single recommendation
   - [ ] Other

---

## 🚀 Implementation Order

1. **Phase 1**: Extend data collection (intake + safety screening)
2. **Phase 2**: Create feature mapper service
3. **Phase 3**: Create prediction service  
4. **Phase 4**: Add API endpoint
5. **Phase 5**: Update chatbot UI
6. **Phase 6**: Test end-to-end
7. **Phase 7**: Deploy

**Estimated Time**: 16-20 hours total

---

## 📞 Your Input Needed

Please review the **6 questions in the checklist** above and let me know your preferences. I'll then:

1. Implement the code according to your answers
2. Create test scripts
3. Update documentation
4. Provide deployment guide

---

**Status**: 🟡 Awaiting your input on the 6 questions above  
**Priority**: 🔴 High  
**Created**: January 2027
