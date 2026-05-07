from __future__ import annotations

import argparse
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


ACCESSION_PATTERN = re.compile(r"^([A-Za-z_]+)(\d+)$")
EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def expand_accessions(accession_string: str) -> list[str]:
    expanded: list[str] = []

    for part in accession_string.split(","):
        token = part.strip()
        if not token:
            continue

        if "-" not in token:
            expanded.append(token)
            continue

        start_token, end_token = [item.strip() for item in token.split("-", maxsplit=1)]
        start_prefix, start_number = parse_accession(start_token)
        end_prefix, end_number = parse_accession(end_token)

        if start_prefix != end_prefix:
            raise ValueError(f"Mismatched accession prefixes: {start_token} and {end_token}")
        if len(start_number) != len(end_number):
            raise ValueError(f"Mismatched accession widths: {start_token} and {end_token}")

        start_value = int(start_number)
        end_value = int(end_number)
        if start_value > end_value:
            raise ValueError(f"Invalid accession range: {start_token}-{end_token}")

        width = len(start_number)
        for value in range(start_value, end_value + 1):
            expanded.append(f"{start_prefix}{value:0{width}d}")

    return expanded


def parse_accession(accession: str) -> tuple[str, str]:
    match = ACCESSION_PATTERN.match(accession)
    if not match:
        raise ValueError(f"Invalid accession format: {accession}")
    return match.group(1), match.group(2)


def genbank_to_fasta(genbank_text: str) -> str:
    fasta_entries: list[str] = []

    for record in genbank_text.split("\n//"):
        record = record.strip()
        if not record:
            continue

        accession_match = re.search(r"^ACCESSION\s+(\S+)", record, re.MULTILINE)
        origin_match = re.search(r"^ORIGIN\s*\n(.*)$", record, re.MULTILINE | re.DOTALL)

        if not accession_match or not origin_match:
            continue

        accession = accession_match.group(1)
        sequence = "".join(re.findall(r"[A-Za-z]+", origin_match.group(1))).upper()
        if not sequence:
            continue

        fasta_entries.append(f">{accession}\n{wrap_sequence(sequence)}")

    if not fasta_entries:
        raise ValueError("No FASTA entries could be generated from the combined GenBank file")

    return "\n".join(fasta_entries) + "\n"


def wrap_sequence(sequence: str, width: int = 80) -> str:
    return "\n".join(sequence[index : index + width] for index in range(0, len(sequence), width))


def download_genbank_record(accession: str, output_dir: Path, email: str, delay_seconds: float) -> Path:
    params = urlencode(
        {
            "db": "nuccore",
            "id": accession,
            "rettype": "gb",
            "retmode": "text",
            "tool": "codex-accession-downloader",
            "email": email,
        }
    )
    url = f"{EUTILS_BASE_URL}?{params}"

    try:
        with urlopen(url) as response:
            content = response.read().decode("utf-8")
    except HTTPError as error:
        raise RuntimeError(f"HTTP error downloading {accession}: {error.code}") from error
    except URLError as error:
        raise RuntimeError(f"Network error downloading {accession}: {error.reason}") from error

    if not content.strip() or "Error occurred" in content:
        raise RuntimeError(f"NCBI returned an invalid response for {accession}")

    output_path = output_dir / f"{accession}.gb"
    output_path.write_text(content, encoding="utf-8")
    time.sleep(delay_seconds)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expand accession ranges and download GenBank records from NCBI."
    )
    parser.add_argument(
        "accessions",
        help='Accession string such as "KY608620-KY608627, KY608632"',
    )
    parser.add_argument(
        "--output-dir",
        default="genbank_downloads",
        help="Directory where downloaded .gb files will be saved.",
    )
    parser.add_argument(
        "--email",
        default="anonymous@example.com",
        help="Contact email passed to NCBI E-utilities.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.34,
        help="Delay in seconds between requests to stay within NCBI rate limits.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    accessions = expand_accessions(args.accessions)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    combined_output_path = output_dir / "combined.gb"
    fasta_output_path = output_dir / "combined.fasta"
    combined_records: list[str] = []

    print(f"Count: {len(accessions)}")

    for accession in accessions:
        output_path = download_genbank_record(
            accession=accession,
            output_dir=output_dir,
            email=args.email,
            delay_seconds=args.delay,
        )
        combined_records.append(output_path.read_text(encoding="utf-8").rstrip())
        print(f"Saved {accession} to {output_path}")

    combined_output_path.write_text("\n\n".join(combined_records) + "\n", encoding="utf-8")
    print(f"Saved combined GenBank file to {combined_output_path}")
    fasta_output_path.write_text(
        genbank_to_fasta(combined_output_path.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    print(f"Saved FASTA file to {fasta_output_path}")


if __name__ == "__main__":
    main()
