#!/usr/bin/env python3
"""
Align a reference protein FASTA to the best-matching translated region
from a query DNA FASTA, then export the query amino acid found at each
reference protein position into a CSV file.

Usage:
    uv run python align_protein_from_dna.py ref_protein.fasta query_dna.fasta output.csv
"""

from __future__ import annotations

import csv
import sys
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from Bio import SeqIO
from Bio.Align import PairwiseAligner
from Bio.Seq import Seq


@dataclass
class FastaRecord:
    name: str
    sequence: str


@dataclass
class FrameTranslation:
    strand: str
    frame: int
    protein: str
    codons: List[str]
    starts: List[int]
    ends: List[int]


@dataclass
class AlignmentResult:
    score: float
    ref_aligned: str
    query_aligned: str
    ref_start: int
    ref_end: int
    query_start: int
    query_end: int


def read_single_fasta(path: str) -> FastaRecord:
    records = list(SeqIO.parse(path, "fasta"))
    if not records:
        raise ValueError(f"{path} does not contain a FASTA record.")
    if len(records) != 1:
        raise ValueError(f"{path} contains more than one FASTA record; expected one.")
    record = records[0]
    sequence = str(record.seq).replace(" ", "").upper()
    if not sequence:
        raise ValueError(f"{path} contains an empty sequence.")
    return FastaRecord(name=record.id, sequence=sequence)


def translate_frame(dna: str, strand: str, frame: int) -> FrameTranslation:
    dna_seq = Seq(dna)
    if strand == "+":
        working = dna_seq
        offset = frame
        total_len = len(dna)

        def coords(idx: int) -> Tuple[int, int]:
            start = offset + idx * 3
            return start + 1, start + 3
    else:
        working = dna_seq.reverse_complement()
        offset = frame
        total_len = len(dna)

        def coords(idx: int) -> Tuple[int, int]:
            rc_start = offset + idx * 3
            rc_end = rc_start + 2
            orig_start = total_len - rc_end
            orig_end = total_len - rc_start
            return orig_start, orig_end

    trimmed_len = ((len(working) - offset) // 3) * 3
    coding_seq = working[offset:offset + trimmed_len]
    protein = str(coding_seq.translate())

    codons: List[str] = []
    starts: List[int] = []
    ends: List[int] = []
    for idx in range(len(protein)):
        start_nt = offset + idx * 3
        codons.append(str(working[start_nt:start_nt + 3]).upper())
        start, end = coords(idx)
        starts.append(start)
        ends.append(end)

    return FrameTranslation(
        strand=strand,
        frame=frame + 1,
        protein=protein,
        codons=codons,
        starts=starts,
        ends=ends,
    )


def build_aligner() -> PairwiseAligner:
    aligner = PairwiseAligner(mode="local")
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -2.0
    aligner.extend_gap_score = -2.0
    return aligner


def alignment_to_strings(ref: str, query: str, alignment) -> AlignmentResult:
    coords = alignment.coordinates
    ref_parts: List[str] = []
    query_parts: List[str] = []

    for block in range(coords.shape[1] - 1):
        ref_start = int(coords[0][block])
        ref_end = int(coords[0][block + 1])
        query_start = int(coords[1][block])
        query_end = int(coords[1][block + 1])
        ref_step = ref_end - ref_start
        query_step = query_end - query_start

        if ref_step > 0 and query_step > 0:
            ref_parts.append(ref[ref_start:ref_end])
            query_parts.append(query[query_start:query_end])
        elif ref_step > 0:
            ref_parts.append(ref[ref_start:ref_end])
            query_parts.append("-" * ref_step)
        elif query_step > 0:
            ref_parts.append("-" * query_step)
            query_parts.append(query[query_start:query_end])

    return AlignmentResult(
        score=alignment.score,
        ref_aligned="".join(ref_parts),
        query_aligned="".join(query_parts),
        ref_start=int(coords[0][0]),
        ref_end=int(coords[0][-1]),
        query_start=int(coords[1][0]),
        query_end=int(coords[1][-1]),
    )


def pick_best_translation(ref_protein: str, dna: str) -> Tuple[FrameTranslation, AlignmentResult]:
    aligner = build_aligner()
    best_frame = None
    best_alignment = None

    for strand in ("+", "-"):
        for frame in range(3):
            translated = translate_frame(dna, strand=strand, frame=frame)
            alignments = aligner.align(ref_protein, translated.protein)
            if not alignments:
                continue
            alignment = alignment_to_strings(ref_protein, translated.protein, alignments[0])
            if best_alignment is None or alignment.score > best_alignment.score:
                best_frame = translated
                best_alignment = alignment

    if best_frame is None or best_alignment is None or best_alignment.score <= 0:
        raise ValueError("No protein-like match was found between reference protein and query DNA.")
    return best_frame, best_alignment


def build_position_table(
    translated: FrameTranslation,
    alignment: AlignmentResult,
) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    ref_index = alignment.ref_start
    query_index = alignment.query_start

    for ref_aa, query_aa in zip(alignment.ref_aligned, alignment.query_aligned):
        ref_pos = None

        if ref_aa != "-":
            ref_pos = ref_index + 1
            ref_index += 1
        if query_aa != "-":
            query_index += 1

        if ref_pos is None:
            continue

        query_value = query_aa if query_aa != "-" else "-"
        diff = "0" if ref_aa == query_value else "1"
        if diff == "0":
            continue
        rows.append(
            {
                "pos": str(ref_pos),
                "ref": ref_aa,
                "query_aa": query_value,
                "diff": diff,
            }
        )

    return rows


def write_position_csv(
    output_csv: str,
    rows: Sequence[Dict[str, str]],
) -> None:
    fieldnames = ["pos", "ref", "query_aa", "diff"]
    with open(output_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_result(
    ref_record: FastaRecord,
    query_record: FastaRecord,
    translated: FrameTranslation,
    alignment: AlignmentResult,
    rows: Sequence[Dict[str, str]],
) -> None:
    print(f"Reference protein: {ref_record.name}")
    print(f"Query DNA: {query_record.name}")
    print(f"Best strand/frame: {translated.strand}{translated.frame}")
    print(f"Alignment score: {alignment.score:.1f}")
    print()
    print("Protein alignment:")
    print(f"aligned_ref ({len(alignment.ref_aligned)} aa):")
    print(alignment.ref_aligned)
    print(f"aligned_query ({len(alignment.query_aligned)} aa):")
    print(alignment.query_aligned)
    print()
    print("Per-reference-position result:")
    print("pos,ref,query_aa,diff")
    for row in rows:
        print(",".join([row["pos"], row["ref"], row["query_aa"], row["diff"]]))


def main(argv: Sequence[str]) -> int:
    if len(argv) != 4:
        print(
            "Usage: uv run python align_protein_from_dna.py ref_protein.fasta query_dna.fasta output.csv",
            file=sys.stderr,
        )
        return 1

    ref_path, query_path, output_csv = argv[1], argv[2], argv[3]

    ref_record = read_single_fasta(ref_path)
    query_record = read_single_fasta(query_path)

    invalid_protein = set(ref_record.sequence) - set("ACDEFGHIKLMNPQRSTVWYBXZJUO*")
    if invalid_protein:
        raise ValueError(f"Reference protein contains invalid characters: {sorted(invalid_protein)}")

    invalid_dna = set(query_record.sequence) - set("ACGTRYSWKMBDHVN")
    if invalid_dna:
        raise ValueError(f"Query DNA contains invalid characters: {sorted(invalid_dna)}")

    translated, alignment = pick_best_translation(ref_record.sequence, query_record.sequence)
    rows = build_position_table(translated, alignment)
    write_position_csv(output_csv, rows)
    print_result(ref_record, query_record, translated, alignment, rows)
    print()
    print(f"CSV saved to: {output_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
