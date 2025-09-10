# Usar una imagen base de Python ligera
FROM python:3.10-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de requisitos e instalar las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de los archivos del proyecto al directorio de trabajo
# Esto copiará CATALOG.py y CATALOG.json
COPY dashboard.py .
COPY __init__.py .
COPY auth.py .
COPY settings.json .
COPY config.yaml .


# Comando para ejecutar el servicio cuando el contenedor se inicie
CMD ["streamlit", "run", "dashboard.py"]
