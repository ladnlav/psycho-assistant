"""Время доставки алертов врачу — техметрика кейса.

Скрипт регистрирует отдельного врача и N тестовых пациентов (по умолчанию 30), подключается как врач
к /ws/doctor и по очереди отправляет за каждого пациента PHQ-9 с пунктом 9 = 1. Это критичный алерт
phq9_suicidal_ideation. Для каждого алерта считаются три времени:

- «до экрана врача» — от отправки PHQ-9 до прихода алерта врачу по WebSocket, на клиенте вместе с сетью;
- «на сервере» — delivered_at − created_at из базы: от создания алерта до отправки врачу;
- «ответ API» — заголовок X-Response-Time-ms у отправки PHQ-9, время на сервере без сети.

    pip install -r loadtest/requirements.txt
    python loadtest/alert_latency.py                              # стенд на http://localhost:8000
    python loadtest/alert_latency.py --patients 50 --csv loadtest/results/latency.csv

Только локальный стенд: скрипт создаёт учётные записи. Его пациентов (latency-…@example.com) видит только
его врач, демо-врачу они не видны. Убрать всё вместе с базой — docker compose down -v.
"""

import argparse
import asyncio
import csv
import json
import os
import platform
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import websockets

RULE = "phq9_suicidal_ideation"


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))  # Python 3.10 не понимает «Z»


def percentile(values: list[float], q: float) -> float:
    """Как percentile_cont в Postgres: линейная интерполяция между соседними значениями."""
    s = sorted(values)
    if not s:
        return float("nan")
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


async def register(api: httpx.AsyncClient, run_id: str, n: int, password: str):
    """Врач и n пациентов по кодам приглашения — как настоящие пользователи, через API."""
    r = await api.post("/api/auth/register/doctor", json={
        "email": f"latency-{run_id}@example.com", "password": password, "full_name": f"Замер доставки {run_id}"})
    r.raise_for_status()
    doctor_token = r.json()["access_token"]
    doctor = {"Authorization": f"Bearer {doctor_token}"}
    patients = []
    for i in range(1, n + 1):
        code = (await api.post("/api/doctor/invites", json={}, headers=doctor)).json()["code"]
        r = await api.post("/api/auth/register/patient", json={
            "email": f"latency-{run_id}-{i:03d}@example.com", "password": password,
            "full_name": f"Замер {run_id} №{i}", "invite_code": code, "consent_pd": True})
        r.raise_for_status()
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
        patient_id = (await api.get("/api/auth/me", headers=headers)).json()["id"]
        patients.append((patient_id, headers))
        print(f"\rРегистрация пациентов: {i}/{n}", end="", flush=True)
    print()
    return doctor_token, doctor, patients


async def run(base: str, n: int, pause: float, timeout: float) -> list[dict]:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    password = secrets.token_urlsafe(16)  # одноразовый, нигде не печатается
    async with httpx.AsyncClient(base_url=base, timeout=30) as api:
        doctor_token, doctor, patients = await register(api, run_id, n, password)
        phq9 = (await api.get("/api/kb/scales/phq9", headers=doctor)).json()
        answers = {item["id"]: 0 for item in phq9["items"]} | {"item9": 1}

        arrived: dict[str, float] = {}
        events = {pid: asyncio.Event() for pid, _ in patients}
        ws_url = base.replace("http", "ws", 1) + f"/ws/doctor?token={doctor_token}"
        async with websockets.connect(ws_url) as ws:
            async def listen() -> None:
                async for raw in ws:
                    alert = json.loads(raw).get("alert") or {}
                    pid = alert.get("patient_id")
                    if alert.get("rule_id") == RULE and pid in events and pid not in arrived:
                        arrived[pid] = time.perf_counter()
                        events[pid].set()

            listener = asyncio.create_task(listen())
            rows = []
            for i, (pid, headers) in enumerate(patients, 1):
                start = time.perf_counter()
                r = await api.post("/api/patient/scales/phq9", json={"answers": answers}, headers=headers)
                r.raise_for_status()
                try:
                    await asyncio.wait_for(events[pid].wait(), timeout)
                    screen_ms = (arrived[pid] - start) * 1000
                except asyncio.TimeoutError:
                    screen_ms = None
                rows.append({"n": i, "patient_id": pid, "screen_ms": screen_ms,
                             "api_ms": float(r.headers.get("X-Response-Time-ms", "nan"))})
                print(f"\rАлерты: {i}/{n}", end="", flush=True)
                await asyncio.sleep(pause)
            print()
            listener.cancel()

        # Время на сервере — из базы через API врача: created_at и delivered_at каждого алерта.
        alerts = (await api.get("/api/doctor/alerts", headers=doctor)).json()
        server = {a["patient_id"]: (ts(a["delivered_at"]) - ts(a["created_at"])).total_seconds() * 1000
                  for a in alerts if a["rule_id"] == RULE and a["delivered_at"]}
        for row in rows:
            row["server_ms"] = server.get(row["patient_id"])
    return rows


def report(rows: list[dict], base: str) -> None:
    print(f"\nМашина: {platform.platform()}, {platform.processor() or platform.machine()}, "
          f"ядер {os.cpu_count()} (память допишите сами)")
    print(f"Стенд: {base}; алертов дошло до врача: {sum(r['screen_ms'] is not None for r in rows)} из {len(rows)}\n")
    print(f"{'':28}{'медиана':>10}{'p95':>10}{'макс':>10}")
    for key, title in (("screen_ms", "До экрана врача, мс"), ("server_ms", "На сервере (БД), мс"),
                       ("api_ms", "Ответ API на PHQ-9, мс")):
        values = [r[key] for r in rows if r[key] is not None]
        if values:
            print(f"{title:28}{percentile(values, 0.5):>10.1f}{percentile(values, 0.95):>10.1f}{max(values):>10.1f}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Замер времени доставки алертов врачу")
    ap.add_argument("--base-url", default="http://localhost:8000", help="адрес backend")
    ap.add_argument("--patients", type=int, default=30, help="сколько пациентов и алертов")
    ap.add_argument("--pause", type=float, default=0.3, help="пауза между алертами, с")
    ap.add_argument("--timeout", type=float, default=10, help="сколько ждать алерт, с")
    ap.add_argument("--csv", type=Path, help="сохранить замеры по каждому алерту")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # кириллица и при выводе в файл или пайп на Windows
    base = args.base_url.rstrip("/")
    rows = asyncio.run(run(base, args.patients, args.pause, args.timeout))
    report(rows, base)
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["n", "patient_id", "screen_ms", "server_ms", "api_ms"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV: {args.csv}")


if __name__ == "__main__":
    main()
