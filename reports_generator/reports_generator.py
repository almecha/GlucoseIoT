import json
import cherrypy
import requests
import pandas as pd

'''
    We 100% need to put Thingspeak API keys in the catalog.json file.
    We need to create a new channel for each patient and put the API key in the catalog.json file.
    Store all the global constans (like basic urls, some constants like timeout time and etc.) in the catalog.json file.

'''

class ReportsGenerator(object):
    def __init__(self, catalog_file_path):
        self.catalog_file_path = catalog_file_path
        self.catalog = json.load(open(self.catalog_file_path, encoding='utf-8'))
        self.patientList = self.catalog["patientsList"]
        self.serviceDetails = self.catalog["serviceDetails"]
        self.base_url = self.serviceDetails[2]["REST_endpoint"]
        self.access_code = "1234"
        self.NUMBER_OF_ENTRIES_PER_REQUEST = 100
        self.THINGSPEAK_USER_API_KEY = "TO BE DONE LATER"
        self.BASE_URL = "https://api.thingspeak.com/channels"
        self.ACCESS_CODE = "1234"

    def generate_report(self, patientID):
        """
        Generates a report for the given patient ID by fetching data from the REST API.
        """
        if patientID not in range(len(self.patientList)):
            return "Error: Patient ID is not valid"
        # Fetch data from thingspeak
        df = self.read_json_from_thingspeak(patientID)
        # Check if the DataFrame is empty
        if df.empty:
            return "No data available for the given patient ID."
        # Calculate the metrics
        glucose_measurements = df["glucose_level"].to_list()
        avg_glucose = sum(glucose_measurements) / len(glucose_measurements)
        min_glucose = min(glucose_measurements)
        max_glucose = max(glucose_measurements)
        tir_metics = self.calculate_time_in_range(glucose_measurements)
        variability_metrics = self.calculate_variability(glucose_measurements)

    def read_json_from_thingspeak(self, patientID):
        """
        Read JSON data from the Thingspeak channel via REST API.
        Called on page refresh...
        """
        channel_id = self._user_api_keys(patientID)
        url = f"{self.BASE_URL}/{channel_id}/feeds.json?api_key={self.THINGSPEAK_USER_API_KEY}&results={self.NUMBER_OF_ENTRIES_PER_REQUEST}"
        response = requests.get(url, timeout=5)  # Send GET request to the URL
        
        if response.status_code == 200:
            data = response.json()  # Parse JSON response
            df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
            return df

        return (f"Failed to fetch data. Status code: {response.status_code}")
    
    def _user_api_keys(self, patient_id):
        """
        To extract user API keys from the catalog.
        """

        if patient_id not in range(len(self.patientList)):
            return "Error: Patient ID is not valid"
        
        return self.patientList[patient_id]["serviceDetails"]["Thingspeak"]["channelAPIkey"]
    
    def calculate_time_in_range(self, glucose_measurements):
        """
        Calculate Time in Range (TIR) metrics:
        - Percentage of time in 70–180 mg/dL (Target)
        - Percentage of time <70 mg/dL (Low)
        - Percentage of time >180 mg/dL (High)
        """
        total_measurements = len(glucose_measurements)
        if total_measurements == 0:
            return {
                "Target (70-180 mg/dL)": 0,
                "Low (<70 mg/dL)": 0,
                "High (>180 mg/dL)": 0
            }

        target = sum(70 <= value <= 180 for value in glucose_measurements) / total_measurements * 100
        low = sum(value < 70 for value in glucose_measurements) / total_measurements * 100
        high = sum(value > 180 for value in glucose_measurements) / total_measurements * 100

        return {
            "Target (70-180 mg/dL)": target,
            "Low (<70 mg/dL)": low,
            "High (>180 mg/dL)": high
        }
    
    def calculate_glucose_variability(self, glucose_measurements):
        """
        Calculate Glucose Variability metrics:
        - Coefficient of Variation (CV)
        - Glucose Management Indicator (GMI)
        """
        if not glucose_measurements:
            return {
                "Coefficient of Variation (CV)": None,
                "Glucose Management Indicator (GMI)": None
            }

        mean_glucose = sum(glucose_measurements) / len(glucose_measurements)
        std_dev_glucose = (sum((x - mean_glucose) ** 2 for x in glucose_measurements) / len(glucose_measurements)) ** 0.5

        # Coefficient of Variation (CV)
        cv = (std_dev_glucose / mean_glucose) * 100 if mean_glucose != 0 else None

        # Glucose Management Indicator (GMI)
        gmi = 3.31 + 0.02392 * mean_glucose

        return {
            "Coefficient of Variation (CV)": cv,
            "Glucose Management Indicator (GMI)": gmi
        }