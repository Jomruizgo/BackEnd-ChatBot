import json
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import crud_conversation
from app.services.llm_handler import GeminiLLMHandler
# NO IMPORTAMOS MCPSQLQueryTool AQUI AHORA
# from app.tools.mcp_sql_query_tool import MCPSQLQueryTool

from app.schemas.chat import ChatMessageResponse

class ChatOrchestrator:
    def __init__(self, db_session: AsyncSession, session_id: str, user_id: Optional[str] = None):
        self.db_session = db_session
        self.session_id = session_id
        self.user_id = user_id

        # --- Desactivar Registro de Tools ---
        self.available_tools = [] # <--- CAMBIO CLAVE: Lista de herramientas vacía
        # ------------------------------------

        self.llm_handler = GeminiLLMHandler(
            model_name="gemini-1.5-flash",
            tools=self.available_tools, # <--- Se pasa la lista vacía
            system_instruction=(
                "Eres un asistente virtual general. Tu objetivo principal es mantener una conversación "
                "amigable y útil. Responde a las preguntas directamente si tienes la información, "
                "o indica que no la tienes. NO tienes acceso a herramientas externas ni a bases de datos. "
                "Sé conciso y claro en tus respuestas."
            )
        )
        self.max_tool_iterations = 0 # <--- CAMBIO CLAVE: No iterar para tools

    async def _load_conversation_history(self) -> List[Dict[str, Any]]:
        """Carga y formatea el historial para el LLM."""
        raw_history = await crud_conversation.get_messages_by_session(
            self.db_session, session_id=self.session_id, limit=20
        )
        
        formatted_history = []
        for msg in raw_history:
            role = "user" if msg.sender == "user" else "model"
            content = msg.message

            try:
                parsed_content = json.loads(content)
                # Si el historial previo guardó tool_calls/responses, necesitamos manejarlos
                # o simplificar el historial para que el modelo no se confunda si no hay tools
                if isinstance(parsed_content, list) and all("function_call" in p or "function_response" in p for p in parsed_content):
                    # Aquí podríamos decidir cómo manejar los mensajes de herramientas en el historial
                    # ya que el modelo ahora no tiene herramientas.
                    # Por ahora, simplemente convertimos la tool_response a texto si es posible,
                    # o ignoramos la tool_call si no es relevante sin una herramienta.
                    # Para la prueba, simplemente lo ignoraremos o lo pasaremos como texto si es posible.
                    # La forma más segura para esta prueba es filtrar completamente los tool_calls/responses
                    # o simplemente pasar solo el texto del mensaje si existía.
                    
                    # Para esta prueba, vamos a pasar solo el texto si lo hay, ignorando las partes de tool
                    # Esto es una simplificación; en un escenario real, deberías decidir cómo el modelo
                    # debe 'ver' su historial previo si la funcionalidad de herramienta cambia.
                    if any("text" in p for p in parsed_content):
                        text_parts = [p["text"] for p in parsed_content if "text" in p]
                        if text_parts:
                            formatted_history.append({"role": role, "parts": [{"text": " ".join(text_parts)}]})
                    # Si solo hay tool_calls/responses, no añadimos nada para evitar que el LLM intente interpretar.
                    # Esto podría "acortar" tu historial si las respuestas previas eran solo de herramientas.
                    
                elif "function_call" in parsed_content or "function_response" in parsed_content:
                    # Ignorar las partes de tool directamente para este flujo de prueba
                    pass
                else:
                    formatted_history.append({"role": role, "parts": [{"text": content}]})
            except (json.JSONDecodeError, TypeError):
                formatted_history.append({"role": role, "parts": [{"text": content}]})
        
        print(f"\n[Orchestrator] Historial cargado y formateado para LLM: {formatted_history}")
        return formatted_history

    async def handle_user_message(self, user_message_text: str) -> ChatMessageResponse:
        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="user", message=user_message_text
        )

        current_chat_history = await self._load_conversation_history()
        
        history_for_llm = current_chat_history[:-1] if current_chat_history else []
        current_prompt = current_chat_history[-1]["parts"][0]["text"] if current_chat_history else user_message_text


        assistant_response_text = None
        tool_used_name = None
        tool_input_args = None

        # Ya no hay bucle de tools, solo una llamada directa
        llm_output = await self.llm_handler.generate_response(
            chat_history=history_for_llm,
            user_prompt=current_prompt
        )

        response_text_from_llm = llm_output.get("text")
        tool_calls_requested = llm_output.get("tool_calls", [])

        # 4.a. Si el LLM pide usar tools (esto NO debería ocurrir ahora)
        if tool_calls_requested:
            # Esto es una condición de error si el LLM intenta usar una tool que no se le dio
            assistant_response_text = "El modelo intentó usar una herramienta, pero no tiene ninguna configurada. Esto es un error inesperado en la configuración."
            print(f"[Orchestrator] ERROR: El LLM solicitó tool(s) sin tools configuradas: {tool_calls_requested}")
            tool_used_name = tool_calls_requested[0]["name"] if tool_calls_requested else None
            tool_input_args = tool_calls_requested[0]["args"] if tool_calls_requested else None
        else:
            assistant_response_text = response_text_from_llm
            if not assistant_response_text:
                # Si el LLM no devuelve texto, pero tampoco pide tools, es un problema
                assistant_response_text = "El modelo no pudo generar una respuesta de texto."

            print(f"[Orchestrator] Respuesta final del LLM: {assistant_response_text}")

        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="assistant", message=assistant_response_text
        )

        return ChatMessageResponse(
            session_id=self.session_id,
            response=assistant_response_text,
            tool_used=tool_used_name,
            tool_input=tool_input_args
        )