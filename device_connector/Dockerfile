FROM python:3.10-slim

# Establecer el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiar el archivo de requisitos e instalar las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Raspberry_Publisher.py .
COPY MyMQTT.py .
COPY settings.json .
COPY glucose_data_simulated_extreme.csv .

#EXPOSE 9080

CMD ["python3", "Raspberry_Publisher.py"]