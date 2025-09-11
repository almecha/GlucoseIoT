FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Thingspeak_adaptor.py .
COPY MyMQTT.py .
COPY settings.json .

CMD ["python3", "Thingspeak_adaptor.py"]