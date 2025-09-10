# the Raspeberry publisher can check how many sensors he has to generate in the catalog, after the patients have been registered


# Raspberry Pi MQTT Publisher for Blood Glucose (OOP)
import os
from MyMQTT import *
import json
import time
import random  # Simulating sensor data, replace with actual sensor read
import requests
import logging
from datetime import datetime
time.sleep(2) # wait for other services to start

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)
def read_blood_glucose():
    """Simulate blood glucose readings (replace with actual sensor logic)."""
    return round(random.uniform(40.0, 190.0), 2)  # Normal glucose range, just to test if works, later gotta figure out how to simulate full data

class RaspberryPIPublisher:
    def __init__(self, clientID, broker, port):
        self.clientID = clientID
        self.broker = broker
        self.port = port
        self.simplePublisherClient = MyMQTT(clientID, broker, port, None)  # No subscriber needed
        self.service_id = "DeviceConnector"
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.catalog_url = catalog_url
        self.ensure_catalog_connection()
        self.register_service()
        
        
    # Catalog     
    def ensure_catalog_connection(self):
        """Ensure catalog service is available before proceeding"""
        for attempt in range(self.max_retries):
            try:
                response = requests.get(f"{self.catalog_url}/config", timeout=3)
                if response.status_code == 200:
                    logger.info("Successfully connected to Catalog service")
                    return True
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}: Catalog not ready yet - {str(e)}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)

        logger.error("Failed to connect to Catalog service after multiple attempts")
        return False

    def register_service(self):
        """Register service with retry mechanism"""
        service_data = {
            "serviceID": self.service_id,
            "REST_endpoint": rest_endpoint,   #check port
            "MQTT_sub": [],
            "MQTT_pub": [topic_base],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    f"{self.catalog_url}/services/{self.service_id}",
                    json=service_data,
                    timeout=5
                )
                if response.status_code in [200, 201]:
                    logger.info("Service registered successfully with Catalog")
                    return True
                else:
                    logger.warning(f"Service registration attempt {attempt + 1} failed: {response.text}")
            except requests.RequestException as e:
                logger.warning(f"Service registration attempt {attempt + 1} failed: {str(e)}")
            
            if attempt < self.max_retries - 1:
                time.sleep(self.retry_delay)

        logger.error("Failed to register service after multiple attempts")
        return False
        
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
    settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_file_path, 'r') as f:
            settings = json.load(f)
        catalog_url = settings.get("catalogURL")
        broker= settings.get("brokerIP")
        port= settings.get("brokerPort")
        service_info = settings.get("serviceInfo", {})
        rest_endpoint = service_info.get("REST_endpoint", "")
        service_id = service_info.get("serviceID", "")
    except Exception as e:
        print(f"Error reading settings: {e}")
        exit(1)
        
    #catalog_uri = "http://0.0.0.0:9080"
    # broker=requests.get(f'{catalog_ur}/broker').json()["IP"]
    # port=requests.get(f'{catalog_uri}/broker').json()['port']
    client_id = "GlucoseMonitor_Publisher"
    topic_base = requests.get(f'{catalog_url}/services/ThingspeakAdaptor').json()["MQTT_sub"][0]

    # Get sensors list
    # Initialize publisher
    client_simplepub = RaspberryPIPublisher(client_id, broker, port)
    client_simplepub.startSim()

    base_time = int(time.time())  # Store base timestamp for relative timing

    try:
        while True:
            sensors = requests.get(f"{catalog_url}/devices/all").json()
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
