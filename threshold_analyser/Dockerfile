FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY settings.json .
COPY threshold_analyzer.py .
COPY MyMQTT.py .

CMD ["python3", "threshold_analyzer.py"]