# app/tools/mcp_sql_query_tool.py
from pydantic import BaseModel, Field
from typing import Dict, Any, List
import json
import aiomysql # Para conexión directa asíncrona a MySQL

from app.tools.base_tool import BaseTool
from app.core.config import settings
# from app.crud.crud_external_data import execute_dynamic_query # Si tienes helpers en CRUD

class MCPSQLQueryArgs(BaseModel):
    natural_language_query: str = Field(description="La pregunta del usuario en lenguaje natural sobre los datos de la empresa.")
    # O podrías intentar que Gemini devuelva una query más estructurada:
    # table_name: Optional[str] = Field(None, description="Nombre de la tabla a consultar si se puede inferir.")
    # columns: Optional[List[str]] = Field(None, description="Columnas a seleccionar.")
    # conditions: Optional[str] = Field(None, description="Condiciones para la cláusula WHERE (formato SQL simplificado).")

class MCPSQLQueryTool(BaseTool):
    name: str = "query_external_company_database"
    description: str = (
        "Consulta la base de datos externa de la empresa para responder preguntas sobre datos específicos. "
        "Utiliza esta herramienta cuando el usuario pregunte por información que reside en la base de datos de la compañía, "
        "como '¿cuántos productos tenemos de la categoría X?' o 'lista los empleados del departamento Y'."
    )
    args_schema: type[BaseModel] = MCPSQLQueryArgs

    async def _generate_safe_sql_from_nl(self, nl_query: str) -> tuple[str, list]:
        """
        Genera SQL y parámetros para una consulta segura.
        Devuelve una tupla (sql_query, params).
        """
        print(f"NL Query para convertir a SQL: {nl_query}")

        sql_query = ""
        params = []

        if "productos de la categoría" in nl_query.lower():
            try:
                # Extraer categoría (esto es lo que el LLM debería ayudar a hacer)
                # Aquí simulamos la extracción, pero el LLM lo haría mejor y más seguro.
                category = nl_query.split("categoría")[-1].strip().replace("?", "")
                
                # ¡USAR PARÁMETROS PARA SEGURIDAD!
                sql_query = "SELECT nombre, precio FROM productos WHERE categoria = %s;"
                params = [category]
            except Exception as e:
                # Fallback, pero idealmente el LLM debería ser más robusto
                print(f"Error extracting category: {e}. Falling back to general query.")
                sql_query = "SELECT nombre, precio, categoria FROM productos LIMIT 10;"
                params = [] # No params needed for LIMIT query
        elif "listar empleados" in nl_query.lower():
            sql_query = "SELECT nombre, departamento, puesto FROM empleados LIMIT 10;"
            params = []
        else:
            raise ValueError("No se pudo generar una consulta SQL segura para la pregunta.")
        
        # Idealmente, aquí usarías el LLM para generar la SQL y luego la validarías.
        # Por ahora, simplemente devolvemos la query y los parámetros.
        return sql_query, params

    async def execute(self, natural_language_query: str) -> str:
        print(f"MCP Tool: Recibida pregunta en lenguaje natural: '{natural_language_query}'")
        sql_query = ""
        params = [] # Initialize params list
        conn = None
        try:
            # --- Opción A: LLM genera SQL y parámetros (más seguro) ---
            # En un sistema real, aquí llamarías al LLM para generar tanto la SQL
            # como los parámetros basados en la pregunta del usuario y el esquema de la BD.
            # Por ahora, usamos la simulación local.
            sql_query, params = await self._generate_safe_sql_from_nl(natural_language_query)

            # --- Opción B: Mapeo simple (SOLO PARA DEMO, NO ESCALABLE NI SEGURO si no usa parámetros) ---
            if not sql_query: # Si _generate_safe_sql_from_nl no generó nada, probamos con las predefinidas
                if "cuántos usuarios hay registrados" in natural_language_query.lower():
                    sql_query = "SELECT COUNT(*) as total_usuarios FROM users;"
                    params = []
                elif "listar los últimos 5 productos" in natural_language_query.lower():
                    sql_query = "SELECT product_name, price FROM products ORDER BY created_at DESC LIMIT 5;"
                    params = []
                else:
                    return json.dumps({"error": "No se pudo interpretar la pregunta para consultar la base de datos. Por favor, sé más específico o reformula tu pregunta."})

            print(f"MCP Tool: SQL query generada/seleccionada: {sql_query} with params: {params}")

            conn = await self._get_db_connection()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # --- EJECUTAR LA QUERY CON PARÁMETROS ---
                if params:
                    await cur.execute(sql_query, params)
                else:
                    await cur.execute(sql_query)
                result = await cur.fetchall()

            if not result:
                return json.dumps({"message": "No se encontraron resultados para tu consulta."})

            return json.dumps({"data": result, "query_executed": sql_query})

        except ValueError as ve:
            print(f"MCP Tool Error (ValueError): {ve}")
            return json.dumps({"error": str(ve)})
        except aiomysql.MySQLError as db_err:
            print(f"MCP Tool Error (Database): {db_err}")
            return json.dumps({"error": f"Hubo un problema al consultar la base de datos. SQL intentada: {sql_query}"})
        except Exception as e:
            print(f"MCP Tool Error (inesperado): {e}")
            return json.dumps({"error": "Ocurrió un error inesperado al procesar tu solicitud con la base de datos."})
        finally:
            if conn:
                conn.close()