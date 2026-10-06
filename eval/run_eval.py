"""Evaluation harness: compares dense vs BM25 vs hybrid vs hybrid+rerank on a labelled question set.

Metrics (chunk level - a retrieved chunk is "relevant" if it contains ALL expected answer keywords):
  recall@k     fraction of answerable questions with a relevant chunk in the top k
  MRR          mean reciprocal rank of the first relevant chunk
End-to-end (hybrid + rerank + generator + citation verification):
  answer accuracy      expected keywords appear in the final answer
  citation precision   fraction of answers whose citation points at a relevant chunk
  faithfulness         mean fraction of answer sentences that passed citation verification
  abstention rate      unanswerable questions correctly answered with "I don't know"

Usage:  python -m eval.run_eval [--k 4] [--data data/raw] [--questions data/eval/questions.jsonl]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from rag.config import get_settings
from rag.loaders import SUPPORTED
from rag.pipeline import MODES, KnowledgeAssistant

ROOT = Path(__file__).resolve().parent.parent


def load_questions(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def relevant(chunk_text: str, keywords: list[str]) -> bool:
    low = chunk_text.lower()
    return all(k.lower() in low for k in keywords)


def evaluate(data_dir: Path, questions_path: Path, k: int) -> dict:
    questions = load_questions(questions_path)
    answerable = [q for q in questions if q["answerable"]]
    unanswerable = [q for q in questions if not q["answerable"]]

    with tempfile.TemporaryDirectory() as tmp:
        settings = replace(get_settings(), chroma_dir=Path(tmp) / "chroma")
        ka = KnowledgeAssistant(settings)
        for f in sorted(data_dir.iterdir()):
            if f.suffix.lower() in SUPPORTED:
                ka.ingest(f)

        retrieval: dict[str, dict] = {}
        for mode in MODES:
            ranks, lat = [], []
            for q in answerable:
                t0 = time.perf_counter()
                hits = ka.retrieve(q["question"], mode, k)
                lat.append((time.perf_counter() - t0) * 1000)
                rank = next((i for i, h in enumerate(hits, 1) if relevant(h.chunk.text, q["answer_keywords"])), None)
                ranks.append(rank)
            retrieval[mode] = {
                "recall@k": sum(r is not None for r in ranks) / len(ranks),
                "mrr": statistics.fmean(1 / r if r else 0.0 for r in ranks),
                "latency_ms": statistics.fmean(lat),
            }

        correct = cite_ok = 0
        faith: list[float] = []
        for q in answerable:
            ans = ka.ask(q["question"])
            faith.append(ans.faithfulness)
            if ans.grounded and all(kw.lower() in ans.answer.lower() for kw in q["answer_keywords"]):
                correct += 1
            if ans.grounded and ans.citations and all(c.source == q["source"] for c in ans.citations):
                cite_ok += 1
        abstained = sum(not ka.ask(q["question"]).grounded for q in unanswerable)

    n = len(answerable)
    return {
        "k": k,
        "n_answerable": n,
        "n_unanswerable": len(unanswerable),
        "retrieval": retrieval,
        "end_to_end": {
            "answer_accuracy": correct / n,
            "citation_precision": cite_ok / n,
            "faithfulness": statistics.fmean(faith),
            "abstention_rate": abstained / len(unanswerable) if unanswerable else None,
        },
    }


def to_markdown(r: dict) -> str:
    k = r["k"]
    lines = [f"| Retriever | Recall@{k} | MRR | Latency (ms) |", "|---|---|---|---|"]
    names = {"dense": "Dense (Chroma)", "bm25": "BM25", "hybrid": "Hybrid (RRF)", "hybrid_rerank": "Hybrid + Rerank"}
    for mode, m in r["retrieval"].items():
        lines.append(f"| {names[mode]} | {m['recall@k']:.2f} | {m['mrr']:.2f} | {m['latency_ms']:.1f} |")
    e = r["end_to_end"]
    lines += [
        "",
        "| End-to-end metric | Score |",
        "|---|---|",
        f"| Answer accuracy | {e['answer_accuracy']:.2f} |",
        f"| Citation precision | {e['citation_precision']:.2f} |",
        f"| Faithfulness | {e['faithfulness']:.2f} |",
        f"| Abstention on unanswerable | {e['abstention_rate']:.2f} |",
        "",
        f"_{r['n_answerable']} answerable + {r['n_unanswerable']} unanswerable questions, k={k}._",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--questions", type=Path, default=ROOT / "data" / "eval" / "questions.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "results.json")
    ap.add_argument("--min-recall", type=float, default=0.0,
                    help="exit non-zero if hybrid+rerank recall is lower (CI quality gate)")
    args = ap.parse_args()
    result = evaluate(args.data, args.questions, args.k)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(to_markdown(result))
    return 0 if result["retrieval"]["hybrid_rerank"]["recall@k"] >= args.min_recall else 1


if __name__ == "__main__":
    sys.exit(main())
