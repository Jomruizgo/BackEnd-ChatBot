# app/core/config.py
import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv() # Carga variables desde el archivo .env

class Settings(BaseSettings):
    PROJECT_NAME: str = "Chatbot con Memoria y Tools"
    API_V1_STR: str = "/api/v1"

    # Base de datos de conversaciones (MySQL Asíncrona)
    CONVERSATION_DB_USER: str = os.getenv("CONVERSATION_DB_USER", "user")
    CONVERSATION_DB_PASSWORD: str = os.getenv("CONVERSATION_DB_PASSWORD", "password")
    CONVERSATION_DB_HOST: str = os.getenv("CONVERSATION_DB_HOST", "localhost")
    CONVERSATION_DB_PORT: str = os.getenv("CONVERSATION_DB_PORT", "3306")
    CONVERSATION_DB_NAME: str = os.getenv("CONVERSATION_DB_NAME", "conversation_db")
    CONVERSATION_DB_URL: str = f"mysql+aiomysql://{CONVERSATION_DB_USER}:{CONVERSATION_DB_PASSWORD}@{CONVERSATION_DB_HOST}:{CONVERSATION_DB_PORT}/{CONVERSATION_DB_NAME}"

    # Base de datos externa para MCP (MySQL Asíncrona)
    EXTERNAL_DB_USER: str = os.getenv("EXTERNAL_DB_USER", "ext_user")
    EXTERNAL_DB_PASSWORD: str = os.getenv("EXTERNAL_DB_PASSWORD", "ext_password")
    EXTERNAL_DB_HOST: str = os.getenv("EXTERNAL_DB_HOST", "localhost")
    EXTERNAL_DB_PORT: str = os.getenv("EXTERNAL_DB_PORT", "3307") # Puerto diferente ejemplo
    EXTERNAL_DB_NAME: str = os.getenv("EXTERNAL_DB_NAME", "external_info_db")
    EXTERNAL_DB_URL: str = f"mysql+aiomysql://{EXTERNAL_DB_USER}:{EXTERNAL_DB_PASSWORD}@{EXTERNAL_DB_HOST}:{EXTERNAL_DB_PORT}/{EXTERNAL_DB_NAME}"

    # Gemini API Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

    # Pydantic Settings la leerá de la variable de entorno GEMINI_LLM_MODEL
    # Si no está definida, usará "gemini-1.5-flash" como valor por defecto.
    GEMINI_LLM_MODEL: str = "gemini-1.5-flash" 

    class Config:
        case_sensitive = True
        env_file = ".env"
        env_file_encoding = 'utf-8'

settings = Settings()