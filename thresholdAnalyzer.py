import json, requests, logging, cherrypy, math, asyncio, httpx
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta, timezone

# print info for troubleshooting
logging.basicConfig(level=logging.INFO)

catalog_url = "http://localhost:9080"


class ThresholdAnalyzer:
    exposed = True
    def __init__(self, catalog):
        # Extract MQTT broker and port
        response = requests.get(f"{catalog}/broker", timeout=5)
        if response.status_code == 200:
            self.broker = response.json()
            self.mqtt_broker = self.broker["ID"]
            self.mqtt_port = self.broker["port"]
        else:
            raise Exception(f"Failed to fetch broker: {response.status_code}")


        # Extract the topics for the threshold analyzer from the catalog
        response = requests.get(f"{catalog}/services/ThresholdAnalyzer", timeout=5)
        if response.status_code == 200:
            service = response.json()
            self.topic_glucose = service["MQTT_sub"][0]
            self.topic_response = service["MQTT_pub"][0]
        else:
            raise Exception(f"Failed to fetch service details: {response.status_code}")


        # Extract Thingspeak endpoint
        response = requests.get(f"{catalog}/services/ThingspeakAdaptor", timeout=5)
        if response.status_code == 200:
            service = response.json()
            self.thingspeak_base = service["REST_endpoint"]
        else:
            raise Exception(f"Failed to fetch ThingspeakAdaptor details: {response.status_code}")


        # Create the MQTT client and assign callbacks.
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message


    def GET(self):
        return "The Threshold Analyzer is running"


    # Retrieve patient information from the Thingspeak service
    def get_patient_info(self, device_id): # the device ID is posted by the sensor itself inside the MQTT topic
        url = f"{self.thingspeak_base}/patients/{device_id}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                logging.info(f"Retrieved patient info: {data}")
                return data
            else:
                logging.error(f"Error retrieving patient info, status code: {response.status_code}")
                return None
        except Exception as exc:
            logging.error(f"Exception retrieving patient info: {exc}")
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
    async def check_fasting(self, channel_id: int, read_api_key: str, field_name: str = "field1",
                                 timeframe_hours: int = 2) -> bool:
        """
        Arguments:
            channel_id (int): ThingSpeak channel ID of the patient.
            read_api_key (str): ThingSpeak read API key for the channel.
            field_name (str): The field name in ThingSpeak where meal data is stored (default "field1").
            timeframe_hours (int): Number of past hours to check (default 2).

        Returns:
            bool: True if meal status == 1 (eating) reported within the last timeframe_hours, else False.
        """

        # Calculate the earliest datetime to look back.
        now = datetime.now(timezone.UTC)
        since_time = now - timedelta(hours=timeframe_hours)

        params = {
            "api_key": read_api_key,
            "results": 100  # max number of recent entries to fetch, adjust as needed
        }

        url = f"{self.thingspeak_base}/retrieve"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        feeds = data.get("feeds", [])

        # Iterate backwards (most recent first) to find if eaten recently
        for feed in reversed(feeds):
            # Parse feed creation time
            created_at_str = feed.get("created_at")  # e.g., "2023-07-18T10:34:00Z"
            if not created_at_str:
                continue
            created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ")

            if created_at < since_time:
                # Older than our timeframe, no need to check further
                break

            field_value = feed.get(field_name)
            if field_value == '1' or field_value == 1:
                # Found a meal report indicating eating within timeframe
                return True

        # No meal "eating" status found in the last timeframe_hours
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
        logging.info(f"Received message on topic {msg.topic}: {msg.payload}")
        try:
            payload = json.loads(msg.payload.decode())
            glucose = payload.get("glucose")
            timestamp = payload.get("timestamp")
            device_id = payload.get("device_id")

            if glucose is None or device_id is None:
                logging.error("Message payload missing required fields ('glucose' or 'device_id').")
                return

            # Ensure glucose is a number and not NaN
            if not isinstance(glucose, (int, float)) or math.isnan(glucose):
                logging.error("Invalid glucose value: must be a number and not NaN.")
                return

            # Retrieve patient details as a JSON file from the Thingspeak service.
            patient_info = self.get_patient_info(device_id)
            if patient_info is None:
                logging.error("Failed to retrieve patient info; cannot process message.")
                return

            # Extract thresholds and patient's data; if not available, use defaults
            thresholds = patient_info.get("threshold_parameters")
            target_glycemia = thresholds.get("target_glucose_level_normal", 100)  # 100 = default
            low_threshold = thresholds.get("low_threshold", 80)
            extreme_low = thresholds.get("extremely_low_threshold", 54) # require immediate action
            fasting_threshold = thresholds.get("fasting_threshold", 160)
            severe_hyperglycemia = thresholds.get("severe_hyperglycemia_threshold", 240) # immediate action
            insulin_resistence = thresholds.get("insulin_resistence", 0) # 0 is normal, 1 is insulin resistant,
            # while 2 is for patients that are insulin sensitive


            patient_meals = patient_info.get("meals") # list of ordered timestamps


            # Analyze the glucose value and decide on the action.
            response = {}
            if glucose >= fasting_threshold: # high glycemia
                response["message"] = ""
                if glucose >= severe_hyperglycemia:
                    response["message"] += (f"Your blood glucose level is dangerously high. "
                                           f"Please, take your insulin dose and, then, contact your doctor.\n")
                if len(patient_meals) != 0:
                    fasting = self.check_fasting(patient_meals[-1]) # checks the latest timestamp to see if the patient
                    # has eaten in the previous 2 hours
                else:
                    fasting = True
                insulin_dose = self.calculate_insulin_dose(glucose, target_glycemia, insulin_resistence)
                response["action"] = "administer_insulin"
                response["suggested_insulin_dose"] = insulin_dose
                response["message"] += f"High glucose: ({glucose} mg/dL).\n"
                if fasting:
                    response["message"] += (f"Unless you have eaten in the last 2 hours, the recommended insulin dose is: {insulin_dose:.1f} unit/-s.\n"
                                            f"Otherwise, if you actually have eaten, take half of the recommended dose: {0.5*insulin_dose:.1f} unit/-s.\n")
                else:
                    response["message"] += (f"According to the record you have eaten in the last 2 hours.\n"
                                            f"Therefore, the recommended insulin dose is: {0.5*insulin_dose:.1f} unit/-s.\n"
                                            f"If that is not the case and you have not, in fact, eaten in the last 2 hours,\n"
                                            f"take double of the recommended dose: {insulin_dose:.1f} unit/-s.\n")

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

            # Include additional information in the response.
            response["timestamp"] = timestamp
            response["device_id"] = device_id

            # Publish the response to the MQTT topic where the patient’s Telegram bot listens.
            self.publish_response(response)

        except Exception as e:
            logging.error(f"Error processing received message: {e}")


    def publish_response(self, response):
        """
        Publishes the response message (with the determined action) to the MQTT topic.
        """
        try:
            payload = json.dumps(response)
            self.client.publish(self.topic_response, payload)
            logging.info(f"Published response on topic {self.topic_response}: {payload}")
        except Exception as e:
            logging.error(f"Error publishing response: {e}")

    def main(self):
        try: # attempt to connect to the broker
            logging.info(f"Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}...")
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_forever()
        except Exception as exc:
            logging.error(f"MQTT connection error: {exc}")


if __name__ == "__main__":
    web_service = ThresholdAnalyzer(catalog_url)
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