from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1)

    @field_validator("email")
    @classmethod
    def validar_email(cls, v: str) -> str:
        v = v.strip().lower()
        if "@" not in v:
            raise ValueError("email inválido")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
