import json
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

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
        """Carga y formatea el historial para el LLM, asegurando un formato alternado."""
        raw_history = await crud_conversation.get_messages_by_session(
            self.db_session, session_id=self.session_id, limit=20, ascending_order=True # Asegura orden ascendente
        )
        
        formatted_history = []
        last_role = None # Para verificar el rol del mensaje anterior

        for msg in raw_history:
            role = "user" if msg.sender == "user" else "model"
            content = msg.message

            # Intentar parsear el contenido si es JSON (tool_calls/responses)
            try:
                parsed_content = json.loads(content)
                
                # Si el contenido es una lista de partes (incluyendo tool_calls/responses)
                if isinstance(parsed_content, list):
                    # Extraer solo las partes de texto para el historial del LLM sin tools
                    text_parts = [p.get("text") for p in parsed_content if "text" in p]
                    if text_parts:
                        content_for_llm = " ".join(text_parts)
                    else:
                        # Si no hay partes de texto, y son solo tool_calls/responses,
                        # podemos decidir ignorarlas o representarlas como un string genérico.
                        # Dado que no hay herramientas, lo mejor es ignorarlas o simplificarlas.
                        # Para la alternancia, si un mensaje de "model" consistía solo en una tool_call,
                        # y no tiene una respuesta textual, podrías optar por no incluirlo para no romper la alternancia.
                        # Sin embargo, si la tool_response tenía texto, sí lo incluirías.
                        # Para simplificar y mantener la alternancia, vamos a poner un placeholder si no hay texto.
                        if role == "model" and any("function_response" in p for p in parsed_content):
                             content_for_llm = "[Respuesta de herramienta sin texto visible]"
                        elif role == "model" and any("function_call" in p for p in parsed_content):
                             # Si el modelo solo hizo una llamada a herramienta y no generó texto,
                             # podemos omitir este turno del modelo para no romper la alternancia.
                             # O poner un placeholder. Omitirlo es más arriesgado si pierdes contexto.
                             content_for_llm = "[El modelo intentó usar una herramienta]"
                        else:
                            continue # Si es un mensaje de herramienta del usuario sin texto, ignóralo para el LLM
                
                # Si el contenido es un dict que representa una sola function_call o function_response
                elif "function_call" in parsed_content:
                    content_for_llm = f"[El modelo utilizó la herramienta: {parsed_content['function_call']['name']}]"
                elif "function_response" in parsed_content:
                    content_for_llm = f"[Respuesta de la herramienta: {parsed_content['function_response'].get('response', {}).get('content', '...')}]"
                else:
                    content_for_llm = content # Es un JSON pero no una estructura de herramienta conocida
            
            except (json.JSONDecodeError, TypeError):
                content_for_llm = content # Es texto plano o JSON inválido, usar como está

            # --- AQUI ESTÁ LA LÓGICA CLAVE PARA ASEGURAR LA ALTERNANCIA ---
            # Si el rol actual es el mismo que el anterior, y el historial no está vacío,
            # intenta fusionar o corregir (esto es un parche, lo ideal es que nunca ocurra)
            if formatted_history and last_role == role:
                # Esto es una situación anómala en tu historial persistido.
                # Una solución simple es concatenar el texto si el rol es el mismo.
                # Otra es simplemente omitir el mensaje para no romper el formato.
                # Optaremos por omitirlo para garantizar el formato del LLM si no es posible una fusión lógica.
                # Sin embargo, lo más robusto es investigar por qué se guardan mensajes consecutivos del mismo rol.
                print(f"ADVERTENCIA: Mensaje consecutivo del mismo rol '{role}'. Ignorando: {content_for_llm}")
                continue
            
            # Si el historial está vacío y el primer mensaje no es del usuario, ignóralo
            if not formatted_history and role == "model":
                print(f"ADVERTENCIA: Primer mensaje del historial es del modelo. Ignorando: {content_for_llm}")
                continue
            
            formatted_history.append({"role": role, "parts": [{"text": content_for_llm}]})
            last_role = role
        # ------------------------------------------------------------------

        # ¡Asegurar que el historial no termine con un mensaje de usuario si el último fue del usuario y no hay respuesta!
        # Si el último mensaje es del usuario y no hubo una respuesta de modelo, la API de Gemini espera una.
        # Esto es handled por el generate_response al añadir el prompt del user.
        # Pero si hay 2 users seguidos en el historial que ya viene de DB, el LLM va a fallar.
        # La lógica de "if last_role == role" arriba debería mitigar esto.
        
        print(f"\n[Orchestrator] Historial cargado y FORMATEADO Y FILTRADO para LLM: {formatted_history}")
        return formatted_history

    async def handle_user_message(self, user_message_text: str) -> ChatMessageResponse:
        # 1. Guardar el mensaje del usuario en la base de datos inmediatamente
        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="user", message=user_message_text
        )

        # 2. Cargar el historial de conversación (excluyendo el mensaje que acabamos de guardar, ya que será el 'user_prompt' directo)
        # El historial retornado por _load_conversation_history ya debería estar formateado para el LLM.
        # Además, como el mensaje del usuario ya fue guardado y lo necesitamos como 'prompt' actual,
        # NO debe formar parte del 'chat_history' que se le pasa al LLM.
        # _load_conversation_history debería cargar hasta el mensaje ANTERIOR al actual si lo quieres usar solo como historial.
        # Alternativamente, puedes cargar todo y luego quitar el último.
        
        # Opción 1: Cargar todos los mensajes Y LUEGO quitar el último (que es el current user message)
        # Este es el comportamiento actual de tu _load_conversation_history y de cómo lo estás usando.
        # Si _load_conversation_history ya carga el mensaje actual del usuario, entonces lo siguiente está bien:
        full_conversation_history = await self._load_conversation_history() # Incluye el mensaje actual del usuario
        
        # El historial para el LLM deben ser todos los mensajes EXCEPTO el último (que es el user_message_text)
        history_for_llm = full_conversation_history[:-1] # Excluye el último mensaje del usuario

        # El prompt actual es simplemente el user_message_text original
        current_prompt = user_message_text # <--- ¡ESTO ES EL CAMBIO CLAVE!

        assistant_response_text = None
        tool_used_name = None
        tool_input_args = None

        # 3. Enviar el historial y el prompt actual al LLM
        llm_output = await self.llm_handler.generate_response(
            chat_history=history_for_llm,
            user_prompt=current_prompt # <--- Usar el user_message_text directo
        )

        response_text_from_llm = llm_output.get("text")
        tool_calls_requested = llm_output.get("tool_calls", [])

        # 4. Procesar la respuesta del LLM
        if tool_calls_requested:
            assistant_response_text = "El modelo intentó usar una herramienta, pero no tiene ninguna configurada. Esto es un error inesperado en la configuración."
            print(f"[Orchestrator] ERROR: El LLM solicitó tool(s) sin tools configuradas: {tool_calls_requested}")
            tool_used_name = tool_calls_requested[0]["name"] if tool_calls_requested else None
            tool_input_args = tool_calls_requested[0]["args"] if tool_calls_requested else None
        else:
            assistant_response_text = response_text_from_llm
            if not assistant_response_text:
                assistant_response_text = "El modelo no pudo generar una respuesta de texto."

            print(f"[Orchestrator] Respuesta final del LLM: {assistant_response_text}")

        # 5. Guardar la respuesta del asistente en la base de datos
        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="assistant", message=assistant_response_text
        )

        # 6. Devolver la respuesta formateada al frontend
        return ChatMessageResponse(
            session_id=self.session_id,
            response=assistant_response_text,
            sender="assistant", # Asegúrate de que el sender sea "assistant" aquí para la respuesta final.
            timestamp=datetime.now(), # Asegúrate de importar datetime
            tool_used=tool_used_name,
            tool_input=tool_input_args
        )