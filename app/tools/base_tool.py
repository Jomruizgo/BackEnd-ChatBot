# app/tools/base_tool.py
from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Type, Any, Optional, Dict
import google.generativeai as genai
import google.generativeai.types as genai_types

class ToolInputSchema(BaseModel):
    """Schema base para los argumentos de una tool. Cada tool puede definir el suyo."""
    pass

class BaseTool(ABC):
    name: str
    description: str
    args_schema: Optional[Type[BaseModel]] = None # Pydantic model para los argumentos

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Ejecuta la lógica de la tool con los argumentos proporcionados."""
        pass

    def _clean_pydantic_schema(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Limpia un esquema JSON generado por Pydantic para que sea compatible con Gemini.
        Elimina 'title' y cualquier otro campo que Gemini no espere.
        Realiza una limpieza recursiva.
        """
        cleaned_schema = {}
        for key, value in schema.items():
            if key == "title":
                continue # Omitir el campo 'title'
            elif isinstance(value, dict):
                # Si el valor es un diccionario, límpialo recursivamente
                cleaned_schema[key] = self._clean_pydantic_schema(value)
            elif isinstance(value, list):
                # Si el valor es una lista, intentar limpiar elementos si son diccionarios
                cleaned_list = []
                for item in value:
                    if isinstance(item, dict):
                        cleaned_list.append(self._clean_pydantic_schema(item))
                    else:
                        cleaned_list.append(item)
                cleaned_schema[key] = cleaned_list
            else:
                cleaned_schema[key] = value
        return cleaned_schema

    def get_gemini_tool_declaration(self) -> genai_types.Tool:
        """Retorna la declaración de la tool en el formato que espera Gemini."""
        parameters_schema = {}

        if self.args_schema:
            try: # Pydantic v2
                # Obtener el esquema JSON de Pydantic
                schema_dict = self.args_schema.model_json_schema()
            except AttributeError: # Pydantic v1
                schema_dict = self.args_schema.schema()

            # --- APLICAR LA LIMPIEZA RECURSIVA ---
            cleaned_schema_dict = self._clean_pydantic_schema(schema_dict)
            # -----------------------------------
            
            # Ahora, construimos el diccionario de parámetros para Gemini
            # Asegúrate de que el tipo principal sea 'object' y que tenga 'properties' y 'required'
            # del esquema limpiado.
            
            parameters_schema = {
                "type": "object",
                "properties": cleaned_schema_dict.get("properties", {}),
                "required": cleaned_schema_dict.get("required", []),
            }
            # Podemos ignorar `$defs` si Pydantic lo genera, ya que no son parte directa
            # de la declaración de parámetros para Gemini a este nivel.

        return genai_types.Tool(
            function_declarations=[
                genai_types.FunctionDeclaration(
                    name=self.name,
                    description=self.description,
                    parameters=parameters_schema # Pasa el esquema construido y limpio
                )
            ]
        )
        # La parte 'else' sigue siendo la misma si no hay args_schema