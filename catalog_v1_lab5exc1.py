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
        if uri[0] == "broker":                                          # broker IP & port
            response = self.catalog["broker"]
            print(response)
            return json.dumps(response)
        elif uri[0] == "services":                                    
            response = self.catalog["servicesList"]                     # if there are no parameters, returns list of all services
            serviceID = params.get("serviceID")
            found = False
            if serviceID:                                               # If a service ID is provided, search for it
                for service in response:
                    if service["serviceID"] == serviceID:   
                        response = service
                        found = True
                        break
                if not found:
                    print(f"No services found for {serviceID}.")
            print(response)
            return json.dumps(response)
        elif uri[0] == "devices":                                      # devices
            response = self.catalog["devicesList"]
            deviceID = params.get("deviceID")
            found = False
            if deviceID: 
                for device in response:
                    if deviceID == device["deviceID"]:
                        response= device
                        found = True
                if not found:
                    print(f"No devices found for {deviceID}.")
            print(response)
            return json.dumps(response)
        elif uri[0] == "users":                                        #users
            response = self.catalog["usersList"] # returns all users
            userID = params.get("userID")
            found = False
            if userID: # if userID is passed as a parameter, it looks for that user in the list
                for user in response:
                    if userID == user["userID"]:
                        response = user
                        found = True
                if not found:
                    print(f"No users found for {userID}.")
            patients_list = [user for user in response if user.get("role") == "Patient"]
            doctors_list = [user for user in response if user.get("role") == "Doctor"]
            if len(uri) > 1: # filtering by patients or doctors
                if uri[1] == "patients":
                    response = patients_list
                if uri[1] == "doctors":
                    response = doctors_list
            print(response) # if no filters/parameters are applied, returns all users
            return json.dumps(response)
        elif uri[0] == "config":                                    # config
            response = {
                "Catalog_url": self.catalog["Catalog_url"],
                "broker": self.catalog["broker"],
                "projectOwners": self.catalog["projectOwners"],
                "project_name": self.catalog["project_name"],
                "lastUpdate": self.catalog["lastUpdate"]                
                }    
            print(response)
            return json.dumps(response)     
        else:
            print("Bad request")
        
    def POST(self,*uri, **params):
        body = cherrypy.request.body.read()
        body = json.loads(body)
        timestamp = time.time()
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
        
    # ---------------------------------------------------------------------------------- data validation
    def validate_service(data):
        """Valida que los datos de un servicio sean correctos"""
        required_fields = {
            "serviceID": str,
            "REST_endpoint": str,
            "MQTT_sub": list,
            "MQTT_pub": list,
            "timestamp": str
        }
        return validate_data(data, required_fields)


    def validate_device(data):
        """Valida que los datos de un dispositivo sean correctos"""
        required_fields = {
            "deviceID": int,
            "deviceName": str,
            "measureType": list,
            "availableServices": list,
            "servicesDetails": list,
            "lastUpdate": str
        }
        return validate_data(data, required_fields)


    def validate_user(data):
        """Valida que los datos de un usuario sean correctos"""
        required_fields = {
            "userID": int,
            "userName": str,
            "role": str
        }
        
        if not validate_data(data, required_fields):
            return False
        
        # Validaciones adicionales para "Patient"
        if data["role"] == "Patient":
            if "connected_devices" not in data or not isinstance(data["connected_devices"], list):
                return False
            if "patient_information" not in data or not isinstance(data["patient_information"], dict):
                return False
            if "threshold_parameters" not in data or not isinstance(data["threshold_parameters"], dict):
                return False

        return True


    def validate_data(data, required_fields):
        """Valida si los datos contienen los campos requeridos con los tipos correctos"""
        if not isinstance(data, dict):
            return False

        for field, field_type in required_fields.items():
            if field not in data or not isinstance(data[field], field_type):
                return False

        return True

    # ----------------------------------------------------------------------------------
    
    
    
    def save_catalog(self):
        with open('service_catalog.json', 'w') as f:
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