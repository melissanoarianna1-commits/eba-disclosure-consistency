"""
STEP 3: Disclosure Adequacy Score (DAS) via Claude API
=======================================================
Author:     Arianna Melissano
Project:    EBA Pillar III Disclosure Consistency Index (DCI)
Course:     AI in Finance — Justus Liebig University Giessen
Supervisor: Prof. Christina Evelies Bannier & Prof. Steven Ongena

WHAT THIS SCRIPT DOES:
    For each bank that submitted qualitative narrative text in Template k_00.03
    of the EBA Pillar III XBRL package, this script uses the Claude API to score
    the text on five disclosure quality dimensions. The resulting Disclosure
    Adequacy Score (DAS) is the qualitative pillar of the Disclosure Consistency
    Index (DCI = DAS - normalized QuantScore).

THE FIVE DAS DIMENSIONS (each scored 0-2):
    1. Specificity     — does the text cite concrete figures, sector names,
                         percentages, or named exclusion lists?
    2. Completeness    — does it address all CPRS fossil fuel sectors
                         (coal, oil/gas, petroleum, gas distribution)?
    3. Forward-looking — does it discuss transition plans, timelines,
                         net-zero targets, or phaseout commitments?
    4. Consistency     — does the narrative align with the bank's quantitative
                         fossil exposure (QuantScore) from Template K_41.00?
    5. Comparability   — could an external analyst use this text to compare
                         this bank's fossil approach against peers?

SCORING SCALE:
    0 = absent or misleading
    1 = partial / vague
    2 = clear, specific, adequate
    Raw DAS range: 0-10
    Normalized DAS: raw / 10 → range 0-1

DCI CONSTRUCTION:
    QuantScore (normalized) = quant_score_pct / max(quant_score_pct across sample)
    DCI = DAS_normalized - QuantScore_normalized
    Interpretation:
        DCI > 0  → disclosure is MORE transparent than fossil exposure warrants
        DCI ≈ 0  → disclosure matches fossil exposure
        DCI < 0  → disclosure UNDERSTATES fossil exposure (red flag)

MODEL CHOICE:
    claude-haiku-4-5-20251001 — fastest and cheapest Claude model,
    sufficient for structured scoring tasks. Estimated cost: <$0.10 for
    all 14 banks in this sample.

INPUTS:
    /output/master_banks_fixed.csv  — bank metadata + qualitative text
    /output/quantscore_final.csv    — QuantScore per bank (from step2c)

OUTPUTS:
    /output/das_scores.csv          — DAS per bank per dimension
    /output/dci_final.csv           — final DCI ranking (main result)

USAGE:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 step3_das_scoring.py

REFERENCES:
    Battiston et al. (2017) "A climate stress-test of the financial system"
        Nature Climate Change — source of CPRS fossil fuel classification
    EBA ITS on Pillar III ESG disclosures (2022) — Template K_41.00 structure
    Anthropic Claude API documentation — https://docs.anthropic.com
"""

import os           # for reading the API key from environment variable
import json         # for parsing structured JSON responses from the API
import time         # for rate-limiting API calls (avoid hitting rate limits)
import pandas as pd # for loading and saving CSV data
import numpy as np  # for numerical operations (normalization, NaN handling)
import anthropic    # Anthropic Python SDK for Claude API access

# ── Configuration ──────────────────────────────────────────────────────────────

# Base directory where all script inputs and outputs live
PAPER1 = "/Users/ariannamelissano/Desktop/Paper1"

# Input files produced by earlier pipeline steps
BANKS_FILE      = f"{PAPER1}/output/master_banks_fixed.csv"
QUANTSCORE_FILE = f"{PAPER1}/output/quantscore_final.csv"

# Output files this script will create
DAS_OUTPUT      = f"{PAPER1}/output/das_scores.csv"
DCI_OUTPUT      = f"{PAPER1}/output/dci_final.csv"

# Claude model to use for scoring
# haiku is cheapest; adequate for structured classification tasks
MODEL = "claude-haiku-4-5-20251001"

# Seconds to wait between API calls to avoid rate limiting
API_DELAY = 1.5

# Bank name lookup for readable output
BANK_NAMES = {
    "5UMCZOEYKCVFAW8ZLO05": "Alpha Bank",
    "K8MS7FD7N5Z2WQ51AZ71": "Santander",
    "PSNL19R2RXX5U3QWHI44": "Banco BPM",
    "M6AD1Y1KW32H8THQ6F76": "Eurobank",
    "5493008QOCP58OLEN998":  "Belfius",
    "7CUNS533WID6K7DGFI87":  "Sabadell",
    "J48C8PCSJVUBR8KCW529":  "Mediobanca",
    "851WYGNLUQLFZBSYGB56":  "DZ Bank",
    "95980020140005881190":  "Abanca",
    "529900HNOAA1KXQJUQ27":  "pbb",
    "5493006QMFDDMYWIAM13":  "BBVA",
    "549300HFEHJOXGE4ZE63":  "Arkea",
    "815600E4E6DCD2D25E30":  "Intesa Sanpaolo",
    "549300OLBL49CW8CT155":  "Ibercaja",
    "549300RG3H390KEL8896":  "Banca Transilvania",
    "5493000LKS7B3UTF7H35":  "PKO Bank Polski",
    "3H0Q3U74FVFED2SHZT16":  "OTP Bank",
    "3157002JBFAI478MD587":  "Tatra Banka",
    "213800A1O379I6DMCU10":  "APS Bank",
    "J4CP7MHCXR8DAQMKIL78":  "Credem",
    "815600AD83B2B6317788":  "Banca MPS",
    "NNVPP80YIZGEY2314M97":  "BPER Banca",
    "FR9695005MSX1OYEMGDF":  "BPCE Group",
    "BFXS5XCH7N0Y05NIXW11":  "ABN AMRO",
    "VWMYAEQSTOPNV0SUGU82":  "Unicaja",
    "635400AKJBGNS5WNQL34":  "AIB Group",
    "LOO0AWXR8GF142JCO404":  "Mediocredito Centrale",
    "96950001WI712W7PQG45":  "Caisse des Depots",
    "529900HEKOENJHPNN480":  "Alandsbanken",
    "7LVZJ6XRIE7VNZ4UBX81":  "Banca Galileo",
    "213800TC9PZRBHMJW403":  "Bank of Valletta",
    "H0YX5LBGKDVOWCXBZ594":  "Swedbank",
    "815600DDCE9083CAC598":  "Banca Patavina",
    "549300IQZVZ949N37S44":  "Crelan",
    "259400YLRTOBISHBVX41":  "Bank Pekao",
}


# ── Scoring Prompt ─────────────────────────────────────────────────────────────

def build_scoring_prompt(lei: str, bank_name: str, qual_text: str,
                          quant_score_pct: float) -> str:
    """
    Build the structured scoring prompt sent to the Claude API.

    The prompt provides:
    - the bank's qualitative narrative text from Template k_00.03
    - the bank's quantitative fossil exposure (QuantScore) for context
    - a precise rubric for each of the five DAS dimensions
    - an instruction to return ONLY valid JSON (no preamble)

    Returns a string prompt ready to send as the user message.
    """
    # Format QuantScore for the prompt context
    qs_str = f"{quant_score_pct:.2f}%" if pd.notna(quant_score_pct) else "not available"

    prompt = f"""You are an expert analyst evaluating the quality of ESG climate disclosure
in European bank regulatory filings. Your task is to score the following qualitative
disclosure text from a bank's EBA Pillar III XBRL submission (Template k_00.03).

BANK: {bank_name} (LEI: {lei})
QUANTITATIVE FOSSIL FUEL EXPOSURE (from Template K_41.00): {qs_str} of total loan portfolio
(This covers NACE sectors: coal mining, oil/gas extraction, petroleum refining, gas distribution)

QUALITATIVE DISCLOSURE TEXT:
---
{qual_text[:3000]}
---

Score this text on EXACTLY these five dimensions. Each dimension is scored 0, 1, or 2.

SCORING RUBRIC:

1. SPECIFICITY (0-2)
   0 = only vague statements ("we consider climate risks"), no numbers or named sectors
   1 = some concrete elements (mentions fossil fuels by name OR gives one percentage)
   2 = clearly specific (names multiple fossil sectors AND provides percentages or thresholds)

2. COMPLETENESS (0-2)
   0 = does not address fossil fuel exposure at all
   1 = addresses fossil fuels partially (e.g. only mentions one sector like coal)
   2 = addresses all major fossil fuel categories (coal, oil/gas, petroleum/refining, gas)

3. FORWARD_LOOKING (0-2)
   0 = no transition plans, timelines, or net-zero commitments
   1 = mentions transition or net-zero goals vaguely, without specific timelines
   2 = concrete transition plan with specific dates, targets, or phaseout commitments

4. CONSISTENCY (0-2)
   0 = narrative contradicts the quantitative data (e.g. claims zero fossil exposure
       when QuantScore > 1%, or claims high exposure when QuantScore is near zero)
   1 = narrative is neutral or non-committal relative to the quantitative data
   2 = narrative explicitly acknowledges and explains the quantitative fossil exposure

5. COMPARABILITY (0-2)
   0 = text is so generic that it could apply to any bank
   1 = some bank-specific content but lacks structure for peer comparison
   2 = structured and specific enough that an analyst could use it to compare
       this bank's fossil approach against peers

IMPORTANT: Return ONLY a valid JSON object with this exact structure, no preamble:
{{
  "specificity": <0, 1, or 2>,
  "completeness": <0, 1, or 2>,
  "forward_looking": <0, 1, or 2>,
  "consistency": <0, 1, or 2>,
  "comparability": <0, 1, or 2>,
  "rationale": "<one sentence explaining the overall assessment>"
}}"""

    return prompt


# ── API Scoring Function ───────────────────────────────────────────────────────

def score_bank(client: anthropic.Anthropic, lei: str, bank_name: str,
               qual_text: str, quant_score_pct: float) -> dict:
    """
    Call the Claude API to score one bank's qualitative disclosure text.

    Args:
        client:          authenticated Anthropic API client
        lei:             bank's Legal Entity Identifier (20-char string)
        bank_name:       human-readable bank name for the prompt
        qual_text:       raw qualitative text from Template k_00.03
        quant_score_pct: bank's QuantScore percentage from Template K_41.00

    Returns:
        dict with keys: lei, bank_name, specificity, completeness,
        forward_looking, consistency, comparability, das_raw, das_normalized,
        rationale, scoring_status
    """
    # Build the prompt for this bank
    prompt = build_scoring_prompt(lei, bank_name, qual_text, quant_score_pct)

    try:
        # Call the Claude API
        # system: sets the AI's role and enforces JSON-only output
        # max_tokens: 300 is sufficient for a small JSON object
        response = client.messages.create(
            model=MODEL,
            max_tokens=300,
            system="You are a precise financial disclosure analyst. "
                   "You always respond with valid JSON only, no markdown, "
                   "no explanation outside the JSON object.",
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract the text content from the API response
        raw_text = response.content[0].text.strip()

        # Remove markdown code fences if the model included them despite instructions
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

        # Parse the JSON response into a Python dictionary
        scores = json.loads(raw_text)

        # Validate that all five required dimension keys are present
        required = ["specificity", "completeness", "forward_looking",
                    "consistency", "comparability"]
        for key in required:
            if key not in scores:
                raise ValueError(f"Missing key in API response: {key}")
            # Clamp each score to valid range 0-2
            scores[key] = max(0, min(2, int(scores[key])))

        # Compute raw DAS (sum of five dimensions, range 0-10)
        das_raw = sum(scores[k] for k in required)

        # Normalize to 0-1 scale
        das_normalized = das_raw / 10.0

        return {
            "lei":             lei,
            "bank_name":       bank_name,
            "specificity":     scores["specificity"],
            "completeness":    scores["completeness"],
            "forward_looking": scores["forward_looking"],
            "consistency":     scores["consistency"],
            "comparability":   scores["comparability"],
            "das_raw":         das_raw,
            "das_normalized":  das_normalized,
            "rationale":       scores.get("rationale", ""),
            "scoring_status":  "ok",
        }

    except json.JSONDecodeError as e:
        # API returned something that wasn't valid JSON
        print(f"    ✗ JSON parse error for {bank_name}: {e}")
        print(f"      Raw response: {raw_text[:200]}")
        return _failed_score(lei, bank_name, f"json_error: {e}")

    except Exception as e:
        # Any other error (network, rate limit, etc.)
        print(f"    ✗ API error for {bank_name}: {e}")
        return _failed_score(lei, bank_name, str(e))


def _failed_score(lei: str, bank_name: str, error: str) -> dict:
    """
    Return a placeholder result when scoring fails.
    Sets all scores to NaN so the bank can be identified and excluded
    from analysis without crashing the pipeline.
    """
    return {
        "lei":             lei,
        "bank_name":       bank_name,
        "specificity":     np.nan,
        "completeness":    np.nan,
        "forward_looking": np.nan,
        "consistency":     np.nan,
        "comparability":   np.nan,
        "das_raw":         np.nan,
        "das_normalized":  np.nan,
        "rationale":       f"FAILED: {error}",
        "scoring_status":  "failed",
    }


# ── DCI Computation ────────────────────────────────────────────────────────────

def compute_dci(das_df: pd.DataFrame, qs_df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge DAS scores with QuantScores and compute the DCI.

    DCI = DAS_normalized - QuantScore_normalized

    QuantScore normalization: divide by the maximum QuantScore in the sample,
    so that the most fossil-exposed bank has a normalized QuantScore of 1.0.
    This puts DAS and QuantScore on the same 0-1 scale for comparability.

    Args:
        das_df: DataFrame with DAS scores (output of scoring loop)
        qs_df:  DataFrame with QuantScores (from step2c output)

    Returns:
        DataFrame with DCI and all component scores, sorted by DCI descending
    """
    # Merge on LEI — keep only banks that have both DAS and QuantScore
    merged = das_df.merge(
        qs_df[["lei", "quant_score_pct", "gca_eur_m", "base_currency",
               "country"]].drop_duplicates("lei"),
        on="lei",
        how="left"
    )

    # Normalize QuantScore to 0-1 scale using max in full sample
    # (including banks without DAS, to preserve relative ranking)
    qs_max = qs_df["quant_score_pct"].max()
    merged["quant_score_normalized"] = merged["quant_score_pct"] / qs_max

    # Compute DCI: positive = over-disclosure, negative = under-disclosure
    merged["dci"] = merged["das_normalized"] - merged["quant_score_normalized"]

    # Round for readability
    for col in ["das_normalized", "quant_score_normalized", "dci"]:
        merged[col] = merged[col].round(4)

    # Sort by DCI descending (most transparent first)
    merged = merged.sort_values("dci", ascending=False).reset_index(drop=True)

    return merged


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    # ── 0. Initialise API client ───────────────────────────────────────────────

    # Read API key from environment variable (never hardcode keys in scripts)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY not set.\n"
            "Run: export ANTHROPIC_API_KEY='sk-ant-...'\n"
            "Then re-run this script."
        )

    # Initialise the Anthropic client with the API key
    client = anthropic.Anthropic(api_key=api_key)
    print(f"Claude API client initialised (model: {MODEL})")

    # ── 1. Load data ───────────────────────────────────────────────────────────

    # Load bank metadata including qualitative text extracted by step1b
    banks = pd.read_csv(BANKS_FILE)
    print(f"Banks loaded: {len(banks)} rows")

    # Load QuantScores from step2c (FX-corrected)
    # Fall back to step2b output if step2c hasn't been run
    if os.path.exists(QUANTSCORE_FILE):
        qs = pd.read_csv(QUANTSCORE_FILE)
    else:
        qs = pd.read_csv(f"{PAPER1}/output/quantscore_taxonomy.csv")
    print(f"QuantScores loaded: {len(qs)} rows")

    # ── 2. Select banks with qualitative text ─────────────────────────────────

    # Filter to banks that actually submitted qualitative narrative text
    # qual_text_chars > 100 filters out banks with only placeholder text
    text_col = "qual_text" if "qual_text" in banks.columns else "qual_text_all"
    banks_with_text = banks[
        banks[text_col].notna() &
        (banks["qual_text_chars"] > 100)
    ].copy()

    # Deduplicate by LEI — keep the row with the most text
    # (handles Santander duplicate submission)
    banks_with_text = (
        banks_with_text
        .sort_values("qual_text_chars", ascending=False)
        .drop_duplicates("lei")
        .reset_index(drop=True)
    )

    print(f"\nBanks with qualifying text: {len(banks_with_text)}")

    # ── 3. Score each bank ─────────────────────────────────────────────────────

    print(f"\n{'='*65}")
    print(f"DAS SCORING — Claude API ({MODEL})")
    print(f"{'='*65}\n")

    results = []

    for i, row in banks_with_text.iterrows():
        lei       = str(row["lei"]).strip()
        qual_text = str(row[text_col])
        bank_name = BANK_NAMES.get(lei, lei[:12])

        # Look up QuantScore for context in the prompt
        qs_row = qs[qs["lei"].astype(str).str.strip() == lei]
        qs_pct = qs_row["quant_score_pct"].values[0] if len(qs_row) > 0 else np.nan

        print(f"[{i+1:02d}/{len(banks_with_text)}] Scoring {bank_name:<25} "
              f"(QS: {qs_pct:.2f}% | text: {len(qual_text):,} chars)")

        # Call the API to score this bank
        result = score_bank(client, lei, bank_name, qual_text, qs_pct)
        results.append(result)

        # Print the scores immediately so you can see progress
        if result["scoring_status"] == "ok":
            s = result
            print(f"         Spec={s['specificity']} Comp={s['completeness']} "
                  f"Fwd={s['forward_looking']} Cons={s['consistency']} "
                  f"Cmp={s['comparability']} "
                  f"→ DAS={s['das_raw']}/10 ({s['das_normalized']:.1f})")
            print(f"         {s['rationale'][:90]}")

        # Wait between calls to respect API rate limits
        if i < len(banks_with_text) - 1:
            time.sleep(API_DELAY)

    # ── 4. Build DAS DataFrame ─────────────────────────────────────────────────

    das_df = pd.DataFrame(results)

    # Save raw DAS scores
    das_df.to_csv(DAS_OUTPUT, index=False)
    print(f"\n✓ DAS scores saved: {DAS_OUTPUT}")

    # ── 5. Compute DCI ────────────────────────────────────────────────────────

    # Merge DAS with QuantScore and compute the DCI
    dci_df = compute_dci(das_df, qs)

    # Save final DCI table
    dci_df.to_csv(DCI_OUTPUT, index=False)
    print(f"✓ DCI results saved: {DCI_OUTPUT}")

    # ── 6. Print final results table ──────────────────────────────────────────

    print(f"\n{'='*80}")
    print(f"FINAL DCI RANKING — Disclosure Consistency Index")
    print(f"DCI = DAS_normalized - QuantScore_normalized")
    print(f"{'='*80}")
    print(f"{'Bank':<28} {'Country':<5} {'QS%':>6} {'DAS/10':>7} "
          f"{'DAS_n':>6} {'QS_n':>6} {'DCI':>7}")
    print(f"-"*80)

    for _, r in dci_df.iterrows():
        name    = str(r["bank_name"])[:27]
        country = str(r.get("country", "??"))
        qs_pct  = r.get("quant_score_pct", np.nan)
        das_raw = r.get("das_raw", np.nan)
        das_n   = r.get("das_normalized", np.nan)
        qs_n    = r.get("quant_score_normalized", np.nan)
        dci     = r.get("dci", np.nan)

        qs_str  = f"{qs_pct:.2f}%" if pd.notna(qs_pct) else "n/a"
        das_str = f"{das_raw:.0f}" if pd.notna(das_raw) else "n/a"
        dasn_s  = f"{das_n:.3f}" if pd.notna(das_n) else "n/a"
        qsn_s   = f"{qs_n:.3f}" if pd.notna(qs_n) else "n/a"
        dci_s   = f"{dci:+.3f}" if pd.notna(dci) else "n/a"

        # Flag direction of DCI
        flag = "▲ over" if pd.notna(dci) and dci > 0.1 else (
               "▼ under" if pd.notna(dci) and dci < -0.1 else "≈ match")

        print(f"{name:<28} {country:<5} {qs_str:>6} {das_str:>7} "
              f"{dasn_s:>6} {qsn_s:>6} {dci_s:>7}  {flag}")

    # ── 7. Summary statistics ─────────────────────────────────────────────────

    valid = dci_df[dci_df["dci"].notna()]
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}")
    print(f"  Banks scored:              {len(das_df[das_df['scoring_status']=='ok'])}")
    print(f"  Banks failed:              {len(das_df[das_df['scoring_status']=='failed'])}")
    print(f"  DCI range:                 {valid['dci'].min():+.3f} to {valid['dci'].max():+.3f}")
    print(f"  DCI mean:                  {valid['dci'].mean():+.3f}")
    print(f"  Over-disclosers (DCI>0.1): {(valid['dci'] > 0.1).sum()}")
    print(f"  Matched (|DCI|≤0.1):       {(valid['dci'].abs() <= 0.1).sum()}")
    print(f"  Under-disclosers (DCI<-0.1): {(valid['dci'] < -0.1).sum()}")
    print(f"\n✅ PIPELINE COMPLETE — ready for Wednesday meeting")


if __name__ == "__main__":
    main()
