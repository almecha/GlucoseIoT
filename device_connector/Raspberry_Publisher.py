# the Raspeberry publisher can check how many sensors he has to generate in the catalog, after the patients have been registered


# Raspberry Pi MQTT Publisher for Blood Glucose (OOP)
from MyMQTT import *
import json
import time
import random  # Simulating sensor data, replace with actual sensor read
import requests

def read_blood_glucose():
    """Simulate blood glucose readings (replace with actual sensor logic)."""
    return round(random.uniform(40.0, 190.0), 2)  # Normal glucose range, just to test if works, later gotta figure out how to simulate full data

class RaspberryPIPublisher:
    def __init__(self, clientID, broker, port):
        self.clientID = clientID
        self.broker = broker
        self.port = port
        self.simplePublisherClient = MyMQTT(clientID, broker, port, None)  # No subscriber needed

    def startSim(self):
        """Start the MQTT connection."""
        self.simplePublisherClient.start()

    def stopSim(self):
        """Stop the MQTT connection."""
        self.simplePublisherClient.stop()

    def publish(self, message_to_publish, topic):
        """Publish a JSON message to the MQTT topic."""
        print("Publishing:", message_to_publish)
        self.simplePublisherClient.myPublish(
            topic, 
            message_to_publish #separators=(",", ":"))
        )

if __name__ == "__main__":
    catalog_uri = "http://0.0.0.0:9080"
    broker=requests.get(f'{catalog_uri}/broker').json()["IP"]
    port=requests.get(f'{catalog_uri}/broker').json()['port']
    client_id = "GlucoseMonitor_Publisher"
    topic_base = requests.get(f'{catalog_uri}/services/ThingspeakAdaptor').json()["MQTT_sub"][0]

    # Get sensors list
    # Initialize publisher
    client_simplepub = RaspberryPIPublisher(client_id, broker, port)
    client_simplepub.startSim()

    
    base_time = int(time.time())  # Store base timestamp for relative timing

    try:
        while True:

            sensors = requests.get(f"{catalog_uri}/devices/all").json()

            for sensor in sensors:

                glucose_value = read_blood_glucose()  # Get simulated blood glucose reading

                topic = sensor["servicesDetails"][0]["topic"][0]

                message_to_send = {
                    "bn": "GlucosIoT/sensor/glucose",
                    "e": [
                        {
                            "n": "blood_glucose",
                            "u": "mg/dL",
                            "t": int(time.time()) - base_time,  # Relative timestamp
                            "v": glucose_value
                        }
                    ]
                }
                time.sleep(1)  # Simulate time delay between readings
                print(topic)
                client_simplepub.publish(message_to_send, topic)
            time.sleep(20)  # Adjust frequency as needed

    except KeyboardInterrupt:
        print("\nStopping publisher...")
        client_simplepub.stopSim()
