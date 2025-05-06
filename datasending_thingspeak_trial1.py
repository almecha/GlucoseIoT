# Thinkspeak adaptor test

import requests
import time
import random

url = 'https://api.thingspeak.com/update.json'
write_api_key = "YW0KZUGQRGCL9FTP"

while True:
    t=float(random.randint(25,40))
    sensor_readings={'api_key':write_api_key,'field1':t}
    requests_headers={'Content-Type':'application/json'}
    print(f"Sendind {t} to thingspeak")
    response=requests.post(url,sensor_readings,requests_headers)

    # Verifica la respuesta
    if response.status_code == 200 and response.text != '0':
        print(f"Datos enviados correctamente. Entry ID: {response.text}")
    else:
        print(f"Error al enviar datos. Código: {response.status_code}, Respuesta: {response.text}")
    
    time.sleep(20)