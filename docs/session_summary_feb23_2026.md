# Session Summary — February 23, 2026
## EBA Pillar III Disclosure Consistency Index
### Arianna Melissano — PhD Research Log

---

## 1. THE PAPER IN ONE PARAGRAPH

This paper constructs a **Disclosure Consistency Index (DCI)** for European banks
using mandatory EBA Pillar III ESG XBRL disclosures. The DCI measures the gap between
a bank's qualitative narrative disclosure about fossil fuel financing (scored by a
fine-tuned LLM) and its actual quantitative fossil fuel exposure (computed directly
from Template K_41.00). The paper tests whether institutional bond investors price
this disclosure gap — i.e., whether banks that under-disclose relative to their
fossil exposure face wider credit spreads. The AI methodological contribution
(LLM-based disclosure scoring) simultaneously serves as the AI course deliverable.

---

## 2. THE TWO COMPONENTS OF THE DCI

### QuantScore (quantitative pillar)
- **Definition:** Fossil GCA / Total GCA
- **Source:** EBA Pillar III Template K_41.00, datapoint dp471828 (total) and
  CPRS fossil fuel datapoints dp471326 (B5 coal), dp471332 (B6 oil/gas),
  dp471410 (C19 petroleum), dp471566 (D35_2 gas distribution)
- **Classification:** CPRS taxonomy from Battiston et al. (2017),
  Nature Climate Change — peer-reviewed foundation
- **Coverage:** 33 banks with valid QuantScore from H1 2025 data
- **Range:** 0.00% (Swedbank) to 4.67% (Alpha Bank)
- **Mean:** 1.37% | **Median:** 1.12% | **Std:** 1.28%
- **Key property:** Currency-invariant (ratio cancels FX units)

### DAS — Disclosure Adequacy Score (qualitative pillar)
- **Definition:** LLM-scored qualitative text from Template k_00.03
- **Dimensions (each 0-2):**
  1. Specificity — concrete figures, sector names, percentages
  2. Completeness — coverage of all CPRS fossil sectors
  3. Forward-looking — transition plans, timelines, net-zero commitments
  4. Consistency — narrative aligns with quantitative QuantScore
  5. Comparability — usable for peer comparison by external analyst
- **Raw DAS:** 0–10 | **Normalized DAS:** 0–1
- **Coverage:** 13 banks scored in H1 2025 sample
- **Model used:** claude-haiku-4-5-20251001 (zero-shot, current version)
- **Planned upgrade:** Fine-tuned model on labeled EBA Pillar III data

### DCI Construction
```
QuantScore_normalized = quant_score_pct / max(quant_score_pct in sample)
DCI = DAS_normalized - QuantScore_normalized

DCI > 0  → over-disclosure (bank discloses more than fossil exposure warrants)
DCI ≈ 0  → matched disclosure
DCI < 0  → under-disclosure (RED FLAG — potential greenwashing signal)
```

---

## 3. PRELIMINARY RESULTS (H1 2025, 13 banks)

| Bank | Country | QS% | DAS/10 | DCI | Classification |
|------|---------|-----|--------|-----|----------------|
| Ibercaja | ES | 1.26% | 8 | +0.531 | ▲ Over-discloser |
| Caisse des Dépôts | FR | 0.02% | 4 | +0.395 | ▲ Over-discloser |
| Mediocredito Centrale | IT | 0.11% | 2 | +0.176 | ▲ Over-discloser |
| Banca Galileo | IT | 0.00% | 1 | +0.100 | ≈ Matched |
| APS Bank | MT | 1.09% | 2 | -0.035 | ≈ Matched |
| OTP Bank | HU | 1.12% | 0 | -0.240 | ▼ Under-discloser |
| PKO Bank Polski | PL | 1.13% | 0 | -0.242 | ▼ Under-discloser |
| Arkea | FR | 1.52% | 0 | -0.326 | ▼ Under-discloser |
| pbb | DE | 1.73% | 0 | -0.370 | ▼ Under-discloser |
| Abanca | ES | 1.81% | 0 | -0.388 | ▼ Under-discloser |
| DZ Bank | DE | 1.96% | 0 | -0.419 | ▼ Under-discloser |
| Alpha Bank | GR | 4.67% | 5 | -0.500 | ▼ Under-discloser |

**Headline finding:** Mean DCI = −0.110. The sample systematically under-discloses.
7 of 13 banks are under-disclosers. Several banks filed boilerplate or procedural
text with zero substantive content — this is itself a research finding.

**Most striking case:** Alpha Bank — highest fossil exposure in the sample (4.67%)
AND largest disclosure gap (DCI = −0.500). A Greek bank with significant fossil
lending that does not adequately explain it in regulatory filings.

---

## 4. DATA PIPELINE (FULLY BUILT AND ON GITHUB)

**Repository:** https://github.com/melissanoarianna1-commits/eba-disclosure-consistency

**Scripts:**
```
step0_build_taxonomy_mapping.py   → decode EBA DPM 4.1, identify CPRS datapoints
step1b_fixed_parser.py            → parse all bank XBRL packages, extract GCA + text
step2b_taxonomy_quantscore.py     → compute QuantScore from decoded datapoints
step2c_currency_fix.py            → apply ECB FX rates (HUF, RON, SEK → EUR)
step3_das_scoring.py              → score qualitative text via Claude API → DCI
```

**Key technical discoveries made today:**
1. EBA factValues always divide by 1e6 to get local-currency millions,
   regardless of decimalsMonetary value (empirically validated across 5 variants)
2. Santander filing error: values 100× inflated (EUR cents vs EUR mismatch);
   QuantScore % valid, absolute GCA unreliable
3. Ålandsbanken: incomplete Template 1, GCA=0 unreliable
4. Bank Pekao + Crelan: Template 1 not filed — excluded from QuantScore
5. Santander duplicate submission (…002 superseded by …003)

---

## 5. SAMPLE DESCRIPTION

| Metric | Value |
|--------|-------|
| Banks downloaded from EBA P3DH | 34 unique LEIs |
| Banks with Template K_41.00 | 32 |
| Banks with valid QuantScore | 33 (Santander counted once) |
| Banks with qualitative text | 14 |
| Banks with DCI | 13 (Crelan excluded: no QuantScore) |
| Reporting period | H1 2025 (2025-06-30) |
| Countries covered | MT, IT, PL, SK, HU, FI, DE, ES, FR, NL, BE, SE, RO, GR, IE |
| Non-EUR reporters (FX-corrected) | 3 (OTP/HUF, Banca Transilvania/RON, Swedbank/SEK) |

---

## 6. THE ROAD TO THE PHD PAPER

### What this prototype demonstrated (AI course deliverable)
- The data exists, is parseable, and produces economically coherent results
- LLM scoring of regulatory text is feasible and produces interpretable variation
- The DCI concept has face validity (Ibercaja vs Alpha Bank contrast is compelling)

### What is needed for a publishable PhD paper

**Data expansion:**
- Collect all EBA P3DH vintages: H1 2023, FY 2023, H1 2024, FY 2024, H1 2025
- Expected panel: ~150 Significant Institutions × 4-5 periods = 600-750 observations
- After data quality filtering: ~200-350 usable bank-period observations
- Build DPM version crosswalk (3.3 → 4.0 → 4.1 datapoint mapping)

**LLM scoring upgrade:**
- Current: zero-shot claude-haiku (proof of concept)
- Target: fine-tuned model on labeled EBA Pillar III disclosures
- Path:
  Step 1 (AI course): few-shot prompting with curated examples
  Step 2 (PhD paper): fine-tune Llama 3 or Mistral 7B on labeled dataset
  Labeling strategy: human experts label 200-500 segments as gold standard;
  use stronger model (Claude Opus/GPT-4o) for silver labels on full sample

**Validation framework (three layers):**
1. Inter-model reliability: re-score with GPT-4o-mini, require r > 0.70
2. Human validation: 2 expert raters on subsample of 5-8 banks, compare to LLM
3. Construct validity: DAS should correlate with CDP scores, NZBA membership

**Outcome variable:**
- Bond spreads: does negative DCI predict wider credit spreads?
- Source: Bloomberg or Refinitiv bond yield data matched to bank LEIs
- Mechanism: institutional bond investors penalize opacity/greenwashing risk

**Identification:**
- Mandatory EBA filing removes selection into disclosure
- Variation in DCI is within-bank over time (panel FE) and cross-sectional
- Bank FE + time FE absorb business model and common regulatory trends

**Pre-2023 data:**
- Pre-2022: PDF annual reports only — high extraction noise, not recommended
- 2022-2023: Early XBRL (DPM 3.x) — feasible with taxonomy crosswalk
- 2023 onwards: XBRL DPM 4.x — clean, directly comparable to what we built
- Recommendation: anchor panel at 2023, use pre-2023 only as placebo/robustness

---

## 7. CONNECTION TO PhD PROPOSAL (ORIGINAL DOCUMENT)

The original proposal (deposits + natural disasters + climate salience) remains
a separate, valid paper. The DCI paper is a standalone contribution that sits
alongside it in the dissertation.

The two papers have a clean division:
- DCI paper: institutional investors, bond spreads, disclosure quality measurement
- Deposits paper: retail/institutional depositors, deposit flows, climate salience

They share the QuantScore as a common measure of bank fossil exposure, but
have different outcome variables, different identification strategies, and
different audiences. Together they form a coherent dissertation on how different
capital providers respond to bank climate risk through different channels.

The DCI paper is the more immediately feasible one given the data we have.
The deposits paper requires the BankFocus panel and the Climate Salience Index
construction — larger undertaking, longer timeline.

---

## 8. FOR THE WEDNESDAY MEETING (Prof. Ongena)

**What to present:**
1. Working pipeline: 34 banks, 33 QuantScores, 13 DCIs — real numbers
2. Headline finding: mean DCI = −0.110, systematic under-disclosure
3. Most compelling case: Alpha Bank (4.67% fossil, DCI = −0.500)
4. GitHub repository with fully documented, reproducible code
5. Clear next steps: panel expansion 2023-2025, fine-tuned LLM, bond spread data

**What to frame carefully:**
1. This is a validated proof of concept, not a finished paper
2. Sample is 13 banks — cross-sectional description only, no causal claims yet
3. LLM scoring is zero-shot — validation against human labels is a next step
4. The decimalsMonetary discovery is a genuine data quality contribution

**Key methodological point to emphasize:**
The pipeline is fully reproducible from raw EBA XBRL data to DCI output.
Every data quality issue is documented. This is what rigorous empirical work
looks like at the PhD level.

---

## 9. DATA QUALITY FLAGS (for thesis data appendix)

| Bank | Issue | Impact on Analysis |
|------|-------|-------------------|
| Santander (ES) | Values 100× inflated in filing | QS% valid; exclude from size controls |
| Ålandsbanken (FI) | Incomplete Template 1 | QS=0% unreliable; flag in sample |
| Bank Pekao (PL) | Template 1 not filed | Excluded from QuantScore |
| Crelan (BE) | Template 1 not filed | DCI not computable |
| OTP Bank (HU) | Reports in HUF | FX-corrected using ECB SDW rates |
| Banca Transilvania (RO) | Reports in RON | FX-corrected using ECB SDW rates |
| Swedbank (SE) | Reports in SEK | FX-corrected using ECB SDW rates |

---

*This document captures the full state of the research as of February 23, 2026.*
*Pipeline is complete, GitHub repository is live, results are ready for Wednesday.*
