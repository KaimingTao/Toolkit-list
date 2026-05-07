# build-genbank-query

Small utility to read FASTA headers, extract accessions, download the matching
GenBank records into one combined file, and parse each record's `FEATURES.source`
into a CSV.

## Usage

Download records from the sample FASTA into `records.gb` and `source.csv`:

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
python3 main.py --genbank-input records.gb
```

Write the parsed source CSV to a different path:

```bash
python3 main.py --genbank-input records.gb --extract-source-csv custom-source.csv
```

## Notes

- The script extracts one accession per FASTA header.
- Duplicate accessions are removed before download.
- `--dry-run` prints the number of unique accessions, skipped headers, and planned batches.
- Headers without a recognizable accession are skipped and reported on stderr.
- Downloads use NCBI `efetch` from the `nuccore` database with `rettype=gb`.
- Default FASTA mode writes both `records.gb` and `source.csv`.
- `--genbank-input` parses each GenBank record's `FEATURES` section and writes one CSV row per record keyed by `accession`.
- The default CSV output path is `source.csv`; override it with `--extract-source-csv`.
- The CSV always includes `accession` and `source_location`, then adds `source_*` columns for any parsed source qualifiers such as `source_organism`, `source_mol_type`, and `source_db_xref`.
