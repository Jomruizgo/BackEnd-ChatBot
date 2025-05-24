# app/tools/mysql_tool.py
import json
from typing import Dict, Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text as sa_text
import logging

from app.tools.base_tool import BaseTool

class MySQLTool(BaseTool):
    name: str = "mysql_tool"
    description: str = "Ejecuta consultas SQL SELECT para obtener información de la base de datos MySQL. Usar cuando el usuario pregunte por datos específicos como productos, empleados, inventario, etc."
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Consulta SQL SELECT válida para ejecutar contra la base de datos MySQL"
            }
        },
        "required": ["query"]
    }

    def __init__(self, db_url: str):
        self.db_url = db_url 
        self.engine = create_async_engine(db_url, echo=False)  # echo=False para menos ruido
        self.AsyncSessionLocal = sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )
        print(f"INFO:app.tools.mysql_tool:MySQLTool inicializado para DB: {db_url.split('@')[-1] if '@' in db_url else db_url}")

    async def run(self, query: str) -> Dict[str, Any]:
        """
        Ejecuta una consulta SQL SELECT contra la base de datos MySQL.
        Solo se permiten consultas SELECT por seguridad.
        """
        # Validar que sea SELECT
        query_stripped = query.strip()
        if not query_stripped.upper().startswith("SELECT"):
            return {
                "success": False,
                "error": "Solo se permiten consultas SELECT por razones de seguridad.",
                "data": []
            }

        async with self.AsyncSessionLocal() as session:
            try:
                print(f"INFO:app.tools.mysql_tool:Ejecutando consulta: {query}")
                
                result = await session.execute(sa_text(query))
                
                # Obtener nombres de columnas y filas
                if result.returns_rows:
                    column_names = list(result.keys())
                    rows = result.fetchall()
                    
                    formatted_results = []
                    for row in rows:
                        row_dict = {}
                        for i, col in enumerate(column_names):
                            value = row[i]
                            # Convertir tipos no serializables a string
                            if hasattr(value, 'isoformat'):  # datetime objects
                                value = value.isoformat()
                            elif isinstance(value, bytes):
                                value = value.decode('utf-8', errors='replace')
                            row_dict[col] = value
                        formatted_results.append(row_dict)
                    
                    print(f"INFO:app.tools.mysql_tool:Consulta exitosa. {len(formatted_results)} filas retornadas")
                    
                    return {
                        "success": True,
                        "data": formatted_results,
                        "row_count": len(formatted_results)
                    }
                else:
                    return {
                        "success": True,
                        "data": [],
                        "message": "Consulta ejecutada exitosamente sin resultados"
                    }
                    
            except Exception as e:
                await session.rollback()
                error_msg = f"Error ejecutando consulta SQL: {str(e)}"
                print(f"ERROR:app.tools.mysql_tool:{error_msg}")
                print(f"ERROR:app.tools.mysql_tool:Consulta problemática: {query}")
                
                return {
                    "success": False,
                    "error": error_msg,
                    "data": []
                }