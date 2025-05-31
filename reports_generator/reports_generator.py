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
        # self.catalog_file_path = catalog_file_path
        # self.catalog = json.load(open(self.catalog_file_path, encoding='utf-8'))
        # self.patientList = self.catalog["patientsList"]
        # self.serviceDetails = self.catalog["serviceDetails"]
        self.base_url = "127.0.0.1:8080/retrieve"  # Base URL for the REST API
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
            "Coefficient of Variation (CV)": cv,
            "Glucose Management Indicator (GMI)": gmi
        }
    
    def generate_report(self, patientID):
        """
        Generates a report for the given patient ID by fetching data from the REST API.
        """
        # if patientID not in range(len(self.patientList)):
        #     return "Error: Patient ID is not valid"
        # Fetch data from thingspeak
        response = requests.get(
            f"{self.base_url}?number_of_entries={self.NUMBER_OF_ENTRIES_PER_REQUEST}",
        )
        data = response.json()
        data = json.loads(data)["feeds"]
        # Check if the DataFrame is empty
        if data == None:
            return "No data available for the given patient ID."
        # Calculate the metrics
        glucose_measurements = [float(reading["field1"]) for reading in data if "field1" in reading]
        avg_glucose = sum(glucose_measurements) / len(glucose_measurements)
        min_glucose = min(glucose_measurements)
        max_glucose = max(glucose_measurements)
        tir_metics = self.calculate_time_in_range(glucose_measurements)
        variability_metrics = self.calculate_glucose_variability(glucose_measurements)
        report = json.dumps({
            "Patient ID": patientID,
            "Average Glucose": avg_glucose,
            "Minimum Glucose": min_glucose,
            "Maximum Glucose": max_glucose,
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
            report = self.generate_report(int(params.get('patientID', 0)))
            return json.dumps(report)
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
    cherrypy.config.update({'server.socket_port':8080})
    cherrypy.engine.start()
    cherrypy.engine.block()
