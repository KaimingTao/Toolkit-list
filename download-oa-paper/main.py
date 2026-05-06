from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

IDCONV_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
PMC_ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/"
SUPPL_BASE_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/supplmat.cgi"
DEFAULT_TIMEOUT = 60
REQUEST_PAUSE_SECONDS = 2
USER_AGENT = "download-oa-paper/0.1.0"
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
PDF_META_RE = re.compile(
    r'<meta\s+name="citation_pdf_url"\s+content="([^"]+)"',
    re.IGNORECASE,
)


class DownloadError(Exception):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Given one or more PMIDs, download the paper PDF if available and "
            "any supplementary files into PMID-named folders."
        )
    )
    parser.add_argument("pmid", nargs="+", help="PubMed ID, for example: 11748933")
    parser.add_argument(
        "-o",
        "--outdir",
        default="downloads",
        help="Base output directory. A subfolder per PMID will be created here.",
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="Skip downloading the main paper PDF.",
    )
    parser.add_argument(
        "--skip-supplementary",
        action="store_true",
        help="Skip downloading supplementary files.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Only print resolved PDF and supplementary URLs without downloading files.",
    )
    return parser


def sanitize_filename(name: str) -> str:
    cleaned = SAFE_FILENAME_RE.sub("_", name.strip())
    return cleaned or "downloaded_file"


def normalize_pmcid(value: str) -> str:
    raw = value.strip().upper()
    if raw.isdigit():
        raw = f"PMC{raw}"
    if not re.fullmatch(r"PMC\d+", raw):
        raise DownloadError(f"Invalid PMCID received: {value}")
    return raw


def build_request_url(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params, doseq=True)}"


def run_curl(url: str, *, output_path: Path | None = None) -> tuple[bytes, str]:
    time.sleep(REQUEST_PAUSE_SECONDS)
    command = [
        "curl",
        "--location",
        "--fail",
        "--silent",
        "--show-error",
        "--max-time",
        str(DEFAULT_TIMEOUT),
        "--user-agent",
        USER_AGENT,
        "--write-out",
        "\n%{url_effective}",
    ]
    if output_path is None:
        command.extend(["--output", "-"])
    else:
        command.extend(["--output", str(output_path)])
    command.append(url)

    try:
        result = subprocess.run(command, capture_output=True, check=True)
    except FileNotFoundError as exc:
        raise DownloadError("curl is required but was not found on PATH") from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace").strip()
        message = stderr or f"curl failed for {url}"
        raise DownloadError(message) from exc

    stdout = result.stdout
    body, _, effective_url = stdout.rpartition(b"\n")
    final_url = effective_url.decode("utf-8", errors="replace").strip() or url
    return body, final_url


def http_get(url: str, params: dict[str, Any] | None = None) -> bytes:
    request_url = build_request_url(url, params)
    try:
        body, _ = run_curl(request_url)
        return body
    except DownloadError as exc:
        raise DownloadError(f"Network error for {request_url}: {exc}") from exc


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    return json.loads(http_get(url, params=params).decode("utf-8"))


def resolve_pmcid(pmid: str) -> str | None:
    data = fetch_json(IDCONV_URL, {"ids": pmid, "format": "json"})
    records = data.get("records", [])
    if not records:
        return None

    record = records[0]
    pmcid = record.get("pmcid")
    if not pmcid:
        return None
    return normalize_pmcid(pmcid)


def fetch_oa_xml(pmcid: str) -> ET.Element:
    return ET.fromstring(http_get(OA_URL, params={"id": pmcid}).decode("utf-8"))


def fetch_article_html(pmcid: str) -> str:
    return http_get(f"{PMC_ARTICLE_URL}{pmcid}/").decode("utf-8", errors="replace")


def normalize_download_url(url: str) -> str:
    if url.startswith("ftp://ftp.ncbi.nlm.nih.gov/"):
        return "https://ftp.ncbi.nlm.nih.gov/" + url.removeprefix("ftp://ftp.ncbi.nlm.nih.gov/")
    if url.startswith("/"):
        return "https://pmc.ncbi.nlm.nih.gov" + url
    return url


def find_pdf_link(root: ET.Element) -> str | None:
    for link in root.findall(".//link"):
        if (link.get("format") or "").lower() != "pdf":
            continue
        href = link.get("href")
        if href:
            return normalize_download_url(href)
    return None


def find_pdf_link_in_article_html(html: str) -> str | None:
    match = PDF_META_RE.search(html)
    if not match:
        return None
    return normalize_download_url(match.group(1))


def fetch_supplementary_list(pmcid: str) -> list[dict[str, str]]:
    url = f"{SUPPL_BASE_URL}/BioC_JSON/{pmcid}/LIST"
    data = json.loads(http_get(url).decode("utf-8"))
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if isinstance(data, list):
        for record in data:
            if not isinstance(record, dict):
                continue

            original_url = record.get("original_file")
            tar_url = record.get("tar_dir")
            source_url = normalize_download_url(original_url or tar_url)
            if not source_url:
                continue

            filename = Path(source_url).name
            key = (filename, source_url)
            if key in seen:
                continue

            seen.add(key)
            items.append({"filename": filename, "url": source_url})

    return items


def resolve_pdf_url(pmcid: str) -> str | None:
    root = fetch_oa_xml(pmcid)
    pdf_url = find_pdf_link(root)
    if not pdf_url:
        article_html = fetch_article_html(pmcid)
        pdf_url = find_pdf_link_in_article_html(article_html)
    return pdf_url


def process_pmid(
    pmid: str,
    root_outdir: Path,
    *,
    skip_pdf: bool,
    skip_supplementary: bool,
    print_only: bool,
) -> int:
    pmid = pmid.strip()
    if not pmid.isdigit():
        print(f"{pmid}: invalid PMID, expected digits only", file=sys.stderr)
        return 1

    outdir = root_outdir / pmid
    if not print_only:
        outdir.mkdir(parents=True, exist_ok=True)

    try:
        pmcid = resolve_pmcid(pmid)
    except Exception as exc:
        print(f"{pmid}: failed to resolve PMCID: {exc}", file=sys.stderr)
        return 1

    if not pmcid:
        print(f"{pmid}: no PMCID found")
        return 1

    print(f"{pmid}: resolved to {pmcid}")

    if not print_only:
        metadata = {"pmid": pmid, "pmcid": pmcid}
        (outdir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    errors = 0

    if not skip_pdf:
        try:
            pdf_url = resolve_pdf_url(pmcid)
            if pdf_url is None:
                print(f"{pmid}: PDF not available from PMC OA service")
            else:
                print(f"{pmid}: PDF download URL: {pdf_url}")
        except Exception as exc:
            errors += 1
            print(f"{pmid}: failed to resolve PDF URL: {exc}", file=sys.stderr)

    if not skip_supplementary:
        try:
            files = fetch_supplementary_list(pmcid)
            if not files:
                print(f"{pmid}: no supplementary files found")
            else:
                print(f"{pmid}: found {len(files)} supplementary files")
                for file_info in files:
                    print(f"{pmid}: supplementary download URL: {file_info['url']}")
        except Exception as exc:
            errors += 1
            print(f"{pmid}: failed to list supplementary files: {exc}", file=sys.stderr)

    return 1 if errors else 0


def main() -> int:
    args = build_parser().parse_args()
    root_outdir = Path(args.outdir)
    root_outdir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for pmid in args.pmid:
        exit_code = max(
            exit_code,
            process_pmid(
                pmid,
                root_outdir,
                skip_pdf=args.skip_pdf,
                skip_supplementary=args.skip_supplementary,
                print_only=args.print_only,
            ),
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
