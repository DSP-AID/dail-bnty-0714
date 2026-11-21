# Bundled input data — provenance and integrity

All files are real public dataset copies (no synthetic placeholders), chosen so
the scan runs end-to-end on a clean machine with **no Kaggle account or token**.
Verified 2026-11-21.

| file | rows | sha256 | source | licence |
|---|---|---|---|---|
| `train.csv` | 2,699 (`id,prompt_id,text,model`) | `40a22ce8d88c5f46feb4637a099db815bef5f713ffe53e89dbe1b7b21de77707` | Kaggle competition **name-that-llm** official `train.csv`, byte-identical copy mirrored at `github.com/johnsonhk88/kaggle-Name-That-LLM` @ main, `dataset/name-that-llm/train.csv` (blob size 2,139,418 matches) | competition data terms |
| `test_public_examples.csv` | 3 (`id,text`) | `4545aa3a3459f4c0724f97ad5bd06c4caa3506bdfea5fab905e8203184fc0c57` | same mirror, `dataset/name-that-llm/test.csv` (blob size 2,218 matches). This is what the public test.csv contains: example rows only; the graded ~4k test rows are hidden server-side. | competition data terms |
| `pool_passages.csv.gz` | 231,036 | `7a45b891871e1435168da09e6c1eee286962ab71b3bbff5fe9a552b8df8aface` | Kaggle dataset `crtproduction/name-that-llm-open-pool` **v18** (2026-11-18), lossless CSV conversion of `ntl_open_pool.parquet`; columns kept: `id,text,model,lab,prompt_group,prompt_canon,source_dataset,n_words,max_cos_train,max_sim_train_prompt,flag_near_train_prompt,flag_train_prompt_regen` | CC BY-SA 4.0 |
| `pool_prompts.csv.gz` | 17,671 (`prompt_canon,prompt_text`) | `5d36b40d83424994b8d73a60b90ae4801e8b1a2c3dc9acee324d8025fb2a0987` | same dataset v18, lossless conversion of `prompts.parquet` | CC BY-SA 4.0 |
| `train_prompts_reconstructed.csv` | 150 (`prompt_id,inferred_prompt,...`) | `41357f850c4309528a59f92ecda5323e2b1c2a925eb69dfc87ea92a4f68d6d6e` | Kaggle dataset `pjmathematician/ntl-train-prompts-reconstructed` — community reconstruction of the 150 competition train prompt texts (official train.csv publishes `prompt_id` only). Covers 150/150 prompt_ids present in `train.csv`. | CC BY-SA 4.0 (attribution: pjmathematician) |

Re-verify locally: `sha256sum data/*` must match the table above.

To reproduce the pool CSVs from Kaggle yourself (only if you want the raw
parquet; not needed for any tool run here):

```bash
kaggle datasets download -d crtproduction/name-that-llm-open-pool   # needs a token
# then: pandas.read_parquet('ntl_open_pool.parquet')[cols].to_csv('pool_passages.csv') ; gzip it
```
