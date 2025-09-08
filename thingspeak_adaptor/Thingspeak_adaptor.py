import requests
import json
from MyMQTT import *
import random
import time
import uuid
import cherrypy

class Thingspeak_MQTT_Worker:
    def __init__(self,settings):
        self.settings = settings
        self.catalogURI = settings['catalogURL']

        self.baseURL=self.settings["ThingspeakWriteURL"]

        self.broker=requests.get(f'{self.catalogURI}/broker').json()['IP']
        self.port=requests.get(f'{self.catalogURI}/broker').json()['port']

        print(f'Broker IP: {self.broker}, Port: {self.port}')

        self.topic=requests.get(f'{self.catalogURI}/services/ThingspeakAdaptor').json()['MQTT_sub'][0] + "/#"
        self.mqttClient = MyMQTT(clientID="nuha", broker=self.broker, port=self.port, notifier=self) #uuid is to generate a random string for the client id
        self.mqttClient.start()
        self.mqttClient.mySubscribe(self.topic)    

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


    def stop(self):
        self.mqttClient.stop()
    
    def notify(self,topic,payload):
        #{'bn':f'SensorREST_MQTT_{self.deviceID}','e':[{'n':'humidity','v':'', 't':'','u':'%'}]}
        print(f"Received message on topic {topic}: {payload}")
        message_decoded=json.loads(payload)
        print(f"Received message on topic {topic}: {type(message_decoded)}")

        sensor_id = int(topic.split('/')[-1])

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
            self.uploadThingspeak(self.userApiKeys[self.sensorIDstoUserID[sensor_id]], field_number=field_number,field_value=message_value)
    

    def uploadThingspeak(self,patient_write_api_key,field_number,field_value):
        #GET https://api.thingspeak.com/update?api_key={}field1={}
        #baseURL -> https://api.thingspeak.com/update?api_key=
        #fieldnumber -> depends on the field (type of measurement) we want to upload the information to
        urlToSend=f'{self.baseURL}{self.channelWriteAPIkey}&field{field_number}={field_value}'
        r=requests.get(urlToSend)
        print(r.text)


class Thingspeak_Adaptor(object):

    def __init__(self, settings):
        self.settings = settings
        self.mqtt_worker = None
        self.catalogURL=settings['catalogURL']
        self.actualTime = time.time()
        self.serviceInfo= requests.get(f'{self.catalogURL}/services/ThingspeakAdaptor').json()
    
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
    settings= json.load(open('settings.json'))
    ts_adaptor=Thingspeak_Adaptor(settings)
    ts_adaptor.start()
    print("Thingspeak Adaptor Started")
    #ts_adaptor.registerService()
    try:
        counter=0
        while True:
            time.sleep(2)
            counter+=1
            if counter==20:
                ts_adaptor.updateService()
                counter=0
    except KeyboardInterrupt:
        ts_adaptor.stop()
        print("Thingspeak Adaptor Stopped")
    



        

