"""Прогон извлечения на размеченном наборе и отчёт по полям.

    cd ml && python -m eval.run_eval              # все документы из eval/data
    python -m eval.run_eval --limit 3             # быстрый прогон

Каждой истории eval/data/<id>.txt соответствует эталон eval/gold/<id>.json (схема app.schemas.ExtractionResult).
Предсказания и отчёт сохраняются в eval/runs/<время>/.
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.extract import extract
from app.schemas import ExtractionResult
from eval.metrics import aggregate, compare

ROOT = Path(__file__).parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    docs = sorted((ROOT / "data").glob("*.txt"))[: args.limit]
    run_dir = ROOT / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    per_doc, latencies = [], []
    for doc in docs:
        gold = ExtractionResult.model_validate_json((ROOT / "gold" / f"{doc.stem}.json").read_text(encoding="utf-8"))
        start = time.perf_counter()
        pred = extract(doc.read_text(encoding="utf-8"))
        latencies.append(time.perf_counter() - start)
        (run_dir / f"{doc.stem}.json").write_text(pred.model_dump_json(indent=2), encoding="utf-8")
        per_doc.append(compare(gold, pred))
        print(f"{doc.stem}: {latencies[-1]:.1f} c")

    total = aggregate(per_doc)
    report = {
        "model": get_settings().llm_model,
        "documents": len(docs),
        "avg_latency_s": sum(latencies) / len(latencies) if latencies else None,
        "fields": {f: {"precision": round(s.precision, 3), "recall": round(s.recall, 3), "f1": round(s.f1, 3),
                       "tp": s.tp, "fp": s.fp, "fn": s.fn} for f, s in total.items()},
    }
    (run_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'поле':<15}{'P':>7}{'R':>7}{'F1':>7}")
    for f, s in report["fields"].items():
        print(f"{f:<15}{s['precision']:>7.2f}{s['recall']:>7.2f}{s['f1']:>7.2f}")
    print(f"\nОтчёт: {run_dir / 'report.json'}")


if __name__ == "__main__":
    main()
