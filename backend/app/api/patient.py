from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.kb import KnowledgeBase, Scale, get_kb
from app.models import AdverseEvent, DiaryEntry, MedicationIntake, Message, Prescription, User, utcnow
from app.schemas import (AdverseEventIn, AdverseEventOut, DiaryIn, DiaryOut, IntakeIn, IntakeOut, MessageIn,
                         MessageOut, PrescriptionOut, SafetyScreen, ScaleSubmit, ScaleSubmitResult)
from app.security import require_patient
from app.services.alerts import apply_rules, hub
from app.services.audit import audit
from app.services.clinical import record_scale, safety_screen

router = APIRouter(prefix="/api/patient", tags=["patient"])


@router.get("/scales", response_model=list[Scale])
def my_scales(user: User = Depends(require_patient), kb: KnowledgeBase = Depends(get_kb)):
    # TODO: расписание (schedule_days) — показывать, какие шкалы пора заполнить
    return [s for s in kb.scales.values() if s.rater == "patient"]


@router.post("/scales/{scale_id}", response_model=ScaleSubmitResult)
def submit_scale(scale_id: str, body: ScaleSubmit, tasks: BackgroundTasks, user: User = Depends(require_patient),
                 db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    result, outcome = record_scale(db, kb, user.id, user.id, scale_id, body.answers, rater="patient")
    tasks.add_task(hub.push, outcome.new_alert_ids)
    return result


@router.post("/diary", response_model=DiaryOut)
def add_diary(body: DiaryIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
              db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    entry = DiaryEntry(patient_id=user.id, day=body.day or utcnow().date(), anxiety=body.anxiety, mood=body.mood,
                       sleep_quality=body.sleep_quality, note=body.note)
    db.add(entry)
    db.flush()
    outcome = apply_rules(db, kb, user.id, trigger="diary")
    db.commit()
    tasks.add_task(hub.push, outcome.new_alert_ids)
    return entry


@router.get("/diary", response_model=list[DiaryOut])
def list_diary(user: User = Depends(require_patient), db: Session = Depends(get_db)):
    return db.scalars(select(DiaryEntry).where(DiaryEntry.patient_id == user.id)
                      .order_by(DiaryEntry.day.desc()).limit(60)).all()


@router.get("/prescriptions", response_model=list[PrescriptionOut])
def my_prescriptions(user: User = Depends(require_patient), db: Session = Depends(get_db)):
    return db.scalars(select(Prescription).where(Prescription.patient_id == user.id, Prescription.active.is_(True))
                      .order_by(Prescription.start_date)).all()


@router.get("/intakes", response_model=list[IntakeOut])
def my_intakes(user: User = Depends(require_patient), db: Session = Depends(get_db)):
    return db.scalars(select(MedicationIntake).where(MedicationIntake.patient_id == user.id)
                      .order_by(MedicationIntake.day.desc()).limit(60)).all()


@router.post("/intakes", response_model=IntakeOut)
def mark_intake(body: IntakeIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
                db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    rx = db.get(Prescription, body.prescription_id)
    if rx is None or rx.patient_id != user.id:
        raise HTTPException(404, "Назначение не найдено")
    day = body.day or utcnow().date()
    intake = db.scalar(select(MedicationIntake).where(MedicationIntake.prescription_id == rx.id,
                                                      MedicationIntake.day == day))
    if intake is None:  # одна отметка на препарат в день; повторная — исправление
        intake = MedicationIntake(patient_id=user.id, prescription_id=rx.id, day=day, status=body.status)
        db.add(intake)
    else:
        intake.status = body.status
    db.flush()
    outcome = apply_rules(db, kb, user.id, trigger="intake")
    db.commit()
    tasks.add_task(hub.push, outcome.new_alert_ids)
    return intake


@router.post("/adverse-events", response_model=AdverseEventOut)
def report_adverse_event(body: AdverseEventIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
                         db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    ae = AdverseEvent(patient_id=user.id, description=body.description, severity=body.severity,
                      serious=body.serious, reported_by=user.id)
    db.add(ae)
    db.flush()
    audit(db, user.id, "adverse_event.reported", "adverse_event", ae.id, {"serious": body.serious})
    outcome = apply_rules(db, kb, user.id, trigger="adverse_event")
    db.commit()
    tasks.add_task(hub.push, outcome.new_alert_ids)
    return ae


@router.get("/safety", response_model=SafetyScreen)
def get_safety(user: User = Depends(require_patient), kb: KnowledgeBase = Depends(get_kb)):
    return safety_screen(kb)


@router.get("/messages", response_model=list[MessageOut])
def list_messages(user: User = Depends(require_patient), db: Session = Depends(get_db)):
    return db.scalars(select(Message).where(Message.patient_id == user.id).order_by(Message.created_at)).all()


@router.post("/messages", response_model=MessageOut)
def send_message(body: MessageIn, user: User = Depends(require_patient), db: Session = Depends(get_db)):
    # TODO: триаж сообщения через ml-service (/triage) → правило «тревожное сообщение»
    msg = Message(patient_id=user.id, sender_id=user.id, body=body.body)
    db.add(msg)
    db.commit()
    return msg
