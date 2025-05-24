# app/tools/base_tool.py
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseTool(ABC):
    """Clase base para todas las herramientas"""
    
    name: str
    description: str
    parameters: Dict[str, Any]
    
    @abstractmethod
    async def run(self, **kwargs) -> Dict[str, Any]:
        """Ejecuta la herramienta con los argumentos proporcionados"""
        pass