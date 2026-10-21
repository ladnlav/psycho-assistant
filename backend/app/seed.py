"""Демо-данные для разработки: врач, пациент на Авиандре, 4 недели дневника и GAD-7 раз в 2 недели.

История заканчивается вчера: сегодняшний день пустой, и GAD-7 уже пора заполнить — это показывают на демо.

Запуск: python -m app.seed   (пароль демо-аккаунтов — переменная SEED_PASSWORD, см. .env.example)
Полноценные клинические сценарии — в scenarios/ (TODO: Савва + Влад).
"""

import os
import random
from datetime import timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.kb import get_kb
from app.models import (DiaryEntry, DoctorPatientLink, DoctorProfile, MedicationIntake, PatientProfile,
                        Prescription, ScaleResponse, User, utcnow)
from app.security import hash_password
from app.services.scoring import score

DOCTOR_EMAIL = "doctor@example.com"
PATIENT_EMAIL = "patient@example.com"
HISTORY_DAYS = 28  # дневник и приём до вчера включительно
GAD7_DAYS_AGO = ((28, 2), (14, 1))  # (дней назад, уровень ответов): раз в 14 дней, тревога снижается


def main() -> None:
    password = os.environ.get("SEED_PASSWORD")
    if not password:
        raise SystemExit("Задайте SEED_PASSWORD (см. .env.example)")
    kb = get_kb()
    rnd = random.Random(42)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == DOCTOR_EMAIL)):
            print("Демо-данные уже есть")
            return
        doctor = User(email=DOCTOR_EMAIL, password_hash=hash_password(password), role="doctor",
                      full_name="Демо Врач (терапевт)")
        patient = User(email=PATIENT_EMAIL, password_hash=hash_password(password), role="patient",
                       full_name="Демо Пациент")
        db.add_all([doctor, patient])
        db.flush()
        db.add_all([DoctorProfile(user_id=doctor.id, specialty="therapist"), PatientProfile(user_id=patient.id)])
        db.flush()
        db.add(DoctorPatientLink(doctor_id=doctor.id, patient_id=patient.id))

        now = utcnow()
        start = now - timedelta(days=HISTORY_DAYS)
        rx = Prescription(patient_id=patient.id, doctor_id=doctor.id, drug_id="aviandr", drug_name="Авиандр",
                          start_date=start.date())
        db.add(rx)
        db.flush()
        for d in range(HISTORY_DAYS):
            ts = start + timedelta(days=d)
            anxiety = max(1, 8 - d // 5 + rnd.randint(-1, 1))
            db.add(DiaryEntry(patient_id=patient.id, day=ts.date(), anxiety=anxiety,
                              mood=min(10, 3 + d // 5 + rnd.randint(-1, 1)), sleep_quality=5 + d // 7,
                              created_at=ts))
            db.add(MedicationIntake(patient_id=patient.id, prescription_id=rx.id, day=ts.date(),
                                    status="taken" if rnd.random() > 0.1 else "missed", created_at=ts))
        for days_ago, level in GAD7_DAYS_AGO:
            answers = {i.id: min(3, max(0, level + rnd.randint(-1, 0))) for i in kb.scales["gad7"].items}
            result = score(kb.scales["gad7"], answers)
            db.add(ScaleResponse(patient_id=patient.id, scale_id="gad7", answers=answers, total=result.total,
                                 severity=result.severity, submitted_by=patient.id,
                                 created_at=now - timedelta(days=days_ago)))
        db.commit()
        print(f"Готово: {DOCTOR_EMAIL} / {PATIENT_EMAIL}")


if __name__ == "__main__":
    main()
