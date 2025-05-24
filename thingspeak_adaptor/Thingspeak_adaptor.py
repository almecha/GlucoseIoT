import requests
import json
from MyMQTT import *
import random
import time
import uuid

class Thingspeak_Adaptor:
    def __init__(self,settings):
        self.settings = settings
        #self.catalogURL=settings['catalogURL']
        self.serviceInfo=settings['serviceInfo']
        self.baseURL=self.settings["ThingspeakURL"]
        self.channelWriteAPIkey=self.settings["ChannelWriteAPIkey"]
        self.channelReadAPIkey=self.settings["ChannelReadAPIKey"]
        self.broker=self.settings["brokerIP"]
        self.port=self.settings["brokerPort"]
        self.topic=self.settings["mqttTopic"]+"/#"
        self.mqttClient = MyMQTT(clientID="nuha", broker=self.broker, port=self.port, notifier=self) #uuid is to generate a random string for the client id
        self.mqttClient.start()
        self.mqttClient.mySubscribe(self.topic)
        self.actualTime = time.time()
    
    def registerService(self):
        self.serviceInfo['last_update']=self.actualTime
        requests.post(f'{self.catalogURL}/services',data=json.dumps(self.serviceInfo))
    
    def updateService(self):
        self.serviceInfo['last_update']=self.actualTime
        requests.put(f'{self.catalogURL}/services',data=json.dumps(self.serviceInfo))

    def stop(self):
        self.mqttClient.stop()
    
    def notify(self,topic,payload):
        #{'bn':f'SensorREST_MQTT_{self.deviceID}','e':[{'n':'humidity','v':'', 't':'','u':'%'}]}
        message_decoded=json.loads(payload)
        message_value=message_decoded["e"][0]['v']
        decide_measurement=message_decoded["e"][0]["n"]
        error=False
        if decide_measurement=="glucose_level":
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

if __name__ == "__main__":
    settings= json.load(open('thingspeak_adaptor/settings.json'))
    ts_adaptor=Thingspeak_Adaptor(settings)
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
    



        

