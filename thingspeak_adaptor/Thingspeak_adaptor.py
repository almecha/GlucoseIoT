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
        self.baseURL=self.settings["ThingspeakWriteURL"]
        self.channelWriteAPIkey=self.settings["ChannelWriteAPIkey"]
        self.broker=self.settings["brokerIP"]
        self.port=self.settings["brokerPort"]
        self.topic=self.settings["mqttTopic"]+"/#"
        self.mqttClient = MyMQTT(clientID="nuha", broker=self.broker, port=self.port, notifier=self) #uuid is to generate a random string for the client id
        self.mqttClient.start()
        self.mqttClient.mySubscribe(self.topic)    

    def stop(self):
        self.mqttClient.stop()
    
    def notify(self,topic,payload):
        #{'bn':f'SensorREST_MQTT_{self.deviceID}','e':[{'n':'humidity','v':'', 't':'','u':'%'}]}
        print(f"Received message on topic {topic}: {payload}")
        message_decoded=json.loads(payload)
        print(f"Received message on topic {topic}: {type(message_decoded)}")
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
            self.uploadThingspeak(field_number=field_number,field_value=message_value)
    
    def uploadThingspeak(self,field_number,field_value):
        #GET https://api.thingspeak.com/update?api_key={}field1={}
        #baseURL -> https://api.thingspeak.com/update?api_key=
        #fieldnumber -> depends on the field (type of measurement) we want to upload the information to
        urlToSend=f'{self.baseURL}{self.channelWriteAPIkey}&field{field_number}={field_value}'
        r=requests.get(urlToSend)
        print(r.text)

@cherrypy.expose
class Thingspeak_REST_Worker(object):
    def __init__(self,settings):
        #https://api.thingspeak.com/channels/2971820/fields/1.json?api_key=2YN0JR2LKQFAV3BI&results=2
        self.TA_adaptor_uri = settings['serviceInfo']['REST_endpoint']
        self.baseURL=settings["ThingspeakReadURL"]
        self.channelReadAPIkey=settings["ChannelReadAPIKey"]
        self.channel_id = settings["ChannelID"]
    
    def GET(self, *uri, **params):
        if len(uri) == 0:
            return "No arguments provided"
        elif uri[0] ==  self.TA_adaptor_uri:
            # Here you would implement the logic to retrieve data from Thingspeak
            # For example, you could return a JSON response with the latest data
            number_of_entries = int(params['number_of_entries']) if 'number_of_entries' in params else 5
            data = self.read_json_from_thingspeak(number_of_entries)
            return json.dumps(data)
        else:
            return "Unknown endpoint"
        

    def read_json_from_thingspeak(self, number_of_entries=5):
        """
        Read JSON data from the Thingspeak channel via REST API.
        Called on page refresh.
        """
        #channel_id = user_api_keys(patientID)
        url = f"{self.baseURL}/{self.channel_id}/fields/1.json?api_key={self.channelReadAPIkey}&results={number_of_entries}"
        print(url)
        response = requests.get(url, timeout=5)  # Send GET request to the URL
        if response.status_code == 200:
            try:
                data = response.json()  # Parse the JSON response
                return data
            except json.JSONDecodeError:
                print("Error decoding JSON response")
                return None
        else:
            print(f"Error: {response.status_code} - {response.text}")
        return None

class Thingspeak_Adaptor(object):

    def __init__(self, settings):
        self.settings = settings
        self.rest_worker = None
        self.mqtt_worker = None
        self.catalogURL=settings['catalogURL']
        self.actualTime = time.time()
        self.serviceInfo=settings['serviceInfo']

    def start(self):
        # Start the MQTT worker
        self.mqtt_worker = Thingspeak_MQTT_Worker(self.settings)
        # Start the REST worker
        self.rest_worker = Thingspeak_REST_Worker(self.settings)
        # Start the REST worker (CherryPy server)
        #Standard configuration to serve the url "localhost:8080"
        conf={
        '/':{
        'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
        'tools.sessions.on':True
        }
        }
        cherrypy.tree.mount(self.rest_worker,'/',conf)
        cherrypy.config.update({'server.socket_port':8080})
        cherrypy.engine.start()

    def stop(self):
        # Stop the MQTT worker
        if self.mqtt_worker:
            self.mqtt_worker.stop()
        # Stop the REST worker (CherryPy server)
        cherrypy.engine.exit()

    def registerService(self):
        self.serviceInfo['last_update']=self.actualTime
        requests.post(f'{self.catalogURL}/services',data=json.dumps(self.serviceInfo))
    
    def updateService(self):
        self.serviceInfo['last_update']=self.actualTime
        requests.put(f'{self.catalogURL}/services',data=json.dumps(self.serviceInfo))

if __name__ == "__main__":
    settings= json.load(open('thingspeak_adaptor/settings.json'))
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
                #ts_adaptor.updateService()
                counter=0
    except KeyboardInterrupt:
        ts_adaptor.stop()
        print("Thingspeak Adaptor Stopped")
    



        

