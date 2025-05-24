# app/services/chat_orchestrator.py
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
#from google.generativeai.types import Part, Tool # Asegúrate de que Tool también sea accesible si la usas

from app.crud import crud_conversation
from app.services.llm_handler_past import GeminiLLMHandler
from app.tools.mcp_sql_query_tool import MCPSQLQueryTool # Importa tu tool
# from app.tools.example_api_tool import ExampleAPITool # Importa otras tools
from app.schemas.chat import ChatMessageResponse # Para la respuesta final

class ChatOrchestrator:
    def __init__(self, db_session: AsyncSession, session_id: str, user_id: Optional[str] = None):
        self.db_session = db_session
        self.session_id = session_id
        self.user_id = user_id

        # --- Registro de Tools ---
        self.mcp_tool = MCPSQLQueryTool()
        # self.api_tool = ExampleAPITool()
        self.available_tools = [self.mcp_tool] #, self.api_tool]
        # -------------------------

        self.llm_handler = GeminiLLMHandler(
            tools=self.available_tools,
            system_instruction=(
                "Eres un asistente virtual de la empresa. Tu objetivo principal es proporcionar "
                "información precisa y actualizada sobre productos y empleados. "
                "PARA CUALQUIER PREGUNTA QUE REQUIERA DATOS ESPECÍFICOS DE LA EMPRESA, "
                "COMO CANTIDAD DE PRODUCTOS POR CATEGORÍA, LISTADOS DE EMPLEADOS O DATOS DE USUARIOS, "
                "DEBES UTILIZAR EXCLUSIVAMENTE LA HERRAMENTA `query_external_company_database`. "
                "NO intentes responder directamente si la información no está en tu conocimiento general. "
                "Siempre formula las preguntas a la herramienta en lenguaje natural, claro y conciso."
            )
        )
        self.max_tool_iterations = 3 # Para evitar bucles infinitos de llamadas a tools

    async def _load_conversation_history(self) -> List[Dict[str, Any]]:
        """Carga y formatea el historial para el LLM."""
        raw_history = await crud_conversation.get_messages_by_session(
            self.db_session, session_id=self.session_id, limit=20 # Limita el historial
        )
        
        formatted_history = []
        for msg in raw_history:
            # El historial para Gemini debe ser una lista de {"role": ..., "parts": ...}
            # Si guardaste tool_calls/responses, necesitas reconstruirlos aquí.
            # Por simplicidad, asumimos que `msg.message` contiene texto o JSON de tool_parts.
            
            role = "user" if msg.sender == "user" else "model"
            content = msg.message

            try:
                parsed_content = json.loads(content)
                if isinstance(parsed_content, list) and all("function_call" in p or "function_response" in p for p in parsed_content):
                    formatted_history.append({"role": role, "parts": parsed_content})
                elif "function_call" in parsed_content:
                    formatted_history.append({"role": role, "parts": [parsed_content]})
                elif "function_response" in parsed_content:
                    formatted_history.append({"role": "user", "parts": [parsed_content]})
                else:
                    formatted_history.append({"role": role, "parts": [{"text": content}]})
            except (json.JSONDecodeError, TypeError):
                formatted_history.append({"role": role, "parts": [{"text": content}]})
        
        print(f"\n[Orchestrator] Historial cargado y formateado para LLM: {formatted_history}")
        return formatted_history

    async def handle_user_message(self, user_message_text: str) -> ChatMessageResponse:
        # 1. Guardar mensaje del usuario
        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="user", message=user_message_text
        )

        # 2. Cargar historial de conversación
        current_chat_history = await self._load_conversation_history()
        
        # El historial ya incluye el último mensaje del usuario porque _load_conversation_history
        # lo obtiene de la BD después de haberlo guardado.
        # Por tanto, no pasamos `user_message_text` directamente a `generate_response`
        # si el historial ya lo contiene. Si no, sí.
        # Para `generate_response` de `llm_handler`, el prompt es el último mensaje.
        # El historial son los mensajes *antes* del prompt actual.
        
        # Separar el prompt actual del historial previo
        history_for_llm = current_chat_history[:-1] if current_chat_history else []
        current_prompt = current_chat_history[-1]["parts"][0]["text"] if current_chat_history else user_message_text


        assistant_response_text = None
        tool_used_name = None
        tool_input_args = None

        for _ in range(self.max_tool_iterations):
            # 3. Obtener respuesta del LLM
            llm_output = await self.llm_handler.generate_response(
                chat_history=history_for_llm, # Enviar historial *sin* el prompt actual
                user_prompt=current_prompt     # Enviar prompt actual separado
            )

            response_text_from_llm = llm_output.get("text")
            tool_calls_requested = llm_output.get("tool_calls", [])

            # 4.a. Si el LLM pide usar tools
            if tool_calls_requested:
                print(f"[Orchestrator] LLM solicitó tool(s): {tool_calls_requested}")
                
                # Guardar la petición de tool del LLM en el historial
                # Gemini espera que la parte de la tool_call esté en 'parts' del mensaje del 'model'
                # La SDK de Gemini construye esto internamente si la respuesta del modelo tiene `function_calls`
                # Si construyes el historial manualmente, necesitas un `Part(function_call=...)`
                # Por ahora, asumimos que llm_output ya tiene la estructura correcta o la guardamos como texto.
                # El `content` del modelo que pide la tool podría tener texto Y `function_calls`.
                model_parts_for_history = []
                if response_text_from_llm:
                    model_parts_for_history.append({"text": response_text_from_llm})

                for tc_req in tool_calls_requested:
                    model_parts_for_history.append({
                        "function_call": {
                            "name": tc_req["name"],
                            "args": tc_req["args"]
                        }
                    })

                await crud_conversation.create_chat_message(
                    db=self.db_session, session_id=self.session_id, sender="model", message=json.dumps(model_parts_for_history)
                )
                history_for_llm.append({"role": "model", "parts": model_parts_for_history})

                
                tool_response_parts_for_gemini = []

                for tc in tool_calls_requested:
                    tool_name = tc["name"]
                    tool_args = tc["args"]
                    tool_used_name = tool_name
                    tool_input_args = tool_args

                    tool_result_str = await self.llm_handler.execute_tool(tool_name, tool_args)

                    tool_response_parts_for_gemini.append({
                        "function_response": {
                            "name": tool_name,
                            "response": {
                                "content": tool_result_str
                            }
                        }
                    })

                serializable_tool_responses = tool_response_parts_for_gemini
                await crud_conversation.create_chat_message(
                    db=self.db_session, session_id=self.session_id, sender="user", message=json.dumps(serializable_tool_responses)
                )
                history_for_llm.append({"role": "user", "parts": tool_response_parts_for_gemini})

            # 4.b. Si el LLM da una respuesta directa (sin tools o después de tools)
            else:
                assistant_response_text = response_text_from_llm
                if not assistant_response_text and llm_output.get("finish_reason") != "STOP":
                    assistant_response_text = "No pude generar una respuesta o la herramienta no devolvió información útil."
                elif not assistant_response_text: # Si es STOP pero no hay texto (raro pero posible)
                    assistant_response_text = "Proceso completado."

                print(f"[Orchestrator] Respuesta final del LLM (o error): {assistant_response_text}")
                break # Salir del bucle de tools

        # 5. Si se agotaron las iteraciones de tools sin respuesta final
        if not assistant_response_text:
            assistant_response_text = "Parece que estoy teniendo problemas para usar mis herramientas correctamente. ¿Podrías reformular tu pregunta?"
            print("[Orchestrator] Se alcanzó el máximo de iteraciones de tools.")

        # 6. Guardar respuesta final del asistente
        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="assistant", message=assistant_response_text
        )

        return ChatMessageResponse(
            session_id=self.session_id,
            response=assistant_response_text,
            tool_used=tool_used_name,
            tool_input=tool_input_args
        )