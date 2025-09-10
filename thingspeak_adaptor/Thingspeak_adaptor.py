import requests
import json
from MyMQTT import *
import random
import time
import uuid
import cherrypy
import logging
from datetime import datetime   
time.sleep(2) # wait for other services to start

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Thingspeak_MQTT_Worker:
    def __init__(self,settings):
        self.settings = settings
        self.catalogURI = settings['catalogURL']

        self.baseURL=self.settings["ThingspeakWriteURL"]
        self.broker=self.settings["brokerIP"]
        self.port=self.settings["brokerPort"]

        print(f'Broker IP: {self.broker}, Port: {self.port}')

        self.topic=self.settings["serviceInfo"]["MQTT_sub"][0]  # e.g. "glucose_data/#"
        self.topic_meal=self.settings["serviceInfo"]["MQTT_sub"][1]  # e.g. "status/meal/#"
       
        self.mqttClient = MyMQTT(clientID="nuha", broker=self.broker, port=self.port, notifier=self) #uuid is to generate a random string for the client id
        self.mqttClient.start()
        self.mqttClient.mySubscribe(self.topic) 
        self.mqttClient.mySubscribe(self.topic_meal) 
        

         # Fetch initial patient list and API keys   

        self.userApiKeys = {}
        self.sensorIDstoUserID = {}
        self.patientList = requests.get(f'{self.catalogURI}/patients').json()

        # Initialize user API keys
        for patient in self.patientList:
            apikeys = patient['thingspeak_info'].get('apikeys', [])
            if apikeys:
                self.userApiKeys[patient['userID']] = apikeys[1] if len(apikeys) > 1 else ''        
        for patient in self.patientList:
            self.sensorIDstoUserID[patient["user_information"]['ID_of_the_sensor']] = patient['userID']


    # Create update patients func to run it periodically
    def updateFromCatalog(self):
        self.patientList = requests.get(f'{self.catalogURI}/patients').json()

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
        urlToSend=f'{self.baseURL}{patient_write_api_key}&field{field_number}={field_value}'
        r=requests.get(urlToSend)
        print(r.json())


class Thingspeak_Adaptor(object):

    def __init__(self, settings):
        self.settings = settings
        self.mqtt_worker = None
        self.catalogURL=settings['catalogURL']
        self.catalog_url = self.catalogURL
        self.actualTime = time.time()
        self.service_id = "thingspeak_adaptor_service"
        self.serviceInfo= requests.get(f'{self.catalogURL}/services/{self.service_id}').json()
        self.max_retries = 5
        self.retry_delay = 5  # seconds
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
            "REST_endpoint": "http://thingspeak_adaptor:8079",   #check port
            "MQTT_sub": [],
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
        # Start the MQTT worker
        self.mqtt_worker = Thingspeak_MQTT_Worker(self.settings)

    def stop(self):
        # Stop the MQTT worker
        if self.mqtt_worker:
            self.mqtt_worker.stop()
        # Stop the REST worker (CherryPy server)
        cherrypy.engine.exit()

    def updateService(self):
        self.serviceInfo['timestamp'] = time.time()
        requests.put(f'{self.catalogURL}/services/ThingspeakAdaptor',data=json.dumps(self.serviceInfo))


if __name__ == "__main__":
    time.sleep(2) # wait for other services to start
    settings= json.load(open('settings.json')) 
    catalogURL = settings.get("catalogURL")
    brokerIP = settings.get("brokerIP")
    brokerPort = settings.get("brokerPort")
    service_info = settings.get("serviceInfo", {})
    topic_sub = service_info.get("MQTT_sub", [None])[0]
    topic_pub = service_info.get("MQTT_pub", [None])[0]
    thingspeak_base = service_info.get("REST_endpoint")
     
    ts_adaptor=Thingspeak_Adaptor(settings)
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
    



        

