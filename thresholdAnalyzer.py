import json, requests, logging
import paho.mqtt.client as mqtt
from datetime import datetime, timedelta

# print info for troubleshooting
logging.basicConfig(level=logging.INFO)


class ThresholdAnalyzer:
    def __init__(self, jsonFile):
        with open(jsonFile, "r") as f:
            self.catalog = json.load(f)

        # Extract MQTT broker and port
        self.mqtt_broker = self.catalog["broker"]["IP"]
        self.mqtt_port = self.catalog["broker"]["port"]

        # Extract the topics for the threshold analyzer from the catalog
        service = next((serviceID for serviceID in self.catalog["servicesList"] if serviceID=='ThresholdAnalyzer'), None)
        self.topic_glucose = service["MQTT_sub"][0]
        self.topic_response = service["MQTT_pub"][0]

        # Extract Thingspeak endpoint
        service = next((serviceID for serviceID in self.catalog["servicesList"] if serviceID=='ThingspeakAdaptor'), None)
        self.thingspeak_base = service["REST_endpoint"]

        # retrieve the endpoint for the patients' data
        self.patient_endpoint = 'patients/'


    # Retrieve patient information from the Thingspeak service
    def get_patient_info(self, device_id): # the device ID is posted by the sensor itself inside the MQTT topic
        url = f"{self.thingspeak_base}{self.patient_endpoint}{device_id}"
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


    def calculate_insulin_dose(self, current_glycemia, target, insulin_resistance, fasting):
        sensitivity_factor = 30
        if insulin_resistance == 1: # if the patient is insulin resistant
            sensitivity_factor /= 2
        elif insulin_resistance == 2: # if the patient is insulin sensitive
            sensitivity_factor *= 2
        dose = (current_glycemia - target) / sensitivity_factor
        if not fasting:
            dose /= 2
        return max((round(dose) * 2) / 2, 0) # round the dose to the nearest .5 (it can't be negative)


    def check_fasting(self,last_meal_timestamp):
        try:
            timestamp = datetime.strptime(last_meal_timestamp, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if now <= timestamp + timedelta(hours=2): # if at least 2 hours have not passed since the patient's
                # latest meal, then, they are not fasting
                return False
            else:
                return True
        except:
            return False


    def on_connect(self, client, userdata, flags, rc):
        """
        Callback for when the client receives a connection response from the MQTT broker.
        On a successful connection (rc==0), the client subscribes to the glucose data topic.
        """
        if rc == 0:
            logging.info("Connected to MQTT broker.")
            client.subscribe(self.topic_glucose)
            logging.info(f"Subscribed to topic: {self.topic_glucose}")
        else:
            logging.error("Failed to connect to MQTT broker, return code: %d", rc)


    def on_message(self, client, userdata, msg): # callback for a received PUBLISH message
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

            # Retrieve patient details from the Thingspeak service.
            patient_info = self.get_patient_info(device_id)
            if patient_info is None:
                logging.error("Failed to retrieve patient info; cannot process message.")
                return

            # Extract thresholds and patient's data; if not available, use defaults
            target_glycemia = patient_info.get("target_glycemia", 100)  # 100 = default
            low_threshold = patient_info.get("low_threshold", 80)
            extreme_low = patient_info.get("extreme_low", 54) # require immediate action
            fasting_threshold = patient_info.get("fasting_threshold", 130)
            after_eating = patient_info.get("after_eating_threshold", 180) # for 2 hours after eating
            sever_hyperglycemia = patient_info.get("sever_hyperglycemia_threshold", 240)
            patient_meals = patient_info.get("meals") # list of ordered timestamps
            insulin_resistence = patient_info.get("insulin_resistence", 0) # 0 is normal, 1 is insulin resistant,
            # while 2 is for patients that are insulin sensitive


            # Analyze the glucose value and decide on the action.
            response = {}
            if glucose >= fasting_threshold: # high glycemia
                fasting = self.check_fasting(patient_meals[-1])
                insulin_dose = self.calculate_insulin_dose(glucose, target_glycemia, insulin_resistence, fasting)
                response["action"] = "administer_insulin"
                response["suggested_insulin_dose"] = insulin_dose
                response["message"] = f"High glucose ({glucose} mg/mL).\n"
                if fasting:
                    response["message"] += (f"Unless you have eaten in the last 2 hours, the recommended insulin dose is: {insulin_dose:.1f} unit/-s.\n"
                                            f"Otherwise, if you actually have eaten, take half of the recommended dose: {0.5*insulin_dose:.1f} unit/-s.")
                else:
                    response["message"] += (f"According to the database you have eaten in the last 2 hours.\n"
                                            f"Therefore, the recommended insulin dose is: {insulin_dose:.1f} unit/-s.\n"
                                            f"If that is not the case and you have not, in fact, eaten in the last 2 hours,\n"
                                            f"take double of the recommended dose: {2*insulin_dose:.1f} unit/-s.")
            elif extreme_low < glucose <= low_threshold: # low glycemia
                response["action"] = "eat_food"
                response["message"] = f"Low glucose ({glucose} mg/mL). Please, have a snack to raise your blood sugar."
            elif glucose <= extreme_low:
                response["action"] = "contact_doctor"
                response["message"] = (f"Extremely low glucose ({glucose} mg/mL). You should immediately eat something "
                                       f"and call either your doctor or the emergency services.")
            else:
                # Glucose level is within acceptable range: no action needed.
                response["action"] = "none"
                response["message"] = f"Glucose level is normal ({glucose} mg/mL). No intervention required."

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


    # Create the MQTT client and assign callbacks.
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message


    def main(self):
        try: # attempt to connect to the broker
            logging.info(f"Connecting to MQTT broker at {self.mqtt_broker}:{self.mqtt_port}...")
            self.client.connect(self.mqtt_broker, self.mqtt_port, 60)
            self.client.loop_forever()
        except Exception as exc:
            logging.error(f"MQTT connection error: {exc}")


if __name__ == "__main__":
    analyzer = ThresholdAnalyzer('service_catalog.json')
