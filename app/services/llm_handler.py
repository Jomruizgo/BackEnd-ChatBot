# app/services/llm_handler.py
import json
import google.generativeai as genai
from typing import List, Dict, Any, Optional
from app.tools.base_tool import BaseTool

class GeminiLLMHandler:
    def __init__(self, model_name: str, tools: List[BaseTool], system_instruction: str = None):
        self.model_name = model_name
        self.tools = tools
        self.system_instruction = system_instruction
        
        # Crear herramientas en formato Gemini
        self.gemini_tools = self._convert_tools_to_gemini_format()
        
        # Configurar modelo SIN herramientas inicialmente
        self.model = genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system_instruction
        )
        
        print(f"INFO:app.services.llm_handler:Gemini Handler inicializado con modelo: {model_name} y tools: {[tool.name for tool in tools]}")

    def _convert_tools_to_gemini_format(self) -> List[Dict[str, Any]]:
        """Convierte las herramientas BaseTool al formato esperado por Gemini"""
        if not self.tools:
            return []
            
        function_declarations = []
        for tool in self.tools:
            function_declarations.append({
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            })
        
        return [{"function_declarations": function_declarations}]

    async def generate_response(self, chat_history: List[Dict[str, Any]], user_prompt: str) -> Dict[str, Any]:
        """Genera una respuesta usando Gemini con soporte para herramientas"""
        try:
            # Preparar el historial completo
            full_history = chat_history + [{"role": "user", "parts": [{"text": user_prompt}]}]
            
            print(f"[LLM Handler] Enviando a Gemini (historial + prompt): {json.dumps(full_history, indent=2)}")
            
            # **CAMBIO CLAVE: Pasar las herramientas en generate_content**
            response = self.model.generate_content(
                full_history,
                tools=self.gemini_tools if self.gemini_tools else None
            )
            
            # Procesar la respuesta
            result = self._process_gemini_response(response)
            
            print(f"[LLM Handler] Respuesta de Gemini: Texto='{result.get('text', '')}', Tools='{result.get('tool_calls', [])}', FinishReason='{result.get('finish_reason', '')}'")
            
            return result
            
        except Exception as e:
            print(f"ERROR:app.services.llm_handler:Error generando respuesta: {e}")
            import traceback
            traceback.print_exc()
            return {
                "text": f"Error al generar respuesta: {str(e)}",
                "tool_calls": [],
                "finish_reason": "ERROR"
            }

    def _process_gemini_response(self, response) -> Dict[str, Any]:
        """Procesa la respuesta de Gemini y extrae texto y/o llamadas a herramientas"""
        result = {
            "text": None,
            "tool_calls": [],
            "finish_reason": "STOP"
        }
        
        try:
            print(f"[LLM Handler] Debug - Response type: {type(response)}")
            print(f"[LLM Handler] Debug - Response dir: {dir(response)}")
            
            if hasattr(response, 'candidates') and response.candidates:
                candidate = response.candidates[0]
                print(f"[LLM Handler] Debug - Candidate: {candidate}")
                
                # Verificar finish_reason
                if hasattr(candidate, 'finish_reason'):
                    result["finish_reason"] = str(candidate.finish_reason)
                
                # Procesar las partes del contenido
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    print(f"[LLM Handler] Debug - Parts count: {len(candidate.content.parts)}")
                    
                    for i, part in enumerate(candidate.content.parts):
                        print(f"[LLM Handler] Debug - Part {i}: {type(part)}, {dir(part)}")
                        
                        # Verificar si es texto
                        if hasattr(part, 'text') and part.text:
                            result["text"] = part.text
                            print(f"[LLM Handler] Debug - Found text: {part.text}")
                        
                        # Verificar si es una llamada a función
                        elif hasattr(part, 'function_call'):
                            func_call = part.function_call
                            print(f"[LLM Handler] Debug - Found function_call: {func_call}")
                            
                            tool_call = {
                                "name": func_call.name,
                                "args": dict(func_call.args) if func_call.args else {}
                            }
                            result["tool_calls"].append(tool_call)
            
            # Fallback para obtener texto
            if not result["text"] and not result["tool_calls"]:
                if hasattr(response, 'text') and response.text:
                    result["text"] = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    # Intentar extraer texto de otra manera
                    try:
                        result["text"] = response.candidates[0].content.parts[0].text
                    except:
                        pass
                        
        except Exception as e:
            print(f"ERROR:app.services.llm_handler:Error procesando respuesta de Gemini: {e}")
            import traceback
            traceback.print_exc()
            result["text"] = "Error procesando la respuesta del modelo"
        
        return result

    async def execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Ejecuta una herramienta específica"""
        try:
            # Buscar la herramienta por nombre
            tool = None
            for t in self.tools:
                if t.name == tool_name:
                    tool = t
                    break
            
            if not tool:
                error_msg = f"Herramienta '{tool_name}' no encontrada"
                print(f"ERROR:app.services.llm_handler:{error_msg}")
                return json.dumps({"error": error_msg})
            
            # Ejecutar la herramienta
            print(f"[LLM Handler] Ejecutando herramienta '{tool_name}' con args: {tool_args}")
            result = await tool.run(**tool_args)
            
            print(f"[LLM Handler] Resultado de herramienta '{tool_name}': {result}")
            return json.dumps(result)
            
        except Exception as e:
            error_msg = f"Error ejecutando herramienta '{tool_name}': {str(e)}"
            print(f"ERROR:app.services.llm_handler:{error_msg}")
            import traceback
            traceback.print_exc()
            return json.dumps({"error": error_msg})