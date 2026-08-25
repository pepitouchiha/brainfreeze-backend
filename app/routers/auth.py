from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models.usuario import Usuario
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales inválidas",
    )

    usuario = db.query(Usuario).filter(Usuario.email == payload.email).first()
    if usuario is None or not verify_password(payload.password, usuario.password_hash):
        raise credenciales_invalidas

    token = create_access_token(subject=usuario.email)
    return TokenResponse(access_token=token)
