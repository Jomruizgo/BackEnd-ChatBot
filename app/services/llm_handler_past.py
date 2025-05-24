# app/services/llm_handler.py
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold, GenerationConfig
from app.core.config import settings
from typing import List, Dict, Any, Optional
from app.tools.base_tool import BaseTool
import logging
import asyncio
import json
from collections.abc import Iterable

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Configuración global de Gemini
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
except Exception as e:
    logger.error(f"Error configurando Gemini API: {e}")

DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

class GeminiLLMHandler:
    def __init__(self, model_name: str = "gemini-1.5-flash", tools: Optional[List[BaseTool]] = None, system_instruction: Optional[str] = None):
        self.model_name = model_name
        self.declared_tools = [tool.get_gemini_tool_declaration() for tool in tools] if tools else None
        self.tool_registry = {tool.name: tool for tool in tools} if tools else {}

        generation_config = GenerationConfig()

        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            safety_settings=DEFAULT_SAFETY_SETTINGS,
            tools=self.declared_tools,
            system_instruction=system_instruction,
            generation_config=generation_config
        )
        logger.info(f"Gemini Handler inicializado con modelo: {model_name} y tools: {[t.name for t in tools] if tools else 'Ninguna'}")

    async def generate_response(self, chat_history: List[Dict[str, Any]], user_prompt: str) -> Dict[str, Any]:
        current_conversation_history = []

        for entry in chat_history:
            entry_parts = entry.get("parts")
            if isinstance(entry_parts, str):
                parts = [{"text": entry_parts}]
            elif isinstance(entry_parts, Iterable) and all(isinstance(p, dict) and "text" in p for p in entry_parts):
                parts = entry_parts
            else:
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
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])

            llm_response = {
                "text": "".join(text_parts) if text_parts else None,
                "tool_calls": [],
                "finish_reason": str(candidate.finish_reason) if candidate.finish_reason else "UNKNOWN"
            }

            if candidate.function_calls:
                for fc in candidate.function_calls:
                    llm_response["tool_calls"].append({
                        "name": fc.name,
                        "args": dict(fc.args)
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
            if hasattr(response, 'prompt_feedback') and getattr(response.prompt_feedback, 'block_reason', None):
                error_message = (
                    f"Tu solicitud fue bloqueada. Razón: "
                    f"{getattr(response.prompt_feedback, 'block_reason_message', None) or response.prompt_feedback.block_reason}"
                )
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
