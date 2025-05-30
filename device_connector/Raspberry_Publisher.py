# Raspberry Pi MQTT Publisher for Blood Glucose (OOP)
from MyMQTT import *
import json
import time
import random  # Simulating sensor data, replace with actual sensor read

def read_blood_glucose():
    """Simulate blood glucose readings (replace with actual sensor logic)."""
    return round(random.uniform(70.0, 140.0), 2)  # Normal glucose range, just to test if works, later gotta figure out how to simulate full data

class RaspberryPIPublisher:
    def __init__(self, clientID, broker, port, topic_publish):
        self.clientID = clientID
        self.broker = broker
        self.port = port
        self.topic_publish = topic_publish
        self.simplePublisherClient = MyMQTT(clientID, broker, port, None)  # No subscriber needed

    def startSim(self):
        """Start the MQTT connection."""
        self.simplePublisherClient.start()

    def stopSim(self):
        """Stop the MQTT connection."""
        self.simplePublisherClient.stop()

    def publish(self, message_to_publish):
        """Publish a JSON message to the MQTT topic."""
        print("Publishing:", message_to_publish)
        self.simplePublisherClient.myPublish(
            self.topic_publish, 
            message_to_publish #separators=(",", ":"))
        )

if __name__ == "__main__":
    broker = "mqtt.eclipseprojects.io"  # Change to your actual MQTT broker
    port = 1883
    client_id = "GlucoseMonitor_Publisher"
    topic = "GlucosIoT/sensor"

    # Initialize publisher
    client_simplepub = RaspberryPIPublisher(client_id, broker, port, topic)
    client_simplepub.startSim()

    base_time = int(time.time())  # Store base timestamp for relative timing

    try:
        while True:
            glucose_value = read_blood_glucose()  # Get simulated blood glucose reading

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

            client_simplepub.publish(message_to_send)
            time.sleep(5)  # Adjust frequency as needed

    except KeyboardInterrupt:
        print("\nStopping publisher...")
        client_simplepub.stopSim()
