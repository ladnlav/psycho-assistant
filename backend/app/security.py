import uuid
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import DoctorPatientLink, User, utcnow

_hasher = PasswordHasher()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_token(user: User) -> str:
    s = get_settings()
    payload = {"sub": str(user.id), "role": user.role, "exp": utcnow() + timedelta(hours=s.jwt_ttl_hours)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def user_from_token(db: Session, token: str) -> User:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        user = None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход", headers={"WWW-Authenticate": "Bearer"})
    return user


def current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return user_from_token(db, token)


def require_doctor(user: User = Depends(current_user)) -> User:
    if user.role != "doctor":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно только врачу")
    return user


def require_patient(user: User = Depends(current_user)) -> User:
    if user.role != "patient":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступно только пациенту")
    return user


def ensure_own_patient(db: Session, doctor: User, patient_id: uuid.UUID) -> None:
    """Врач видит только закреплённых за ним пациентов."""
    linked = db.scalar(
        select(DoctorPatientLink.id).where(
            DoctorPatientLink.doctor_id == doctor.id,
            DoctorPatientLink.patient_id == patient_id,
            DoctorPatientLink.active.is_(True),
        )
    )
    if linked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Пациент не найден")
