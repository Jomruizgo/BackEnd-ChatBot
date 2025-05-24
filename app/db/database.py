# app/db/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Motor para la base de datos de conversaciones
async_engine_conv = create_async_engine(
    settings.CONVERSATION_DB_URL,
    pool_recycle=3600, # Opcional: reciclar conexiones
    echo=False # Poner en True para debugging SQL
)
AsyncSessionLocalConversation = sessionmaker(
    bind=async_engine_conv, class_=AsyncSession, expire_on_commit=False
)
BaseConversation = declarative_base() # Los modelos de conversación heredarán de aquí

# Motor para la base de datos externa (si se accede vía SQLAlchemy en alguna tool)
# A menudo, las tools pueden usar conexiones directas (ej: aiomysql.connect)
# pero si hay ORM involucrado para la tool, se definiría similar.
async_engine_external = create_async_engine(
    settings.EXTERNAL_DB_URL,
    pool_recycle=3600,
    echo=False
)
AsyncSessionLocalExternal = sessionmaker(
    bind=async_engine_external, class_=AsyncSession, expire_on_commit=False
)
BaseExternal = declarative_base() # Los modelos de datos externos heredarán de aquí

# Dependencia para obtener sesión de BD de conversaciones en endpoints
async def get_conv_db() -> AsyncSession:
    async with AsyncSessionLocalConversation() as session:
        yield session

# Dependencia para obtener sesión de BD externa (si es necesaria)
async def get_external_db() -> AsyncSession:
    async with AsyncSessionLocalExternal() as session:
        yield session

# Función para crear tablas (ejecutar en startup)
async def create_db_and_tables():
    async with async_engine_conv.begin() as conn:
        # await conn.run_sync(BaseConversation.metadata.drop_all) # Para limpiar en desarrollo
        await conn.run_sync(BaseConversation.metadata.create_all)
    # Si tienes modelos para la DB externa y quieres crearlos con SQLAlchemy:
    # async with async_engine_external.begin() as conn:
    #     await conn.run_sync(BaseExternal.metadata.create_all)