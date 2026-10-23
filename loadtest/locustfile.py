"""Нагрузочный тест: время ответа API и доля ошибок под нагрузкой — техметрика кейса.

Виртуальные пациенты открывают главную, пишут дневник, открывают и заполняют GAD-7. Виртуальный врач
открывает список пациентов, карточки и алерты. На каждого врача приходится 10 пациентов. Учётные записи
создаются в начале прогона через обычный API; у каждого прогона свой врач load-…@example.com.

    pip install -r loadtest/requirements.txt
    locust -f loadtest/locustfile.py --host http://localhost:8000     # веб-интерфейс: http://localhost:8089
    locust -f loadtest/locustfile.py --host http://localhost:8000 --headless -u 10 -r 2 -t 2m --csv loadtest/results/u10

Ступени — 10, 50 и 100 пользователей, по 2 минуты каждая. Регистрация идёт мимо статистики locust, поэтому
строку Aggregated можно брать в таблицу как есть. В конце прогона печатается ещё и время на сервере по заголовку
X-Response-Time-ms: без сети и без очереди на стороне locust.

Только локальный стенд: тест создаёт учётные записи. Убрать всё вместе с базой — docker compose down -v.
"""

import itertools
import random
import secrets
import statistics
from collections import defaultdict
from datetime import datetime

import requests
from locust import HttpUser, between, events, task

PASSWORD = secrets.token_urlsafe(16)  # одноразовый, нигде не печатается
_run = ""
_numbers = itertools.count(1)
_doctor: dict[str, str] = {}  # заголовок авторизации врача текущего прогона
_server_ms: dict[str, list[float]] = defaultdict(list)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@events.test_start.add_listener
def _register_doctor(environment, **_):
    """Один врач на прогон: его коды приглашения получают виртуальные пациенты."""
    global _run
    _run = datetime.now().strftime("%Y%m%d-%H%M%S")
    _server_ms.clear()
    r = requests.post(f"{environment.host}/api/auth/register/doctor", timeout=30, json={
        "email": f"load-{_run}@example.com", "password": PASSWORD, "full_name": f"Нагрузочный тест {_run}"})
    r.raise_for_status()
    _doctor.update(_auth(r.json()["access_token"]))


@events.request.add_listener
def _collect_server_time(name, response, exception, **_):
    if exception is None and response is not None and "X-Response-Time-ms" in response.headers:
        _server_ms[name].append(float(response.headers["X-Response-Time-ms"]))


@events.test_stop.add_listener
def _print_server_time(**_):
    rows = sorted(_server_ms.items())
    if not rows:
        return
    rows.append(("все запросы", [x for _, ms in rows for x in ms]))
    print(f"\nВремя на сервере (X-Response-Time-ms), прогон {_run}")
    print(f"{'запрос':38}{'n':>7}{'медиана':>10}{'p95':>10}")
    for name, ms in rows:
        p95 = statistics.quantiles(ms, n=20, method="inclusive")[18] if len(ms) > 1 else ms[0]
        print(f"{name:38}{len(ms):>7}{statistics.median(ms):>10.1f}{p95:>10.1f}")


class Patient(HttpUser):
    weight = 10
    wait_time = between(1, 3)

    def on_start(self):
        # Регистрация — подготовка, а не нагрузка: идёт мимо self.client и не попадает в статистику.
        invite = requests.post(f"{self.host}/api/doctor/invites", json={}, headers=_doctor, timeout=30)
        invite.raise_for_status()
        r = requests.post(f"{self.host}/api/auth/register/patient", timeout=30, json={
            "email": f"load-{_run}-{next(_numbers):04d}@example.com", "password": PASSWORD,
            "full_name": f"Нагрузка {_run}", "invite_code": invite.json()["code"], "consent_pd": True})
        r.raise_for_status()
        self.headers = _auth(r.json()["access_token"])
        scale = requests.get(f"{self.host}/api/kb/scales/gad7", headers=self.headers, timeout=30).json()
        self.gad7_items = [item["id"] for item in scale["items"]]

    @task(3)
    def home(self):
        self.client.get("/api/patient/scales/schedule", headers=self.headers, name="пациент: расписание шкал")
        self.client.get("/api/patient/diary", headers=self.headers, name="пациент: дневник")

    @task(2)
    def write_diary(self):
        self.client.post("/api/patient/diary", headers=self.headers, name="пациент: запись дневника", json={
            "anxiety": random.randint(2, 7), "mood": random.randint(3, 8), "sleep_quality": random.randint(3, 8)})

    @task(1)
    def fill_gad7(self):
        self.client.get("/api/kb/scales/gad7", headers=self.headers, name="пациент: открыть GAD-7")
        answers = {item: random.randint(0, 1) for item in self.gad7_items}
        self.client.post("/api/patient/scales/gad7", json={"answers": answers}, headers=self.headers,
                         name="пациент: отправить GAD-7")


class Doctor(HttpUser):
    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        self.patient_ids: list[str] = []

    @task(3)
    def patients(self):
        r = self.client.get("/api/doctor/patients", headers=_doctor, name="врач: список пациентов")
        if r.ok:
            self.patient_ids = [p["id"] for p in r.json()]

    @task(2)
    def card(self):
        if self.patient_ids:
            self.client.get(f"/api/doctor/patients/{random.choice(self.patient_ids)}", headers=_doctor,
                            name="врач: карточка пациента")

    @task(1)
    def alerts(self):
        self.client.get("/api/doctor/alerts", headers=_doctor, name="врач: алерты")
