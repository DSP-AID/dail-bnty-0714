#!/usr/bin/env python3
"""Near-duplicate decontamination scan for the Name That LLM open pool (bnty_0699 / bnty_0714).

Scans pool passages and pool prompts against competition inputs and reports every
near-duplicate pair above the configured thresholds. Pure Python 3 stdlib, no
third-party packages, deterministic: same inputs always produce identical counts.

Method
------
- Normalize text: Unicode NFKC, casefold, underscores to spaces, tokenize as
  runs of unicode word characters (punctuation and quotes act as separators).
- Represent each document as the set of its word n-gram shingles
  (default n=5 for passages, n=3 for prompts; a document with fewer than n
  words yields a single shingle of all its words).
- Near-duplicate score = Jaccard similarity |A n B| / |A u B| over shingle sets.
- Candidate search uses prefix filtering on an inverted index of the reference
  side ordered by ascending global document frequency. Any pair with
  Jaccard >= min(thresholds) is guaranteed to be found (checked against a
  brute-force scan in tests/test_decontam_scan.py), and every reported score is
  recomputed exactly from full shingle sets - no approximation error.
- Shingles are stored as 64-bit blake2b hashes; collision probability across a
  ~50M-shingle run is < 1e-8 (noted in the report).

Output: JSON summary (--out) with per-comparison counts at each threshold,
matched pairs (capped by --max-pairs-json, sorted by score desc then ids), and
an optional uncapped full pairs CSV (--pairs-csv).

Usage (defaults point at the data/ directory shipped in this repo):
    python decontam_scan.py --out report/scan_results.json
"""

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import re
import sys
import unicodedata
from collections import Counter

TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def normalize(text):
    """NFKC, casefold, underscores to spaces. Deterministic across platforms."""
    if text is None:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    t = t.casefold().replace("_", " ")
    return t


def tokenize(text):
    return TOKEN_RE.findall(normalize(text))


def shingle_ids(tokens, n):
    """Set of 64-bit int hashes of word n-gram shingles (see module docstring)."""
    if not tokens:
        return set()
    if len(tokens) < n:
        grams = [tuple(tokens)]
    else:
        grams = zip(*[tokens[i:] for i in range(n)])
    out = set()
    for g in grams:
        h = hashlib.blake2b("\x1f".join(g).encode("utf-8"), digest_size=8)
        out.add(int.from_bytes(h.digest(), "big"))
    return out


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b) if len(a) < len(b) else len(b & a)
    union = len(a) + len(b) - inter
    return inter / union if union else 0.0


def open_text(path):
    """Open a text file, transparently gunzipping when the magic bytes say so."""
    raw = open(path, "rb")
    head = raw.read(2)
    raw.seek(0)
    if head == b"\x1f\x8b":
        return io.TextIOWrapper(gzip.GzipFile(fileobj=raw), encoding="utf-8", newline="")
    return io.TextIOWrapper(raw, encoding="utf-8", newline="")


def read_rows(path, required):
    """Stream a CSV (optionally gzipped) yielding dicts; error if columns missing.

    Header validation happens when the generator is first advanced.
    """
    def gen():
        with open_text(path) as f:
            reader = csv.DictReader(f)
            cols = reader.fieldnames or []
            missing = [c for c in required if c not in cols]
            if missing:
                raise SystemExit(f"{path}: missing columns {missing}; found {cols}")
            yield from reader
    return gen()


class Doc:
    __slots__ = ("doc_id", "shingles")

    def __init__(self, doc_id, shingles):
        self.doc_id = doc_id
        self.shingles = shingles


def build_index(ref_docs, threshold):
    """Inverted index of reference-side shingles under prefix filtering.

    Shingles are ordered by ascending global document frequency over ALL docs
    (reference and query). A doc indexes only its p(s) = s - ceil(t*s) + 1
    rarest shingles; a query probes its own p(q)-rarest. If J(Q,R) >= t the
    prefixes must share at least one shingle, so no true match is missed.
    Returns (postings: {shingle: [ref_idx,...]}, df: {shingle: count}).
    """
    df = Counter()
    for doc in ref_docs:
        df.update(doc.shingles)
    postings = {}
    for i, doc in enumerate(ref_docs):
        if not doc.shingles:
            continue
        s = len(doc.shingles)
        p = max(1, s - math.ceil(threshold * s) + 1)
        prefix = sorted(doc.shingles, key=lambda x: (df[x], x))[:p]
        for sh in prefix:
            postings.setdefault(sh, []).append(i)
    return postings, df


def compare_all(query_docs, ref_docs, thresholds):
    """Scan once at the minimum threshold, bucket hits into all thresholds.

    query_docs may be any iterable of Doc (streamed, so memory stays O(reference)).
    Returns (hits, buckets, query_row_count).
    """
    tmin = min(thresholds)
    postings, df = build_index(ref_docs, tmin)
    ref_sizes = [len(d.shingles) for d in ref_docs]
    hits = []
    q_rows = 0
    for qi, q in enumerate(query_docs):
        q_rows += 1
        qs = len(q.shingles)
        if not q.shingles:
            continue
        lo = math.ceil(tmin * qs)
        hi = qs / tmin
        p = max(1, qs - math.ceil(tmin * qs) + 1)
        prefix = sorted(q.shingles, key=lambda x: (df.get(x, 0), x))[:p]
        cand = set()
        for sh in prefix:
            lst = postings.get(sh)
            if lst:
                cand.update(lst)
        for ri in cand:
            rsz = ref_sizes[ri]
            if rsz < lo or rsz > hi:
                continue
            j = jaccard(q.shingles, ref_docs[ri].shingles)
            if j >= tmin:
                hits.append((q.doc_id, ref_docs[ri].doc_id, j))
    hits.sort(key=lambda h: (-h[2], h[0], h[1]))
    res = {}
    for t in sorted(thresholds, reverse=True):
        sel = [h for h in hits if h[2] >= t - 1e-9]
        res[f"{t:g}"] = {
            "pairs": len(sel),
            "distinct_query_rows": len({h[0] for h in sel}),
            "distinct_reference_rows": len({h[1] for h in sel}),
        }
    return hits, res, q_rows


def load_side(path, id_col, text_col, n):
    """Yield Doc objects, one CSV row at a time (streaming)."""
    for i, r in enumerate(read_rows(path, [id_col, text_col])):
        doc_id = (r.get(id_col) or f"row{i}").strip() or f"row{i}"
        yield Doc(doc_id, shingle_ids(tokenize(r.get(text_col) or ""), n))


def run(args):
    thresholds = [float(x) for x in args.thresholds.split(",")]
    comparisons = []
    all_pairs = []

    def do(name, q_path, q_id, q_text, q_n, r_path, r_id, r_text, r_n, note=""):
        if not (q_path and r_path):
            return
        r_docs = list(load_side(r_path, r_id, r_text, r_n))
        hits, buckets, q_rows = compare_all(load_side(q_path, q_id, q_text, q_n), r_docs, thresholds)
        entry = {
            "name": name,
            "note": note,
            "query_file": q_path,
            "reference_file": r_path,
            "shingle_n_words": q_n,
            "query_rows": q_rows,
            "reference_rows": len(r_docs),
            "counts_by_threshold": buckets,
            "pairs": [
                {
                    "score": round(h[2], 6),
                    "query_id": h[0],
                    "reference_id": h[1],
                }
                for h in hits[: args.max_pairs_json]
            ],
        }
        comparisons.append(entry)
        for h in hits:
            all_pairs.append(
                {
                    "comparison": name,
                    "score": round(h[2], 6),
                    "query_id": h[0],
                    "reference_id": h[1],
                }
            )
        print(
            f"[{name}] query={q_rows} reference={len(r_docs)} "
            + " ".join(f"J>={t:g}:{buckets[f'{t:g}']['pairs']}" for t in sorted(thresholds, reverse=True)),
            file=sys.stderr,
        )

    do(
        "pool_passages_vs_train",
        args.pool_passages, args.pool_id, args.pool_text, args.n_passage,
        args.train, args.train_id, args.train_text, args.n_passage,
        note="competition train.csv passages (official)",
    )
    do(
        "pool_passages_vs_test_public_examples",
        args.pool_passages, args.pool_id, args.pool_text, args.n_passage,
        args.test, args.test_id, args.test_text, args.n_passage,
        note="test.csv as published publicly: example rows only; hidden test not public",
    )
    do(
        "pool_prompts_vs_train_prompts_reconstructed",
        args.pool_prompts, args.prompt_canon_col, args.prompt_text_col, args.n_prompt,
        args.train_prompts, args.recon_id, args.recon_text, args.n_prompt,
        note="community-reconstructed train prompt texts (official prompt text is not public)",
    )
    do(
        "train_vs_test_public_examples",
        args.train, args.train_id, args.train_text, args.n_passage,
        args.test, args.test_id, args.test_text, args.n_passage,
        note="sanity check between the two competition files themselves",
    )

    summary = {
        "tool": "decontam_scan",
        "version": "1.0",
        "method": (
            "normalized word n-gram Jaccard near-duplicate scan with exact "
            "prefix-filter inverted-index candidate generation (see README)"
        ),
        "thresholds": sorted(thresholds, reverse=True),
        "comparisons": comparisons,
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False)
        f.write("\n")
    if args.pairs_csv:
        with open(args.pairs_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["comparison", "score", "query_id", "reference_id"])
            w.writeheader()
            w.writerows(all_pairs)
    print(json.dumps({c["name"]: c["counts_by_threshold"] for c in comparisons}, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    d = "data/"
    ap.add_argument("--pool-passages", default=d + "pool_passages.csv.gz")
    ap.add_argument("--pool-prompts", default=d + "pool_prompts.csv.gz")
    ap.add_argument("--train", default=d + "train.csv")
    ap.add_argument("--test", default=d + "test_public_examples.csv")
    ap.add_argument("--train-prompts", default=d + "train_prompts_reconstructed.csv")
    ap.add_argument("--pool-id", default="id")
    ap.add_argument("--pool-text", default="text")
    ap.add_argument("--prompt-canon-col", default="prompt_canon")
    ap.add_argument("--prompt-text-col", default="prompt_text")
    ap.add_argument("--train-id", default="id")
    ap.add_argument("--train-text", default="text")
    ap.add_argument("--test-id", default="id")
    ap.add_argument("--test-text", default="text")
    ap.add_argument("--recon-id", default="prompt_id")
    ap.add_argument("--recon-text", default="inferred_prompt")
    ap.add_argument("--n-passage", type=int, default=5, dest="n_passage")
    ap.add_argument("--n-prompt", type=int, default=3, dest="n_prompt")
    ap.add_argument("--thresholds", default="0.6,0.8,1.0")
    ap.add_argument("--max-pairs-json", type=int, default=200)
    ap.add_argument("--out", default="scan_results.json")
    ap.add_argument("--pairs-csv", default=None)
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
