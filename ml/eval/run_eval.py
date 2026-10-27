"""Прогон извлечения на размеченном наборе и отчёт по полям.

    cd ml && python -m eval.run_eval              # все истории eval/data/hist_*.txt
    python -m eval.run_eval --limit 3             # быстрый прогон
    python -m eval.run_eval --rescore eval/runs/<время>   # пересчитать метрики по ответам прошлого прогона, без модели

Каждой истории eval/data/<id>.txt соответствует эталон eval/gold/<id>.json (схема app.schemas.ExtractionResult).
example_001 — пример формата, эталон к нему врач не проверял, поэтому в метрику он не входит.
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
    ap.add_argument("--rescore", type=Path, default=None,
                    help="папка прошлого прогона eval/runs/<время>: пересчитать метрики по его ответам без модели")
    args = ap.parse_args()

    docs = sorted((ROOT / "data").glob("hist_*.txt"))[: args.limit]
    run_dir = ROOT / "runs" / (datetime.now().strftime("%Y%m%d-%H%M%S") + ("-rescore" if args.rescore else ""))
    run_dir.mkdir(parents=True)
    old = json.loads((args.rescore / "report.json").read_text(encoding="utf-8")) if args.rescore else {}
    per_doc, latencies = [], {}
    for doc in docs:
        gold = ExtractionResult.model_validate_json((ROOT / "gold" / f"{doc.stem}.json").read_text(encoding="utf-8"))
        if args.rescore:
            pred = ExtractionResult.model_validate_json((args.rescore / f"{doc.stem}.json").read_text(encoding="utf-8"))
            if doc.stem in old.get("latency_s", {}):
                latencies[doc.stem] = old["latency_s"][doc.stem]
        else:
            start = time.perf_counter()
            pred = extract(doc.read_text(encoding="utf-8"))
            latencies[doc.stem] = time.perf_counter() - start
            (run_dir / f"{doc.stem}.json").write_text(pred.model_dump_json(indent=2), encoding="utf-8")
            print(f"{doc.stem}: {latencies[doc.stem]:.1f} c")
        per_doc.append(compare(gold, pred))

    total = aggregate(per_doc)
    report = {
        "model": old.get("model") if args.rescore else get_settings().llm_model,
        "rescored_from": str(args.rescore) if args.rescore else None,
        "documents": len(docs),
        "avg_latency_s": sum(latencies.values()) / len(latencies) if latencies else None,
        "latency_s": {k: round(v, 2) for k, v in latencies.items()},
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
