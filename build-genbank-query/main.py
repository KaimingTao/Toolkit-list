from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ACCESSION_PATTERNS = (
    re.compile(r"\b(?:[A-Z]{1,2}_)?[A-Z]{1,2}\d{5,8}(?:\.\d+)?\b"),
    re.compile(r"\b(?:NC|NG|NM|NP|NR|NT|NW|XM|XP|XR|WP|AP|AC|CP|AE|BK|CM)_\d+(?:\.\d+)?\b"),
)
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def parse_fasta_headers(path: Path) -> list[str]:
    headers: list[str] = []
    with path.open() as handle:
        for line in handle:
            if line.startswith(">"):
                headers.append(line[1:].strip())
    return headers


def extract_accession(header: str) -> str | None:
    first_token = header.split()[0]
    for pattern in ACCESSION_PATTERNS:
        match = pattern.search(first_token)
        if match:
            return match.group(0)

    for pattern in ACCESSION_PATTERNS:
        match = pattern.search(header)
        if match:
            return match.group(0)

    return None


def unique_accessions(headers: list[str]) -> tuple[list[str], list[str]]:
    found: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    for header in headers:
        accession = extract_accession(header)
        if accession is None:
            missing.append(header)
            continue
        if accession not in seen:
            seen.add(accession)
            found.append(accession)

    return found, missing


def batched(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def fetch_genbank_records(accessions: list[str], batch_size: int) -> str:
    chunks: list[str] = []
    for batch in batched(accessions, batch_size):
        query = urlencode(
            {
                "db": "nuccore",
                "id": ",".join(batch),
                "rettype": "gb",
                "retmode": "text",
            }
        )
        with urlopen(f"{EFETCH_URL}?{query}") as response:
            chunks.append(response.read().decode("utf-8"))
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read FASTA headers, extract GenBank accessions, and download all "
            "matching GenBank records into one file."
        )
    )
    parser.add_argument("fasta", type=Path, help="Input FASTA file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("records.gb"),
        help="Output file for combined GenBank records",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of accessions to fetch per NCBI request",
    )
    args = parser.parse_args()

    headers = parse_fasta_headers(args.fasta)
    if not headers:
        print(f"No FASTA headers found in {args.fasta}", file=sys.stderr)
        return 1

    accessions, missing_headers = unique_accessions(headers)
    if not accessions:
        print("No recognizable accessions were found in the FASTA headers.", file=sys.stderr)
        return 1

    genbank_text = fetch_genbank_records(accessions, args.batch_size)
    args.output.write_text(genbank_text)

    print(f"Downloaded {len(accessions)} GenBank record(s) to {args.output}")
    if missing_headers:
        print(
            f"Skipped {len(missing_headers)} header(s) without a recognizable accession.",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
