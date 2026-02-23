# Data Quality Notes
## EBA Pillar III Disclosure Consistency Index Project

Last updated: February 2026

---

## Known Issues

### 1. Santander (LEI: K8MS7FD7N5Z2WQ51AZ71, ES)

**Issue:** The `...003` submission (the valid, most recent filing) contains
factValues that are approximately 100× larger than expected given
`decimalsMonetary = -6`.

**Evidence:**  
- dp471828 (grand total GCA) = 2.09 × 10^14  
- With standard /1e6 scaling: 209,161,273M EUR (209 trillion EUR)  
- Santander's actual total assets (2024 annual report): ~1,800,000M EUR  
- Expected filing value: ~2,091,613M EUR  
- Discrepancy factor: exactly 100×  

**Most likely cause:** Values were filed in EUR cents (unit = 0.01 EUR) but
`decimalsMonetary` was not updated from -6 to -8. This is a filing error
in Santander's submission to the EBA P3DH portal.

**Impact on analysis:**
- QuantScore % = **4.23% — VALID** (both numerator and denominator are inflated
  by the same 100× factor, so the ratio cancels correctly)
- Absolute GCA in EUR millions = **UNRELIABLE** (overstated by 100×)

**Recommended treatment:**
- Include Santander in QuantScore ranking with a footnote
- Exclude from any regression using absolute bank size (total_assets, log_gca)
  as a control variable
- Flag in the data appendix of the thesis

---

### 2. Ålandsbanken (LEI: 529900HEKOENJHPNN480, FI)

**Issue:** Template K_41.00 is present but the grand total datapoint (dp471828)
returns 0 or a near-zero value. The bank's qualitative text was also not filed.

**Evidence:**  
- dp471828 factValue ≈ 0 after scaling  
- Known total assets: ~5.5B EUR (Ålandsbanken Abp, Finnish retail bank)  
- Expected GCA: ~3,000–4,000M EUR  

**Most likely cause:** Incomplete Template 1 submission — the bank filed
the XBRL package but did not populate quantitative exposure data. This may
reflect a partial waiver, a late amendment, or a data quality issue at the
EBA P3DH portal.

**Impact:**  
- QuantScore = 0.00% — UNRELIABLE (not genuinely zero fossil exposure)
- Excluded from QuantScore distribution statistics

---

### 3. Bank Pekao (LEI: 259400YLRTOBISHBVX41, PL)

**Issue:** Template K_41.00 file (`k_41.00.csv`) is absent from the XBRL package.

**Evidence:** `FilingIndicators.csv` shows K_41.00 = false (not filed).

**Most likely cause:** Bank elected not to file Template 1 for this reporting
period, or the submission is still pending.

**Impact:** Excluded from QuantScore computation entirely.
Bank Pekao is Poland's second-largest bank (total assets ~€50B). Its absence
is notable — future data collection should check for a later submission.

---

### 4. Crelan (LEI: 549300IQZVZ949N37S44, BE)

**Issue:** Template K_41.00 absent, despite qualitative text being present
(4,974 characters in k_00.03.csv).

**Most likely cause:** Small Belgian cooperative bank; may have received a
partial exemption from quantitative Template 1 requirements, or filed
qualitative text separately from the quantitative data.

**Impact:** Excluded from QuantScore computation. Qualitative text available
for DAS scoring but DCI cannot be computed without QuantScore.

**Interesting research angle:** The presence of qualitative text without
quantitative Template 1 data is itself a disclosure inconsistency worth
flagging in the thesis as a pattern.

---

### 5. Santander Duplicate Submission

**Issue:** Two XBRL packages exist for the same LEI (K8MS7FD7N5Z2WQ51AZ71):
- `...002` submission: all factValues = 0 (empty/superseded filing)
- `...003` submission: contains data (but affected by issue #1 above)

**Treatment:** The `...002` submission is treated as superseded and discarded.
Only the `...003` submission is used in analysis.

---

## decimalsMonetary Variants Observed

| decimalsMonetary | Banks | Notes |
|-----------------|-------|-------|
| -6 | 23 | Most common; standard millions |
| -3 | 8  | Thousands; apply /1e6 scaling (same as -6) |
| 0  | 1  | EUR units; apply /1e6 scaling |
| 2  | 3  | EUR with cent precision; apply /1e6 scaling |
| 4  | 1  | EUR with 0.0001 precision; apply /1e6 scaling |

**Key finding:** Despite five different `decimalsMonetary` values in this sample,
dividing factValue by 1,000,000 yields the correct local-currency millions figure
in all cases. The `decimalsMonetary` attribute indicates reporting precision only,
not storage unit. This is consistent with the XBRL specification but not
immediately obvious from EBA documentation.

---

## Non-EUR Reporters

| Bank | Currency | ECB Rate (2025-06-30) | GCA (M EUR) |
|------|----------|----------------------|-------------|
| OTP Bank (HU) | HUF | 0.002538 | ~11,217M |
| Banca Transilvania (RO) | RON | 0.200803 | ~13,970M |
| Swedbank (SE) | SEK | 0.087108 | ~14,648M |

ECB reference rates sourced from ECB Statistical Data Warehouse (SDW).
For full reproducibility, rates should be pulled programmatically from:
https://data-api.ecb.europa.eu/service/data/EXR/D.{CCY}.EUR.SP00.A
