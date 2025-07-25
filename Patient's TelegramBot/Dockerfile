FROM python:3.10-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de requisitos e instalar las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY patients_telegrambot.py .
COPY MyMQTT.py .
COPY settings.json .

# Comando para ejecutar el servicio cuando el contenedor se inicie
CMD ["python3", "patients_telegrambot.py"]