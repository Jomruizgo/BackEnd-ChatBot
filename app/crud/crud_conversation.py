# app/crud/crud_conversation.py
import json
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select # Using sqlalchemy.future.select for modern async patterns
from sqlalchemy.orm import selectinload
from sqlalchemy import desc, asc, delete # Import 'delete' here

from app.db.models_conversation import ChatSession, ChatMessage # Assuming these are your ORM models

async def create_chat_session(
    db: AsyncSession,
    session_id: str,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> ChatSession:
    """Crea una nueva sesión de chat en la base de datos."""
    session_metadata_json = json.dumps(metadata) if metadata else None
    db_session = ChatSession(
        id=session_id,
        user_id=user_id,
        metadata=session_metadata_json
    )
    db.add(db_session)
    await db.commit()
    await db.refresh(db_session)
    return db_session

async def get_chat_session(db: AsyncSession, session_id: str) -> Optional[ChatSession]:
    """Obtiene una sesión de chat por su ID."""
    result = await db.execute(select(ChatSession).filter(ChatSession.id == session_id))
    return result.scalar_one_or_none()

async def create_chat_message(
    db: AsyncSession,
    session_id: str,
    sender: str, # "user" o "assistant" o "tool"
    message: str, # Puede ser texto plano o JSON de partes de tool
) -> ChatMessage:
    """Crea un nuevo mensaje de chat en la base de datos."""
    db_message = ChatMessage(
        session_id=session_id,
        sender=sender,
        message=message,
    )
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message

# app/crud/crud_conversation.py (fragmento)

async def get_messages_by_session(
    db: AsyncSession,
    session_id: str,
    limit: Optional[int] = 20,
    offset: int = 0,
    ascending_order: bool = True
) -> List[ChatMessage]:
    """
    Obtiene mensajes de una sesión específica, ordenados por fecha de creación.
    Opcionalmente limita el número de mensajes y define el orden.
    """
    # CAMBIO AQUÍ: Usar ChatMessage.timestamp
    order_direction = asc(ChatMessage.timestamp) if ascending_order else desc(ChatMessage.timestamp)
    
    stmt = (
        select(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(order_direction)
        .offset(offset)
    )
    
    if limit is not None:
        stmt = stmt.limit(limit)
        
    result = await db.execute(stmt)
    messages = result.scalars().all()
    return list(messages)

# Y también en get_full_conversation_history si la usas para ordenar sus mensajes cargados
async def get_full_conversation_history(db: AsyncSession, session_id: str) -> Optional[ChatSession]:
    """Obtiene una sesión de chat con todos sus mensajes cargados."""
    result = await db.execute(
        select(ChatSession)
        .filter(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages)) # Removí joinedload porque a veces causa problemas con el orden
    )
    session = result.scalar_one_or_none()
    if session and session.messages:
        # CAMBIO AQUÍ: Usar m.timestamp
        session.messages.sort(key=lambda m: m.timestamp) 
    return session

# También asegúrate de que get_all_sessions siga usando ChatSession.created_at (que sí existe)
async def get_all_sessions(db: AsyncSession, user_id: Optional[str] = None) -> List[ChatSession]:
    """
    Obtiene todas las sesiones de conversación, opcionalmente filtradas por user_id.
    Ordena por fecha de creación descendente para mostrar las más recientes primero.
    """
    query = select(ChatSession)
    if user_id:
        query = query.where(ChatSession.user_id == user_id)
    # ESTO YA ESTÁ CORRECTO: ChatSession sí tiene 'created_at'
    query = query.order_by(desc(ChatSession.created_at)) 
    result = await db.execute(query)
    return result.scalars().all()

async def update_session_metadata(
    db: AsyncSession,
    session_id: str,
    new_metadata: Dict[str, Any]
) -> Optional[ChatSession]:
    """Actualiza los metadatos de una sesión de chat."""
    session = await get_chat_session(db, session_id)
    if session:
        current_metadata = json.loads(session.metadata) if session.metadata else {}
        current_metadata.update(new_metadata)
        session.metadata = json.dumps(current_metadata)
        await db.commit()
        await db.refresh(session)
    return session

# --- NUEVAS FUNCIONES ---

async def delete_session(db: AsyncSession, session_id: str) -> bool:
    """
    Elimina una sesión de conversación y todos sus mensajes asociados.
    Retorna True si la sesión fue encontrada y eliminada, False en caso contrario.
    """
    # Primero, eliminar todos los mensajes asociados a la sesión
    delete_messages_stmt = delete(ChatMessage).where(ChatMessage.session_id == session_id)
    await db.execute(delete_messages_stmt)

    # Luego, eliminar la sesión misma
    delete_session_stmt = delete(ChatSession).where(ChatSession.id == session_id)
    result = await db.execute(delete_session_stmt)
    await db.commit() # Confirmar la transacción para aplicar los cambios
    
    return result.rowcount > 0 # Retorna True si se eliminó al menos una sesión
