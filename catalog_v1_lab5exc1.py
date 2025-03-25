# CATALOG SERVICE

import cherrypy
import json
from datetime import datetime,timedelta
import time

class Catalog:
    exposed = True
    def __init__(self):
        with open("service_catalog.json","r") as f:
            self.catalog = json.load(f)
            
    def GET(self, *uri, **params):
        if uri[0] == "broker":                                          
            response = self.catalog["broker"]
            print(response)
            return json.dumps(response)
        elif uri[0] == "alldevices":                                    #4
            response = self.catalog["devicesList"]
            print(response)
            return json.dumps(response)
        elif uri[0] == "deviceID":                                      #5 
            found = False
            device_ID = params[0]["deviceID"]
            for device in self.catalog["devicesList"]:
                if device_ID == device["deviceID"]:
                    response= device
                    found = True
            if not found:
                print(f"No devices found for {device_ID}.")
            print(response)
            return json.dumps(response)
        elif uri[0] == "userID":                                        #8
            found = False
            user_ID = params[0]["userID"]
            for user in self.catalog["usersList"]:
                if user_ID == user["userID"]:
                    response= user
                    found = True
            if not found:
                print(f"No users found for {user_ID}.")
            print(response)
            return json.dumps(response)
        elif uri[0] == "config":                                    #4
            response = self.catalog["devicesList"]
            print(response)
            return json.dumps(response)     
        else:
            print("Bad request")
        
    def POST(self,*uri, **params):
        #body = cherrypy.request.body.read()
        #body = json.loads(body)
        #body["insert-timestamp"] = time.time()
        if uri[0] == "devices":                                         #2
            #self.catalog["devicesList"].append(body)
            new_device = {
                'deviceID': input("Enter device ID: "),
                'endpoints': input("Enter endpoints: ").split(','),
                'availableServices': input("Enter available services (comma separated): ").split(','),
                'servicesDetails': [],
                'lastUpdate': datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            self.catalog["devicesList"].append(new_device)
            self.save_catalog()
        elif uri[0] == "users":                                         #6
            #self.catalog["usersList"].append(body)
            new_user = {
                'userID': input("Enter user ID: "),
                'userName': input("Enter user name: "),
                'userSurname': input("Enter user surname: "),
                'email': input("Enter user email address(es): ").split(","),
                'telegramID': input("Enter user telegram chat ID: ")
            }
            self.catalog["usersList"].append(new_user)
            self.save_catalog()
        else:
            print("Bad request")
            
    def PUT(self,*uri, **params):
        if uri[0] == "deviceID":                                                # 3
            device_ID = params.get("deviceID")
            updated_device = json.loads(cherrypy.request.body.read())
            for device in self.catalog["devicesList"]:
                if device["deviceID"] == device_ID:
                    device.update(updated_device)
                    device["lastUpdate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self.save_catalog()
                    return json.dumps(device), 200
            return json.dumps({"error": "Device not found"}), 404
        else:
            return json.dumps({"error": "Bad request"}), 400
    
    def save_catalog(self):
        with open('catalog.json', 'w') as f:
                json.dump(self.catalog, f, indent=4)
                
    def remove_old_devices(self):
        while True:
            now = datetime.now()
            two_minutes_ago = now - timedelta(minutes=2)
            self.catalog['devicesList'] = [device for device in self.catalog['devicesList'] if datetime.strptime(device['insert-timestamp'], "%Y-%m-%d %H:%M:%S") > two_minutes_ago]
            self.save_catalog()
            time.sleep(60)  # Esperar un minuto antes de la siguiente verificación
        
if __name__ == "__main__":
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }
    cherrypy.tree.mount(Catalog(), '/', conf)
    cherrypy.config.update({'server.socket_port': 9080})
    cherrypy.engine.start()
    cherrypy.engine.block()