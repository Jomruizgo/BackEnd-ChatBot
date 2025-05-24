# app/main.py
import os
from dotenv import load_dotenv # Import load_dotenv

# --- Load environment variables from .env file ---
# This must happen before any module that imports 'settings'
# to ensure settings are populated correctly from the .env file.
load_dotenv()
# --- End .env loading ---

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware # Import the CORS middleware

from app.api.v1.endpoints import chat as chat_v1
from app.core.config import settings
from app.db.database import create_db_and_tables # Function to create tables at startup (optional)
# from app.services.llm_handler import init_llm_client # If the LLM client needs global initialization

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json" # Good practice to include openapi_url
)

# --- CORS Configuration ---
# Define allowed origins for your frontend.
# IMPORTANT: For production, replace "*" with your actual frontend domain(s)!
origins = [
    "http://localhost",
    "http://localhost:3000", # Example: if your React/Vue/Angular app runs here
    "http://localhost:5173", # Another common dev port
    # "https://your-frontend-domain.com", # Add your production frontend domain(s) here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,         # Specifies which origins are allowed to make requests.
    allow_credentials=True,        # Allows cookies, authorization headers, etc.
    allow_methods=["*"],           # Allows all standard HTTP methods (GET, POST, PUT, DELETE, etc.).
    allow_headers=["*"],           # Allows all HTTP headers.
)
# --- End CORS Configuration ---


@app.on_event("startup")
async def on_startup():
    # await init_llm_client() # Example: initialize Gemini client
    await create_db_and_tables() # Create conversation DB tables if they don't exist
    print("FastAPI application startup complete.")

app.include_router(chat_v1.router, prefix=settings.API_V1_STR, tags=["Chat V1"])

@app.get("/", tags=["Root"])
async def read_root():
    return {"message": f"Welcome to {settings.PROJECT_NAME}"}