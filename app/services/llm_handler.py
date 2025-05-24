import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig
from app.core.config import settings # Importa la instancia de settings
from typing import List, Dict, Any, Optional
from app.tools.base_tool import BaseTool
import logging
import asyncio
import json
from collections.abc import Iterable

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configuración global de Gemini (asegúrate de que esto se ejecute solo una vez,
# por ejemplo, al inicio de la aplicación o en un módulo de inicialización)
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    if not settings.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY no está configurada. Las llamadas a la API de Gemini podrían fallar.")
except Exception as e:
    logger.error(f"Error configurando Gemini API: {e}")

DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

class GeminiLLMHandler:
    # El nombre del modelo ahora se toma por defecto de settings.GEMINI_LLM_MODEL
    def __init__(self, model_name: str = settings.GEMINI_LLM_MODEL, tools: Optional[List[BaseTool]] = None, system_instruction: Optional[str] = None):
        self.model_name = model_name
        self.declared_tools = [tool.get_gemini_tool_declaration() for tool in tools] if tools else None
        self.tool_registry = {tool.name: tool for tool in tools} if tools else {}

        generation_config = GenerationConfig()

        self.model = genai.GenerativeModel(
            model_name=self.model_name, # ¡Aquí se usa la variable de la configuración!
            safety_settings=DEFAULT_SAFETY_SETTINGS,
            tools=self.declared_tools,
            system_instruction=system_instruction,
            generation_config=generation_config
        )
        logger.info(f"Gemini Handler inicializado con modelo: {self.model_name} y tools: {[t.name for t in tools] if tools else 'Ninguna'}")

    async def generate_response(self, chat_history: List[Dict[str, Any]], user_prompt: str) -> Dict[str, Any]:
        current_conversation_history = []

        for entry in chat_history:
            entry_parts = entry.get("parts")
            if isinstance(entry_parts, str):
                parts = [{"text": entry_parts}]
            # Asegura que entry_parts sea una lista de diccionarios con "text"
            elif isinstance(entry_parts, Iterable) and all(isinstance(p, dict) and "text" in p for p in entry_parts):
                parts = entry_parts
            else:
                # Si no es string ni lista de dicts con text, se convierte a string y se pone en un dict
                parts = [{"text": str(entry_parts)}]

            current_conversation_history.append({
                "role": entry["role"],
                "parts": parts
            })

        current_conversation_history.append({
            "role": "user",
            "parts": [{"text": user_prompt}]
        })

        logger.debug(f"[LLM Handler] Últimos mensajes: {current_conversation_history[-2:]}")

        try:
            response = await asyncio.wait_for(
                self.model.generate_content_async(contents=current_conversation_history),
                timeout=15
            )

            candidate = response.candidates[0]

            text_parts = []
            if candidate.content and isinstance(candidate.content.parts, list):
                for part in candidate.content.parts:
                    # Accede a .text si el objeto part lo tiene
                    if hasattr(part, 'text') and isinstance(part.text, str):
                        text_parts.append(part.text)
                    # Si el part es un diccionario (menos común directamente desde Gemini, pero por robustez)
                    elif isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])

            llm_response = {
                "text": "".join(text_parts) if text_parts else None,
                "tool_calls": [],
                "finish_reason": str(candidate.finish_reason) if candidate.finish_reason else "UNKNOWN"
            }

            # Acceder a function_calls de forma segura
            if hasattr(candidate, 'function_calls') and candidate.function_calls:
                for fc in candidate.function_calls:
                    llm_response["tool_calls"].append({
                        "name": fc.name,
                        "args": dict(fc.args) # Convertir a dict para asegurar serialización
                    })

            logger.info(
                f"[LLM Handler] Respuesta: texto='{llm_response['text']}', "
                f"tools={llm_response['tool_calls']}, "
                f"finalización='{llm_response['finish_reason']}'"
            )

            return llm_response

        except asyncio.TimeoutError:
            logger.error("[LLM Handler] Tiempo de espera agotado en llamada a Gemini.")
            return {
                "text": "La solicitud tomó demasiado tiempo.",
                "tool_calls": [],
                "finish_reason": "TIMEOUT"
            }

        except Exception as e:
            logger.error(f"[LLM Handler] Error al llamar a Gemini: {e}")
            error_message = "Lo siento, no pude procesar tu solicitud en este momento."
            
            # Manejo de errores específicos de Gemini
            # Captura información de bloqueo si está disponible
            if hasattr(e, 'response') and hasattr(e.response, 'prompt_feedback') and getattr(e.response.prompt_feedback, 'block_reason', None):
                 error_message = (
                    f"Tu solicitud fue bloqueada por el modelo. Razón: "
                    f"{getattr(e.response.prompt_feedback, 'block_reason_message', None) or e.response.prompt_feedback.block_reason}"
                )
            # Captura el mensaje de error de la API si está disponible
            elif hasattr(e, 'message') and isinstance(e.message, str):
                error_message = f"Error del servicio de IA: {e.message}"
            # Captura detalles adicionales del error si están disponibles
            elif hasattr(e, 'details') and isinstance(e.details, str):
                error_message = f"Error del servicio de IA: {e.details}"
            # Mensaje genérico para otros errores no capturados
            else:
                error_message = f"Ocurrió un error inesperado al procesar tu solicitud: {str(e)}"

            return {
                "text": error_message,
                "tool_calls": [],
                "finish_reason": "ERROR"
            }


    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        if tool_name in self.tool_registry:
            tool_instance = self.tool_registry[tool_name]
            logger.info(f"[LLM Handler] Ejecutando tool: {tool_name} con args: {tool_args}")
            try:
                result = await tool_instance.execute(**tool_args)
                return result
            except Exception as e:
                logger.error(f"[LLM Handler] Error ejecutando la tool {tool_name}: {e}")
                return json.dumps({"error": f"Error interno al ejecutar la tool '{tool_name}': {str(e)}"})
        else:
            logger.warning(f"[LLM Handler] Tool '{tool_name}' no encontrada en el registro.")
            return json.dumps({"error": f"Tool '{tool_name}' no reconocida."})