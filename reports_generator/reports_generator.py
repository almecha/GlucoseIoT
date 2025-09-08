import json
import cherrypy
import requests
import pandas as pd

'''
    We 100% need to put Thingspeak API keys in the catalog.json file.
    We need to create a new channel for each patient and put the API key in the catalog.json file.
    Store all the global constans (like basic urls, some constants like timeout time and etc.) in the catalog.json file.

'''
@cherrypy.expose
class ReportsGenerator(object):
    def __init__(self, catalog_file_path):
        # self.catalog_file_path = catalog_file_path
        # self.catalog = json.load(open(self.catalog_file_path, encoding='utf-8'))
        self.catalog = "catalog"
        # self.patientList = self.catalog["patientsList"]
        # self.serviceDetails = self.catalog["serviceDetails"]
        #self.base_url = requests.get(f"http://{self.catalog}/services/ThingspeakAdaptor").json()["REST_endpoint"]
        self.base_url = "https://api.thingspeak.com/channels"  # Base URL for the REST API
        self.NUMBER_OF_ENTRIES_PER_REQUEST = 100


    
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
            "Coefficient of Variation (CV)": round(cv,2),
            "Glucose Management Indicator (GMI)": round(gmi,2)
        }
    

    def user_api_keys(self,patient_id):
        """
        To extract user API keys from the catalog.
        """

        response = requests.get("http://0.0.0.0:9080/patients", params={"userID": patient_id})

        if response.status_code == 200:
            user_data = response.json()
            if user_data and "userID" in user_data:
                return user_data["thingspeak_info"]["apikeys"][0], user_data["thingspeak_info"]["channel"]
            else:
                return None

    def read_json_from_thingspeak(self,patientID, number_of_entries=100):
        # MAKE IT USE THE THIGNSPEAK ADAPTOR
        """
        Read JSON data from the Thingspeak channel via REST API.
        Called on page refresh.
        """
        read_api_key, read_channel = self.user_api_keys(patientID)
        
        url = f"{self.base_url}/{read_channel}/fields/1.json?api_key={read_api_key}&results={number_of_entries}"
        response = requests.get(url, timeout=5)  # Send GET request to the URL
        
        if response.status_code == 200:
            data = response.json()  # Parse JSON response
            df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
            return df
        return None
    

    def generate_report(self, patientID):
        """
        Generates a report for the given patient ID by fetching data from the REST API.
        """
        # if patientID not in range(len(self.patientList)):
        #     return "Error: Patient ID is not valid"
        # Fetch data from thingspeak
        # CHANGE HERE RECENTLY TO WORK WITH CATALOG
        
        
        data = self.read_json_from_thingspeak(patientID, self.NUMBER_OF_ENTRIES_PER_REQUEST)
        # Check if the DataFrame is empty
        if data is None:
            return "No data available for the given patient ID."
        
        # Calculate the metrics
        glucose_measurements = pd.to_numeric(data["field1"], errors="coerce").dropna().to_list()        
        avg_glucose = sum(glucose_measurements) / len(glucose_measurements)
        min_glucose = min(glucose_measurements)
        max_glucose = max(glucose_measurements)
        tir_metics = self.calculate_time_in_range(glucose_measurements)
        variability_metrics = self.calculate_glucose_variability(glucose_measurements)
        report = json.dumps({
            "Patient ID": patientID,
            "Average Glucose": round(avg_glucose, 2),
            "Minimum Glucose": round(min_glucose, 2),
            "Maximum Glucose": round(max_glucose, 2),
            "Time in Range Metrics": tir_metics,
            "Glucose Variability Metrics": variability_metrics
        })
        return report

    def GET(self, *uri, **params):
        """
        Handle GET requests to generate the report.
        """
        if len(uri) == 0:
            return "No arguments provided"
        elif uri[0] == "generate_report":
            # Return the report as a JSON response
            report = self.generate_report(params.get('patientID', 0))
            return report
        else:
            return "Unknown endpoint"

if __name__ == "__main__":
    web_service = ReportsGenerator("catalog.json")
    conf={
        '/':{
        'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
        'tools.sessions.on':True
        }
        }
    cherrypy.tree.mount(web_service,'/',conf)
    cherrypy.config.update({'server.socket_port':8093})
    cherrypy.engine.start()
    cherrypy.engine.block()
