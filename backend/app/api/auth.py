from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.deps import get_current_user
from app.schemas.auth import LoginRequest, LoginResponse, UserInfo
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username, User.active.is_(True)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )
    token = create_access_token(user.id, user.username, user.role_code)
    return LoginResponse(
        access_token=token,
        user_id=user.id,
        username=user.username,
        role_code=user.role_code,
        full_name=user.full_name,
        mine_id=user.mine_id,
    )


@router.get("/me", response_model=UserInfo)
def get_me(user: User = Depends(get_current_user)):
    return UserInfo(
        id=user.id,
        username=user.username,
        full_name=user.full_name,
        role_code=user.role_code,
        role_label=user.role.label,
        mine_id=user.mine_id,
        mine_name=user.mine.name if user.mine else None,
        department=user.department,
        can_enter=user.role.can_enter,
        can_approve=user.role.can_approve,
    )
