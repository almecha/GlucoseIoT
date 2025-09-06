# Description: This file contains the code for the dashboard of the GlucoseIoT project.
# The dashboard will display the glucose levels of the patient in real-time and the time series
# data will be fetched from the Thingspeak channel. The dashboard will be built using Streamlit.

# QUESTIONS:  
# 1. What metrics will we display on the dashboard? (Glucose level, age, etc.)
# 2. Authentication will be done using streamlit-authenticator https://github.com/mkhorasani/Streamlit-Authenticator
# DESIGN CONSIDERATIONS:
'''
    1.  Idea is to implement authentication using ordinary username & password.
        Credentials will be created via streamlit registration page.
        And username & password will be save in config.yaml file also in the catalog.json file
        Same credentials will be used.

'''
import json
import yaml
import requests
import pandas as pd
import cherrypy
import streamlit as st
from auth import GlucoseIoTAuth

# catalog = json.load(open('../catalog.json', encoding='utf-8'))
# patientList = catalog["patientsList"]

NUMBER_OF_ENTRIES_PER_REQUEST = 5
USER_CHANNEL_ID = "2971820"
READ_API_KEY = "2YN0JR2LKQFAV3BI"
BASE_URL = "https://api.thingspeak.com/channels"
ACCESS_CODE = "1234"

# def user_api_keys(patient_id):
#     """
#     To extract user API keys from the catalog.
#     """

#     if patient_id not in range(len(patientList)):
#         return "Error: Patient ID is not valid"
    
#     return patientList[patient_id]["serviceDetails"]["Thingspeak"]["channelAPIkey"]


@cherrypy.expose
class Dashboard_REST_Worker(object):
    def __init__(self):
        #https://api.thingspeak.com/channels/2971820/fields/1.json?api_key=2YN0JR2LKQFAV3BI&results=2
        self.config_file = yaml.safe_load(open('config.yaml'))
        self.CONFIG_PATH = 'config.yaml'
    
    def POST(self, *uri, **params):
        if len(uri) == 0:
            return "No arguments provided"
        
        elif uri[0] ==  'register_dashboard':
            try:
                body = json.loads(cherrypy.request.body.read().decode("utf-8"))
            except json.JSONDecodeError:
                cherrypy.response.status = 400
                return json.dumps({"error": "Invalid JSON body"}).encode('utf-8')
            
            self.config_file = yaml.safe_load(open(self.CONFIG_PATH))
            # Here I want to validate the fields and create a new user in config.yaml
            # Add/update user if provided
            updated = {}
            username = body.get("username")
            fields = body.get("fields")
            if username and isinstance(fields, dict):
                user = self.config_file["credentials"]["usernames"].get(username, {})
                user.update(fields)
                self.config_file["credentials"]["usernames"][username] = user
                updated["username"] = username
                updated["user"] = user
                if not updated:
                    cherrypy.response.status = 400
                    return json.dumps({"error": "Nothing to update (provide 'cookie' and/or 'username' + 'fields')"}).encode("utf-8")
                # Save YAML back
                with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                    yaml.safe_dump(self.config_file, f, sort_keys=False, allow_unicode=True)

                return json.dumps({"status": "ok", **updated}).encode("utf-8")

        else:
                return "Unknown endpoint"

def header(userName):
    """
    Template header for the dashboard.
    """
    st.title("GlucoseIoT Dashboard")
    st.write(f"Hello, {userName} !" + " This dashboard displays your glucose levels, important metrics and time-series.")
    st.badge("GlucoseIoT", icon="🩸", color="red")

def read_json_from_thingspeak(patientID, number_of_entries=NUMBER_OF_ENTRIES_PER_REQUEST):
    # MAKE IT USE THE THIGNSPEAK ADAPTOR
    """
    Read JSON data from the Thingspeak channel via REST API.
    Called on page refresh.
    """
    #channel_id = user_api_keys(patientID)
    url = f"{BASE_URL}/{USER_CHANNEL_ID}/fields/1.json?api_key={READ_API_KEY}&results={number_of_entries}"
    response = requests.get(url, timeout=5)  # Send GET request to the URL
    
    if response.status_code == 200:
        data = response.json()  # Parse JSON response
        df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
        return df
    st.error(f"Failed to fetch data. Status code: {response.status_code}")
    return None

# CHECK THE REPORT AND ADAPT THE DASHVOARD TO IT
def display_metrics(generatedReport):
    """
    To display relevant metrics on the dashboard.
    Called on page refresh.
    WILL BE REDONE LATER WITH REPORTS GENERATOR DATA
    """
    if generatedReport is not None:
        st.subheader("Key Metrics")
        # col1, col2, col3 = st.columns(3)  # Create a single row with two columns
        # with col1:
        #     st.metric(label="Average Glucose (mg/dL)", value=generatedReport["Average Glucose"])
        # with col2:
        #     st.metric(label="Minimum Glucose (mg/dL) ", value=generatedReport['Minimum Glucose'])
        # with col3:
        #     st.metric(label="Maximum Glucose (mg/dL) ", value=generatedReport['Maximum Glucose'])

        # col4, col5 = st.columns(2)  # Create a single row with two columns
        # with col4:
        #     st.metric(label="Coefficient of Variation (%)", value=generatedReport["Glucose Variability Metrics"]['Coefficient of Variation (CV)'])
        # with col5:
        #     st.metric(label="Glucose Management Indicator (%)", value=generatedReport["Glucose Variability Metrics"]['Glucose Management Indicator (GMI)'])

        # col6,col7,col8 = st.columns(3)  # Create a single row with two columns
        # with col6:
        #     st.metric(label="Time in Range (%)", value=generatedReport["Time in Range Metrics"]['Target (70-180 mg/dL)'])
        # with col7:
        #     st.metric(label="Time Below Range (%)", value=generatedReport["Time in Range Metrics"]['Low (<70 mg/dL)'])
        # with col8:
        #     st.metric(label="Time Above Range (%)", value=generatedReport["Time in Range Metrics"]['High (>180 mg/dL)'])
    # else:
    #     st.warning("No data available to display metrics.")


def display_plot():
    """
    Handles the creation and refreshing of the line chart.
    WILL BE REDONE LATER WITH THINGSPEAK DATA
    """
    plot_placeholder = st.empty()
    df = read_json_from_thingspeak(0)  # Fetch data from Thingspeak channel
    df['field1'] = pd.to_numeric(df['field1'], errors='coerce')  # Convert field1 to numeric
    plot_placeholder.line_chart(data = df,x ='created_at',y = "field1", x_label="time")  # Display line chart with the DataFrame

    if st.button("Refresh Plot"):
        plot_placeholder.empty()
        st.write("Refreshing plot...")
        df = read_json_from_thingspeak(0)
        df['field1'] = pd.to_numeric(df['field1'], errors='coerce')  # Convert field1 to numeric
        #df['created_at'] = pd.to_datetime(df['created_at'])
        plot_placeholder.line_chart(data = df,x ='created_at',y = "field1", x_label="time")

def main_dash(patientID = 0, authenticator = None):
    """
    Main function to run the dashboard.
    """
    userName = st.session_state['username']
    #patientID = username_to_id(userName)  # Convert username to patient ID

    authenticator.logout_button() 
    authenticator.reset_password_button() 
    header(userName)

    last_glucose_level = read_json_from_thingspeak(0,1)["field1"][0]  # Fetch data from Thingspeak channel
    # generatedReport = requests.get(f"")
    display_metrics({"glucose": float(last_glucose_level), "age": 25})

    display_plot() 

# def username_to_id(userName):
#     """
#     Convert username to patient ID.
#     """
#     for patient in patientList:
#         if patient['userName'] == userName:
#             return patient['patientID']
#     st.error("User not found in the catalog.")
#     return None

if __name__ == "__main__":
    st.set_page_config(page_title="Dashboard", layout="wide")
    authenticator = GlucoseIoTAuth("config.yaml")
    authenticator.login_feature() 
    if not st.session_state.get('authentication_status'):
        st.stop()  # Stop execution if not authenticated

    rest_worker = Dashboard_REST_Worker()
    # Start the REST worker (CherryPy server)
    #Standard configuration to serve the url "localhost:8080"
    conf={
    '/':{
    'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
    'tools.sessions.on':True
    }
    }
    cherrypy.tree.mount(rest_worker,'/',conf)
    cherrypy.config.update({'server.socket_port':8090})
    cherrypy.engine.start()

    main_dash(authenticator= authenticator)  # Run the main dashboard function
