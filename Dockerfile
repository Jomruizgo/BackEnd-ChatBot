# Usa una imagen base oficial de Python
# Recomendado usar una versión específica y slim para reducir el tamaño
FROM python:3.10-slim-buster

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de requerimientos e instala las dependencias primero
# Esto aprovecha el cache de Docker si los requerimientos no cambian
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto de tu código de la aplicación al contenedor
COPY . .

# Expone el puerto en el que la aplicación FastAPI va a correr
EXPOSE 8000

# Comando para correr la aplicación FastAPI con Uvicorn
# Las variables de entorno se pasarán al contenedor cuando lo ejecutes
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]