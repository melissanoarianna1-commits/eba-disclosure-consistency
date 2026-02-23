"""
STEP 2b: Taxonomy-Based QuantScore Calculator
=============================================
Uses the decoded EBA DPM 4.1 mapping to compute exact CPRS fossil fuel
exposure shares directly from Template 1 (k_41.00) datapoints.

This is the rigorous PhD-grade QuantScore, validated against the
text-based proxy from step2.

CPRS Fossil Fuel Sectors (Battiston et al. 2017, adopted by EBA ITS):
  B5   = NACE 05 - Mining of coal and lignite
  B6   = NACE 06 - Extraction of crude petroleum and natural gas
  C19  = NACE 19 - Manufacture of coke and refined petroleum products
  D35_2= NACE 35.2 - Manufacture/distribution of gaseous fuels
  G46_71 = NACE 46.71 - Wholesale of solid/liquid/gaseous fuels
  G47_3  = NACE 47.3 - Retail sale of automotive fuel
  H49_5  = NACE 49.5 - Transport via pipeline

Usage:
  python step2b_taxonomy_quantscore.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
PAPER1 = Path("/Users/ariannamelissano/Desktop/Paper1")
MAPPING_FILE  = PAPER1 / "output" / "dp_mapping_k41.csv"
T1_RAW_FILE   = PAPER1 / "output" / "master_t1_raw.csv"
BANKS_FILE    = PAPER1 / "output" / "master_banks.csv"
OUTPUT_FILE   = PAPER1 / "output" / "quantscore_taxonomy.csv"

# ── CPRS fossil NAC codes ──────────────────────────────────────────────────────
CPRS_NAC = {"B5", "B6", "C19", "D35_2", "G46_71", "G47_3", "H49_5"}

def main():
    # 1. Load taxonomy mapping
    mapping = pd.read_csv(MAPPING_FILE)
    print(f"Mapping loaded: {len(mapping)} datapoints")

    # 2. Identify the key datapoints we need
    #    - c0010 = Gross Carrying Amount (our primary measure)
    #    - Grand total row (r0560, no NAC code)
    #    - CPRS fossil rows (c0010 only)

    fossil_dps = mapping[
        (mapping["is_cprs_fossil"] == True) &
        (mapping["col_code"] == "c0010")
    ][["datapoint", "nac_code", "nac_label"]].copy()

    total_dps = mapping[
        (mapping["is_grand_total"] == True) &
        (mapping["col_code"] == "c0010")
    ][["datapoint"]].copy()

    print(f"\nCPRS fossil datapoints (c0010): {len(fossil_dps)}")
    for _, r in fossil_dps.iterrows():
        print(f"  {r['datapoint']} | {r['nac_code']} | {r['nac_label']}")

    print(f"\nGrand total datapoints: {len(total_dps)}")
    print(f"  {total_dps['datapoint'].tolist()}")

    # 3. Load raw Template 1 data (wide format: one row per bank, one col per dp)
    t1 = pd.read_csv(T1_RAW_FILE)
    banks = pd.read_csv(BANKS_FILE)

    print(f"\nTemplate 1 data: {len(t1)} banks × {len(t1.columns)} columns")

    # 4. Extract fossil and total columns
    fossil_cols = [dp for dp in fossil_dps["datapoint"].tolist() if dp in t1.columns]
    total_col   = total_dps["datapoint"].tolist()[0] if len(total_dps) > 0 else None

    print(f"\nFossil columns found in data: {len(fossil_cols)} / {len(fossil_dps)}")
    missing = set(fossil_dps["datapoint"]) - set(fossil_cols)
    if missing:
        print(f"  Missing (no data for any bank): {missing}")

    if not total_col or total_col not in t1.columns:
        print("WARNING: Grand total column not found, using max value fallback")
        total_col = None

    # 5. Compute QuantScore per bank
    results = []

    # Get LEI from first column or from banks file
    lei_col = "lei" if "lei" in t1.columns else t1.columns[0]

    for _, row in t1.iterrows():
        lei = str(row.get(lei_col, "unknown"))

        # Sum CPRS fossil sectors
        fossil_vals = []
        fossil_breakdown = {}
        for dp in fossil_cols:
            val = row.get(dp, np.nan)
            if pd.notna(val) and val > 0:
                fossil_vals.append(val)
                # Get NAC label for this dp
                nac = fossil_dps[fossil_dps["datapoint"] == dp]["nac_code"].values[0]
                fossil_breakdown[nac] = val

        fossil_total = sum(fossil_vals) if fossil_vals else np.nan

        # Get grand total GCA
        if total_col:
            grand_total = row.get(total_col, np.nan)
        else:
            # Fallback: use GCA from master_banks
            bank_row = banks[banks["lei"].astype(str).str.startswith(lei[:15])]
            grand_total = bank_row["total_gca_eur"].values[0] if len(bank_row) > 0 else np.nan

        # Compute QuantScore
        if pd.notna(fossil_total) and pd.notna(grand_total) and grand_total > 0:
            quant_score = fossil_total / grand_total
            coverage = "full"
        elif pd.notna(grand_total) and grand_total > 0:
            # No fossil data found = assume 0 (bank has no CPRS exposures)
            quant_score = 0.0
            fossil_total = 0.0
            coverage = "zero_fossil"
        else:
            quant_score = np.nan
            coverage = "no_data"

        # Get bank metadata
        bank_meta = banks[banks["lei"].astype(str).str.startswith(lei[:15])]
        country = bank_meta["country"].values[0] if len(bank_meta) > 0 and "country" in bank_meta.columns else "unknown"
        ref_period = bank_meta["ref_period"].values[0] if len(bank_meta) > 0 else "unknown"

        results.append({
            "lei":              lei,
            "country":          country,
            "ref_period":       ref_period,
            "grand_total_eur_m": grand_total / 1e6 if pd.notna(grand_total) else np.nan,
            "fossil_total_eur_m": fossil_total / 1e6 if pd.notna(fossil_total) else np.nan,
            "quant_score":      quant_score,
            "quant_score_pct":  quant_score * 100 if pd.notna(quant_score) else np.nan,
            "coverage":         coverage,
            # Breakdown by CPRS sector
            "B5_coal_eur_m":    fossil_breakdown.get("B5", 0) / 1e6,
            "B6_oilgas_eur_m":  fossil_breakdown.get("B6", 0) / 1e6,
            "C19_petrol_eur_m": fossil_breakdown.get("C19", 0) / 1e6,
            "D35_2_gas_eur_m":  fossil_breakdown.get("D35_2", 0) / 1e6,
            "G46_71_wholesale_eur_m": fossil_breakdown.get("G46_71", 0) / 1e6,
            "G47_3_retail_eur_m":    fossil_breakdown.get("G47_3", 0) / 1e6,
            "H49_5_pipeline_eur_m":  fossil_breakdown.get("H49_5", 0) / 1e6,
        })

    df = pd.DataFrame(results)

    # 6. Print results
    print("\n" + "="*70)
    print("TAXONOMY-BASED QUANTSCORE — ALL BANKS")
    print("="*70)
    print(f"{'LEI':<22} {'Country':<8} {'GCA (M EUR)':>12} {'Fossil (M EUR)':>14} {'QuantScore':>10}")
    print("-"*70)

    df_sorted = df.dropna(subset=["quant_score"]).sort_values("quant_score", ascending=False)

    for _, r in df_sorted.iterrows():
        lei_short = str(r["lei"])[:20]
        print(f"{lei_short:<22} {str(r['country']):<8} {r['grand_total_eur_m']:>12.0f} "
              f"{r['fossil_total_eur_m']:>14.1f} {r['quant_score_pct']:>9.2f}%")

    no_data = df[df["coverage"] == "no_data"]
    if len(no_data) > 0:
        print(f"\nBanks with no GCA data (excluded): {len(no_data)}")
        for _, r in no_data.iterrows():
            print(f"  {str(r['lei'])[:20]}")

    # 7. Summary stats
    valid = df[df["quant_score"].notna()]
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Banks with QuantScore:     {len(valid)} / {len(df)}")
    print(f"  Coverage breakdown:")
    print(f"    Full (fossil + total):   {(df['coverage']=='full').sum()}")
    print(f"    Zero fossil:             {(df['coverage']=='zero_fossil').sum()}")
    print(f"    No data:                 {(df['coverage']=='no_data').sum()}")
    print(f"\n  QuantScore distribution (% of GCA in CPRS fossil sectors):")
    print(f"    Min:    {valid['quant_score_pct'].min():.2f}%")
    print(f"    Mean:   {valid['quant_score_pct'].mean():.2f}%")
    print(f"    Median: {valid['quant_score_pct'].median():.2f}%")
    print(f"    Max:    {valid['quant_score_pct'].max():.2f}%")
    print(f"\n  Top 5 brownest banks:")
    for _, r in df_sorted.head(5).iterrows():
        print(f"    {str(r['lei'])[:20]:<22} {r['quant_score_pct']:.2f}%  ({r['grand_total_eur_m']:.0f}M EUR, {r['country']})")

    print(f"\n  Top 5 greenest banks:")
    for _, r in df_sorted.tail(5).iterrows():
        print(f"    {str(r['lei'])[:20]:<22} {r['quant_score_pct']:.2f}%  ({r['grand_total_eur_m']:.0f}M EUR, {r['country']})")

    # 8. Save
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✓ Saved: {OUTPUT_FILE}")
    print(f"\n✅ NEXT STEP: run step3_das_scoring.py (GPT-4 qualitative scoring)")

if __name__ == "__main__":
    main()
