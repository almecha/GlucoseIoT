import json
import cherrypy
import requests

class ReportsGenerator(object):
    """
    Provide GET method for reports generator to send reports to the dashboard.
    The reports generator will be used to generate reports for the patients.
    To retrieve the reports, endpoint is "glucoseiot/reports/<patient_id>?REPORT_API_KEY = <API_KEY>"
    """

    def __init__(self):
        self.catalog = json.load(open('../catalog.json', encoding='utf-8'))
        self.patientList = self.catalog["patientsList"]
        self.servicesList = self.catalog["servicesList"]
        self.base_url = self.servicesList[2]["REST_endpoint"]
    
    exposed = True

    def GET(self, *uri, **params):
        uri = ''.join(uri)
        if uri.split("/")[0] != "reports":
            return "Error: Invalid endpoint"
        
        patientID = uri.split("/")[1]
        if patientID not in range(len(self.patientList)):
            return "Error: Patient ID is not valid"
        
        if "REPORT_API_KEY" not in params:
            return "Error: REPORT_API_KEY is missing"
        report_api_key = params["REPORT_API_KEY"]
        if report_api_key != self.patientList[patientID]["serviceDetails"][1]["REPORT_API_KEY"]:
            return "Error: Invalid REPORT_API_KEY"
        
        return json.dumps(self.generate_report(patientID))


    def generate_report(self, patientID):
        """
        Generate a report for the patient with the given ID.
        Fetch data from Thingspeak and process it to create a report.
        This is a placeholder function and should be replaced with actual logic.
        """
        # Placeholder for report generation logic
        # In a real scenario, this would involve complex calculations and data retrieval
        report = {
            "patient_id": patientID,
            "report_data": "This is a sample report data."
        }
        return report
        

    exposed = True



