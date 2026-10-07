from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, RegistrationStatus, TokenResponse
from app.schemas.user import UserRead

router = APIRouter(prefix="/api/auth", tags=["auth"])

REGISTRATION_CLOSED = "Sign-ups are closed. This sportsbook is limited to a few friends."


def registration_open(db: Session) -> bool:
    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    return user_count < get_settings().max_users


@router.get("/registration", response_model=RegistrationStatus)
def registration_status(db: Session = Depends(get_db)) -> RegistrationStatus:
    return RegistrationStatus(open=registration_open(db))


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Serialize sign-ups so two at once can't both squeeze under the limit.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('register'))"))
    if not registration_open(db):
        raise HTTPException(status_code=403, detail=REGISTRATION_CLOSED)

    email = payload.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        balance_cents=get_settings().starting_balance_cents,
    )
    db.add(user)
    db.commit()

    return TokenResponse(access_token=create_access_token(subject=str(user.id)))


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(subject=str(user.id)))


@router.get("/me", response_model=UserRead)
def me(current: User = Depends(get_current_user)) -> User:
    return current
