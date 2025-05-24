import google.generativeai as genai
from typing import List, Dict, Any, Optional
from app.tools.base_tool import BaseTool # Asegúrate de que esta importación sea correcta
import json

class GeminiLLMHandler:
    def __init__(self, model_name: str = "gemini-1.5-flash", tools: Optional[List[BaseTool]] = None, system_instruction: Optional[str] = None):
        self.model_name = model_name
        self.tools = tools if tools is not None else [] # Asegurarse de que sea una lista vacía si no se pasa nada
        self.system_instruction = system_instruction
        
        # Mapeo de nombres de herramientas a instancias
        self.tool_map = {tool.name: tool for tool in self.tools}

        # Configurar el modelo con o sin herramientas
        if self.tools: # Si hay herramientas, las pasamos
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                tools=[tool.to_tool_metadata() for tool in self.tools],
                system_instruction=self.system_instruction
            )
        else: # Si no hay herramientas, no pasamos el argumento tools
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=self.system_instruction
            )

        print(f"INFO:app.services.llm_handler:Gemini Handler inicializado con modelo: {self.model_name} y tools: {[t.name for t in self.tools]}")

    async def generate_response(self, chat_history: List[Dict[str, Any]], user_prompt: str) -> Dict[str, Any]:
        full_conversation = chat_history + [{"role": "user", "parts": [{"text": user_prompt}]}]
        
        print(f"[LLM Handler] Enviando a Gemini (historial + prompt): {full_conversation}")
        
        response_text = None
        tool_calls = []
        finish_reason = None

        try:
            # Aquí es donde ocurre la llamada real al modelo de Gemini
            response = await self.model.generate_content_async(
                contents=full_conversation,
                # No se requiere `tools` aquí si ya se pasó en el constructor del modelo
                # Los `tool_config` pueden ser relevantes si necesitas un control más fino,
                # pero para deshabilitar las tools, no pasarlas en el constructor es suficiente.
            )
            
            # --- Manejo de la respuesta del modelo ---
            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content:
                    for part in candidate.content.parts:
                        if part.text:
                            response_text = part.text
                        if part.function_call:
                            # Aunque no esperamos tool_calls, las capturamos si aparecen.
                            tool_calls.append({
                                "name": part.function_call.name,
                                "args": part.function_call.args
                            })
                if candidate.finish_reason:
                    finish_reason = candidate.finish_reason.name # Convertir a string
            
            print(f"[LLM Handler] Respuesta de Gemini: Texto='{response_text}', Tools='{tool_calls}', FinishReason='{finish_reason}'")

            return {
                "text": response_text,
                "tool_calls": tool_calls,
                "finish_reason": finish_reason
            }

        except Exception as e:
            print(f"ERROR:app.services.llm_handler:[LLM Handler] Error al llamar a Gemini: {e}")
            # Considerar la respuesta de error de `response.prompt_feedback` si está disponible
            error_message = "Lo siento, no pude procesar tu solicitud en este momento."
            # Si el error es de la API, podemos intentar obtener más detalles
            if hasattr(e, 'message'): # Para errores de google.api_core.exceptions
                error_message += f" Detalle: {e.message}"
            return {
                "text": error_message,
                "tool_calls": [],
                "finish_reason": "ERROR"
            }

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        # Este método no debería ser llamado si no hay tools configuradas,
        # pero lo mantenemos para evitar errores si el flujo lo alcanza inesperadamente.
        print(f"[LLM Handler] Ejecutando tool: {tool_name} con args: {tool_args}")
        tool = self.tool_map.get(tool_name)
        if tool:
            try:
                result = await tool.run(**tool_args)
                return json.dumps(result)
            except Exception as e:
                return json.dumps({"error": f"Error al ejecutar la herramienta {tool_name}: {e}"})
        else:
            return json.dumps({"error": f"Herramienta '{tool_name}' no encontrada."})