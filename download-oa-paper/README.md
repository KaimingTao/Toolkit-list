# download-oa-paper

Download a paper PDF and supplementary files from one or more PubMed IDs.

## Usage

```bash
uv run python main.py 11748933
```

Each PMID is saved into its own folder:

```text
downloads/
  11748933/
    metadata.json
    paper.pdf
    supplementary-file-1.ext
    supplementary-file-2.ext
```

## Options

```bash
uv run python main.py 11748933 31452104 -o papers
uv run python main.py 11748933 --skip-pdf
uv run python main.py 11748933 --skip-supplementary
```
