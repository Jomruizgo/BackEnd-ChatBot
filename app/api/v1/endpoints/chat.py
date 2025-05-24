import uuid
import json
from typing import List, Optional # Importa List y Optional
from fastapi import APIRouter, Depends, HTTPException, Body, status # Importa status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_conv_db
from app.schemas.chat import ChatMessageCreate, ChatMessageResponse, SessionCreate, SessionResponse
from app.services.chat_orchestrator import ChatOrchestrator
from app.crud import crud_conversation # Para crear/obtener/eliminar sesiones y mensajes

router = APIRouter()

# Endpoint para crear una nueva sesión de chat
@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_new_chat_session(
    session_data: SessionCreate = Body(None), # Permite user_id opcional o metadata
    db: AsyncSession = Depends(get_conv_db)
):
    session_id = str(uuid.uuid4())
    user_id = session_data.user_id if session_data else None
    metadata = session_data.metadata if session_data else None
    
    try:
        session = await crud_conversation.create_chat_session(
            db=db, session_id=session_id, user_id=user_id, metadata=metadata
        )
        return SessionResponse(
            session_id=session.id,
            user_id=session.user_id,
            created_at=session.created_at,
            metadata=json.loads(session.metadata) if session.metadata else None
        )
    except Exception as e:
        print(f"Error creando sesión: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="No se pudo crear la sesión de chat.")


# Endpoint principal para enviar mensajes a una sesión existente
@router.post("/sessions/{session_id}/messages", response_model=ChatMessageResponse)
async def post_chat_message(
    session_id: str,
    message_in: ChatMessageCreate,
    db: AsyncSession = Depends(get_conv_db)
):
    # Verificar si la sesión existe
    session = await crud_conversation.get_chat_session(db, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión de chat no encontrada.")

    orchestrator = ChatOrchestrator(db_session=db, session_id=session_id, user_id=message_in.user_id or session.user_id)
    
    try:
        response = await orchestrator.handle_user_message(message_in.message)
        return response
    except Exception as e:
        print(f"Error en el endpoint de chat: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Ocurrió un error interno en el servidor: {str(e)}")


# --- app/api/v1/endpoints/chat.py (Fragmento de código) ---

# ... Tus importaciones existentes (uuid, json, List, Optional, APIRouter, Depends, HTTPException, Body, status)
# ... y tus routers (router = APIRouter())
# ... y tus endpoints existentes (create_new_chat_session, post_chat_message)

# --- Endpoint para eliminar una Conversación Completa ---
@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(session_id: str, db: AsyncSession = Depends(get_conv_db)):
    """
    Elimina una conversación completa y todos sus mensajes asociados.
    Retorna 204 No Content si la eliminación fue exitosa.
    """
    # Llama a la función CRUD para eliminar la sesión y sus mensajes.
    # Esta función debe estar definida en app/crud/crud_conversation.py
    success = await crud_conversation.delete_session(db, session_id=session_id)
    
    if not success:
        # Si delete_session retorna False, significa que la sesión no existía o no se pudo eliminar.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversación con ID '{session_id}' no encontrada o no se pudo eliminar."
        )
    # Si todo fue bien, FastAPI automáticamente enviará un 204 No Content.
    return 

# --- Fin del fragmento de código ---


@router.get("/sessions", response_model=List[SessionResponse]) # Cambiado a SessionResponse para más detalle
async def list_user_sessions(user_id: Optional[str] = None, db: AsyncSession = Depends(get_conv_db)):
    """
    Lista todas las sesiones de conversación, opcionalmente filtradas por user_id.
    """
    sessions = await crud_conversation.get_all_sessions(db, user_id=user_id)
    return [
        SessionResponse(
            session_id=s.id,
            user_id=s.user_id,
            created_at=s.created_at,
            # --- ¡CAMBIO AQUÍ! Usar 's.session_data' en lugar de 's.metadata' ---
            # --- Y manejar el caso de que no sea un JSON válido si hay datos antiguos/corruptos ---
            metadata=json.loads(s.session_data) if s.session_data else None # <-- LÍNEA CORREGIDA
        ) for s in sessions
    ]


@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_conversation_messages(session_id: str, db: AsyncSession = Depends(get_conv_db)):
    """
    Recupera todos los mensajes de una conversación específica, formateados para el frontend.
    """
    session = await crud_conversation.get_chat_session(db, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sesión de chat no encontrada.")

    raw_history = await crud_conversation.get_messages_by_session(db, session_id=session_id, limit=None) # Sin límite
    
    formatted_messages = []
    for msg in raw_history:
        message_content = msg.message
        # Intentar parsear el contenido si es JSON (como tool_calls/responses guardadas)
        try:
            parsed_content = json.loads(message_content)
            if isinstance(parsed_content, list) and all(isinstance(p, dict) for p in parsed_content):
                # Si son partes, extraer el texto si existe o una representación de la tool
                text_parts = [p.get("text") for p in parsed_content if "text" in p]
                if text_parts:
                    message_content = " ".join(text_parts)
                elif any("function_call" in p for p in parsed_content):
                    calls = [p["function_call"]["name"] for p in parsed_content if "function_call" in p]
                    message_content = f"[El asistente utilizó la herramienta: {', '.join(calls)}]"
                elif any("function_response" in p for p in parsed_content):
                    responses_content = []
                    for p in parsed_content:
                        if "function_response" in p and p["function_response"].get("response"):
                            # Asumimos que la respuesta de la tool es un dict con 'content'
                            responses_content.append(str(p["function_response"]["response"].get("content", "...")))
                    if responses_content:
                        message_content = f"[Respuesta de la herramienta: {', '.join(responses_content)}]"
                    else:
                        message_content = "[La herramienta respondió, pero sin contenido visible.]"
                else:
                    message_content = "[Contenido especial no textual]"
            elif "function_call" in parsed_content:
                message_content = f"[El asistente utilizó la herramienta: {parsed_content['function_call']['name']}]"
            elif "function_response" in parsed_content:
                message_content = f"[Respuesta de la herramienta: {parsed_content['function_response']['response'].get('content', '...')}]"
            
        except (json.JSONDecodeError, TypeError):
            # Es texto plano o no se puede parsear, no hacer nada
            pass

        formatted_messages.append(ChatMessageResponse(
            session_id=msg.session_id,
            response=message_content,
            sender=msg.sender,
            created_at=msg.timestamp # <--- ¡CAMBIO AQUÍ! Should be 'timestamp'
        ))
    return formatted_messages