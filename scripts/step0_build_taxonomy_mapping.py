"""
STEP 0: Build Datapoint Label Mapping from EBA DPM 4.1 Taxonomy
================================================================
Run this ONCE to build the mapping table. Output is saved as a CSV
that all subsequent steps use to decode datapoints.

REQUIRES: EBA Full Taxonomy extracted to your machine

Usage:
  python step0_build_taxonomy_mapping.py --taxonomy-path "/path/to/Full_taxonomy_and_technical_documentation"
"""

import json, re, argparse, os
import pandas as pd
from pathlib import Path

# CPRS Fossil fuel NAC codes (ETH Zurich classification, adopted by EBA)
CPRS_FOSSIL_NAC = {
    "B5": "NACE 05 - Mining of coal and lignite",
    "B6": "NACE 06 - Extraction of crude petroleum and natural gas",
    "C19": "NACE 19 - Manufacture of coke and refined petroleum products",
    "D35_2": "NACE 35.2 - Manufacture/distribution of gaseous fuels",
    "G46_71": "NACE 46.71 - Wholesale of solid/liquid/gaseous fuels",
    "G47_3": "NACE 47.3 - Retail sale of automotive fuel",
    "H49_5": "NACE 49.5 - Transport via pipeline",
}

# All NAC codes with labels (from NACE Rev 2)
NAC_LABELS = {
    "x12": "Total - Sectors NOT contributing highly to climate change",
    "x13": "Total - Sectors contributing highly to climate change",
    "x10": "Other sectors (households, public admin, education, health, etc.)",
    "A":   "Agriculture, forestry and fishing (NACE A)",
    "B":   "Mining and quarrying - TOTAL (NACE B)",
    "B5":  "Mining of coal and lignite (NACE 05)",
    "B6":  "Extraction of crude petroleum and natural gas (NACE 06)",
    "B7":  "Mining of metal ores (NACE 07)",
    "B8":  "Other mining and quarrying (NACE 08)",
    "B9":  "Mining support service activities (NACE 09)",
    "C":   "Manufacturing - TOTAL (NACE C)",
    "C10": "Manufacture of food products (NACE 10)",
    "C11": "Manufacture of beverages (NACE 11)",
    "C12": "Manufacture of tobacco products (NACE 12)",
    "C13": "Manufacture of textiles (NACE 13)",
    "C14": "Manufacture of wearing apparel (NACE 14)",
    "C15": "Manufacture of leather products (NACE 15)",
    "C16": "Manufacture of wood products (NACE 16)",
    "C17": "Manufacture of paper (NACE 17)",
    "C18": "Printing and reproduction of recorded media (NACE 18)",
    "C19": "Manufacture of coke and refined petroleum products (NACE 19)",
    "C20": "Manufacture of chemicals (NACE 20)",
    "C21": "Manufacture of pharmaceuticals (NACE 21)",
    "C22": "Manufacture of rubber and plastics (NACE 22)",
    "C23": "Manufacture of non-metallic mineral products (NACE 23)",
    "C24": "Manufacture of basic metals (NACE 24)",
    "C25": "Manufacture of fabricated metal products (NACE 25)",
    "C26": "Manufacture of computer and electronic products (NACE 26)",
    "C27": "Manufacture of electrical equipment (NACE 27)",
    "C28": "Manufacture of machinery and equipment (NACE 28)",
    "C29": "Manufacture of motor vehicles (NACE 29)",
    "C30": "Manufacture of other transport equipment (NACE 30)",
    "C31": "Manufacture of furniture (NACE 31)",
    "C32": "Other manufacturing (NACE 32)",
    "C33": "Repair and installation of machinery (NACE 33)",
    "D":   "Electricity, gas, steam and air conditioning supply - TOTAL (NACE D)",
    "D35_1": "Electricity, gas and steam supply - subsection (NACE 35.1 group)",
    "D35_11": "Electric power generation from renewables (NACE 35.11)",
    "D35_2": "Manufacture of gas; distribution of gaseous fuels (NACE 35.2)",
    "D35_3": "Steam and air conditioning supply (NACE 35.3)",
    "E":   "Water supply; sewerage, waste management (NACE E)",
    "F":   "Construction - TOTAL (NACE F)",
    "F41": "Construction of buildings (NACE 41)",
    "F42": "Civil engineering (NACE 42)",
    "F43": "Specialised construction activities (NACE 43)",
    "G":   "Wholesale and retail trade - TOTAL (NACE G)",
    "G46_71": "Wholesale of solid, liquid and gaseous fuels (NACE 46.71)",
    "G47_3": "Retail sale of automotive fuel (NACE 47.3)",
    "H":   "Transportation and storage - TOTAL (NACE H)",
    "H49": "Land transport and transport via pipelines (NACE 49)",
    "H49_5": "Transport via pipeline (NACE 49.5)",
    "H50": "Water transport (NACE 50)",
    "H51": "Air transport (NACE 51)",
    "H52": "Warehousing and support for transportation (NACE 52)",
    "H53": "Postal and courier activities (NACE 53)",
    "I":   "Accommodation and food service activities (NACE I)",
    "J":   "Information and communication (NACE J)",
    "K":   "Financial and insurance activities (NACE K)",
    "L":   "Real estate activities (NACE L)",
    "M":   "Professional, scientific and technical activities (NACE M)",
    "N":   "Administrative and support service activities (NACE N)",
}

COL_LABELS = {
    "c0010": "Gross carrying amount - TOTAL",
    "c0020": "Of which: performing",
    "c0030": "Of which: past due > 30 days",
    "c0040": "Of which: non-performing",
    "c0050": "Of which: subject to impairment",
    "c0060": "Accumulated impairment",
    "c0070": "Net carrying amount",
    "c0080": "Of which: fossil fuel related",
    "c0090": "Of which: subject to transition risk",
    "c0100": "Number of obligors",
    "c0110": "Of which: SMEs",
    "c0120": "Weighted average maturity",
    "c0130": "Of which: <= 5 years",
    "c0140": "Of which: > 5 years and <= 10 years",
    "c0150": "Of which: > 10 years and <= 20 years",
    "c0160": "Of which: > 20 years",
}


def build_mapping(taxonomy_path: str, output_path: str = "./output/dp_mapping_k41.csv"):
    """Parse k_41.00.json and build datapoint -> (row, col, nac, label) mapping."""
    
    # Find the k_41.00.json file
    base = Path(taxonomy_path)
    # Handle the nested ~ path from 7zip extraction
    candidates = list(base.rglob("k_41.00.json"))
    if not candidates:
        raise FileNotFoundError(f"k_41.00.json not found under {taxonomy_path}")
    
    json_path = candidates[0]
    print(f"Reading: {json_path}")
    
    with open(json_path) as f:
        data = json.load(f)
    
    props = data["tableTemplates"]["K_41-00"]["columns"]["datapoint"]["propertyGroups"]
    
    rows = []
    for dp, info in props.items():
        doc = info.get("eba:documentation", {})
        cc = doc.get("cellcode", "")
        m = re.search(r'r(\d+),\s*c(\d+)', cc)
        if not m:
            continue
        
        row_code = "r" + m.group(1)
        col_code = "c" + m.group(2)
        
        # Extract NAC dimension
        dims = info.get("dimensions", {})
        nac = ""
        for k, v in dims.items():
            if "NAC" in k:
                nac = v.split(":")[-1]  # e.g. "eba_NC:B5" -> "B5"
                break
        
        nac_label = NAC_LABELS.get(nac, f"Unknown NAC: {nac}")
        col_label = COL_LABELS.get(col_code, col_code)
        is_cprs = nac in CPRS_FOSSIL_NAC
        is_total = row_code == "r0560"
        
        rows.append({
            "datapoint":   dp,
            "row_code":    row_code,
            "col_code":    col_code,
            "nac_code":    nac,
            "nac_label":   nac_label,
            "col_label":   col_label,
            "is_cprs_fossil": is_cprs,
            "is_grand_total": is_total,
            "cellcode":    cc,
        })
    
    df = pd.DataFrame(rows)
    Path(output_path).parent.mkdir(exist_ok=True)
    df.to_csv(output_path, index=False)
    
    print(f"\n✓ Mapping built: {len(df)} datapoints")
    print(f"  CPRS fossil datapoints: {df['is_cprs_fossil'].sum()}")
    print(f"  Grand total datapoints: {df['is_grand_total'].sum()}")
    print(f"✓ Saved: {output_path}")
    
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--taxonomy-path", 
        default="/Users/ariannamelissano/Downloads/Full_taxonomy_and_technical_documentation",
        help="Path to extracted Full_taxonomy_and_technical_documentation folder")
    parser.add_argument("--output", default="./output/dp_mapping_k41.csv")
    args = parser.parse_args()
    
    build_mapping(args.taxonomy_path, args.output)
