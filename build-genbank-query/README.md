# build-genbank-query

Small utility to read FASTA headers, extract accessions, and download the matching
GenBank records into one combined file.

## Usage

Download records from the sample FASTA into `records.gb`:

```bash
python3 main.py example.fasta
```

Write to a different file:

```bash
python3 main.py example.fasta --output downloaded.gb
```

Control how many accessions are fetched per NCBI request:

```bash
python3 main.py example.fasta --batch-size 50
```

Dry run without downloading, just print how many accessions were found:

```bash
python3 main.py example.fasta --dry-run
```

Extract the `source` feature from a downloaded GenBank file into CSV:

```bash
python3 main.py --genbank-input records.gb --extract-source-csv source.csv
```

## Notes

- The script extracts one accession per FASTA header.
- Duplicate accessions are removed before download.
- `--dry-run` prints the number of unique accessions, skipped headers, and planned batches.
- Headers without a recognizable accession are skipped and reported on stderr.
- Downloads use NCBI `efetch` from the `nuccore` database with `rettype=gb`.
- `--extract-source-csv` writes a CSV with `accession`, `source_location`, and the raw `source_feature` block from `FEATURES`.
