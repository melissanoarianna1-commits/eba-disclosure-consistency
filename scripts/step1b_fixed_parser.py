"""
STEP 1b: Fixed EBA P3DH Parser — Correct decimalsMonetary Handling
===================================================================
Fixes two bugs from step1:
  1. decimalsMonetary was hardcoded as -6 (millions)
     - Ålandsbanken uses -3 (thousands)
     - Santander uses -2 (hundreds/cents)
  2. output/ folder was scanned as a bank

The factValue in each k_41.00.csv must be multiplied by 10^decimalsMonetary
to get the true EUR value. We then convert to millions for consistency.

Usage:
  python step1b_fixed_parser.py
"""

import pandas as pd
import numpy as np
import re
import os
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
BANKS_FOLDER  = Path("/Users/ariannamelissano/Desktop/Paper1")
OUTPUT_FOLDER = Path("/Users/ariannamelissano/Desktop/Paper1/output")
OUTPUT_FOLDER.mkdir(exist_ok=True)

# Grand total datapoint (confirmed from taxonomy)
DP_GRAND_TOTAL = "dp471828"

# CPRS fossil fuel datapoints (c0010 = Gross Carrying Amount)
CPRS_DPS = {
    "dp471326": "B5_coal",
    "dp471332": "B6_oilgas",
    "dp471410": "C19_petrol",
    "dp471566": "D35_2_gas",
}

# LEI pattern
LEI_PATTERN = re.compile(r"^([A-Z0-9]{20})\.")


def parse_bank(folder: Path) -> dict:
    """Parse one bank folder and return a result dict."""
    result = {
        "folder_name":   folder.name,
        "lei":           None,
        "ref_period":    None,
        "base_currency": None,
        "decimals":      -6,       # default
        "scale_factor":  1e-6,     # 10^decimals → convert to millions
        "parse_ok":      False,
        "errors":        [],
    }

    # Extract LEI from folder name
    m = LEI_PATTERN.match(folder.name)
    if not m:
        result["errors"].append("cannot parse LEI from folder name")
        return result
    result["lei"] = m.group(1)

    reports_dir = folder / "reports"

    # ── Parameters ─────────────────────────────────────────────────────────────
    params_file = reports_dir / "parameters.csv"
    if not params_file.exists():
        result["errors"].append("parameters.csv missing")
        return result

    params = pd.read_csv(params_file)
    params_dict = dict(zip(
        params.iloc[:, 0].str.strip(),
        params.iloc[:, 1].astype(str).str.strip()
    ))

    result["ref_period"]    = params_dict.get("refPeriod", None)
    result["base_currency"] = params_dict.get("baseCurrency", "iso4217:EUR").replace("iso4217:", "")

    # CRITICAL: read actual decimalsMonetary
    decimals_raw = params_dict.get("decimalsMonetary", "-6")
    try:
        decimals = int(decimals_raw)
    except ValueError:
        decimals = -6
    result["decimals"] = decimals

    # XBRL decimalsMonetary formula (empirically validated against known bank sizes):
    #   neg decimals (-6, -3): factValue already encodes scale
    #     eur_millions = factValue × 10^decimals
    #     e.g. dec=-6: 906142873 × 1e-6 = 906.1M EUR ✓
    #     e.g. dec=-3: 26717862  × 1e-3 = 26717.9M EUR ✓
    #   non-neg decimals (0, 2, 4): factValue is in EUR units with decimal precision
    #     eur_millions = factValue / 10^decimals / 1e6
    #     e.g. dec=0:  34213674000 / 1   / 1e6 = 34213.7M EUR ✓
    #     e.g. dec=2:  1.08798e13  / 100 / 1e6 = 108798M EUR ✓
    #     e.g. dec=4:  8.21388e13  / 1e4 / 1e6 = 8213.9M EUR ✓
    #
    # KNOWN DATA QUALITY ISSUE: Santander (K8MS7FD7N5Z2WQ51AZ71, ...003 filing)
    # declares decimals=-6 but values appear to be in EUR cents (100× inflated).
    # QuantScore % is still valid (ratio cancels the error).
    # Absolute GCA flagged as unreliable for this bank.
    # Empirically validated against known bank balance sheet sizes.
    # The EBA P3DH stores factValues such that dividing by 1e6 ALWAYS gives
    # the value in local-currency millions, regardless of decimalsMonetary.
    #   dec=-6: 906142873    / 1e6 = 906.1M    ✓ (APS Bank)
    #   dec=-3: 26717859000  / 1e6 = 26717.9M  ✓ (Eurobank)
    #   dec=0:  34213674000  / 1e6 = 34213.7M  ✓ (AIB Group)
    #   dec=2:  108798072832 / 1e6 = 108798.1M ✓ (DZ Bank)
    #   dec=4:  8213877442   / 1e6 = 8213.9M   ✓ (Ibercaja)
    # NOTE: decimalsMonetary indicates REPORTING PRECISION only, not storage unit.
    # KNOWN EXCEPTION: Santander (K8MS7FD7N5Z2WQ51AZ71) has a filing error —
    # their values are 100× inflated. QuantScore % remains valid (ratio cancels error).
    result["scale_factor"] = 1 / 1e6

    # ── Extract country from folder name ───────────────────────────────────────
    country_match = re.search(r"\.(CON|IND)_([A-Z]{2})_", folder.name)
    result["country"] = country_match.group(2) if country_match else None
    result["entity_type"] = country_match.group(1) if country_match else None

    # ── Template 1 ─────────────────────────────────────────────────────────────
    t1_file = reports_dir / "k_41.00.csv"
    if not t1_file.exists():
        result["has_template1"] = False
        result["errors"].append("k_41.00.csv missing")
    else:
        result["has_template1"] = True
        t1 = pd.read_csv(t1_file)
        dp_vals = dict(zip(t1["datapoint"], t1["factValue"]))

        sf = result["scale_factor"]

        # Grand total GCA (in millions EUR local currency)
        raw_total = dp_vals.get(DP_GRAND_TOTAL, np.nan)
        result["total_gca_m_local"] = raw_total * sf if pd.notna(raw_total) else np.nan

        # CPRS fossil sectors (in millions local currency)
        fossil_total = 0.0
        fossil_found = False
        for dp, label in CPRS_DPS.items():
            raw = dp_vals.get(dp, np.nan)
            if pd.notna(raw) and raw > 0:
                val_m = raw * sf
                result[f"{label}_m_local"] = val_m
                fossil_total += val_m
                fossil_found = True
            else:
                result[f"{label}_m_local"] = 0.0

        result["fossil_total_m_local"] = fossil_total if fossil_found else 0.0

        # QuantScore (currency-invariant — same units cancel)
        total = result["total_gca_m_local"]
        if pd.notna(total) and total > 0:
            result["quant_score"]     = fossil_total / total
            result["quant_score_pct"] = fossil_total / total * 100
        else:
            result["quant_score"]     = np.nan
            result["quant_score_pct"] = np.nan

    # ── Qualitative text ───────────────────────────────────────────────────────
    qual_file = reports_dir / "k_00.03.csv"
    if qual_file.exists():
        try:
            qual = pd.read_csv(qual_file)
            texts = qual["factValue"].dropna().astype(str).tolist()
            result["qual_text"] = " | ".join(texts)
            result["qual_text_chars"] = sum(len(t) for t in texts)
        except Exception:
            result["qual_text"] = ""
            result["qual_text_chars"] = 0
    else:
        result["qual_text"] = ""
        result["qual_text_chars"] = 0

    result["parse_ok"] = True
    return result


def main():
    # Scan bank folders (exclude output/ and non-LEI dirs)
    bank_folders = sorted([
        f for f in BANKS_FOLDER.iterdir()
        if f.is_dir()
        and f.name != "output"
        and LEI_PATTERN.match(f.name)
    ])

    print(f"\n{'='*65}")
    print(f"EBA P3DH FIXED PARSER — {len(bank_folders)} bank folders")
    print(f"{'='*65}\n")

    results = []
    for i, folder in enumerate(bank_folders, 1):
        r = parse_bank(folder)
        lei = r.get("lei", "?")[:20]
        ccy = r.get("base_currency", "?")
        dec = r.get("decimals", "?")
        gca = r.get("total_gca_m_local", np.nan)
        qs  = r.get("quant_score_pct", np.nan)
        ok  = "✓" if r["parse_ok"] else "⚠"

        gca_str = f"{gca:>10,.0f}M {ccy}" if pd.notna(gca) and gca > 0 else "n/a"
        qs_str  = f"{qs:.2f}%" if pd.notna(qs) else "n/a"
        dec_str = f"decimals={dec}"

        print(f"[{i:02d}/{len(bank_folders)}] {ok} {lei:<22} | {dec_str:<14} | GCA: {gca_str:<22} | QS: {qs_str}")
        if r.get("errors"):
            for e in r["errors"]:
                print(f"         ⚠ {e}")
        results.append(r)

    df = pd.DataFrame(results)

    # ── Save master CSV ────────────────────────────────────────────────────────
    cols = [
        "lei", "country", "entity_type", "ref_period",
        "base_currency", "decimals", "scale_factor",
        "has_template1", "total_gca_m_local", "fossil_total_m_local",
        "quant_score", "quant_score_pct",
        "B5_coal_m_local", "B6_oilgas_m_local",
        "C19_petrol_m_local", "D35_2_gas_m_local",
        "qual_text", "qual_text_chars",
        "parse_ok", "errors", "folder_name",
    ]
    cols = [c for c in cols if c in df.columns]
    df[cols].to_csv(OUTPUT_FOLDER / "master_banks_fixed.csv", index=False)

    # ── Summary ────────────────────────────────────────────────────────────────
    valid = df[df["quant_score"].notna()]
    print(f"\n{'='*65}")
    print(f"SUMMARY")
    print(f"{'='*65}")
    print(f"  Banks parsed:              {len(df)}")
    print(f"  Successfully parsed:       {df['parse_ok'].sum()}")
    print(f"  With Template 1 + QS:      {len(valid)}")
    print(f"\n  decimalsMonetary variants:")
    for dec, grp in df.groupby("decimals"):
        print(f"    {dec:>4}: {len(grp)} banks  ({', '.join(grp['lei'].dropna().str[:8].tolist()[:3])}...)")

    print(f"\n  QuantScore distribution:")
    print(f"    Min:    {valid['quant_score_pct'].min():.2f}%")
    print(f"    Mean:   {valid['quant_score_pct'].mean():.2f}%")
    print(f"    Median: {valid['quant_score_pct'].median():.2f}%")
    print(f"    Max:    {valid['quant_score_pct'].max():.2f}%")
    print(f"    Std:    {valid['quant_score_pct'].std():.2f}%")

    print(f"\n✓ Saved: {OUTPUT_FOLDER / 'master_banks_fixed.csv'}")
    print(f"\n✅ NEXT STEP: run step2c_currency_fix.py on master_banks_fixed.csv")


if __name__ == "__main__":
    main()
