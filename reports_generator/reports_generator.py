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

    

    def read_json_from_thingspeak(self, patientID):
        """
        Read JSON data from the Thingspeak channel via REST API.
        Called on page refresh...
        """
        channel_id = self.user_api_keys(patientID)
        url = f"{self.BASE_URL}/{channel_id}/feeds.json?api_key={self.THINGSPEAK_USER_API_KEY}&results={self.NUMBER_OF_ENTRIES_PER_REQUEST}"
        response = requests.get(url, timeout=5)  # Send GET request to the URL
        
        if response.status_code == 200:
            data = response.json()  # Parse JSON response
            df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
            return df

        return (f"Failed to fetch data. Status code: {response.status_code}")
    
    def user_api_keys(self, patient_id):
        """
        To extract user API keys from the catalog.
        """

        if patient_id not in range(len(self.patientList)):
            return "Error: Patient ID is not valid"
        
        return self.patientList[patient_id]["serviceDetails"]["Thingspeak"]["channelAPIkey"]