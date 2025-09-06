import json
import time
from datetime import datetime, timedelta
import threading
import logging
import cherrypy
import os
import bcrypt

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

CATALOG_FILENAME = "CATALOG.json"

def validate_data(data, required_fields):
    """Validate if body has required fields with correct types."""
    if not isinstance(data, dict):
        return False
    for field, field_type in required_fields.items():
        if field not in data or not isinstance(data[field], field_type):
            return False
    return True

class Catalog:
    exposed = True

    def __init__(self):
        self.catalog_file_path = os.path.join(os.path.dirname(__file__), CATALOG_FILENAME)
        try:
            with open(self.catalog_file_path, "r") as f:
                self.catalog = json.load(f)
            logger.info(f"Catalog loaded from {self.catalog_file_path}")
        except FileNotFoundError:
            logger.warning(f"{self.catalog_file_path} not found. Initializing with empty catalog.")
            self.catalog = self._get_default_catalog_structure()
        except json.JSONDecodeError:
            logger.error(f"Error decoding {self.catalog_file_path}. Starting with default catalog structure.")
            self.catalog = self._get_default_catalog_structure()

        # Ensure all lists are properly initialized
        for list_name in ["servicesList", "devicesList", "doctorsList", "patientsList"]:
            self.catalog.setdefault(list_name, [])
            if not isinstance(self.catalog[list_name], list):
                self.catalog[list_name] = []
                logger.warning(f"{list_name} was not a list, re-initialized to empty list.")

        self.save_catalog()

    def _get_default_catalog_structure(self):
        """Returns default empty catalog structure."""
        return {
            "catalog_url": "http://catalog:9080",
            "projectOwners": [],
            "project_name": "GlucoseIoT",
            "lastUpdate": "",
            "broker": {},
            "servicesList": [],
            "serviceDetails": [],
            "devicesList": [],
            "doctorsList": [],
            "patientsList": []
        }

    def save_catalog(self):
        """Saves current catalog state to JSON file."""
        try:
            self.catalog["lastUpdate"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.catalog_file_path, 'w') as f:
                json.dump(self.catalog, f, indent=4)
            logger.info(f"Catalog saved to {self.catalog_file_path}")
        except Exception as e:
            logger.error(f"Error saving catalog: {e}")

    # Validation Methods
    @staticmethod
    def validate_service(data):
        required_fields = {
            "serviceID": str,
            "REST_endpoint": str,
            "MQTT_sub": list,
            "MQTT_pub": list,
        }
        return validate_data(data, required_fields)

    @staticmethod
    def validate_device(data):
        required_fields = {
            "deviceID": str,
            "deviceName": str,
            "measureType": list,
            "availableServices": list,
            "servicesDetails": list,
        }
        return validate_data(data, required_fields)

    @staticmethod
    def validate_doctor(data, is_post=True):
        required_fields = {
            "userID": str,
            "userName": str,
            "role": str,
            "telegram_chat_id": (int, type(None)),
            "patients_id": list
        }
        if not validate_data(data, required_fields):
            return False
        if data["role"] not in ["Doctor", "MasterDoctor"]:
            return False
        if is_post and "password_hash" not in data:
            return False
        return True

    @staticmethod
    def validate_patient(data):
        required_fields = {
            "userID": str,
            "role": str,
            "doctorID": str,
            "user_information": dict,
            "threshold_parameters": dict,
            "connected_devices": list,
            "telegram_chat_id": (int, type(None)),
            "thingspeak_info": dict,
            "dashboard_info": dict
        }
        if not validate_data(data, required_fields):
            return False
        return data.get("role") == "Patient"

    # REST API Endpoints
    def GET(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if not uri:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid request. Specify a resource type."}).encode('utf-8')

        resource_type = uri[0]
        response = None

        try:
            if resource_type == "broker":
                response = self.catalog.get("broker", {})
            
            elif resource_type == "services":
                response = self.catalog.get("servicesList", [])
                if len(uri) > 1:  # Path parameter
                    serviceID = uri[1]
                    response = next((s for s in response if s["serviceID"] == serviceID), None)
                elif "serviceID" in params:  # Query parameter
                    serviceID = params["serviceID"]
                    response = next((s for s in response if s["serviceID"] == serviceID), None)
                if not response and (len(uri) > 1 or "serviceID" in params):
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Service not found"}).encode('utf-8')
            
            elif resource_type == "devices":
                response = self.catalog.get("devicesList", [])
                if len(uri) > 1:
                    deviceID = uri[1]
                    response = next((d for d in response if d["deviceID"] == deviceID), None)
                elif "deviceID" in params:
                    deviceID = params["deviceID"]
                    response = next((d for d in response if d["deviceID"] == deviceID), None)
                if not response and (len(uri) > 1 or "deviceID" in params):
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Device not found"}).encode('utf-8')
            
            elif resource_type == "doctors":
                response = self.catalog.get("doctorsList", [])
                if len(uri) > 1:
                    doctor_id = uri[1]
                    response = next((d for d in response if d["userID"] == doctor_id), None)
                elif "userID" in params:
                    doctor_id = params["userID"]
                    response = next((d for d in response if d["userID"] == doctor_id), None)
                elif "telegram_chat_id" in params:
                    try:
                        chat_id = int(params["telegram_chat_id"])
                        response = [d for d in response if d.get("telegram_chat_id") == chat_id]
                    except ValueError:
                        cherrypy.response.status = 400
                        return json.dumps({"error": "Invalid telegram_chat_id format"}).encode('utf-8')
                
                if not response and (len(uri) > 1 or "userID" in params or "telegram_chat_id" in params):
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Doctor not found"}).encode('utf-8')
            
            elif resource_type == "patients":
                response = self.catalog.get("patientsList", [])
                if len(uri) > 1:
                    patientID = uri[1]
                    response = next((p for p in response if p["userID"] == patientID), None)
                elif "userID" in params:
                    patientID = params["userID"]
                    response = next((p for p in response if p["userID"] == patientID), None)
                elif "doctorID" in params:
                    doctorID = params["doctorID"]
                    response = [p for p in response if p.get("doctorID") == doctorID]
                if not response and (len(uri) > 1 or "userID" in params):
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Patient not found"}).encode('utf-8')
            
            elif resource_type == "config":
                response = {
                    "catalog_url": self.catalog.get("catalog_url"),
                    "broker": self.catalog.get("broker"),
                    "projectOwners": self.catalog.get("projectOwners"),
                    "project_name": self.catalog.get("project_name"),
                    "lastUpdate": self.catalog.get("lastUpdate")
                }
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Invalid resource type: {resource_type}"}).encode('utf-8')

            return json.dumps(response).encode('utf-8')
        except Exception as e:
            logger.error(f"GET error for {resource_type}: {e}", exc_info=True)
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error"}).encode('utf-8')

    def POST(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            body = json.loads(cherrypy.request.body.read().decode("utf-8"))
        except json.JSONDecodeError:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid JSON body"}).encode('utf-8')

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not uri:
            cherrypy.response.status = 400
            return json.dumps({"error": "Specify resource type to POST"}).encode('utf-8')

        resource_type = uri[0]

        try:
            if resource_type == 'services':
                if not Catalog.validate_service(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid service format"}).encode('utf-8')
                
                if any(s["serviceID"] == body["serviceID"] for s in self.catalog["servicesList"]):
                    cherrypy.response.status = 409
                    return json.dumps({"error": f"Service {body['serviceID']} already exists"}).encode('utf-8')
                
                body["timestamp"] = current_time
                self.catalog["servicesList"].append(body)
                cherrypy.response.status = 201
            
            elif resource_type == "devices":
                if not Catalog.validate_device(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid device format"}).encode('utf-8')

                if any(d["deviceID"] == body["deviceID"] for d in self.catalog["devicesList"]):
                    cherrypy.response.status = 409
                    return json.dumps({"error": f"Device {body['deviceID']} already exists"}).encode('utf-8')
                
                body["lastUpdate"] = current_time
                self.catalog["devicesList"].append(body)
                cherrypy.response.status = 201
            
            elif resource_type == "doctors":
                if not Catalog.validate_doctor(body, is_post=True):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid doctor format"}).encode('utf-8')
                
                if any(d["userID"] == body["userID"] for d in self.catalog["doctorsList"]):
                    cherrypy.response.status = 409
                    return json.dumps({"error": f"Doctor {body['userID']} already exists"}).encode('utf-8')
                
                body["lastUpdate"] = current_time
                body.setdefault("patients_id", [])
                self.catalog["doctorsList"].append(body)
                cherrypy.response.status = 201
            
            elif resource_type == "patients":
                if not Catalog.validate_patient(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid patient format"}).encode('utf-8')
                
                if any(p["userID"] == body["userID"] for p in self.catalog["patientsList"]):
                    cherrypy.response.status = 409
                    return json.dumps({"error": f"Patient {body['userID']} already exists"}).encode('utf-8')
                
                # Verify assigned doctor exists
                doctor = next((d for d in self.catalog["doctorsList"] if d["userID"] == body["doctorID"]), None)
                if not doctor:
                    cherrypy.response.status = 400
                    return json.dumps({"error": f"Doctor {body['doctorID']} not found"}).encode('utf-8')
                # Set default values for new fields
                body.setdefault("telegram_chat_id", None)
                body.setdefault("thingspeak_info", {
                    "apikeys": [],
                    "channel": ""
                })
                body.setdefault("dashboard_info", {
                    "dashboard_username": f"{body['userID']}_dashboard",
                    "dashboard_password": None
                })
                body["lastUpdate"] = current_time
                body["role"] = "Patient"
                self.catalog["patientsList"].append(body)
                
                # Add patient to doctor's list if not already there
                if body["userID"] not in doctor["patients_id"]:
                    doctor["patients_id"].append(body["userID"])
                
                cherrypy.response.status = 201
            
            elif resource_type == "login":
                required_fields = {"userID": str, "password": str}
                if not validate_data(body, required_fields):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Missing userID or password"}).encode('utf-8')
                
                doctor = next((d for d in self.catalog["doctorsList"] if d["userID"] == body["userID"]), None)
                if not doctor:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Doctor not found"}).encode('utf-8')
                
                if not bcrypt.checkpw(body["password"].encode('utf-8'), doctor["password_hash"].encode('utf-8')):
                    cherrypy.response.status = 401
                    return json.dumps({"error": "Invalid credentials"}).encode('utf-8')
                
                # Return doctor data without password hash
                doctor_data = {k:v for k,v in doctor.items() if k != "password_hash"}
                return json.dumps({"message": "Login successful", "doctor": doctor_data}).encode('utf-8')
            
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Cannot POST to {resource_type}"}).encode('utf-8')

            self.save_catalog()
            return json.dumps({"message": "Resource created", "body": body}).encode('utf-8')
        except Exception as e:
            logger.error(f"POST error for {resource_type}: {e}", exc_info=True)
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error"}).encode('utf-8')

    def PUT(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            body = json.loads(cherrypy.request.body.read().decode("utf-8"))
        except json.JSONDecodeError:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid JSON body"}).encode('utf-8')

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if len(uri) < 2:
            cherrypy.response.status = 400
            return json.dumps({"error": "Specify resource type and ID"}).encode('utf-8')

        resource_type = uri[0]
        resource_id = uri[1]
        updated = False

        try:
            if resource_type == 'services':
                for i, service in enumerate(self.catalog["servicesList"]):
                    if service["serviceID"] == resource_id:
                        self.catalog["servicesList"][i].update(body)
                        self.catalog["servicesList"][i]["timestamp"] = current_time
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Service not found"}).encode('utf-8')
            
            elif resource_type == "devices":
                for i, device in enumerate(self.catalog["devicesList"]):
                    if device["deviceID"] == resource_id:
                        self.catalog["devicesList"][i].update(body)
                        self.catalog["devicesList"][i]["lastUpdate"] = current_time
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Device not found"}).encode('utf-8')
            
            elif resource_type == "doctors":
                for i, doctor in enumerate(self.catalog["doctorsList"]):
                    if doctor["userID"] == resource_id:
                        # Prevent role change via PUT
                        if "role" in body and body["role"] != doctor["role"]:
                            cherrypy.response.status = 400
                            return json.dumps({"error": "Cannot change doctor role"}).encode('utf-8')
                        
                        self.catalog["doctorsList"][i].update(body)
                        self.catalog["doctorsList"][i]["lastUpdate"] = current_time
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Doctor not found"}).encode('utf-8')
            
            elif resource_type == "patients":
                old_doctor_id = None
                new_doctor_id = None
                
                for i, patient in enumerate(self.catalog["patientsList"]):
                    if patient["userID"] == resource_id:
                        if "doctorID" in body and body["doctorID"] != patient["doctorID"]:
                            old_doctor_id = patient["doctorID"]
                            new_doctor_id = body["doctorID"]
                        
                        # Preserve default values if not provided in update
                        if "telegram_chat_id" not in body:
                            body["telegram_chat_id"] = patient.get("telegram_chat_id")
                        if "thingspeak_info" not in body:
                            body["thingspeak_info"] = patient.get("thingspeak_info", {
                                "apikeys": [],
                                "channel": ""
                            })
                        if "dashboard_info" not in body:
                            body["dashboard_info"] = patient.get("dashboard_info", {
                                "dashboard_username": f"{resource_id}_dashboard",
                                "dashboard_password": None
                            })
                        
                        self.catalog["patientsList"][i].update(body)
                        self.catalog["patientsList"][i]["lastUpdate"] = current_time
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Patient not found"}).encode('utf-8')
                
                # Handle doctor reassignment
                if old_doctor_id and new_doctor_id:
                    # Remove from old doctor's list
                    old_doctor = next((d for d in self.catalog["doctorsList"] if d["userID"] == old_doctor_id), None)
                    if old_doctor and resource_id in old_doctor["patients_id"]:
                        old_doctor["patients_id"].remove(resource_id)
                    
                    # Add to new doctor's list
                    new_doctor = next((d for d in self.catalog["doctorsList"] if d["userID"] == new_doctor_id), None)
                    if new_doctor and resource_id not in new_doctor["patients_id"]:
                        new_doctor["patients_id"].append(resource_id)
                    elif not new_doctor:
                        cherrypy.response.status = 400
                        return json.dumps({"error": f"New doctor {new_doctor_id} not found"}).encode('utf-8')
            
            elif resource_type == "broker":
                self.catalog["broker"].update(body)
                updated = True
            
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Invalid resource type: {resource_type}"}).encode('utf-8')
            
            self.save_catalog()
            return json.dumps({"message": "Resource updated", "body": body}).encode('utf-8')
        except Exception as e:
            logger.error(f"PUT error for {resource_type}: {e}", exc_info=True)
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error"}).encode('utf-8')

    def DELETE(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'

        if len(uri) < 2:
            cherrypy.response.status = 400
            return json.dumps({"error": "Specify resource type and ID"}).encode('utf-8')

        resource_type = uri[0]
        resource_id = uri[1]
        deleted = False

        try:
            if resource_type == "doctors":
                # Remove doctor and unassign all their patients
                for i, doctor in enumerate(self.catalog["doctorsList"]):
                    if doctor["userID"] == resource_id:
                        # Find a master doctor to reassign patients to
                        master_doctor = next((d for d in self.catalog["doctorsList"] if d["role"] == "MasterDoctor"), None)
                        
                        # Reassign patients or remove doctor field
                        for patient_id in doctor["patients_id"]:
                            patient = next((p for p in self.catalog["patientsList"] if p["userID"] == patient_id), None)
                            if patient:
                                if master_doctor:
                                    patient["doctorID"] = master_doctor["userID"]
                                    master_doctor["patients_id"].append(patient_id)
                                else:
                                    patient["doctorID"] = None
                        
                        del self.catalog["doctorsList"][i]
                        deleted = True
                        break
                
                if not deleted:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Doctor not found"}).encode('utf-8')
            
            elif resource_type == "patients":
                for i, patient in enumerate(self.catalog["patientsList"]):
                    if patient["userID"] == resource_id:
                        # Remove from doctor's list
                        doctor = next((d for d in self.catalog["doctorsList"] if d["userID"] == patient["doctorID"]), None)
                        if doctor and resource_id in doctor["patients_id"]:
                            doctor["patients_id"].remove(resource_id)
                        
                        del self.catalog["patientsList"][i]
                        deleted = True
                        break
                
                if not deleted:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Patient not found"}).encode('utf-8')
            
            elif resource_type == "services":
                self.catalog["servicesList"] = [s for s in self.catalog["servicesList"] if s["serviceID"] != resource_id]
                deleted = len(self.catalog["servicesList"]) < len([s for s in self.catalog["servicesList"] if s["serviceID"] != resource_id])
            
            elif resource_type == "devices":
                self.catalog["devicesList"] = [d for d in self.catalog["devicesList"] if d["deviceID"] != resource_id]
                deleted = len(self.catalog["devicesList"]) < len([d for d in self.catalog["devicesList"] if d["deviceID"] != resource_id])
            
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Invalid resource type: {resource_type}"}).encode('utf-8')
            
            self.save_catalog()
            return json.dumps({"message": f"{resource_type[:-1]} {resource_id} deleted"}).encode('utf-8')
        except Exception as e:
            logger.error(f"DELETE error for {resource_type}: {e}", exc_info=True)
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error"}).encode('utf-8')

    # def remove_old_devices(self):
    #     """Remove devices not updated in last 2 minutes."""
    #     while True:
    #         try:
    #             now = datetime.now()
    #             cutoff = now - timedelta(minutes=2)
    #             
    #             initial_count = len(self.catalog["devicesList"])
    #             self.catalog["devicesList"] = [
    #                 d for d in self.catalog["devicesList"]
    #                 if "lastUpdate" in d and 
    #                 datetime.strptime(d["lastUpdate"], "%Y-%m-%d %H:%M:%S") > cutoff
    #             ]
    #             
    #             if len(self.catalog["devicesList"]) < initial_count:
    #                 self.save_catalog()
    #                 logger.info(f"Removed {initial_count - len(self.catalog['devicesList'])} old devices")
    #             
    #         except Exception as e:
    #             logger.error(f"Error in device cleanup: {e}")
    #         
    #         time.sleep(60)

if __name__ == "__main__":
    import time
    time.sleep(2)  # Wait for other services
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }
    
    catalog = Catalog()
    cherrypy.tree.mount(catalog, '/', conf)
    
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 9080
    })
    
    # # Start background cleanup thread
    # cleanup_thread = threading.Thread(target=catalog.remove_old_devices)
    # cleanup_thread.daemon = True
    # cleanup_thread.start()
    
    logger.info("Catalog service starting on port 9080")
    cherrypy.engine.start()
    cherrypy.engine.block()
