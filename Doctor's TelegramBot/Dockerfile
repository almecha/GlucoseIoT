# Usar una imagen base de Python ligera
FROM python:3.9-slim-buster

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de requisitos e instalar las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto de los archivos del proyecto al directorio de trabajo
# Esto copiará CATALOG.py y CATALOG.json
COPY . .

# Exponer el puerto en el que escucha el servicio
EXPOSE 9080

# Comando para ejecutar el servicio cuando el contenedor se inicie
CMD ["python3", "doctor_telegrambot.py"]