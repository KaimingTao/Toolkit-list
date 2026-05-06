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

## Notes

- The script extracts one accession per FASTA header.
- Duplicate accessions are removed before download.
- Headers without a recognizable accession are skipped and reported on stderr.
- Downloads use NCBI `efetch` from the `nuccore` database with `rettype=gb`.
