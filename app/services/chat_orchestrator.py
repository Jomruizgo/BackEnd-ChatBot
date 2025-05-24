# app/services/chat_orchestrator.py
import json
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime # ¡Asegúrate de importar datetime!

from app.crud import crud_conversation
from app.services.llm_handler import GeminiLLMHandler
from app.schemas.chat import ChatMessageResponse

# NUEVAS IMPORTACIONES
from app.tools.mysql_tool import MySQLTool 
from app.core.config import settings

class ChatOrchestrator:
    def __init__(self, db_session: AsyncSession, session_id: str, user_id: Optional[str] = None):
        self.db_session = db_session
        self.session_id = session_id
        self.user_id = user_id

        # --- CAMBIO AQUI: Instanciar la herramienta de MySQL ---
        self.mysql_tool = MySQLTool(db_url=settings.EXTERNAL_DB_URL)
        self.available_tools = [self.mysql_tool] # Ahora contiene nuestra herramienta de MySQL

        self.llm_handler = GeminiLLMHandler(
            model_name="gemini-2.0-flash-lite",
            tools=self.available_tools,
            system_instruction=(
                "Eres un asistente virtual experto en la base de datos MySQL `nilo_db`. "
                "Tu ÚNICA FUNCIÓN Y HABILIDAD PRINCIPAL es utilizar la herramienta `mysql_tool` "
                "para ejecutar consultas SQL (SOLO SELECT) y obtener información DIRECTAMENTE de `nilo_db`. "
                "Siempre que una pregunta requiera información de la base de datos, DEBES SÍ O SÍ usar la herramienta `mysql_tool`. "
                "Esta herramienta es COMPLETAMENTE FUNCIONAL y tiene ACCESO REAL a la base de datos.\n\n"

                "**Manejo del Esquema de la Base de Datos:**\n"
                "No tienes precargado el esquema completo de todas las tablas de `nilo_db`. "
                "Si necesitas conocer las columnas de una tabla específica para generar una consulta SQL, **debes usar la herramienta `mysql_tool` para ejecutar la consulta `DESCRIBE table_name;` o `SHOW COLUMNS FROM table_name;`**. "
                "Una vez que obtengas la estructura de la tabla, utiliza esa información para construir la consulta SELECT que responde a la pregunta del usuario.\n\n"

                "**Tablas Disponibles en `nilo_db`:**\n"
                "Las siguientes son las **tablas reales** disponibles en la base de datos `nilo_db`. Considera **todas** estas tablas al momento de formular tus consultas, y consulta su estructura si no la conoces:\n"
                " - `accounting_account_balances`\n"
                " - `accounting_accounts`\n"
                " - `accounting_configurations`\n"
                " - `accounting_movements`\n"
                " - `accounting_voucher_items`\n"
                " - `accounting_voucher_types`\n"
                " - `accounting_vouchers`\n"
                " - `api_access_tokens`\n"
                " - `billing_numberings`\n"
                " - `client_consumptions`\n"
                " - `client_subscriptions`\n"
                " - `company`\n"
                " - `company_areas`\n"
                " - `configurations`\n"
                " - `consolidated_retention_certificates`\n"
                " - `contact_accounts`\n"
                " - `contact_items_interests`\n"
                " - `contact_login_codes`\n"
                " - `contact_password_resets`\n"
                " - `contact_register_validation_codes`\n"
                " - `contact_relationships`\n"
                " - `contact_statements`\n"
                " - `contacts`\n"
                " - `contract_salary_history`\n"
                " - `costs_and_expenses`\n"
                " - `costs_and_expenses_categories`\n"
                " - `coupon_groups`\n"
                " - `coupon_redemptions`\n"
                " - `coupons`\n"
                " - `custom_fields`\n"
                " - `dining_tables`\n"
                " - `discounts`\n"
                " - `document_items`\n"
                " - `documents`\n"
                " - `documents_external_register_status`\n"
                " - `ecommerce_configurations`\n"
                " - `ecommerce_contact_us`\n"
                " - `ecommerce_contact_users`\n"
                " - `ecommerce_item_questions`\n"
                " - `ecommerce_items_quantity_by_users`\n"
                " - `ecommerce_legal_info`\n"
                " - `ecommerce_purchase_orders`\n"
                " - `ecommerce_shipping_options`\n"
                " - `ecommerce_shopping_chats`\n"
                " - `ecommerce_user_register_validations`\n"
                " - `electronic_billing_counters`\n"
                " - `electronic_documents_configurations`\n"
                " - `electronic_payroll_data`\n"
                " - `electronic_payroll_submissions`\n"
                " - `electronic_payroll_test_set`\n"
                " - `employee_contracts`\n"
                " - `employee_positions`\n"
                " - `employees`\n"
                " - `epayco_payments`\n"
                " - `fixed_asset_depreciations`\n"
                " - `fixed_assets`\n"
                " - `fixed_assets_groups`\n"
                " - `headquarter_warehouses`\n"
                " - `headquarters`\n"
                " - `integrations`\n"
                " - `inventory_adjustments`\n"
                " - `inventory_groups`\n"
                " - `item_balance`\n"
                " - `item_categories`\n"
                " - `item_depreciations`\n"
                " - `item_kardex`\n"
                " - `item_subcategories`\n"
                " - `item_variations`\n"
                " - `items`\n"
                " - `ledgers`\n"
                " - `mercado_pago_payments`\n"
                " - `migrations`\n"
                " - `notification_configurations`\n"
                " - `oauth_access_tokens`\n"
                " - `oauth_auth_codes`\n"
                " - `oauth_clients`\n"
                " - `oauth_personal_access_clients`\n"
                " - `oauth_refresh_tokens`\n"
                " - `opening_inventory_balances`\n"
                " - `opening_receivable_payable_balances`\n"
                " - `payment_conditions`\n"
                " - `payments`\n"
                " - `paynilo`\n"
                " - `paynilo_payments`\n"
                " - `payroll_configurations`\n"
                " - `payroll_consolidated`\n"
                " - `payroll_deductions`\n"
                " - `payroll_details`\n"
                " - `payroll_incomes`\n"
                " - `payroll_providers`\n"
                " - `payrolls`\n"
                " - `plan_electronic_documents`\n"
                " - `plan_restrictions`\n"
                " - `plan_system_controller`\n"
                " - `price_lists`\n"
                " - `radian_documents`\n"
                " - `radian_events`\n"
                " - `retention_concepts`\n"
                " - `retentions`\n"
                " - `retentions_applied`\n"
                " - `retentions_certificates`\n"
                " - `role_permissions`\n"
                " - `roles`\n"
                " - `severance_payments`\n"
                " - `system_counters`\n"
                " - `system_restrictions`\n"
                " - `taxes`\n"
                " - `template_versions`\n"
                " - `templates`\n"
                " - `term_and_conditions`\n"
                " - `user_data`\n"
                " - `user_headquarters`\n"
                " - `user_roles`\n"
                " - `values_x_item`\n"
                " - `warehouse_transfer_logs`\n"
                " - `warehouses`\n\n"

                "**Después de ejecutar la consulta y obtener los datos, siempre formula una respuesta clara y concisa para el usuario.**\n"
                "Nota que todos los nombres de las tablas están en ingles, y probablemente las los mensajes se te pediran en español, por lo que debes TRADUCIR los nombres de las tablas del español al inglés para hacer las consultas SQL. Por ejemplo, si te preguntan por 'empleados' realmente DEBES usar la tabla 'employees'.\n\n"
                "Si una pregunta no se relaciona con estas tablas o no requiere datos de la DB, responde sin usar la herramienta. PERO PRIORIZA el uso de la herramienta si la pregunta puede ser respondida por la DB."
            )
        )
        self.max_tool_iterations = 5 # Permitir hasta 5 llamadas a herramientas en un turno

    async def _load_conversation_history(self) -> List[Dict[str, Any]]:
        """
        Carga y formatea el historial para el LLM, asegurando un formato alternado
        y manejando adecuadamente tool_calls y tool_responses para la API de Gemini.
        """
        raw_history = await crud_conversation.get_messages_by_session(
            self.db_session, session_id=self.session_id, limit=20, ascending_order=True
        )
        
        formatted_history = []
        
        # El historial de Gemini DEBE empezar con "user" y alternar "model", "tool", "model", "user", etc.
        # Si la DB guarda sender="tool", esto es más fácil. Si no, inferimos el rol "tool" del contenido.

        for msg in raw_history:
            parts_for_llm = []
            
            # Determinar el rol para la API de Gemini
            # Asumimos que msg.sender es 'user' o 'assistant'.
            # Si el contenido de 'assistant' es una tool_call o tool_response, ajustamos el rol de Gemini.
            gemini_role = "user" if msg.sender == "user" else "model" # Rol por defecto para 'assistant'

            # Intentar parsear el contenido si es JSON (tool_calls/responses)
            try:
                parsed_content = json.loads(msg.message)
                
                if isinstance(parsed_content, list): # Contenido de múltiples partes (ej. texto + función, o múltiples respuestas de función)
                    for part in parsed_content:
                        if "text" in part:
                            parts_for_llm.append({"text": part["text"]})
                        elif "function_call" in part:
                            parts_for_llm.append({"function_call": part["function_call"]})
                            gemini_role = "model" # El modelo hizo una llamada a función
                        elif "function_response" in part:
                            parts_for_llm.append({"function_response": part["function_response"]})
                            gemini_role = "tool" # La respuesta es de una herramienta
                elif "function_call" in parsed_content: # Una sola llamada a función
                    parts_for_llm.append({"function_call": parsed_content["function_call"]})
                    gemini_role = "model"
                elif "function_response" in parsed_content: # Una sola respuesta de función
                    parts_for_llm.append({"function_response": parsed_content["function_response"]})
                    gemini_role = "tool"
                else: # Contenido JSON genérico no estructurado como tool part
                    parts_for_llm.append({"text": json.dumps(parsed_content)})
            
            except (json.JSONDecodeError, TypeError): # Contenido es texto plano o JSON inválido
                parts_for_llm = [{"text": msg.message}]
            
            # Asegurar que haya partes si el parseo no generó nada útil pero el mensaje existía
            if not parts_for_llm:
                parts_for_llm = [{"text": msg.message}] # Fallback a texto original

            # Validar y corregir la alternancia para Gemini
            # Esto es crítico. Gemini requiere 'user' -> 'model' -> 'tool' -> 'model' -> 'user'
            # No pueden haber dos roles iguales consecutivos (excepto `tool` si hay varias respuestas, pero Gemini API espera una única parte de `tool` por turno).
            # Si el historial `formatted_history` ya tiene elementos, y el rol actual es el mismo que el último...
            if formatted_history:
                last_entry_role = formatted_history[-1]["role"]
                # Si el último rol fue 'user' y este también es 'user', o 'model' y este es 'model' (texto a texto)
                # O si el último fue 'tool' y este también es 'tool' (si hubieran varias respuestas de tools en el mismo turno)
                if last_entry_role == gemini_role:
                    # Si ambos son 'model' y ambos son texto, podemos fusionarlos.
                    if gemini_role == "model" and parts_for_llm[0].get("text") is not None and formatted_history[-1]["parts"][0].get("text") is not None:
                        formatted_history[-1]["parts"][0]["text"] += "\n" + parts_for_llm[0]["text"]
                        continue # No añadir un nuevo elemento, solo fusionar
                    else:
                        # Si no es un caso de fusión trivial, y rompe la alternancia,
                        # esto es un problema en el historial o en cómo se guarda.
                        # Para evitar el fallo de la API, podríamos omitir el mensaje.
                        # Sin embargo, omitir mensajes puede perder contexto.
                        # La forma más robusta es que el guardado en DB *siempre* mantenga la alternancia.
                        # Para esta integración, si el historial persistido no cumple,
                        # podríamos registrar una advertencia.
                        print(f"ADVERTENCIA: Historial no alternado detectado para rol '{gemini_role}'. Esto podría causar problemas. Mensaje ignorado o fusionado. Contenido: {msg.message}")
                        # Por ahora, simplemente lo añadimos y confiamos en Gemini para manejarlo
                        # o en el hecho de que la API de Gemini lanza un error si la alternancia es incorrecta.
                        # Si el problema persiste, es vital reevaluar el guardado en crud_conversation.
            
            formatted_history.append({"role": gemini_role, "parts": parts_for_llm})
        
        # El historial de Gemini no puede empezar con 'model' o 'tool'.
        # Si el primer mensaje del historial cargado es 'model' o 'tool', lo descartamos.
        while formatted_history and formatted_history[0]["role"] in ["model", "tool"]:
            print(f"ADVERTENCIA: Primer mensaje del historial cargado es de rol '{formatted_history[0]['role']}'. Ignorando.")
            formatted_history.pop(0)

        print(f"\n[Orchestrator] Historial cargado y FORMATEADO para LLM (con tools): {json.dumps(formatted_history, indent=2)}")
        return formatted_history

    async def handle_user_message(self, user_message_text: str) -> ChatMessageResponse:
        # 1. Guardar el mensaje del usuario en la base de datos inmediatamente
        await crud_conversation.create_chat_message(
            db=self.db_session, session_id=self.session_id, sender="user", message=user_message_text
        )

        # 2. Obtener el historial de conversación (incluyendo el mensaje actual del usuario)
        # _load_conversation_history ahora ya no quita el último mensaje, lo formatea directamente.
        full_conversation_history = await self._load_conversation_history()
        
        # El historial para el LLM son todos los mensajes MENOS el último (que es el mensaje actual del usuario)
        # Esto es crucial para que el user_prompt se envíe por separado en generate_content_async
        history_for_llm = full_conversation_history[:-1] if full_conversation_history else []
        
        # El prompt actual es el mensaje del usuario original
        current_prompt = user_message_text

        assistant_response_text = None
        final_tool_used_name = None # Puede ser útil si solo una herramienta se usa y queremos mostrarla
        final_tool_input_args = None # Ídem

        # 3. Entrar en el bucle de ejecución de herramientas
        for i in range(self.max_tool_iterations):
            print(f"[Orchestrator] Iteración de LLM (nº {i+1}). Historial len: {len(history_for_llm)}")
            llm_output = await self.llm_handler.generate_response(
                chat_history=history_for_llm,
                user_prompt=current_prompt # El prompt del usuario es el mismo para cada iteración de tool
            )

            response_text_from_llm = llm_output.get("text")
            tool_calls_requested = llm_output.get("tool_calls", [])
            finish_reason = llm_output.get("finish_reason")

            if tool_calls_requested:
                print(f"[Orchestrator] LLM solicitó tool call(s): {tool_calls_requested}")
                final_tool_used_name = tool_calls_requested[0]["name"] if tool_calls_requested else None
                final_tool_input_args = tool_calls_requested[0]["args"] if tool_calls_requested else None

                # Crear las partes de la llamada a la herramienta para guardar en la DB y para el historial
                tool_call_parts_for_db = []
                tool_call_parts_for_llm_history = []
                for tc in tool_calls_requested:
                    call_part = {"function_call": {"name": tc["name"], "args": tc["args"]}}
                    tool_call_parts_for_db.append(call_part)
                    tool_call_parts_for_llm_history.append(call_part)
                
                # Guardar la llamada a la herramienta del asistente
                await crud_conversation.create_chat_message(
                    db=self.db_session, session_id=self.session_id, sender="assistant", # Guardar como 'assistant'
                    message=json.dumps(tool_call_parts_for_db) # Guardar como JSON serializado
                )
                
                # Añadir la llamada a la herramienta al historial para la siguiente iteración del LLM
                history_for_llm.append({"role": "model", "parts": tool_call_parts_for_llm_history})

                # Ejecutar cada llamada a la herramienta
                tool_responses_for_db = []
                tool_responses_for_llm_history = []
                for tool_call in tool_calls_requested:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    
                    tool_response_content = await self.llm_handler.execute_tool(tool_name, tool_args)
                    print(f"[Orchestrator] Respuesta de la herramienta '{tool_name}': {tool_response_content}")

                    response_part = {"function_response": {"name": tool_name, "response": {"content": json.loads(tool_response_content)}}}
                    tool_responses_for_db.append(response_part)
                    tool_responses_for_llm_history.append(response_part)
                
                # --- CAMBIO AQUI: Ahora podemos usar sender="tool" ---
                await crud_conversation.create_chat_message(
                    db=self.db_session, session_id=self.session_id, sender="tool", # ¡Guardar como "tool"!
                    message=json.dumps(tool_responses_for_db)
                )
                # -----------------------------------------------------
                
                # Añadir las respuestas de las herramientas al historial para la siguiente iteración del LLM
                history_for_llm.append({"role": "tool", "parts": tool_responses_for_llm_history})

                # El bucle continuará, enviando el historial actualizado y el prompt original del usuario.
                # El LLM decidirá si genera texto o llama a otra herramienta.
            
            elif response_text_from_llm:
                # El LLM proporcionó una respuesta de texto, salir del bucle
                print(f"[Orchestrator] LLM proporcionó respuesta de texto final: {response_text_from_llm}")
                assistant_response_text = response_text_from_llm
                break # Salir del bucle, tenemos una respuesta final

            elif finish_reason == "STOP" and not response_text_from_llm and not tool_calls_requested:
                # El modelo se detuvo sin generar texto ni llamadas a herramientas (ej. por filtros de seguridad, o sin contenido)
                print(f"[Orchestrator] LLM se detuvo sin texto ni llamadas a herramientas. Razón: {finish_reason}")
                assistant_response_text = "El modelo no pudo generar una respuesta de texto."
                break
            else:
                # No hay texto, no hay llamadas a herramientas, y no es un "STOP" claro. Esto es inesperado.
                print(f"[Orchestrator] Respuesta del LLM vacía o inesperada. Output: {llm_output}")
                assistant_response_text = "El modelo no pudo generar una respuesta de texto inesperada."
                break
        else: # El bucle terminó sin un 'break' (se alcanzó max_tool_iterations)
            print(f"[Orchestrator] Se alcanzó el máximo de iteraciones de herramientas sin una respuesta de texto final.")
            assistant_response_text = "El asistente alcanzó el límite de llamadas a herramientas y no pudo generar una respuesta final."

        # 4. Guardar la respuesta final del asistente
        if assistant_response_text: # Asegurarse de no guardar vacío si ya se manejó arriba
             await crud_conversation.create_chat_message(
                db=self.db_session, session_id=self.session_id, sender="assistant", message=assistant_response_text
            )

        # 5. Devolver la respuesta formateada al frontend
        return ChatMessageResponse(
            session_id=self.session_id,
            response=assistant_response_text,
            sender="assistant",
            timestamp=datetime.now(),
            tool_used=final_tool_used_name,
            tool_input=final_tool_input_args
        )