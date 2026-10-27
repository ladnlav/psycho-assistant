import secrets
import uuid
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.kb import KnowledgeBase, get_kb
from app.models import (AdverseEvent, Alert, AuditLog, DiaryEntry, DoctorPatientLink, Invite, MedicationIntake,
                        Message, PatientProfile, Prescription, Recommendation, Referral, ScaleResponse, User, utcnow)
from app.schemas import (AdverseEventOut, AlertOut, Decision, DiaryOut, IntakeOut, InviteCreate,
                         InviteOut, MessageIn, MessageOut, PatientCard, PatientSummary, PrescriptionCheck,
                         PrescriptionIn, PrescriptionOut, PrescriptionStop, RecommendationOut, ReferralIn,
                         ReferralOut, ScaleResult, ScaleSubmit, ScaleSubmitResult)
from app.security import ensure_own_patient, require_doctor
from app.services.alerts import hub
from app.services.anamnesis import diagnoses
from app.services.audit import audit
from app.services.clinical import record_scale
from app.services.context import pdc_7d
from app.services.drug_checks import check_prescription
from app.services.referrals import close_after_referral

router = APIRouter(prefix="/api/doctor", tags=["doctor"])

LEVEL_RANK = {"critical": 3, "high": 2, "medium": 1}
VIEW_AUDIT_WINDOW = timedelta(minutes=10)
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # без похожих символов (O/0, I/1)


@router.post("/invites", response_model=InviteOut)
def create_invite(body: InviteCreate, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    invite = Invite(code="".join(secrets.choice(_CODE_ALPHABET) for _ in range(8)), doctor_id=doctor.id,
                    patient_label=body.patient_label)
    db.add(invite)
    db.commit()
    return invite


@router.get("/invites", response_model=list[InviteOut])
def list_invites(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return db.scalars(select(Invite).where(Invite.doctor_id == doctor.id).order_by(Invite.created_at.desc())).all()


@router.get("/patients", response_model=list[PatientSummary])
def list_patients(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    """Список пациентов врача, отсортированный по риску (сначала открытые критические алерты).
    Дальше: индекс риска с разбором факторов."""
    patients = db.scalars(
        select(User).join(DoctorPatientLink, DoctorPatientLink.patient_id == User.id)
        .where(DoctorPatientLink.doctor_id == doctor.id, DoctorPatientLink.active.is_(True))
    ).all()
    out = []
    for p in patients:
        open_alerts = db.scalars(
            select(Alert.level).where(Alert.patient_id == p.id, Alert.acknowledged_at.is_(None))
        ).all()
        last: dict[str, ScaleResult] = {}
        for row in db.scalars(select(ScaleResponse).where(ScaleResponse.patient_id == p.id)
                              .order_by(ScaleResponse.created_at)):
            last[row.scale_id] = ScaleResult.model_validate(row)
        top = max(open_alerts, key=lambda lvl: LEVEL_RANK.get(lvl, 0), default=None)
        out.append(PatientSummary(id=p.id, full_name=p.full_name, open_alerts=len(open_alerts),
                                  top_alert_level=top, last_scores=last, diagnoses=diagnoses(db, p.id)))
    out.sort(key=lambda s: (-LEVEL_RANK.get(s.top_alert_level or "", 0), -s.open_alerts, s.full_name))
    return out


@router.get("/patients/{patient_id}", response_model=PatientCard)
def patient_card(patient_id: uuid.UUID, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    ensure_own_patient(db, doctor, patient_id)
    user = db.get(User, patient_id)
    profile = db.get(PatientProfile, patient_id)
    scales: dict[str, list[ScaleResult]] = {}
    for row in db.scalars(select(ScaleResponse).where(ScaleResponse.patient_id == patient_id)
                          .order_by(ScaleResponse.created_at)):
        scales.setdefault(row.scale_id, []).append(ScaleResult.model_validate(row))
    # Карточка опрашивается раз в 10 с; в журнал — один просмотр на врача и пациента за VIEW_AUDIT_WINDOW.
    seen = db.scalar(select(AuditLog.id).where(
        AuditLog.actor_id == doctor.id, AuditLog.action == "patient_card.viewed",
        AuditLog.entity_id == str(patient_id), AuditLog.created_at >= utcnow() - VIEW_AUDIT_WINDOW).limit(1))
    if seen is None:
        audit(db, doctor.id, "patient_card.viewed", "patient", patient_id)
        db.commit()
    return PatientCard(
        id=patient_id,
        full_name=user.full_name,
        birth_date=profile.birth_date if profile else None,
        diagnoses=diagnoses(db, patient_id),
        scales=scales,
        diary=[DiaryOut.model_validate(d) for d in db.scalars(
            select(DiaryEntry).where(DiaryEntry.patient_id == patient_id).order_by(DiaryEntry.day))],
        prescriptions=[PrescriptionOut.model_validate(p) for p in db.scalars(
            select(Prescription).where(Prescription.patient_id == patient_id).order_by(Prescription.start_date))],
        intakes=[IntakeOut.model_validate(i) for i in db.scalars(
            select(MedicationIntake).where(MedicationIntake.patient_id == patient_id)
            .order_by(MedicationIntake.day.desc()).limit(60))],
        pdc_7d=pdc_7d(db, patient_id, utcnow().date()),
        adverse_events=[AdverseEventOut.model_validate(a) for a in db.scalars(
            select(AdverseEvent).where(AdverseEvent.patient_id == patient_id)
            .order_by(AdverseEvent.created_at.desc()))],
        alerts=[AlertOut.model_validate(a) for a in db.scalars(
            select(Alert).where(Alert.patient_id == patient_id).order_by(Alert.created_at.desc()))],
        recommendations=[RecommendationOut.model_validate(r) for r in db.scalars(
            select(Recommendation).where(Recommendation.patient_id == patient_id)
            .order_by(Recommendation.created_at.desc()))],
        referrals=[ReferralOut.model_validate(r) for r in db.scalars(
            select(Referral).where(Referral.patient_id == patient_id).order_by(Referral.created_at.desc()))],
    )


def _ensure_registered(kb: KnowledgeBase, body: PrescriptionIn) -> None:
    if body.drug_id is not None:
        drug = kb.drugs.get(body.drug_id)
        if drug is None or not drug.registered_rf:
            raise HTTPException(422, "Препарат не найден среди зарегистрированных в РФ (kb/drugs)")


@router.post("/patients/{patient_id}/prescriptions/check", response_model=PrescriptionCheck)
def check_prescription_endpoint(patient_id: uuid.UUID, body: PrescriptionIn, doctor: User = Depends(require_doctor),
                                db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    """Пункты инструкции, которые врач должен учесть до назначения, и доза по инструкции для формы.
    Ничего не сохраняет."""
    ensure_own_patient(db, doctor, patient_id)
    _ensure_registered(kb, body)
    return check_prescription(db, kb, patient_id, body)


@router.post("/patients/{patient_id}/prescriptions", response_model=PrescriptionOut)
def prescribe(patient_id: uuid.UUID, body: PrescriptionIn, doctor: User = Depends(require_doctor),
              db: Session = Depends(get_db), kb: KnowledgeBase = Depends(get_kb)):
    """Назначение делает только врач. Пункты инструкции он должен учесть, а при противопоказании,
    найденном в карточке, — написать обоснование; всё это пишется в аудит."""
    ensure_own_patient(db, doctor, patient_id)
    _ensure_registered(kb, body)
    result = check_prescription(db, kb, patient_id, body)
    if any(w.id not in body.acknowledged_warnings for w in result.warnings):
        raise HTTPException(409, "Есть пункты инструкции, которые нужно учесть до назначения — обновите проверку")
    if any(w.requires_reason for w in result.warnings) and not (body.override_note or "").strip():
        raise HTTPException(422, "Назначение при противопоказании требует обоснования врача")
    rx = Prescription(patient_id=patient_id, doctor_id=doctor.id, drug_id=body.drug_id, drug_name=body.drug_name,
                      dose_mg=body.dose_mg, frequency=body.frequency, start_date=body.start_date or utcnow().date())
    db.add(rx)
    db.flush()
    details = body.model_dump(mode="json") | {
        "checked": result.checked, "warnings": [{"id": w.id, "kind": w.kind, "status": w.status} for w in result.warnings]}
    audit(db, doctor.id, "prescription.created", "prescription", rx.id, details)
    db.commit()
    return rx


@router.post("/prescriptions/{rx_id}/stop", response_model=PrescriptionOut)
def stop_prescription(rx_id: uuid.UUID, body: PrescriptionStop | None = None, doctor: User = Depends(require_doctor),
                      db: Session = Depends(get_db)):
    """Отменяет назначение тоже только врач; причина необязательна и пишется в аудит."""
    rx = db.get(Prescription, rx_id)
    if rx is None:
        raise HTTPException(404, "Назначение не найдено")
    ensure_own_patient(db, doctor, rx.patient_id)
    if not rx.active:
        raise HTTPException(409, "Назначение уже отменено")
    rx.active, rx.end_date = False, utcnow().date()
    reason = ((body.reason if body else None) or "").strip() or None
    audit(db, doctor.id, "prescription.stopped", "prescription", rx.id, {"reason": reason})
    db.commit()
    return rx


@router.post("/patients/{patient_id}/scales/{scale_id}", response_model=ScaleSubmitResult)
def submit_clinician_scale(patient_id: uuid.UUID, scale_id: str, body: ScaleSubmit, tasks: BackgroundTasks,
                           doctor: User = Depends(require_doctor), db: Session = Depends(get_db),
                           kb: KnowledgeBase = Depends(get_kb)):
    ensure_own_patient(db, doctor, patient_id)
    result, outcome = record_scale(db, kb, patient_id, doctor.id, scale_id, body.answers, rater="clinician")
    tasks.add_task(hub.push, outcome.push_ids)
    return result


@router.get("/alerts", response_model=list[AlertOut])
def open_alerts(doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    return db.scalars(select(Alert).where(Alert.doctor_id == doctor.id, Alert.acknowledged_at.is_(None))
                      .order_by(Alert.created_at.desc())).all()


@router.post("/alerts/{alert_id}/ack", response_model=AlertOut)
def acknowledge_alert(alert_id: uuid.UUID, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if alert is None or alert.doctor_id != doctor.id:
        raise HTTPException(404, "Алерт не найден")
    if alert.acknowledged_at is None:
        alert.acknowledged_at, alert.acknowledged_by = utcnow(), doctor.id
        audit(db, doctor.id, "alert.acknowledged", "alert", alert.id)
        db.commit()
    return alert


@router.post("/recommendations/{rec_id}/decision", response_model=RecommendationOut)
def decide(rec_id: uuid.UUID, body: Decision, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    """Единственное место, где предложение системы становится клиническим действием — решением врача."""
    rec = db.get(Recommendation, rec_id)
    if rec is None:
        raise HTTPException(404, "Рекомендация не найдена")
    ensure_own_patient(db, doctor, rec.patient_id)
    if rec.status != "proposed":
        raise HTTPException(409, "Решение уже принято")
    rec.status, rec.decided_by, rec.decided_at, rec.decision_note = body.decision, doctor.id, utcnow(), body.note
    audit(db, doctor.id, f"recommendation.{body.decision}", "recommendation", rec.id, {"note": body.note})
    if body.decision == "accepted" and rec.kind == "referral":
        db.add(Referral(patient_id=rec.patient_id, recommendation_id=rec.id, to_specialty=rec.payload["to"],
                        level=rec.payload["level"], reason=rec.payload.get("reason_ru", ""),
                        confirmed_by=doctor.id))
        db.flush()  # autoflush выключен: без этого rec в базе ещё «proposed» и закрылся бы с остальными
        close_after_referral(db, doctor.id, rec.patient_id, rec.payload["to"])
    db.commit()
    return rec


@router.post("/patients/{patient_id}/referrals", response_model=ReferralOut)
def create_referral(patient_id: uuid.UUID, body: ReferralIn, doctor: User = Depends(require_doctor),
                    db: Session = Depends(get_db)):
    """Направление по решению врача, без предложения правила: уровень и причину врач указывает сам.
    Открытые предложения правил к тому же специалисту закрываются: пациент уже направлен."""
    ensure_own_patient(db, doctor, patient_id)
    ref = Referral(patient_id=patient_id, to_specialty=body.to_specialty, level=body.level, reason=body.reason,
                   confirmed_by=doctor.id)
    db.add(ref)
    db.flush()
    audit(db, doctor.id, "referral.created", "referral", ref.id, body.model_dump())
    close_after_referral(db, doctor.id, patient_id, body.to_specialty)
    db.commit()
    return ref


@router.get("/patients/{patient_id}/messages", response_model=list[MessageOut])
def list_messages(patient_id: uuid.UUID, doctor: User = Depends(require_doctor), db: Session = Depends(get_db)):
    ensure_own_patient(db, doctor, patient_id)
    return db.scalars(select(Message).where(Message.patient_id == patient_id).order_by(Message.created_at)).all()


@router.post("/patients/{patient_id}/messages", response_model=MessageOut)
def send_message(patient_id: uuid.UUID, body: MessageIn, doctor: User = Depends(require_doctor),
                 db: Session = Depends(get_db)):
    ensure_own_patient(db, doctor, patient_id)
    msg = Message(patient_id=patient_id, sender_id=doctor.id, body=body.body)
    db.add(msg)
    db.commit()
    return msg
