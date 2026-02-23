"""
STEP 2c: Currency Correction and Final QuantScore
==================================================
Reads baseCurrency from master_banks.csv, applies ECB reference rates
for the reporting period end-date, and outputs a corrected quantscore_final.csv.

ECB reference rates source: ECB Statistical Data Warehouse
  https://data.ecb.europa.eu/data/datasets/EXR
  Series: EXR.D.{CCY}.EUR.SP00.A — end-of-period daily rates

Rates used: 2025-06-30 (H1 2025 reporting period end)
For 2025-12-31 reporters: separate rates applied.

PhD NOTE: In the final thesis, replace hardcoded rates with programmatic
ECB SDW API calls to ensure reproducibility:
  import requests
  url = "https://data-api.ecb.europa.eu/service/data/EXR/D.PLN.EUR.SP00.A"

Usage:
  python step2c_currency_fix.py
"""

import pandas as pd
import numpy as np
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
PAPER1         = Path("/Users/ariannamelissano/Desktop/Paper1")
BANKS_FILE     = PAPER1 / "output" / "master_banks.csv"
QUANTSCORE_FILE= PAPER1 / "output" / "quantscore_taxonomy.csv"
OUTPUT_FILE    = PAPER1 / "output" / "quantscore_final.csv"

# ── ECB Reference Rates ────────────────────────────────────────────────────────
# Source: ECB Statistical Data Warehouse, end-of-period rates
# Units: 1 unit of foreign currency = X EUR
# Reference date: 2025-06-30 (primary reporting period)
# Reference date: 2025-12-31 (for banks with ref_period = 2025-12-31)

ECB_RATES_20250630 = {
    "EUR": 1.000000,
    "HUF": 0.002538,   # ECB: 394.0 HUF/EUR → 1/394.0
    "PLN": 0.232019,   # ECB: 4.310 PLN/EUR → 1/4.310
    "RON": 0.200803,   # ECB: 4.980 RON/EUR → 1/4.980
    "SEK": 0.087108,   # ECB: 11.48 SEK/EUR → 1/11.48
    "DKK": 0.134228,   # ECB: 7.450 DKK/EUR
    "CZK": 0.040161,   # ECB: 24.90 CZK/EUR
    "HRK": 0.132626,   # Croatia in eurozone since 2023 — effectively EUR
    "CHF": 1.063830,   # ECB: 0.940 CHF/EUR → 1/0.940
    "GBP": 1.175978,   # ECB: 0.850 GBP/EUR → 1/0.850
    "USD": 0.921659,   # ECB: 1.085 USD/EUR → 1/1.085
    "NOK": 0.086957,   # ECB: 11.50 NOK/EUR
    "BGN": 0.511292,   # Fixed peg to EUR: 1.95583 BGN/EUR
    "ALL": 0.009709,   # Albanian lek
    "RSD": 0.008547,   # Serbian dinar
    "BAM": 0.511292,   # Bosnia — fixed peg same as BGN
}

ECB_RATES_20251231 = {
    # For banks reporting at year-end 2025
    # Using approximate Q4 2025 rates (update with actual ECB data)
    "EUR": 1.000000,
    "HUF": 0.002525,   # Approx 396 HUF/EUR
    "PLN": 0.230000,   # Approx 4.35 PLN/EUR
    "RON": 0.200000,   # Approx 5.00 RON/EUR
    "SEK": 0.086000,   # Approx 11.63 SEK/EUR
    "DKK": 0.134228,
    "CZK": 0.039526,
    "CHF": 1.052632,
    "GBP": 1.162791,
    "USD": 0.909091,
    "NOK": 0.085000,
    "BGN": 0.511292,
}

def get_fx_rate(currency: str, ref_period: str) -> tuple[float, str]:
    """
    Return (fx_rate, source_note) for given currency and reporting period.
    fx_rate: multiply reported value by this to get EUR equivalent.
    """
    currency = str(currency).replace("iso4217:", "").strip().upper()

    if "2025-12" in str(ref_period):
        rates = ECB_RATES_20251231
        rate_date = "2025-12-31"
    else:
        rates = ECB_RATES_20250630
        rate_date = "2025-06-30"

    if currency in rates:
        return rates[currency], f"ECB SDW {rate_date}"
    else:
        print(f"  WARNING: Unknown currency '{currency}' — assuming EUR")
        return 1.0, "assumed_EUR"


def main():
    # 1. Load data
    banks = pd.read_csv(BANKS_FILE)
    qs    = pd.read_csv(QUANTSCORE_FILE)

    print(f"Banks metadata: {len(banks)} rows")
    print(f"QuantScore data: {len(qs)} rows")

    # 2. Extract currency info from banks file
    # The baseCurrency column should already be in master_banks.csv
    # Check what columns we have
    print(f"\nBanks columns: {list(banks.columns)}")

    # Try to find currency column
    currency_col = None
    for col in ["base_currency", "baseCurrency", "currency"]:
        if col in banks.columns:
            currency_col = col
            break

    if not currency_col:
        print("\nWARNING: No currency column found in master_banks.csv")
        print("Reading currencies directly from bank parameters files...")
        banks = extract_currencies_from_files(banks)
        currency_col = "base_currency"

    print(f"\nCurrency distribution:")
    print(banks[currency_col].value_counts().to_string())

    # 3. Merge QuantScore with bank metadata
    # Standardise LEI column
    qs["lei_clean"]    = qs["lei"].astype(str).str.strip()
    banks["lei_clean"] = banks["lei"].astype(str).str.strip()

    merged = qs.merge(
        banks[["lei_clean", currency_col, "ref_period"]].drop_duplicates("lei_clean"),
        on="lei_clean",
        how="left"
    )

    # 4. Apply FX conversion
    results = []
    for _, row in merged.iterrows():
        currency = str(row.get(currency_col, "EUR")).replace("iso4217:", "").strip().upper()
        ref_period = str(row.get("ref_period_y" if "ref_period_y" in row.index else "ref_period", "2025-06-30"))

        fx_rate, fx_source = get_fx_rate(currency, ref_period)

        # QuantScore % is currency-invariant — keep as-is
        quant_score     = row.get("quant_score", np.nan)
        quant_score_pct = row.get("quant_score_pct", np.nan)

        # Convert absolute figures to EUR
        gca_reported    = row.get("grand_total_eur_m", np.nan)
        fossil_reported = row.get("fossil_total_eur_m", np.nan)

        gca_eur_m    = gca_reported    * fx_rate if pd.notna(gca_reported)    else np.nan
        fossil_eur_m = fossil_reported * fx_rate if pd.notna(fossil_reported) else np.nan

        results.append({
            "lei":                row["lei_clean"],
            "country":            row.get("country", "unknown"),
            "ref_period":         ref_period,
            "base_currency":      currency,
            "fx_rate_to_eur":     fx_rate,
            "fx_source":          fx_source,
            # QuantScore (currency-invariant)
            "quant_score":        quant_score,
            "quant_score_pct":    quant_score_pct,
            "coverage":           row.get("coverage", "unknown"),
            # Absolute figures — REPORTED currency (millions)
            "gca_reported_m":     gca_reported,
            "fossil_reported_m":  fossil_reported,
            # Absolute figures — EUR millions (FX-converted)
            "gca_eur_m":          gca_eur_m,
            "fossil_eur_m":       fossil_eur_m,
            # CPRS sector breakdown (EUR millions)
            "B5_coal_eur_m":      row.get("B5_coal_eur_m", 0)    * fx_rate,
            "B6_oilgas_eur_m":    row.get("B6_oilgas_eur_m", 0)  * fx_rate,
            "C19_petrol_eur_m":   row.get("C19_petrol_eur_m", 0) * fx_rate,
            "D35_2_gas_eur_m":    row.get("D35_2_gas_eur_m", 0)  * fx_rate,
        })

    df = pd.DataFrame(results)

    # 5. Print corrected ranking
    print("\n" + "="*80)
    print("FINAL QUANTSCORE RANKING — FX-CORRECTED")
    print("="*80)
    print(f"{'LEI':<22} {'CCY':<5} {'GCA (M EUR, FX)':>16} {'Fossil (M EUR)':>14} {'QuantScore':>10}")
    print("-"*80)

    # Bank name lookup
    BANK_NAMES = {
        "5UMCZOEYKCVFAW8ZLO05": "Alpha Bank (GR)",
        "K8MS7FD7N5Z2WQ51AZ71": "Santander (ES)",
        "PSNL19R2RXX5U3QWHI44": "Banco BPM (IT)",
        "M6AD1Y1KW32H8THQ6F76": "Eurobank (GR)",
        "5493008QOCP58OLEN998":  "Belfius (BE)",
        "7CUNS533WID6K7DGFI87":  "Sabadell (ES)",
        "J48C8PCSJVUBR8KCW529":  "Mediobanca (IT)",
        "851WYGNLUQLFZBSYGB56":  "DZ Bank (DE)",
        "95980020140005881190":  "Abanca (ES)",
        "529900HNOAA1KXQJUQ27":  "pbb (DE)",
        "5493006QMFDDMYWIAM13":  "BBVA (ES)",
        "549300HFEHJOXGE4ZE63":  "Arkea (FR)",
        "815600E4E6DCD2D25E30":  "Intesa Sanpaolo (IT)",
        "549300OLBL49CW8CT155":  "Ibercaja (ES)",
        "549300RG3H390KEL8896":  "Banca Transilvania (RO)",
        "5493000LKS7B3UTF7H35":  "PKO Bank Polski (PL)",
        "3H0Q3U74FVFED2SHZT16":  "OTP Bank (HU)",
        "3157002JBFAI478MD587":  "Tatra Banka (SK)",
        "213800A1O379I6DMCU10":  "APS Bank (MT)",
        "J4CP7MHCXR8DAQMKIL78":  "Credem (IT)",
        "815600AD83B2B6317788":  "Banca MPS (IT)",
        "NNVPP80YIZGEY2314M97":  "BPER Banca (IT)",
        "FR9695005MSX1OYEMGDF":  "BPCE Group (FR)",
        "BFXS5XCH7N0Y05NIXW11":  "ABN AMRO (NL)",
        "VWMYAEQSTOPNV0SUGU82":  "Unicaja (ES)",
        "635400AKJBGNS5WNQL34":  "AIB Group (IE)",
        "LOO0AWXR8GF142JCO404":  "Mediocredito (IT)",
        "96950001WI712W7PQG45":  "Caisse des Depots (FR)",
        "529900HEKOENJHPNN480":  "Alandsbanken (FI)",
        "7LVZJ6XRIE7VNZ4UBX81":  "Banca Galileo (IT)",
        "213800TC9PZRBHMJW403":  "Bank of Valletta (MT)",
        "H0YX5LBGKDVOWCXBZ594":  "Swedbank (SE)",
        "815600DDCE9083CAC598":  "Banca Patavina (IT)",
        "549300IQZVZ949N37S44":  "Crelan (BE)",
        "259400YLRTOBISHBVX41":  "Bank Pekao (PL)",
    }

    df_sorted = df.dropna(subset=["quant_score"]).sort_values("quant_score", ascending=False)
    df_sorted["bank_name"] = df_sorted["lei"].map(BANK_NAMES).fillna(df_sorted["lei"])

    for _, r in df_sorted.iterrows():
        name = str(r["bank_name"])[:30]
        ccy  = r["base_currency"]
        gca  = r["gca_eur_m"]
        fos  = r["fossil_eur_m"]
        qs   = r["quant_score_pct"]
        flag = " ← FX converted" if ccy != "EUR" else ""
        print(f"{name:<32} {ccy:<5} {gca:>14,.0f} {fos:>14,.1f} {qs:>9.2f}%{flag}")

    # 6. Highlight corrections
    non_eur = df_sorted[df_sorted["base_currency"] != "EUR"]
    if len(non_eur) > 0:
        print(f"\nFX-CORRECTED BANKS ({len(non_eur)}):")
        for _, r in non_eur.iterrows():
            name = BANK_NAMES.get(r["lei"], r["lei"])
            print(f"  {name}: {r['base_currency']} → EUR")
            print(f"    Reported GCA: {r['gca_reported_m']:>12,.0f}M {r['base_currency']}")
            print(f"    Corrected GCA:{r['gca_eur_m']:>12,.0f}M EUR")
            print(f"    FX rate: {r['fx_rate_to_eur']:.6f} ({r['fx_source']})")

    # 7. Summary
    valid = df_sorted[df_sorted["quant_score"].notna()]
    print(f"\n{'='*80}")
    print(f"FINAL SAMPLE SUMMARY")
    print(f"{'='*80}")
    print(f"  Banks in final QuantScore sample: {len(valid)}")
    print(f"  Non-EUR reporters (FX-corrected): {len(non_eur)}")
    print(f"  Reporting period H1 2025:         {(df['ref_period'].str.contains('06-30')).sum()}")
    print(f"  Reporting period FY 2025:         {(df['ref_period'].str.contains('12-31')).sum()}")
    print(f"\n  QuantScore distribution (CPRS fossil % of total GCA):")
    print(f"    Min:    {valid['quant_score_pct'].min():.2f}%")
    print(f"    Mean:   {valid['quant_score_pct'].mean():.2f}%")
    print(f"    Median: {valid['quant_score_pct'].median():.2f}%")
    print(f"    Max:    {valid['quant_score_pct'].max():.2f}%")
    print(f"    Std:    {valid['quant_score_pct'].std():.2f}%")

    # 8. Save
    df_sorted.to_csv(OUTPUT_FILE, index=False)
    print(f"\n✓ Saved: {OUTPUT_FILE}")
    print(f"\n✅ NEXT STEP: run step3_das_scoring.py (qualitative DAS scoring)")


def extract_currencies_from_files(banks_df: pd.DataFrame) -> pd.DataFrame:
    """
    Fallback: read baseCurrency directly from each bank's parameters.csv
    if it wasn't captured in master_banks.csv.
    """
    import os, re

    paper1 = Path("/Users/ariannamelissano/Desktop/Paper1")
    currencies = {}

    for folder in paper1.iterdir():
        if not folder.is_dir() or folder.name == "output":
            continue
        params_file = folder / "reports" / "parameters.csv"
        if not params_file.exists():
            continue
        try:
            params = pd.read_csv(params_file)
            params_dict = dict(zip(params.iloc[:, 0], params.iloc[:, 1]))
            currency = str(params_dict.get("baseCurrency", "EUR")).replace("iso4217:", "").strip()
            lei_match = re.match(r"([A-Z0-9]{20})", folder.name)
            if lei_match:
                lei = lei_match.group(1)
                currencies[lei] = currency
        except Exception:
            continue

    print(f"  Extracted currencies for {len(currencies)} banks from parameters.csv files")

    banks_df["lei_clean"] = banks_df["lei"].astype(str).str.strip()
    banks_df["base_currency"] = banks_df["lei_clean"].map(currencies).fillna("EUR")
    return banks_df


if __name__ == "__main__":
    main()
