"""Unit tests for decontam_scan.py (stdlib unittest, no third-party deps).

Run from the repo root:  python -m unittest discover -s tests -v
"""

import json
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import decontam_scan as ds


def brute_force(q_docs, r_docs, tmin):
    out = set()
    for qi, q in enumerate(q_docs):
        for ri, r in enumerate(r_docs):
            j = ds.jaccard(q.shingles, r.shingles)
            if j >= tmin:
                out.add((qi, ri, round(j, 9)))
    return out


class TestText(unittest.TestCase):
    def test_normalize_casefold_nfkc(self):
        self.assertEqual(ds.normalize("ﬁnd STRASSE_5"), "find strasse 5")

    def test_tokenize_punct_separators(self):
        self.assertEqual(ds.tokenize("Don't—stop, meow! (9 lives)"), ["don", "t", "stop", "meow", "9", "lives"])

    def test_short_doc_single_shingle_and_identical_jaccard(self):
        toks = ds.tokenize("cat sat mat")
        s1 = ds.shingle_ids(toks, 5)
        self.assertEqual(len(s1), 1)
        self.assertEqual(ds.jaccard(s1, ds.shingle_ids(ds.tokenize("Cat, sat; MAT!"), 5)), 1.0)

    def test_empty_doc(self):
        self.assertEqual(ds.shingle_ids([], 3), set())
        self.assertEqual(ds.jaccard(set(), {1, 2}), 0.0)


class TestScan(unittest.TestCase):
    def make_docs(self, texts, n=3, prefix="d"):
        return [ds.Doc(f"{prefix}{i}", ds.shingle_ids(ds.tokenize(t), n)) for i, t in enumerate(texts)]

    def test_random_equivalence_bruteforce(self):
        rnd = random.Random(42)
        vocab = [f"w{k}" for k in range(40)]
        for trial in range(6):
            corpus = []
            for _ in range(18):
                ln = rnd.randint(10, 50)
                corpus.append(" ".join(rnd.choice(vocab) for _ in range(ln)))
            # inject near-duplicates (edits of existing docs) and exact dupes
            for _ in range(8):
                base = rnd.choice(corpus).split()
                for _ in range(rnd.randint(0, 4)):
                    i = rnd.randrange(len(base))
                    base[i] = rnd.choice(vocab)
                corpus.append(" ".join(base))
            corpus.append("")
            corpus.append("one two")
            q = self.make_docs(corpus, prefix="q")
            r = self.make_docs(list(reversed(corpus)), prefix="r")
            qids = {d.doc_id: i for i, d in enumerate(q)}
            rids = {d.doc_id: i for i, d in enumerate(r)}
            for tmin in (0.5, 0.6, 0.8):
                hits, _buckets, nrows = ds.compare_all(iter(q), r, [tmin])
                self.assertEqual(nrows, len(q))
                got = {(qids[qid], rids[rid], round(j, 9)) for qid, rid, j in hits}
                self.assertEqual(got, brute_force(q, r, tmin), f"trial {trial} t={tmin}")

    def test_buckets_and_ordering(self):
        texts = [
            "the quick brown fox jumps over the lazy dog today",
            "the quick brown fox leaps over the lazy dog today",  # high sim to 0
            "completely different content about economics and markets here",
            "the quick brown fox jumps over the lazy dog today",  # exact dupe of 0
        ]
        q = self.make_docs(texts[:1], prefix="q")
        r = self.make_docs(texts[1:], prefix="r")
        hits, buckets, _n = ds.compare_all(q, r, [0.6, 0.8, 1.0])
        self.assertGreater(buckets["0.6"]["pairs"], 0)
        # scores strictly descending
        scores = [h[2] for h in hits]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestCLI(unittest.TestCase):
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as td:
            def write(name, text):
                p = os.path.join(td, name)
                with open(p, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
                return p

            train = write("train.csv", "id,prompt_id,text,model\n"
                          't1,p001,"The quick brown fox jumps over the lazy dog, again and again for ten words.",m1\n'
                          't2,p002,"Quantum chromodynamics binds quarks via gluon exchange inside protons and neutrons.",m2\n')
            test = write("test.csv", "id,text\n"
                         'x1,"Economics essay about the jevons paradox in energy use growth today ok extra."\n')
            pool = write("pool.csv", "id,text,prompt_canon\n"
                         'p1,"the quick brown fox jumps over the lazy dog, again and again for ten words.",c1\n'
                         'p2,"An unrelated passage about coral reefs bleaching in warming shallow seas now.",c2\n')
            prompts = write("prompts.csv", "prompt_canon,prompt_text\n"
                            'c1,"Write a vivid passage about foxes and dogs, using imagery, forty words please.",\n')
            recon = write("recon.csv", "prompt_id,inferred_prompt\n"
                          'p001,"write a vivid passage about foxes and dogs using imagery forty words please",\n')
            out = os.path.join(td, "out.json")
            rc = ds.main([
                "--pool-passages", pool, "--pool-prompts", prompts,
                "--train", train, "--test", test, "--train-prompts", recon,
                "--out", out,
            ])
            self.assertEqual(rc, 0)
            with open(out, encoding="utf-8") as f:
                data = json.load(f)
            by = {c["name"]: c for c in data["comparisons"]}
            self.assertGreaterEqual(by["pool_passages_vs_train"]["counts_by_threshold"]["1"]["pairs"], 1)
            self.assertEqual(by["pool_passages_vs_test_public_examples"]["counts_by_threshold"]["1"]["pairs"], 0)
            self.assertGreaterEqual(by["pool_prompts_vs_train_prompts_reconstructed"]["counts_by_threshold"]["0.6"]["pairs"], 1)


if __name__ == "__main__":
    unittest.main()
