import json, requests, logging, cherrypy, math, os, time
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta, timezone
import pandas as pd

time.sleep(2) # wait for other services to start

# print info for troubleshooting
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class ThresholdAnalyzer:
    exposed = True
    def __init__(self):
        self.catalog_url = catalog_url
        self.service_id = service_id
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.mqtt_broker = brokerIP
        self.mqtt_port = brokerPort
        self.topic_glucose = topic_sub 
        self.topic_response = topic_pub  # e.g. "glucose_alerts/{patient_id}"
        self.thingspeak_base =  thingspeak_base # Thingspeak endpoint
        # Initialize connection to Catalog
        self.ensure_catalog_connection()
        self.register_service()

        # Create the MQTT client and assign callbacks.
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

        try: # attempt to connect to the broker
            logging.info(f"Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}...")
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_start()
        except Exception as exc:
            logging.error(f"MQTT connection error: {exc}")
            
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
            "REST_endpoint": "http://threshold_analyzer:8080",   #check port
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


    def user_api_keys(self,patient_id):
        """
        To extract user API keys from the catalog.
        """

        response = requests.get(f"{self.catalog_url}/patients", params={"userID": patient_id})
        if response.status_code == 200:
            user_data = response.json()
            if user_data and "userID" in user_data:
                return user_data["thingspeak_info"].get("apikeys")[0], user_data["thingspeak_info"]["channel"]
            else:
                logging.error(f"No user data found for patient ID: {patient_id}")
        return None

    def read_json_from_thingspeak(self, patientID, number_of_entries):
        # MAKE IT USE THE THIGNSPEAK ADAPTOR
        """
        Read JSON data from the Thingspeak channel via REST API.
        Called on page refresh.
        """
        BASE_URL = "https://api.thingspeak.com/channels"
        read_api_key, channel_id = self.user_api_keys(patientID)
        print("Read API Key:", read_api_key)
        url = f"{BASE_URL}/{channel_id}/fields/2/last.json?api_key={read_api_key}"
        print("Thingspeak URL:", url)
        response = requests.get(url, timeout=5)  # Send GET request to the URL
        
        if response.status_code == 200:
            data = response.json()  # Parse JSON response
            data = data['created_at']  # Extract 'feeds' from the response
            return data
        # st.warning(f"Failed to fetch data. Status code: {response.status_code}")
        return None

    def GET(self):
        return "The Threshold Analyzer is running"


    # Retrieve patient information from the Thingspeak service
    def get_patient_info(self, device_id): # the device ID is posted by the sensor itself inside the MQTT topic
        try:
            response = requests.get(f"{self.catalog_url}/patients",params={"userID": device_id} , timeout=5)
            if response.status_code == 200:
                patient = response.json()

                # Find the patient that has this device
                return patient

            else:
                logging.error(f"Error retrieving patients list: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"Exception retrieving patients list: {e}")
            return None


    def calculate_insulin_dose(self, current_glycemia, target, insulin_resistence):
        sensitivity_factor = 30
        if insulin_resistence == 1: # if the patient is insulin resistant
            sensitivity_factor /= 2
        elif insulin_resistence == 2: # if the patient is insulin sensitive
            sensitivity_factor *= 2
        dose = (current_glycemia - target) / sensitivity_factor
        dose = round(dose * 2) / 2
        return max(dose, 0) # round the dose to the nearest .5 (it can't be negative)


    # returns true only if the patient has not eaten in 2 hours
    def check_fasting(self, patient_info) -> bool:
        """
        Check if the patient has eaten recently by querying ThingSpeak for meal data.

        Args:
            patient_info: The patient's unique identifier

        Returns:
            bool: True if patient has eaten in the last 2 hours (not fasting), False otherwise
        """
        try:
            

            # Calculate timeframe (last 2 hours)
            feeds = self.read_json_from_thingspeak(patient_info['userID'], 1)

            if feeds is None or len(feeds) == 0:
                logging.info("No meal data found; assuming fasting.")
                return False
            
            last_meal_timestamp = feeds
            current_time = datetime.now(timezone.utc)
            # OR f-strings (fine, but formatting happens even if level is disabled)
            logging.info(f"Last meal timestamp: {last_meal_timestamp}")
            logging.info(f"Current time: {current_time}")            
            last_meal_time = datetime.strptime(last_meal_timestamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            current_time = datetime.now(timezone.utc)
            time_diff = current_time - last_meal_time
            if time_diff <= timedelta(hours=2):
                return True
            else:
                return False

        except Exception as e:
            logging.error(f"Error checking fasting status: {e}")
            return False


    def on_connect(self, client, _userdata, _flags, rc):
        """
        Callback for when the client receives a connection response from the MQTT broker.
        On a successful connection (rc==0), the client subscribes to the glucose data topic.
        """
        if rc == 0:
            logging.info("Connected to MQTT broker.")
            client.subscribe(self.topic_glucose)
            logging.info(f"Subscribed to topic: {self.topic_glucose}")
        else:
            logging.error(f"Failed to connect to MQTT broker, return code: {rc:,}")


    def on_message(self, _client, _userdata, msg): # callback for a received PUBLISH message
        """
        Expecting a JSON payload with:
         - glucose: the measured glucose level (in mg/dL)
         - timestamp: date-time of the measurement
         - device_id: identifier of the glucose sensor/device
        """
        
        try:
            payload = json.loads(msg.payload.decode())
            glucose = payload.get("e")[0]["v"]
            patient_id = msg.topic.split("/")[-1] # extract patient ID from the topic
            logging.info(f"Received message on topic {msg.topic}: {msg.payload}")
            if glucose is None or patient_id is None:
                logging.error("Message payload missing required fields ('glucose' or 'device_id').")
                return

            # Ensure glucose is a number and not NaN
            if not isinstance(glucose, (int, float)) or math.isnan(glucose):
                logging.error("Invalid glucose value: must be a number and not NaN.")
                return

            # Retrieve patient details as a JSON file from the Thingspeak service.
            patient_info = self.get_patient_info(patient_id)
            if patient_info is None:
                logging.error("Failed to retrieve patient info; cannot process message.")
                return

            # Extract thresholds and patient's data; if not available, use defaults
            thresholds = patient_info.get("threshold_parameters", {})
            target_glycemia = thresholds.get("target_glucose_level_normal", 100)  # 100 = default
            low_threshold = thresholds.get("low_threshold", 80)
            extreme_low = thresholds.get("extremely_low_threshold", 54) # require immediate action
            fasting_threshold = thresholds.get("fasting_threshold", 160)
            severe_hyperglycemia = thresholds.get("severe_hyperglycemia_threshold", 240) # immediate action
            insulin_resistence = thresholds.get("insulin_resistence", 0) # 0 is normal, 1 is insulin resistant,
            # while 2 is for patients that are insulin sensitive
            # print(f"Patient {patient_id} - Fasting threshold: {fasting_threshold}")
            # Analyze the glucose value and decide on the action.
            response = {}
            if glucose >= fasting_threshold: # high glycemia
                response["message"] = ""
                if glucose >= severe_hyperglycemia:
                    response["message"] += (f"Your blood glucose level is dangerously high. "
                                           f"Please, take your insulin dose and, then, contact your doctor.\n")

                has_eaten = self.check_fasting(patient_info) # checks to see if the patient
                    # has eaten in the previous 2 hours

                insulin_dose = self.calculate_insulin_dose(glucose, target_glycemia, insulin_resistence)
                response["action"] = "administer_insulin"
                response["suggested_insulin_dose"] = insulin_dose
                response["message"] += f"High glucose: ({glucose} mg/dL).\n"
                if has_eaten:
                    # System thinks patient has eaten recently
                    response["message"] += (
                        f"Our records indicate you've eaten in the last 2 hours. "
                        f"Based on this, the recommended insulin dose is: {0.5 * insulin_dose:.1f} units.\n"
                        f"If this is incorrect and you haven't actually eaten, please take the full dose: {insulin_dose:.1f} units.\n"
                        f"Please ensure your meal records are accurate for future recommendations."
                    )
                    response["suggested_insulin_dose"] = 0.5 * insulin_dose
                else:
                    # System thinks patient hasn't eaten recently (fasting)
                    response["message"] += (
                        f"Our records indicate you haven't eaten in the last 2 hours (fasting state). "
                        f"Based on this, the recommended insulin dose is: {insulin_dose:.1f} units.\n"
                        f"If this is incorrect and you have actually eaten, please take half the dose: {0.5 * insulin_dose:.1f} units.\n"
                        f"Please ensure your meal records are accurate for future recommendations."
                    )
                    response["suggested_insulin_dose"] = insulin_dose

            elif glucose <= extreme_low: # extremely low glycemia
                response["immediate_action"] = "contact_doctor"
                response["message"] = (f"Extremely low glucose: ({glucose} mg/dL). You should immediately eat something "
                                       f"and call either your doctor or the emergency services.")

            elif extreme_low < glucose <= low_threshold:  # low glycemia
                response["action"] = "eat_food"
                response["message"] = f"Low glucose: ({glucose} mg/dL). Please, have a snack to raise your blood sugar."

            else: # Glucose level is within acceptable range: no action needed.
                response["action"] = "none"
                response["message"] = f"Glucose level is normal ({glucose} mg/dL). No intervention required."


            patient_id = patient_info["userID"]
            response["patientID"] = patient_id

            # Publish the response to the MQTT topic where the patient’s Telegram bot listens.
            self.publish_response(response, patient_id)

        except Exception as e:
            logging.error(f"Error processing received message: {e}")


    def publish_response(self, response, patient_id):
        """
        Publishes the response message (with the determined action) to the MQTT topic.
        """
        try:
            topic = self.topic_response.replace("{patient_id}", str(patient_id))
            payload = json.dumps(response)
            self.client.publish(topic, payload)
            logging.info(f"Published response on topic {topic}: {payload}")
        except Exception as e:
            logging.error(f"Error publishing response: {e}")


if __name__ == "__main__":    
    settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_file_path, 'r') as f:
            settings = json.load(f)
        catalog_url = settings.get("catalogURL")
        brokerIP = settings.get("brokerIP")
        brokerPort = settings.get("brokerPort")
        service_info = settings.get("serviceInfo", {})
        service_id = service_info.get("serviceID", "ThresholdAnalyzer")
        topic_sub = service_info.get("MQTT_sub", [None])[0]
        topic_pub = service_info.get("MQTT_pub", [None])[0]
        thingspeak_base = service_info.get("REST_endpoint")
    except Exception as e:
        print(f"Error reading settings: {e}")
        exit(1)
    web_service = ThresholdAnalyzer()
    conf={
        '/':{
        'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
        'tools.sessions.on':True
        }
        }
    cherrypy.tree.mount(web_service,'/',conf)
    cherrypy.config.update({'server.socket_port':8080})
    cherrypy.engine.start()
    cherrypy.engine.block()