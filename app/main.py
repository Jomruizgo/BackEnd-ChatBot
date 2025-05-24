# app/main.py
from fastapi import FastAPI
from app.api.v1.endpoints import chat as chat_v1
from app.core.config import settings
from app.db.database import create_db_and_tables # Función para crear tablas al inicio (opcional)
# from app.services.llm_handler import init_llm_client # Si el cliente LLM necesita inicialización global

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

@app.on_event("startup")
async def on_startup():
    # await init_llm_client() # Ejemplo: inicializar cliente Gemini
    await create_db_and_tables() # Crea tablas de la BD de conversaciones si no existen
    print("FastAPI application startup complete.")

app.include_router(chat_v1.router, prefix=settings.API_V1_STR, tags=["Chat V1"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}