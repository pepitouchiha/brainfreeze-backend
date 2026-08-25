from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import CORS_ORIGINS
from app.db.base_all import Base
from app.db.session import engine
from app.routers import auth, categorias, health, insumos, mesas, productos, reportes, ventas


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="BrainFreeze API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(categorias.router)
app.include_router(mesas.router)
app.include_router(productos.router)
app.include_router(insumos.router)
app.include_router(ventas.router)
app.include_router(reportes.router)
