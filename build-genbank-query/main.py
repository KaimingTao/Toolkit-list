from __future__ import annotations

import argparse
import csv
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


def split_genbank_records(text: str) -> list[str]:
    records = []
    for chunk in text.split("\n//"):
        record = chunk.strip()
        if record:
            records.append(f"{record}\n//\n")
    return records


def extract_accession_from_genbank(record: str) -> str:
    match = re.search(r"^ACCESSION\s+(\S+)", record, re.MULTILINE)
    if match:
        return match.group(1)
    raise ValueError("Missing ACCESSION line in GenBank record.")


def parse_qualifier_value(raw_value: str) -> str:
    value = raw_value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_source_feature(record: str) -> dict[str, str]:
    lines = record.splitlines()
    in_features = False
    source_location = ""
    qualifiers: dict[str, str] = {}
    current_key: str | None = None

    for line in lines:
        if line.startswith("FEATURES             Location/Qualifiers"):
            in_features = True
            continue
        if not in_features:
            continue
        if line.startswith("ORIGIN") or line.startswith("BASE COUNT") or line.startswith("CONTIG"):
            break

        feature_key = line[5:21] if len(line) >= 21 else ""
        content = line[21:].rstrip() if len(line) > 21 else ""

        if source_location:
            if feature_key.strip():
                break
            if not content:
                continue
            if content.startswith("/"):
                key, _, raw_value = content[1:].partition("=")
                qualifiers[key] = parse_qualifier_value(raw_value)
                current_key = key
            elif current_key is not None:
                qualifiers[current_key] = f"{qualifiers[current_key]} {parse_qualifier_value(content)}".strip()
            continue

        if feature_key.strip() == "source":
            source_location = content.strip()

    source_data = {"source_location": source_location}
    for key, value in qualifiers.items():
        source_data[f"source_{key}"] = value
    return source_data


def write_source_csv(genbank_path: Path, output_path: Path) -> int:
    records = split_genbank_records(genbank_path.read_text())
    if not records:
        print(f"No GenBank records found in {genbank_path}", file=sys.stderr)
        return 1

    rows: list[dict[str, str]] = []
    fieldnames = ["accession", "source_location"]

    for record in records:
        accession = extract_accession_from_genbank(record)
        source_data = parse_source_feature(record)
        row = {"accession": accession, **source_data}
        rows.append(row)
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote source feature CSV for {len(records)} record(s) to {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read FASTA headers, extract GenBank accessions, and download all "
            "matching GenBank records into one file."
        )
    )
    parser.add_argument("fasta", nargs="?", type=Path, help="Input FASTA file")
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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print accession counts without downloading GenBank records",
    )
    parser.add_argument(
        "--extract-source-csv",
        type=Path,
        help="Read an existing GenBank file from --genbank-input and write source features to CSV",
    )
    parser.add_argument(
        "--genbank-input",
        type=Path,
        help="Input GenBank file used with --extract-source-csv",
    )
    args = parser.parse_args()

    if args.extract_source_csv is not None:
        if args.genbank_input is None:
            print("--genbank-input is required with --extract-source-csv", file=sys.stderr)
            return 1
        return write_source_csv(args.genbank_input, args.extract_source_csv)

    if args.fasta is None:
        print("FASTA input is required unless using --extract-source-csv.", file=sys.stderr)
        return 1

    headers = parse_fasta_headers(args.fasta)
    if not headers:
        print(f"No FASTA headers found in {args.fasta}", file=sys.stderr)
        return 1

    accessions, missing_headers = unique_accessions(headers)
    if not accessions:
        print("No recognizable accessions were found in the FASTA headers.", file=sys.stderr)
        return 1

    batch_count = len(batched(accessions, args.batch_size))
    print(
        f"Found {len(accessions)} unique accession(s) from {len(headers)} header(s); "
        f"{len(missing_headers)} header(s) skipped; {batch_count} batch(es) planned."
    )

    if args.dry_run:
        return 0

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
