# Decontamination report — open pool v18 vs competition inputs (bnty_0714 / bnty_0699)

Run date: 2026-11-21. Tool: `decontam_scan.py` v1.0 in this repo (pure Python
stdlib, deterministic). Inputs and their SHA-256: see `data/README.md`.

- Pool: `crtproduction/name-that-llm-open-pool` **v18** (2026-11-18) — 231,036 retained passages, 17,671 prompt texts.
- Train: official competition `train.csv` — 2,699 rows (150 prompts × 18 models, one row missing).
- Test: public `test.csv` — **3 example rows only**; the graded ~4k test passages are hidden server-side.

## Exact results (from `report/scan_results.json`, reproduced byte-for-byte by a fresh run)

| comparison | query rows | reference rows | pairs J≥0.6 | pairs J≥0.8 | pairs J=1.0 | distinct pool rows matched | reference rows covered |
|---|---|---|---|---|---|---|---|
| pool passages vs train.csv | 231,036 | 2,699 | **0** | **0** | **0** | 0 | 0 / 2,699 |
| pool passages vs public test example rows | 231,036 | 3 | **0** | **0** | **0** | 0 | 0 / 3 |
| pool prompts vs reconstructed train prompts | 17,671 | 150 | **0** | **0** | **0** | 0 | 0 / 150 |
| train vs public test example rows (sanity) | 2,699 | 3 | **0** | **0** | **0** | — | — |

Method: NFKC-normalized, casefolded text → word 5-gram shingle sets (passages) /
word 3-gram (prompts) → exact Jaccard ≥ threshold, found via a prefix-filter
inverted index that provably misses no true match (brute-force equivalence in
unit tests). Thresholds reported: 0.6 / 0.8 / 1.0 (configurable). Full run:
231,036 × 2,699 + 231,036 × 3 + 17,671 × 150 + 2,699 × 3 document pairs,
~174 s single-core (Python 3.12), streaming query side so RAM stays O(reference).

## Margin — how far apart real pool and competition rows actually are

`python scripts/selfcheck.py` (seed 7, 60,000-passage random sample vs full
train): **zero pairs even at J ≥ 0.15** — the closest of 60k×2,699 pairs scores
below 0.15. Pool prompts vs the 150 reconstructed train prompts: max J = 0.242,
one pair above 0.2, none above 0.3. Independent corroboration from the pool's
own curator columns (kept in `pool_passages.csv.gz`): over all 231,036 kept rows
`max_sim_train_prompt` ≤ 0.40, `max_cos_train` (embedding cosine) ≤ 0.30, and
`flag_near_train_prompt` is True on **0** kept rows — because the curator had
already removed 284 rows for `train_prompt_overlap` upstream (their
`removal_summary.csv`). Our scan confirms nothing near-threshold survived that
curation.

## Sensitivity — why "zero" is not a false negative

180 synthetic pool rows built from **real train passages** (seed 3), each in
three perturbation classes, scanned against all 2,699 train rows:

| injected variant | caught at J ≥ 0.6 | score range |
|---|---|---|
| exact copy | 60 / 60 | 1.0 |
| padded + one word substituted | 60 / 60 | 0.667 – 0.933 (median 0.85) |
| ~4% scattered words dropped | 60 / 60 (selfcheck seed); separate 60-passage measurement: min 0.597, median 0.692, max 0.809 — one borderline variant lands just under 0.6 | |

So the detector fires across the whole near-duplicate band (exact → light-edit →
scattered-word churn), while real pool/train pairs sit an order of magnitude
below it. Verdict: **the retained v18 pool is decontaminated against every
publicly checkable competition input, with a large margin.**

## What was checked — and what cannot be checked by anyone

Checked (complete): all 231,036 pool passages vs all 2,699 train passages; all
231,036 vs the 3 public test example rows; all 17,671 pool prompt texts vs the
150 reconstructed train prompts; train vs the public test examples (sanity).

Cannot be checked:

1. **Hidden test set.** The graded ~4k test passages and their prompts are not
   public; public `test.csv` = example rows only. Overlap vs the real test set
   cannot be fully verified by submitters or by the house until Kaggle reveals
   it. This is the one open risk of the decontamination guarantee.
2. **Official train prompt text** is not published (`train.csv` has `prompt_id`
   only). The prompt-side check therefore uses the community reconstruction
   (CC BY-SA 4.0, `pjmathematician/ntl-train-prompts-reconstructed`, covers
   150/150 prompt_ids) as a stand-in — reconstruction error is possible, though
   passage-side overlap (the actual leakage vector) is checked against official
   bytes.
3. **Pool prompts without text:** 18,398 of the pool's 36,069 distinct canonical
   prompts ship no text in `prompts.parquet` (source datasets published
   passages only) — unscannable by anyone; passage-side coverage is complete.
4. **Semantic paraphrase** (synonym/order rewrites) scores below the 0.6 lexical
   band by design; embedding cosine is covered by the curator's own audit
   (`max_cos_train` ≤ 0.30), not by this tool.

## Re-run recipe (house verification, fresh clone, no Kaggle token needed)

```bash
python decontam_scan.py --out report/scan_results.json   # must reproduce the JSON byte-for-byte
python -m unittest discover -s tests                     # correctness incl. brute-force equivalence
python scripts/selfcheck.py                              # margin + injected-positives proof, prints SELFCHECK PASS
```
