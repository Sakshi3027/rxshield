"""NDC parsing helpers shared across sources."""
import re

NDC_PATTERN = re.compile(r"\b\d{4,5}-\d{3,4}-\d{1,2}\b")


def extract_ndcs(text):
    return set(NDC_PATTERN.findall(text or ""))


def to_product_ndc(package_ndc):
    return "-".join(package_ndc.split("-")[:2])