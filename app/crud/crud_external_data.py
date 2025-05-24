# app/crud/crud_external_data.py
import aiomysql
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text # Para ejecutar SQL raw con SQLAlchemy
from app.core.config import settings # Para la URL de la BD externa

# --- Opción 1: Usando aiomysql directamente (similar a como lo haría la tool) ---

async def _get_external_db_connection_direct():
    """Helper para obtener una conexión directa a la BD externa."""
    # Parsear la URL de forma más robusta es recomendable
    db_url_parts = settings.EXTERNAL_DB_URL.replace("mysql+aiomysql://", "").split("@")
    user_pass, host_db = db_url_parts[0], db_url_parts[1]
    user, password = user_pass.split(":")
    host_port, db_name = host_db.split("/")
    host, port_str = host_port.split(":")

    return await aiomysql.connect(
        host=host, port=int(port_str),
        user=user, password=password,
        db=db_name, autocommit=True
    )

async def execute_raw_sql_external_db_direct(sql_query: str, params: Optional[tuple] = None) -> List[Dict[str, Any]]:
    """
    Ejecuta una consulta SQL raw en la base de datos externa y devuelve los resultados.
    ¡ASEGÚRATE DE QUE LA SQL SEA SEGURA SI VIENE DE UNA ENTRADA NO CONFIABLE!
    Esta función es la que usaría tu `MCPSQLQueryTool` internamente.
    """
    conn = None
    results = []
    try:
        conn = await _get_external_db_connection_direct()
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql_query, args=params)
            results = await cur.fetchall()
        return results
    except Exception as e:
        print(f"Error ejecutando SQL en BD externa (directo): {e}")
        # Aquí podrías relanzar la excepción o devolver un error estructurado
        raise  # O return {"error": str(e), "query": sql_query}
    finally:
        if conn:
            conn.close()

# --- Opción 2: Usando SQLAlchemy para la BD externa (si defines modelos o prefieres su API) ---
# Necesitarías definir `async_engine_external` y `AsyncSessionLocalExternal` en `app/db/database.py`
# y modelos en `app/db/models_external.py` si usas ORM.

async def execute_raw_sql_external_db_sqlalchemy(db: AsyncSession, sql_query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Ejecuta una consulta SQL raw en la base de datos externa usando una sesión de SQLAlchemy.
    ¡ASEGÚRATE DE QUE LA SQL SEA SEGURA!
    """
    try:
        result = await db.execute(text(sql_query), params)
        # Si es un SELECT, puedes obtener los resultados como diccionarios
        if result.returns_rows:
            return [dict(row) for row in result.mappings().all()]
        await db.commit() # Para INSERT, UPDATE, DELETE
        return [] # O un mensaje de éxito
    except Exception as e:
        await db.rollback()
        print(f"Error ejecutando SQL en BD externa (SQLAlchemy): {e}")
        raise # O return {"error": str(e), "query": sql_query}

# --- EJEMPLOS DE FUNCIONES ESPECÍFICAS (QUE TU TOOL PODRÍA LLAMAR INTERNAMENTE) ---
# Estos son solo ejemplos, DEBES adaptarlos a tu esquema de BD externa.

# async def get_products_by_category_from_external_db(category_name: str) -> List[Dict[str, Any]]:
#     """Ejemplo: Obtener productos por categoría de la BD externa."""
#     # ¡VALIDAR Y SANITIZAR category_name!
#     query = "SELECT product_id, name, price, stock FROM products WHERE category = %s"
#     # Usando la conexión directa:
#     # return await execute_raw_sql_external_db_direct(query, (category_name,))
#
#     # O si usas SQLAlchemy session pasada a esta función:
#     # async with AsyncSessionLocalExternal() as session_ext:
#     #     return await execute_raw_sql_external_db_sqlalchemy(session_ext, query, {"category": category_name})


# async def count_users_in_external_db() -> Optional[int]:
#     """Ejemplo: Contar usuarios en la BD externa."""
#     query = "SELECT COUNT(*) as total_users FROM external_users_table;"
#     results = await execute_raw_sql_external_db_direct(query)
#     if results and results[0].get('total_users') is not None:
#         return int(results[0]['total_users'])
#     return None