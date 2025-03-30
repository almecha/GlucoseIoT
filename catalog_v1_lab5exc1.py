# CATALOG SERVICE

import cherrypy
import json
from datetime import datetime,timedelta
import time

class Catalog:
    exposed = True
    def __init__(self):
        with open("service_catalog.json","r") as f:                     # open file json catalog
            self.catalog = json.load(f)
            
    def GET(self, *uri, **params):      # -------------------------     GET     -----------------------------
        if uri[0] == "broker":                                          # broker IP & port
            response = self.catalog["broker"]
            print(response)
            return json.dumps(response)
        elif uri[0] == "services":                                     
            response = self.catalog["servicesList"]                     # if there are no parameters, returns list of all services
            if len(uri) > 1:  # Path parameter
                serviceID = uri[1]
                response = next((service for service in response if service["serviceID"] == serviceID), None)
                if not response:
                    return json.dumps({"error": "Service not found"}), 404
            elif "serviceID" in params:  # Query parameter
                serviceID = params["serviceID"]
                response = next((service for service in response if service["serviceID"] == serviceID), None)
                if not response:
                    return json.dumps({"error": "Service not found"}), 404
            print(response)
            return json.dumps(response)
        elif uri[0] == "devices":                                      # devices
            response = self.catalog["devicesList"]
            if len(uri) > 1:  # Path parameter
                deviceID = uri[1]
                response = next((device for device in response if device["deviceID"] == deviceID), None)
                if not response:
                    return json.dumps({"error": "Device not found"}), 404
            elif "deviceID" in params:  # Query parameter - if there is a parameter
                deviceID = params["deviceID"]
                response = next((device for device in response if device["deviceID"] == deviceID), None)
                if not response:
                    return json.dumps({"error": "Device not found"}), 404
            print(response)
            return json.dumps(response)
        elif uri[0] == "users":                                        # users
            response = self.catalog["usersList"] # returns all users
            if len(uri) > 1:  # Path parameter
                userID = uri[1]
                response = next((user for user in response if str(user["userID"]) == userID), None)
                if not response:
                    return json.dumps({"error": "User not found"}), 404
            elif "userID" in params:  # Query parameter
                userID = params["userID"]
                response = next((user for user in response if str(user["userID"]) == userID), None)
                if not response:
                    return json.dumps({"error": "User not found"}), 404
            elif "role" in params:  # Filtering by role
                role = params["role"].capitalize()
                response = [user for user in response if user.get("role") == role]
            print(response)
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
            return json.dumps({"error": "Invalid request"}), 400 
        
    def POST(self,*uri, **params):      # -------------------------     POST     -----------------------------
        body = cherrypy.request.body.read() #.decode("utf-8")  check if necessary
        body = json.loads(body)
        timestamp = time.time() #datetime.now().strftime("%Y-%m-%d %H:%M:%S")  check best way to put it
        if uri[0] == 'services':                                    # services
            if not validate_service(body):
                return json.dumps({"error": "Invalid device format"}), 400
            body["timestamp"] = timestamp
            self.catalog.setdefault("servicesList", []).append(body)
        elif uri[0] == "devices":                                   # devices                                      
            if not validate_device(body):
                return json.dumps({"error": "Invalid device format"}), 400
            body["lastUpdate"] = timestamp
            self.catalog.setdefault("devicesList", []).append(body)
        elif uri[0] == "users":                                     # users                             
            if not validate_user(body):
                return json.dumps({"error": "Invalid device format"}), 400
            body["timestamp"] = timestamp
            self.catalog.setdefault("usersList", []).append(body)
        else:
            print("Bad request")
        self.save_catalog()
        return json.dumps({"message": "Resource posted successfully","body": body})

    def PUT(self,*uri, **params):       # -------------------------     PUT     -----------------------------
        body = cherrypy.request.body.read()
        body = json.loads(body)
        timestamp = time.time()  

        if uri[0] == 'services':
            if not validate_service(body):
                return json.dumps({"error": "Invalid service format"}), 400
            
            updated = False
            for i, service in enumerate(self.catalog.get("servicesList", [])):
                if service["serviceID"] == body["serviceID"]:
                    body["timestamp"] = timestamp
                    self.catalog["servicesList"][i] = body
                    updated = True
                    break
            
            if not updated:
                return json.dumps({"error": "Service not found"}), 404

        elif uri[0] == "devices": 
            if not validate_device(body):
                return json.dumps({"error": "Invalid device format"}), 400
            
            updated = False
            for i, device in enumerate(self.catalog.get("devicesList", [])):
                if device["deviceID"] == body["deviceID"]:
                    body["lastUpdate"] = timestamp
                    self.catalog["devicesList"][i] = body
                    updated = True
                    break
            
            if not updated:
                return json.dumps({"error": "Device not found"}), 404

        elif uri[0] == "users":
            if not validate_user(body):
                return json.dumps({"error": "Invalid user format"}), 400
            
            updated = False
            for i, user in enumerate(self.catalog.get("usersList", [])):
                if user["userID"] == body["userID"]:
                    body["timestamp"] = timestamp
                    self.catalog["usersList"][i] = body
                    updated = True
                    break
            
            if not updated:
                return json.dumps({"error": "User not found"}), 404
        
        elif uri[0] == "broker":
            self.catalog["broker"] = body

        else:
            return json.dumps({"error": "Invalid resource"}), 400
        
        self.save_catalog()
        return json.dumps({"message": "Resource updated successfully", "body":body})
    
    def DELETE(self,*uri,**params):     # -------------------------     DELETE     -----------------------------
        if len(uri) < 2:
            return json.dumps({"error": "Invalid request"}), 400

        resource_type = uri[0]
        resource_id = uri[1]
        
        if resource_type == "users":  
            users_list = self.catalog.get("usersList", [])
            for i, user in enumerate(users_list):
                if str(user["userID"]) == resource_id:
                    del self.catalog["usersList"][i]
                    self.save_catalog()
                    return json.dumps({"message": "User deleted successfully"})
            return json.dumps({"error": "User not found"}), 404
        
        elif resource_type == "services": 
            services_list = self.catalog.get("servicesList", [])
            for i, service in enumerate(services_list):
                if service["serviceID"] == resource_id:
                    del self.catalog["servicesList"][i]
                    self.save_catalog()
                    return json.dumps({"message": "Service deleted successfully"})
            return json.dumps({"error": "Service not found"}), 404
        
        elif resource_type == "devices":  
            devices_list = self.catalog.get("devicesList", [])
            for i, device in enumerate(devices_list):
                if str(device["deviceID"]) == resource_id:
                    del self.catalog["devicesList"][i]
                    self.save_catalog()
                    return json.dumps({"message": "Device deleted successfully"})
            return json.dumps({"error": "Device not found"}), 404
        
        else:
            return json.dumps({"error": "Invalid resource"}), 400
        
                                        # -------------------------     data validation functions     ----------------------------- 
    def validate_service(data):
        required_fields = {
            "serviceID": str,
            "REST_endpoint": str,
            "MQTT_sub": list,
            "MQTT_pub": list,
            "timestamp": str
        }
        return validate_data(data, required_fields)

    def validate_device(data):
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
        required_fields = {
            "userID": int,
            "userName": str,
            "role": str,
            "timestamp": str
        }
        if not validate_data(data, required_fields):
            return False
        if data["role"] == "Patient":
            if "connected_devices" not in data or not isinstance(data["connected_devices"], list):
                return False
            if "patient_information" not in data or not isinstance(data["patient_information"], dict):
                return False
            if "threshold_parameters" not in data or not isinstance(data["threshold_parameters"], dict):
                return False
        return True

    def validate_data(data, required_fields): # validates if body has the required fields and with their correct types
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
                
    def remove_old_devices(self):                           # check if implement this or not #
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