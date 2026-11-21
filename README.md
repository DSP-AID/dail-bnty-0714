# decontam-scan — open-pool near-duplicate decontamination tool (bnty_0714)

Pure-stdlib Python 3 tool that verifies an external passage pool (the Kaggle
[Name That LLM](https://www.kaggle.com/competitions/name-that-llm) "open pool",
`crtproduction/name-that-llm-open-pool`) does not contain near-duplicates of the
competition's train rows or public test rows. Built for the bnty_0699 house
verification rule ("any submission training on the open pool must ship a
near-duplicate scan vs train.csv and test.csv; the house re-runs it").

Works on any pool in CSV form: columns are configurable, so future pool
submissions plug in without code changes.

## Quickstart (fresh clone, Python 3.8+, no pip installs, no Kaggle token)

```bash
python decontam_scan.py --out report/scan_results.json   # full scan, ~3 min single core
python -m unittest discover -s tests                     # unit tests (incl. brute-force equivalence)
python scripts/selfcheck.py                              # margin + injected-positives sensitivity, ~1 min
```

All three run end-to-end on the data shipped in `data/` (see `data/README.md`
for provenance and SHA-256). The scan is deterministic: identical inputs give a
byte-identical JSON.

## What the default run checks

| Comparison | Query side | Reference side |
|---|---|---|
| `pool_passages_vs_train` | 231,036 pool passages | 2,699 train.csv passages (official) |
| `pool_passages_vs_test_public_examples` | 231,036 pool passages | 3 public test.csv example rows |
| `pool_prompts_vs_train_prompts_reconstructed` | 17,671 pool prompts with text | 150 community-reconstructed train prompt texts |
| `train_vs_test_public_examples` | 2,699 train passages | 3 public test example rows (sanity) |

## Method and thresholds

- **Normalize:** Unicode NFKC, casefold, `_`→space; tokenize as runs of unicode
  word chars (punctuation/quotes are separators).
- **Similarity:** Jaccard coefficient over sets of word n-gram shingles
  (`--n-passage 5` for passages, `--n-prompt 3` for prompts; texts shorter than
  n produce one shingle).
- **Thresholds reported:** J ≥ 1.0 (exact after normalization), ≥ 0.8, ≥ 0.6.
  Configurable via `--thresholds 0.6,0.8,1.0`.
- **Search:** exact prefix-filter inverted index (Chopra-style, df-ascending).
  Every pair with J ≥ min(threshold) is guaranteed found; scores are recomputed
  exactly from full shingle sets — no sampling, no LSH error. Verified against a
  brute-force scan in `tests/test_decontam_scan.py`.
- **Memory:** the query side streams row by row; peak RAM is O(reference side)
  (tens of MB). Runtime for the full 231k pool: ~3 min on one core.
- Shingles are 64-bit blake2b hashes; collision probability over a ~50M-shingle
  run < 1e-8.

## Result on the shipped inputs (pool v18, 2026-11-18)

All four comparisons: **0 pairs at J ≥ 0.6, ≥ 0.8 and = 1.0** — see
`report/REPORT.md` for counts, margin analysis (closest pool/train pair < J 0.15
on a 60k sample; prompts max J 0.24) and the sensitivity proof (injected
perturbed real train passages are caught at J ≥ 0.6: exact 60/60 at J=1.0,
padded 60/60, word-dropped 60/60).

## What this check cannot check (read before trusting a "clean" verdict)

- **Hidden test rows.** The public `test.csv` holds only example rows (3 in the
  shipped copy); the graded ~4k test passages and their prompts are not public.
  No tool — this one included — can check pool overlap against them.
- **Official train prompt text** is not published (`train.csv` carries
  `prompt_id` only). The prompt-side check uses the community reconstruction
  (CC BY-SA, shipped) as a proxy; it covers all 150 train prompt_ids but is not
  byte-official.
- **Pool prompts without text.** 17,671 of the pool's 36,069 distinct canonical
  prompts have text in the pool's own `prompts.parquet`; the remaining 18,398
  source datasets published passages only, so those prompts cannot be scanned
  by anyone. The passage side is complete (231,036/231,036).
- **Semantic paraphrase.** Word-order / synonym rewrites score below the 0.6
  band by design; this is a lexical near-duplicate check. The pool's own
  embedding column (`max_cos_train`, ≤ 0.30 on kept rows) covers semantic
  similarity.

## Layout

- `decontam_scan.py` — the tool (stdlib only)
- `data/` — shipped inputs with provenance + SHA-256 (`data/README.md`)
- `tests/` — unittest suite; `scripts/selfcheck.py` — margin + sensitivity
- `report/scan_results.json`, `report/pairs_all.csv` — machine-readable output of the default run
- `report/REPORT.md` — the human report (method, counts, limits)

## Scanning a different pool

```bash
python decontam_scan.py \
  --pool-passages their_pool.csv --pool-id row_id --pool-text passage \
  --train data/train.csv --test data/test_public_examples.csv \
  --out their_scan.json --pairs-csv their_pairs.csv
```

Gzipped CSV inputs are handled transparently. Code is MIT-licensed; bundled
data keeps its upstream licenses (see `data/README.md`).
