# app/tools/postgres_tool.py
import json
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text as sa_text

# Asume que BaseTool está definida así o similar en app/tools/base_tool.py
# Si no la tienes, te la proporciono al final.
from app.tools.base_tool import BaseTool

class PostgresTool(BaseTool):
    # La clase BaseTool requiere que estas propiedades sean definidas
    name: str = "postgres_query_tool" 
    description: str = "Ejecuta una consulta SQL SELECT contra la base de datos PostgreSQL externa para obtener información de la base de datos."
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "La consulta SQL a ejecutar. DEBE ser una instrucción SELECT válida."
            }
        },
        "required": ["query"]
    }

    def __init__(self, db_url: str):
        self.db_url = db_url # Guardamos la URL para propósitos de logging si es necesario
        self.engine = create_async_engine(db_url)
        self.AsyncSessionLocal = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        print(f"INFO:app.tools.postgres_tool:PostgresTool inicializado para DB: {db_url.split('@')[-1]}")

    async def run(self, query: str) -> Dict[str, Any]:
        """
        Ejecuta una consulta SQL contra la base de datos PostgreSQL.
        Solo se permiten consultas SELECT.
        """
        # Validación de seguridad: solo permitir SELECT
        if not query.strip().upper().startswith("SELECT"):
            return {"error": "Solo se permiten consultas SELECT por razones de seguridad."}

        async with self.AsyncSessionLocal() as session:
            try:
                # Ejecutar la consulta
                result = await session.execute(sa_text(query))
                
                # Obtener nombres de columnas
                column_names = list(result.keys())
                
                # Obtener todas las filas
                rows = result.fetchall()
                
                # Formatear resultados como una lista de diccionarios
                formatted_results = []
                for row in rows:
                    formatted_results.append({col: row[i] for i, col in enumerate(column_names)})
                
                print(f"DEBUG:app.tools.postgres_tool:Consulta SQL ejecutada: {query}")
                print(f"DEBUG:app.tools.postgres_tool:Resultados: {json.dumps(formatted_results, indent=2)}")

                return {"success": True, "data": formatted_results}
            except Exception as e:
                await session.rollback() # Revertir la transacción en caso de error
                print(f"ERROR:app.tools.postgres_tool:Error al ejecutar la consulta SQL '{query}': {e}")
                return {"success": False, "error": f"Error al ejecutar la consulta SQL: {str(e)}"}