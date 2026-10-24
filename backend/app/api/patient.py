from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.kb import KnowledgeBase, Scale, get_kb
from app.models import (AdverseEvent, DiaryEntry, MedicationIntake, Message, Prescription, ScaleResponse, User,
                        utcnow)
from app.schemas import (AdverseEventIn, AdverseEventOut, AdverseEventSent, DiaryIn, DiaryOut, HelpIn, IntakeIn, IntakeOut,
                         MessageIn, MessageOut, MessageSent, PrescriptionOut, Reminder, SafetyScreen, ScaleSchedule,
                         ScaleSubmit, ScaleSubmitResult)
from app.security import require_patient
from app.services.alerts import apply_rules, hub, patient_reminders
from app.services.audit import audit
from app.services.clinical import record_scale, safety_screen
from app.services.triage import classify

router = APIRouter(prefix="/api/patient", tags=["patient"])


@router.get("/scales", response_model=list[Scale])
def my_scales(user: User = Depends(require_patient), kb: KnowledgeBase = Depends(get_kb)):
    return [s for s in kb.scales.values() if s.rater == "patient"]


@router.get("/scales/schedule", response_model=list[ScaleSchedule])
def my_schedule(user: User = Depends(require_patient), db: Session = Depends(get_db),
                kb: KnowledgeBase = Depends(get_kb)):
    """Когда заполнять шкалы: первый раз — сразу, дальше раз в schedule_days из kb/scales.
    Заполнить раньше срока можно всегда («Стало хуже — пройти сейчас»)."""
    today = utcnow().date()
    out = []
    for s in kb.scales.values():
        if s.rater != "patient":
            continue
        last = db.scalar(select(func.max(ScaleResponse.created_at))
                         .where(ScaleResponse.patient_id == user.id, ScaleResponse.scale_id == s.id))
        next_due = last.date() + timedelta(days=s.schedule_days) if last and s.schedule_days else None
        out.append(ScaleSchedule(scale_id=s.id, last_taken_at=last, next_due=next_due,
                                 due=next_due is None or today >= next_due))
    return out


@router.post("/scales/{scale_id}", response_model=ScaleSubmitResult)
def submit_scale(scale_id: str, body: ScaleSubmit, tasks: BackgroundTasks, user: User = Depends(require_patient),
                 db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    result, outcome = record_scale(db, kb, user.id, user.id, scale_id, body.answers, rater="patient")
    tasks.add_task(hub.push, outcome.push_ids)
    return result


@router.post("/diary", response_model=DiaryOut)
def add_diary(body: DiaryIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
              db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    day = body.day or utcnow().date()
    entry = db.scalar(select(DiaryEntry).where(DiaryEntry.patient_id == user.id, DiaryEntry.day == day)
                      .order_by(DiaryEntry.created_at.desc()).limit(1))
    if entry is None:  # одна запись в день; повторное сохранение — исправление
        entry = DiaryEntry(patient_id=user.id, day=day)
        db.add(entry)
    entry.anxiety, entry.mood, entry.sleep_quality, entry.note = body.anxiety, body.mood, body.sleep_quality, body.note
    db.flush()
    outcome = apply_rules(db, kb, user.id, trigger="diary")
    db.commit()
    tasks.add_task(hub.push, outcome.push_ids)
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
    tasks.add_task(hub.push, outcome.push_ids)
    return intake


@router.get("/adverse-events", response_model=list[AdverseEventOut])
def my_adverse_events(user: User = Depends(require_patient), db: Session = Depends(get_db)):
    return db.scalars(select(AdverseEvent).where(AdverseEvent.patient_id == user.id)
                      .order_by(AdverseEvent.created_at.desc()).limit(10)).all()


@router.post("/adverse-events", response_model=AdverseEventSent)
def report_adverse_event(body: AdverseEventIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
                         db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    ae = AdverseEvent(patient_id=user.id, description=body.description, severity=body.severity,
                      serious=body.serious, reported_by=user.id, triage=classify(body.description))
    db.add(ae)
    db.flush()
    audit(db, user.id, "adverse_event.reported", "adverse_event", ae.id, {"serious": body.serious})
    outcome = apply_rules(db, kb, user.id, trigger="adverse_event")
    db.commit()
    tasks.add_task(hub.push, outcome.push_ids)
    return AdverseEventSent(**AdverseEventOut.model_validate(ae).model_dump(),
                            safety=safety_screen(kb, bool(outcome.push_ids)) if outcome.show_safety_screen else None)


@router.get("/safety", response_model=SafetyScreen)
def get_safety(user: User = Depends(require_patient), kb: KnowledgeBase = Depends(get_kb)):
    return safety_screen(kb)


@router.post("/help", response_model=MessageSent)
def ask_for_help(body: HelpIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
                 db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    """Кнопка «Нужна срочная помощь»: экран 112/103 пациент видит сразу, а после того как напишет, что
    случилось, причина уходит врачу — сообщением в чат и алертом (правило patient_help_request)."""
    msg = Message(patient_id=user.id, sender_id=user.id, body=body.reason, kind="help", triage=classify(body.reason))
    db.add(msg)
    db.flush()
    audit(db, user.id, "help_request.created", "message", msg.id)
    outcome = apply_rules(db, kb, user.id, trigger="help_request")
    db.commit()
    tasks.add_task(hub.push, outcome.push_ids)
    return MessageSent(**MessageOut.model_validate(msg).model_dump(), safety=safety_screen(kb, bool(outcome.push_ids)))


@router.get("/reminders", response_model=list[Reminder])
def my_reminders(user: User = Depends(require_patient), db: Session = Depends(get_db),
                 kb: KnowledgeBase = Depends(get_kb)):
    """Напоминания из правил с remind_patient (kb/rules): например, «нет записей 3 дня»."""
    return [Reminder(rule_id=rid, text_ru=text) for rid, text in patient_reminders(db, kb, user.id)]


@router.get("/messages", response_model=list[MessageOut])
def list_messages(user: User = Depends(require_patient), db: Session = Depends(get_db)):
    return db.scalars(select(Message).where(Message.patient_id == user.id).order_by(Message.created_at)).all()


@router.post("/messages", response_model=MessageSent)
def send_message(body: MessageIn, tasks: BackgroundTasks, user: User = Depends(require_patient),
                 db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    msg = Message(patient_id=user.id, sender_id=user.id, body=body.body, triage=classify(body.body))
    db.add(msg)
    db.flush()
    outcome = apply_rules(db, kb, user.id, trigger="message")
    db.commit()
    tasks.add_task(hub.push, outcome.push_ids)
    return MessageSent(**MessageOut.model_validate(msg).model_dump(),
                       safety=safety_screen(kb, bool(outcome.push_ids)) if outcome.show_safety_screen else None)
