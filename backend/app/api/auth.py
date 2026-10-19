from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Consent, DoctorPatientLink, DoctorProfile, Invite, PatientProfile, User, utcnow
from app.schemas import DoctorRegister, Me, PatientRegister, Token
from app.security import create_token, current_user, hash_password, verify_password
from app.services.alerts import lead_doctor_id
from app.services.audit import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])

CONSENT_VERSION = "v0-draft"  # TODO: текст согласия (152-ФЗ) — юридически выверенная версия


def _ensure_email_free(db: Session, email: str) -> None:
    if db.scalar(select(User.id).where(User.email == email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Пользователь с таким email уже существует")


@router.post("/register/doctor", response_model=Token)
def register_doctor(body: DoctorRegister, db: Session = Depends(get_db)):
    _ensure_email_free(db, body.email)
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), role="doctor",
                full_name=body.full_name)
    db.add(user)
    db.flush()
    db.add(DoctorProfile(user_id=user.id, specialty=body.specialty))
    audit(db, user.id, "user.registered", "user", user.id, {"role": "doctor"})
    db.commit()
    return Token(access_token=create_token(user))


@router.post("/register/patient", response_model=Token)
def register_patient(body: PatientRegister, db: Session = Depends(get_db)):
    if not body.consent_pd:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Без согласия на обработку персональных данных "
                                                          "регистрация невозможна")
    invite = db.scalar(select(Invite).where(Invite.code == body.invite_code.strip().upper()))
    if invite is None or invite.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код приглашения недействителен")
    _ensure_email_free(db, body.email)

    user = User(email=body.email.lower(), password_hash=hash_password(body.password), role="patient",
                full_name=body.full_name)
    db.add(user)
    db.flush()
    db.add(PatientProfile(user_id=user.id))
    db.flush()
    db.add(DoctorPatientLink(doctor_id=invite.doctor_id, patient_id=user.id))
    db.add(Consent(patient_id=user.id, kind="pd_processing", version=CONSENT_VERSION))
    invite.used_at, invite.used_by = utcnow(), user.id
    audit(db, user.id, "user.registered", "user", user.id, {"role": "patient", "doctor": str(invite.doctor_id)})
    db.commit()
    return Token(access_token=create_token(user))


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный email или пароль")
    return Token(access_token=create_token(user))


@router.get("/me", response_model=Me)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    out = Me(id=user.id, email=user.email, full_name=user.full_name, role=user.role)
    if user.role == "doctor" and user.doctor_profile:
        out.specialty = user.doctor_profile.specialty
    if user.role == "patient":
        doctor_id = lead_doctor_id(db, user.id)
        doctor = db.get(User, doctor_id) if doctor_id else None
        out.doctor_name = doctor.full_name if doctor else None
    return out
