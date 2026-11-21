#!/usr/bin/env python3
"""Self-check for decontam_scan: margin analysis + injected-positives sensitivity.

Runs on the data/ shipped in this repo only (no network, no Kaggle token):

A. Margin - how far apart real pool and competition rows are:
   seeded 60k-passage sample vs train.csv, all pool prompts vs reconstructed
   train prompts; prints bucket counts down to J=0.15/0.2 and the top scores.
B. Sensitivity - proof the detector fires on true near-duplicates:
   60 real train passages perturbed three ways (exact copy / ~4% scattered word
   drop / padded + one word substituted) are injected as a synthetic pool and
   scanned against train; exact must hit 1.0, padded and dropped must be caught
   at J>=0.6 (one drop variant may land just under the threshold: measured min
   0.597 on seed 3).

Prints SELFCHECK PASS / exits non-zero on failure. Deterministic seeds.

    python scripts/selfcheck.py [--sample N]
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import decontam_scan as ds  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def rows_of(path, cols):
    return ds.read_rows(path, cols)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=60000)
    args = ap.parse_args()

    train = list(rows_of(os.path.join(DATA, "train.csv"), ["id", "text"]))
    ref = [ds.Doc(r["id"], ds.shingle_ids(ds.tokenize(r["text"]), 5)) for r in train]

    # ---- A. margin: seeded passage sample vs train ----
    pool_rows = [(r["id"], r["text"]) for r in rows_of(os.path.join(DATA, "pool_passages.csv.gz"), ["id", "text"])]
    sample = random.Random(7).sample(pool_rows, min(args.sample, len(pool_rows)))
    qdocs = (ds.Doc(i, ds.shingle_ids(ds.tokenize(t), 5)) for i, t in sample)
    hits, buckets, n = ds.compare_all(qdocs, ref, [0.15, 0.2, 0.25, 0.3, 0.6])
    top = sorted((h[2] for h in hits), reverse=True)[:5]
    print(f"[margin passages] {n} sampled pool passages vs {len(ref)} train rows")
    for t in ("0.6", "0.3", "0.25", "0.2", "0.15"):
        print(f"  J>={t}: {buckets[t]['pairs']} pairs")
    print(f"  top scores: {[round(s, 3) for s in top] or 'none'}")

    prompts = list(rows_of(os.path.join(DATA, "pool_prompts.csv.gz"), ["prompt_canon", "prompt_text"]))
    recon = list(rows_of(os.path.join(DATA, "train_prompts_reconstructed.csv"), ["prompt_id", "inferred_prompt"]))
    refp = [ds.Doc(r["prompt_id"], ds.shingle_ids(ds.tokenize(r["inferred_prompt"]), 3)) for r in recon]
    qp = (ds.Doc(r["prompt_canon"], ds.shingle_ids(ds.tokenize(r["prompt_text"]), 3)) for r in prompts)
    hits2, buckets2, np_ = ds.compare_all(qp, refp, [0.2, 0.3, 0.4, 0.6])
    top2 = sorted((h[2] for h in hits2), reverse=True)[:5]
    print(f"[margin prompts] {np_} pool prompts vs {len(refp)} reconstructed train prompts")
    for t in ("0.6", "0.4", "0.3", "0.2"):
        print(f"  J>={t}: {buckets2[t]['pairs']} pairs")
    print(f"  top scores: {[round(s, 3) for s in top2] or 'none'}")

    # ---- B. sensitivity: injected perturbed real train passages ----
    tr_s = random.Random(3).sample(train, 60)
    variants = []
    for i, r in enumerate(tr_s):
        toks = ds.tokenize(r["text"])
        variants.append(("exact", r["text"]))
        variants.append(("drop", " ".join(t for j, t in enumerate(toks) if (j * 37 + i) % 100 >= 4)))
        mid = len(toks) // 2
        variants.append(("pad", "In addition, note this. " + " ".join(toks[:mid] + ["zzqx"] + toks[mid + 1:]) + " End of note."))
    q2 = [ds.Doc(f"inj_{k}{i}", ds.shingle_ids(ds.tokenize(t), 5)) for i, (k, t) in enumerate(variants)]
    hits3, buckets3, _ = ds.compare_all(q2, ref, [0.6, 0.8, 1.0])
    caught = {"exact": set(), "drop": set(), "pad": set()}
    for qid, rid, j in hits3:
        if j >= 0.6:
            kind = "exact" if "_exact" in qid else ("drop" if "_drop" in qid else "pad")
            caught[kind].add(qid)
    print("[sensitivity] injected 180 perturbed real train passages vs full train")
    print(f"  caught at J>=0.6: exact {len(caught['exact'])}/60, "
          f"pad {len(caught['pad'])}/60, drop {len(caught['drop'])}/60")
    ok = len(caught["exact"]) == 60 and len(caught["pad"]) == 60 and len(caught["drop"]) >= 59
    if buckets3["1"]["pairs"] != 60:
        ok = False
    print("SELFCHECK PASS" if ok else "SELFCHECK FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
