"""Кнопка «Нужна срочная помощь»: экран 112/103 — сразу, а после причины — сообщение в чат и алерт врачу."""

from tests.conftest import auth


def patient_id(client, doctor_token) -> str:
    return client.get("/api/doctor/patients", headers=auth(doctor_token)).json()[0]["id"]


def open_alerts(client, doctor_token) -> list[dict]:
    return client.get("/api/doctor/alerts", headers=auth(doctor_token)).json()


def test_screen_without_reason_sends_nothing(client, doctor_token, patient_token):
    screen = client.get("/api/patient/safety", headers=auth(patient_token)).json()
    assert {c["phone"] for c in screen["contacts"]} >= {"112", "103"}
    assert open_alerts(client, doctor_token) == [], "без причины врачу ничего не уходит"
    r = client.post("/api/patient/help", json={"reason": ""}, headers=auth(patient_token))
    assert r.status_code == 422


def test_reason_alerts_doctor_and_lands_in_chat(client, doctor_token, patient_token):
    r = client.post("/api/patient/help", json={"reason": "Очень сильная паника, не могу успокоиться"},
                    headers=auth(patient_token))
    assert r.status_code == 200, r.text
    assert r.json()["kind"] == "help" and r.json()["safety"]["contacts"], "экран помощи остаётся"

    [alert] = open_alerts(client, doctor_token)
    assert (alert["rule_id"], alert["level"], alert["trigger"]) == ("patient_help_request", "critical", "help_request")
    assert alert["evidence"] == {"help.requests_24h": 1}

    chat = client.get(f"/api/doctor/patients/{patient_id(client, doctor_token)}/messages",
                      headers=auth(doctor_token)).json()
    assert [(m["kind"], m["body"]) for m in chat] == [("help", "Очень сильная паника, не могу успокоиться")]

    client.post("/api/patient/help", json={"reason": "Стало ещё хуже"}, headers=auth(patient_token))
    [again] = open_alerts(client, doctor_token)
    assert again["id"] == alert["id"] and again["updated_at"], "вторая просьба — новые данные в том же алерте"


def test_risky_reason_also_fires_text_rule(client, doctor_token, patient_token):
    client.post("/api/patient/help", json={"reason": "Хочу умереть"}, headers=auth(patient_token))
    rules = {a["rule_id"] for a in open_alerts(client, doctor_token)}
    assert rules == {"patient_help_request", "free_text_risk"}


def test_screen_says_doctor_notified_only_after_alert(client, doctor_token, patient_token):
    """Кнопка помощи открывает экран до всякого алерта — фразы «врач получил уведомление» там быть не должно."""
    screen = client.get("/api/patient/safety", headers=auth(patient_token)).json()
    assert "получил уведомление" not in screen["message_ru"]
    sent = client.post("/api/patient/help", json={"reason": "Плохо"}, headers=auth(patient_token)).json()
    assert "получил уведомление" in sent["safety"]["message_ru"]
