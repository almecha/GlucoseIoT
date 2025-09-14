import requests
import json
from MyMQTT import *
import random
import time
import uuid
import cherrypy
import logging
import os
from datetime import datetime   
time.sleep(2) # wait for other services to start

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# global variables
catalog_url = ''
broker_ip = ''
broker_port = 0
service_id = ''
rest_endpoint = '' #base url for thingspeak
mqtt_sub_topics = []
thingspeak_write_url = ''
thingspeak_read_url = ''


class Thingspeak_MQTT_Worker:
    def __init__(self):        
        self.catalog_url = catalog_url
        self.base_url= thingspeak_write_url
        self.broker=broker_ip
        self.port=broker_port
        self.topic=mqtt_sub_topics[0]  # e.g. "glucose_data/#"
        self.topic_meal=mqtt_sub_topics[1]  # e.g. "status/meal/#"
       
        self.mqttClient = MyMQTT(clientID="nuha", broker=self.broker, port=self.port, notifier=self) #uuid is to generate a random string for the client id
        self.mqttClient.start()
        self.mqttClient.mySubscribe(self.topic) 
        self.mqttClient.mySubscribe(self.topic_meal) 
        

         # Fetch initial patient list and API keys   

        self.userApiKeys = {}
        self.sensorIDstoUserID = {}
        self.patientList = requests.get(f'{self.catalog_url}/patients').json()

        # Initialize user API keys
        for patient in self.patientList:
            apikeys = patient['thingspeak_info'].get('apikeys', [])
            if apikeys:
                self.userApiKeys[patient['userID']] = apikeys[1] if len(apikeys) > 1 else ''        
        for patient in self.patientList:
            self.sensorIDstoUserID[patient["user_information"]['ID_of_the_sensor']] = patient['userID']


    # Create update patients func to run it periodically
    def updateFromCatalog(self):
        self.patientList = requests.get(f'{self.catalog_url}/patients').json()

        # Initialize user API keys
        for patient in self.patientList:
            apikeys = patient['thingspeak_info'].get('apikeys', [])
            if apikeys:
                self.userApiKeys[patient['userID']] = apikeys[1] if len(apikeys) > 1 else ''        
        for patient in self.patientList:
            self.sensorIDstoUserID[patient["user_information"]['ID_of_the_sensor']] = patient['userID']

    def stop(self):
        self.mqttClient.stop()
    
    def notify(self,topic,payload):
        #{'bn':f'SensorREST_MQTT_{self.deviceID}','e':[{'n':'humidity','v':'', 't':'','u':'%'}]}
        print(f"Received message on topic {topic}: {payload}")
        message_decoded=json.loads(payload)
        if (topic.split('/')[1] == self.topic.split('/')[1]):
            patient_id = int(topic.split('/')[-1])
            message_value=message_decoded['e'][0]['v'] 
            decide_measurement=message_decoded['e'][0]['n']

            error=False

            if decide_measurement=="blood_glucose":
                print("\n \n Glucose Message")
                field_number=1
            else: 
                error=True
            if error:
                print("Error")
            else:
                print(message_decoded)
                self.uploadThingspeak(self.userApiKeys[patient_id], field_number=field_number,field_value=message_value)
        elif (topic == self.topic_meal[:-2]):
            patient_id = message_decoded["patient_id"]
            value = message_decoded["value"]
            if (value == "eating"):
                value = 1
                print("Meal: Eating")
                field_number = 2  # Assuming field 2 is for meal information
                
                self.uploadThingspeak(self.userApiKeys[patient_id], field_number,value)

    def uploadThingspeak(self,patient_write_api_key,field_number,field_value):
        #GET https://api.thingspeak.com/update?api_key={}field1={}
        #baseURL -> https://api.thingspeak.com/update?api_key=
        #fieldnumber -> depends on the field (type of measurement) we want to upload the information to
        urlToSend=f'{thingspeak_write_url}{patient_write_api_key}&field{field_number}={field_value}'
        logger.info(f"Uploading to ThingSpeak: {urlToSend}")
        r=requests.get(urlToSend)
        print(r.json())


class Thingspeak_Adaptor(object):

    def __init__(self):
        self.mqtt_worker = None
        self.catalog_url = catalog_url
        self.actualTime = time.time()
        self.service_id = service_id
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.ensure_catalog_connection()
        logger.info("Thingspeak connected to Catalog service")
        self.register_service()
        logger.info("Thingspeak service registered with Catalog")
        
        
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
            "MQTT_sub": mqtt_sub_topics,
            "MQTT_pub": [],
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
    
    def start(self):
        try:
            self.mqtt_worker = Thingspeak_MQTT_Worker()
            logger.info("✅ MQTT worker started successfully")
        except Exception as e:
            logger.error(f"❌ Failed to start MQTT worker: {e}")

    def stop(self):
        # Stop the MQTT worker
        if self.mqtt_worker:
            self.mqtt_worker.stop()
        # Stop the REST worker (CherryPy server)
        cherrypy.engine.exit()

    def updateService(self):
        service_data['timestamp'] = time.time()
        requests.put(f'{self.catalog_url}/services/{service_id}',data=json.dumps(service_data))


if __name__ == "__main__":
    time.sleep(2) # wait for other services to start
    settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    with open(settings_file_path, 'r') as f:
        settings = json.load(f)
    catalog_url = settings.get("catalogURL")
    broker_ip = settings.get("brokerIP")
    broker_port = settings.get("brokerPort")
    service_info = settings.get("serviceInfo", {})
    service_id = service_info.get("serviceID", "ThingspeakAdaptor")
    rest_endpoint = service_info.get("REST_endpoint", "http://thingspeak-adaptor:8079") 
    mqtt_sub_topics = service_info.get("MQTT_sub", [])
    thingspeak_write_url = settings.get("ThingspeakWriteURL") #base url for thingspeak
    thingspeak_read_url = settings.get("ThingspeakReadURL")
    service_data = {
            "serviceID": service_id,
            "REST_endpoint": rest_endpoint,   #check port
            "MQTT_sub": mqtt_sub_topics,
            "MQTT_pub": [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
     
    ts_adaptor=Thingspeak_Adaptor()
    ts_adaptor.start()
    print("Thingspeak Adaptor Started")
    try:
        counter=0
        while True:
            time.sleep(2)
            counter+=1
            if counter==20:
                ts_adaptor.updateService()
                ts_adaptor.mqtt_worker.updateFromCatalog()
                counter=0
    except KeyboardInterrupt:
        ts_adaptor.stop()
        print("Thingspeak Adaptor Stopped")
    



        

