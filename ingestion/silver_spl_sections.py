"""Extract clinically relevant label sections from SPL XML into silver, for retrieval."""
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

V = "{urn:hl7-org:v3}"
RAW_DIR = Path("data/raw/spl")
SILVER_DIR = Path("data/silver")

KEEP_SECTIONS = {
    "34066-1": "Boxed Warning",
    "34067-9": "Indications and Usage",
    "34068-7": "Dosage and Administration",
    "43678-2": "Dosage Forms and Strengths",
    "34070-3": "Contraindications",
    "43685-7": "Warnings and Precautions",
    "34071-1": "Warnings",
    "42232-9": "Precautions",
    "34073-7": "Drug Interactions",
    "34089-3": "Description",
    "34069-5": "How Supplied / Storage and Handling",
}


def clean_text(element):
    return " ".join("".join(element.itertext()).split())


def kept_sections(element):
    for child in element:
        if child.tag == f"{V}section":
            code = child.find(f"{V}code")
            section_code = code.get("code") if code is not None else None
            if section_code in KEEP_SECTIONS:
                yield section_code, child
                continue
        yield from kept_sections(child)


def product_label(root):
    name = root.findtext(f".//{V}manufacturedProduct/{V}name")
    generic = root.findtext(f".//{V}genericMedicine/{V}name")
    name = name.strip() if name else None
    generic = generic.strip().lower() if generic else None
    if name and generic and name.lower() != generic:
        return f"{name} ({generic})"
    return name or generic


def parse_label(path):
    root = ET.parse(path).getroot()
    label = product_label(root)
    rows = []
    for index, (section_code, section) in enumerate(kept_sections(root)):
        text = clean_text(section)
        if not text:
            continue
        rows.append({
            "section_id": f"{path.stem}|{section_code}|{index}",
            "spl_set_id": path.stem,
            "product_label": label,
            "section_code": section_code,
            "section_name": KEEP_SECTIONS[section_code],
            "text": text,
            "char_count": len(text),
        })
    return rows


def main():
    rows = []
    for path in sorted(RAW_DIR.glob("*.xml")):
        rows.extend(parse_label(path))
    sections = pd.DataFrame(rows)

    print(f"Sections extracted: {len(sections)} from {sections['spl_set_id'].nunique()} labels")
    print(f"Duplicate section_ids: {sections['section_id'].duplicated().sum()}")
    print(f"Labels missing a product name: {sections.loc[sections['product_label'].isna(), 'spl_set_id'].nunique()}")
    print("\nSections by type:")
    print(sections["section_name"].value_counts().to_string())
    print("\nCharacters per section:")
    print(sections["char_count"].describe(percentiles=[0.5, 0.9, 0.99]).round(0).to_string())

    SILVER_DIR.mkdir(parents=True, exist_ok=True)
    sections.to_parquet(SILVER_DIR / "spl_sections.parquet", index=False)
    print(f"\nSaved spl_sections ({len(sections)})")


if __name__ == "__main__":
    main()