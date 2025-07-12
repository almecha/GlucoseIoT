# CATALOG SERVICE
import json
import time
from datetime import datetime, timedelta
import threading
import logging # Import logging
import cherrypy

# Enable logging for the Catalog service
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


# Helper function for data validation (moved outside the class)
def validate_data(data, required_fields):
    """Validates if body has the required fields and with their correct types."""
    if not isinstance(data, dict):
        return False
    for field, field_type in required_fields.items():
        if field not in data or not isinstance(data[field], field_type):
            return False
    return True

class Catalog:
    exposed = True

    def __init__(self):
        try:
            with open("service_catalog.json", "r") as f:
                self.catalog = json.load(f)
            logger.info("Catalog loaded from service_catalog.json")
        except FileNotFoundError:
            logger.warning("service_catalog.json not found. Initializing with empty catalog.")
            self.catalog = {} # Initialize empty if file doesn't exist
        except json.JSONDecodeError:
            logger.error("Error decoding service_catalog.json. Starting with empty catalog.")
            self.catalog = {} # Initialize empty if file is malformed

        # Ensure core lists are initialized as lists, even if they were null or missing in the file
        self.catalog.setdefault("servicesList", [])
        self.catalog.setdefault("devicesList", [])
        self.catalog.setdefault("usersList", [])

        # Robustly ensure they are lists if they somehow loaded as non-list types (e.g., null)
        if not isinstance(self.catalog["servicesList"], list):
            self.catalog["servicesList"] = []
            logger.warning("servicesList was not a list, re-initialized to empty list.")
        if not isinstance(self.catalog["devicesList"], list):
            self.catalog["devicesList"] = []
            logger.warning("devicesList was not a list, re-initialized to empty list.")
        if not isinstance(self.catalog["usersList"], list):
            self.catalog["usersList"] = []
            logger.warning("usersList was not a list, re-initialized to empty list.")

        self.save_catalog() # Save the corrected structure immediately


    def save_catalog(self):
        """Saves the current state of the catalog to the JSON file."""
        try:
            with open('service_catalog.json', 'w') as f:
                json.dump(self.catalog, f, indent=4)
            logger.info("Catalog saved to service_catalog.json")
        except Exception as e:
            logger.error(f"Error saving catalog to file: {e}")

    # --- Data Validation Static Methods ---
    @staticmethod
    def validate_service(data):
        required_fields = {
            "serviceID": str,
            "REST_endpoint": str,
            "MQTT_sub": list,
            "MQTT_pub": list,
            # "timestamp" is added by the catalog itself
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
            # "lastUpdate" is added by the catalog itself
        }
        return validate_data(data, required_fields)

    @staticmethod
    def validate_user(data):
        required_fields = {
            "userID": str,
            "userName": str,
            "role": str,
            # "timestamp" is added by the catalog itself, not required in payload
        }
        if not validate_data(data, required_fields):
            return False
        
        # Additional validation based on role
        if data["role"] == "Patient":
            if "connected_devices" not in data or not isinstance(data["connected_devices"], list):
                return False
            if "user_information" not in data or not isinstance(data["user_information"], dict):
                return False
            if "threshold_parameters" not in data or not isinstance(data["threshold_parameters"], dict):
                return False
        return True

    # --- REST API Endpoints ---
    def GET(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        
        if not uri:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid request. Specify a resource type (e.g., /broker, /services)."}).encode('utf-8')

        resource_type = uri[0]
        response = None

        try:
            if resource_type == "broker":
                response = self.catalog.get("broker")
            elif resource_type == "services":
                response = self.catalog.get("servicesList", [])
                if len(uri) > 1:  # Path parameter
                    serviceID = uri[1]
                    response = next((service for service in response if service["serviceID"] == serviceID), None)
                elif "serviceID" in params:  # Query parameter
                    serviceID = params["serviceID"]
                    response = next((service for service in response if service["serviceID"] == serviceID), None)
                if not response:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Service not found"}).encode('utf-8')
            elif resource_type == "devices":
                response = self.catalog.get("devicesList", [])
                if len(uri) > 1:  # Path parameter
                    deviceID = uri[1]
                    response = next((device for device in response if device["deviceID"] == deviceID), None)
                elif "deviceID" in params:  # Query parameter
                    deviceID = params["deviceID"]
                    response = next((device for device in response if device["deviceID"] == deviceID), None)
                if not response:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Device not found"}).encode('utf-8')
            elif resource_type == "users":
                response = self.catalog.get("usersList", [])
                if len(uri) > 1:  # Path parameter
                    userID = uri[1]
                    response = next((user for user in response if user["userID"] == userID), None)
                elif "userID" in params:  # Query parameter
                    userID = params["userID"]
                    response = next((user for user in response if user["userID"] == userID), None)
                elif "role" in params:  # Filtering by role
                    role = params["role"].capitalize()
                    response = [user for user in response if user.get("role") == role]
                if not response and (len(uri) > 1 or "userID" in params): # Only 404 if specific user not found
                    cherrypy.response.status = 404
                    return json.dumps({"error": "User not found"}).encode('utf-8')
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
            logger.error(f"Error in GET request for {resource_type}: {e}")
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error during GET request"}).encode('utf-8')


    def POST(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            body = json.loads(cherrypy.request.body.read().decode("utf-8"))
        except json.JSONDecodeError:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid JSON in request body"}).encode('utf-8')

        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not uri:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid request. Specify a resource type to POST (e.g., /services)."}).encode('utf-8')

        resource_type = uri[0]

        try:
            if resource_type == 'services':
                if not Catalog.validate_service(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid service format"}).encode('utf-8')
                body["timestamp"] = current_timestamp
                self.catalog.setdefault("servicesList", []).append(body)
                cherrypy.response.status = 201
            elif resource_type == "devices":
                if not Catalog.validate_device(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid device format"}).encode('utf-8')
                body["lastUpdate"] = current_timestamp
                self.catalog.setdefault("devicesList", []).append(body)
                cherrypy.response.status = 201
            elif resource_type == "users":
                if not Catalog.validate_user(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid user format"}).encode('utf-8')
                
                # Check for duplicate userID before appending
                existing_users = self.catalog.get("usersList", [])
                if any(user.get("userID") == body.get("userID") for user in existing_users):
                    cherrypy.response.status = 409 # Conflict
                    return json.dumps({"error": f"User with ID '{body.get('userID')}' already exists."}).encode('utf-8')

                body["lastUpdate"] = current_timestamp
                self.catalog["usersList"].append(body) # 'usersList' is guaranteed to be a list by __init__
                cherrypy.response.status = 201
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Bad request: Cannot POST to {resource_type}"}).encode('utf-8')

            self.save_catalog()
            return json.dumps({"message": "Resource posted successfully", "body": body}).encode('utf-8')
        except Exception as e:
            logger.error(f"Error in POST request for {resource_type}: {e}", exc_info=True) # Log full traceback
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error during POST request"}).encode('utf-8')


    def PUT(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        try:
            body = json.loads(cherrypy.request.body.read().decode("utf-8"))
        except json.JSONDecodeError:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid JSON in request body"}).encode('utf-8')

        current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not uri:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid request. Specify a resource type to PUT (e.g., /services)."}).encode('utf-8')

        resource_type = uri[0]
        updated = False

        try:
            if resource_type == 'services':
                if not Catalog.validate_service(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid service format"}).encode('utf-8')
                
                for i, service in enumerate(self.catalog.get("servicesList", [])):
                    if service.get("serviceID") == body.get("serviceID"):
                        body["timestamp"] = current_timestamp
                        self.catalog["servicesList"][i] = body
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Service not found"}).encode('utf-8')

            elif resource_type == "devices":
                if not Catalog.validate_device(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid device format"}).encode('utf-8')
                
                for i, device in enumerate(self.catalog.get("devicesList", [])):
                    if device.get("deviceID") == body.get("deviceID"):
                        body["lastUpdate"] = current_timestamp
                        self.catalog["devicesList"][i] = body
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Device not found"}).encode('utf-8')

            elif resource_type == "users":
                if not Catalog.validate_user(body):
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Invalid user format"}).encode('utf-8')
                
                for i, user in enumerate(self.catalog.get("usersList", [])):
                    if user.get("userID") == body.get("userID"):
                        body["lastUpdate"] = current_timestamp
                        self.catalog["usersList"][i] = body
                        updated = True
                        break
                
                if not updated:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "User not found"}).encode('utf-8')
            
            elif resource_type == "broker":
                self.catalog["broker"] = body
                updated = True
                
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Invalid resource type: {resource_type}"}).encode('utf-8')
            
            self.save_catalog()
            return json.dumps({"message": "Resource updated successfully", "body":body}).encode('utf-8')
        except Exception as e:
            logger.error(f"Error in PUT request for {resource_type}: {e}", exc_info=True)
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error during PUT request"}).encode('utf-8')
    
    def DELETE(self, *uri, **params):
        cherrypy.response.headers['Content-Type'] = 'application/json'

        if len(uri) < 2:
            cherrypy.response.status = 400
            return json.dumps({"error": "Invalid request. Specify resource type and ID (e.g., /users/user_id)."}).encode('utf-8')

        resource_type = uri[0]
        resource_id = uri[1]
        deleted = False
        
        try:
            if resource_type == "users":
                users_list = self.catalog.get("usersList", [])
                # Create a new list excluding the item to be deleted
                initial_count = len(users_list)
                self.catalog["usersList"] = [user for user in users_list if user.get("userID") != resource_id]
                deleted = len(self.catalog["usersList"]) < initial_count
                
                if not deleted:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "User not found"}).encode('utf-8')
                
            elif resource_type == "services": 
                services_list = self.catalog.get("servicesList", [])
                initial_count = len(services_list)
                self.catalog["servicesList"] = [service for service in services_list if service.get("serviceID") != resource_id]
                deleted = len(self.catalog["servicesList"]) < initial_count
                
                if not deleted:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Service not found"}).encode('utf-8')
                
            elif resource_type == "devices": 
                devices_list = self.catalog.get("devicesList", [])
                initial_count = len(devices_list)
                self.catalog["devicesList"] = [device for device in devices_list if device.get("deviceID") != resource_id]
                deleted = len(self.catalog["devicesList"]) < initial_count
                
                if not deleted:
                    cherrypy.response.status = 404
                    return json.dumps({"error": "Device not found"}).encode('utf-8')
            
            else:
                cherrypy.response.status = 400
                return json.dumps({"error": f"Invalid resource type: {resource_type}"}).encode('utf-8')
            
            self.save_catalog()
            return json.dumps({"message": f"{resource_type.capitalize()} '{resource_id}' deleted successfully"}).encode('utf-8')
        except Exception as e:
            logger.error(f"Error in DELETE request for {resource_type}: {e}", exc_info=True)
            cherrypy.response.status = 500
            return json.dumps({"error": "Internal Server Error during DELETE request"}).encode('utf-8')

    def remove_old_devices(self):
        """Removes devices that haven't been updated for 2 minutes."""
        logger.info("Starting background thread for removing old devices.")
        while True:
            try:
                now = datetime.now()
                two_minutes_ago = now - timedelta(minutes=2)
                
                # Filter devices based on 'lastUpdate' field
                original_device_count = len(self.catalog.get('devicesList', []))
                self.catalog['devicesList'] = [
                    device for device in self.catalog.get('devicesList', [])
                    if 'lastUpdate' in device and datetime.strptime(device['lastUpdate'], "%Y-%m-%d %H:%M:%S") > two_minutes_ago
                ]
                if len(self.catalog['devicesList']) < original_device_count:
                    self.save_catalog()
                    logger.info("Removed old devices and saved catalog.")
                
            except Exception as e:
                logger.error(f"Error in remove_old_devices background task: {e}", exc_info=True)
            
            time.sleep(60) # Check every minute

if __name__ == "__main__":
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True
        }
    }
    
    # Create an instance of the Catalog
    catalog_instance = Catalog()

    # Mount the Catalog instance at the root URL
    cherrypy.tree.mount(catalog_instance, '/', conf)

    # Set the server port
    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 9080})

    # Start the background thread for removing old devices (if desired)
    # Uncomment the following lines if you want this feature active
    # cleanup_thread = threading.Thread(target=catalog_instance.remove_old_devices)
    # cleanup_thread.daemon = True # Daemonize thread so it exits when main program exits
    # cleanup_thread.start()
    # logger.info("Catalog cleanup thread started.")

    # Start the CherryPy engine and block the main thread
    logger.info("Catalog Service: Starting CherryPy server on port 9080...")
    cherrypy.engine.start()
    cherrypy.engine.block()
