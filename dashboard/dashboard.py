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
import atexit
import json
import threading
import yaml
import requests
import pandas as pd
import cherrypy
import streamlit as st
import streamlit_authenticator as st_auth
from auth import GlucoseIoTAuth
import os
import logging
import time
import datetime
from datetime import datetime


# catalog = json.load(open('../catalog.json', encoding='utf-8'))
# patientList = catalog["patientsList"]
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

NUMBER_OF_ENTRIES_PER_REQUEST = 100
BASE_URL = "https://api.thingspeak.com/channels"


def user_api_keys(patient_id):
    """
    To extract user API keys from the catalog.
    """
    global catalog_url
    logger.info(f"Fetching API keys for patient ID: {patient_id}")
    response = requests.get(f"{catalog_url}/patients", params={"userID": patient_id})
    logger.info(f"Catalog response status: {response.status_code}")
    if response.status_code == 200:
        user_data = response.json()
        if user_data and "userID" in user_data:
            api_key = user_data["thingspeak_info"]["apikeys"][0]
            channel_id = user_data["thingspeak_info"]["channel"]
            logger.info(f"Successfully retrieved API key and channel ID for patient {patient_id}")
            return api_key, channel_id
        else:
            logger.warning(f"User not found in catalog for patient ID: {patient_id}")
            st.error("User not found in the catalog.")
    return None


@cherrypy.expose
class Dashboard_REST_Worker(object):
    def __init__(self):
        self.config_file = yaml.safe_load(open('config.yaml'))
        self.catalog_url = catalog_url
        self.CONFIG_PATH = 'config.yaml'
        self.service_id = service_id
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.ensure_catalog_connection()
        self.register_service()
        if not self.ensure_catalog_connection():
            logger.error("Failed to connect to Catalog service during initialization.")
        if not self.register_service():
            logger.error("Failed to register service during initialization.")
        
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
            "serviceID": service_id,
            "REST_endpoint": rest_endpoint,   #check port
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
    
    def POST(self, *uri, **params):
        if len(uri) == 0:
            return "No arguments provided"
        
        elif uri[0] ==  'dashboard' and uri[1] == 'register':
            try:
                body = json.loads(cherrypy.request.body.read().decode("utf-8"))
                logger.info(f"Received registration request: {body}")
            except json.JSONDecodeError:
                logger.error("Invalid JSON body in registration request")
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
                    st_auth.Hasher.hash_passwords(self.config_file['credentials'])
                    logger.info(f"Successfully updated user {username} in config")
                return json.dumps({"status": "ok"}).encode("utf-8")
            else:
                logger.error("Invalid username or fields in registration request")
                cherrypy.response.status = 400
                return json.dumps({"error": "Invalid 'username' or 'fields'"}).encode("utf-8")

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
    logger.info(f"Reading data from Thingspeak for patient {patientID}")

    read_api_key, channel_id = user_api_keys(patientID)
    print("Read API Key:", read_api_key)
    logger.info(f"Read API Key: {read_api_key}, Channel ID: {channel_id}")
    if not read_api_key or not channel_id:
        logger.error("Missing API key or channel ID for Thingspeak")
        return None
    url = f"{BASE_URL}/{channel_id}/fields/1.json?api_key={read_api_key}&results={number_of_entries}"
    print("Thingspeak URL:", url)
    logger.info(f"Thingspeak URL: {url}")
    try:
        response = requests.get(url, timeout=10)  # Send GET request to the URL
        logger.info(f"Thingspeak response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()  # Parse JSON response
            logger.info(f"Successfully fetched {len(data.get('feeds', []))} entries from Thingspeak")
            df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
            return df
        else:
            logger.warning(f"Failed to fetch data from Thingspeak. Status code: {response.status_code}")
            logger.warning(f"Response text: {response.text}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching data from Thingspeak: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error reading from Thingspeak: {str(e)}")
    
    return None


# "threshold_parameters": {
#                 "target_glucose_level_normal": 100.0,
#                 "target_glucose_level_excersise_premeal": 90.0,
#                 "target_glucose_level_excersise_postmeal": 200.0,
#                 "max_daily_amount_insulin": 40.0,
#                 "low_threshold": 80.0,
#                 "extremely_low_threshold": 54.0,
#                 "fasting_threshold": 160.0,
#                 "severe_hyperglycemia_threshold": 240.0,
#                 "insuline_resistence": 0
#             }

def display_user_tresholds():
    patient_id = st.session_state.get('patientID', 0)
    logger.info(f"Fetching threshold parameters for patient {patient_id}")
    try:
        response = requests.get(f"{catalog_url}/patients", params={"userID": patient_id}, timeout=10)
        logger.info(f"Threshold fetch response status: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            logger.info(f"User data for thresholds: {user_data}")
            
            if user_data and "threshold_parameters" in user_data:
                thresholds = user_data["threshold_parameters"]
                st.subheader("Your Glucose Thresholds")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric(label="Target Glucose Level (Normal)", value=f"{thresholds['target_glucose_level_normal']} mg/dL")
                    st.metric(label="Target Glucose Level (Pre-meal Exercise)", value=f"{thresholds['target_glucose_level_excersise_premeal']} mg/dL")
                    st.metric(label="Target Glucose Level (Post-meal Exercise)", value=f"{thresholds['target_glucose_level_excersise_postmeal']} mg/dL")
                    st.metric(label="Max Daily Amount of Insulin", value=f"{thresholds['max_daily_amount_insulin']} units")
                with col2:
                    st.metric(label="Low Threshold", value=f"{thresholds['low_threshold']} mg/dL")
                    st.metric(label="Extremely Low Threshold", value=f"{thresholds['extremely_low_threshold']} mg/dL")
                    st.metric(label="Fasting Threshold", value=f"{thresholds['fasting_threshold']} mg/dL")
                    st.metric(label="Severe Hyperglycemia Threshold", value=f"{thresholds['severe_hyperglycemia_threshold']} mg/dL")
            else:
                logger.warning("No threshold parameters found in user data")
                st.warning("No threshold parameters found for the user.")
        else:
            logger.warning(f"Failed to fetch threshold parameters. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching thresholds: {str(e)}")
        st.error("Error connecting to catalog service for thresholds")
    except Exception as e:
        logger.error(f"Unexpected error fetching thresholds: {str(e)}")
        st.error(f"Error fetching threshold parameters: {str(e)}")

# CHECK THE REPORT AND ADAPT THE DASHVOARD TO IT
def display_metrics(generatedReport):
    """
    To display relevant metrics on the dashboard.
    Called on page refresh.
    WILL BE REDONE LATER WITH REPORTS GENERATOR DATA
    """
    logger.info(f"Displaying metrics from report: {generatedReport is not None}")
    if generatedReport is not None:
        st.subheader("Key Metrics")
        col1, col2, col3 = st.columns(3)  # Create a single row with two columns
        with col1:
            st.metric(label="Average Glucose (mg/dL)", value=generatedReport["Average Glucose"])
        with col2:
            st.metric(label="Minimum Glucose (mg/dL) ", value=generatedReport['Minimum Glucose'])
        with col3:
            st.metric(label="Maximum Glucose (mg/dL) ", value=generatedReport['Maximum Glucose'])

        col4, col5, col6 = st.columns(3)  # Create a single row with two columns
        with col4:
            st.metric(label="Coefficient of Variation (%)", value=generatedReport["Glucose Variability Metrics"]['Coefficient of Variation (CV)'])
        with col5:
            st.metric(label="Glucose Management Indicator (%)", value=generatedReport["Glucose Variability Metrics"]['Glucose Management Indicator (GMI)'])

        col7,col8,col9 = st.columns(3)  # Create a single row with two columns
        with col6:
            st.metric(label="Time in Range (%)", value=generatedReport["Time in Range Metrics"]['Target (70-180 mg/dL)'])
        with col7:
            st.metric(label="Time Below Range (%)", value=generatedReport["Time in Range Metrics"]['Low (<70 mg/dL)'])
        with col8:
            st.metric(label="Time Above Range (%)", value=generatedReport["Time in Range Metrics"]['High (>180 mg/dL)'])
        with col9:
            st.metric(label="Last Glucose Level (mg/dL)", value=generatedReport["Last Glucose Level"])
    else:
        st.warning("No data available to display metrics.")


def display_plot():
    """
    Handles the creation and refreshing of the line chart.
    WILL BE REDONE LATER WITH THINGSPEAK DATA
    """
    logger.info("Displaying plot")
    plot_placeholder = st.empty()
    patient_id = st.session_state.get('patientID', 0)
    df = read_json_from_thingspeak(patient_id)  # Fetch data from Thingspeak channel
    if df is None or df.empty or 'field1' not in df:
        st.warning("No glucose data available yet.")
        return
    df['field1'] = pd.to_numeric(df['field1'], errors='coerce')  # Convert field1 to numeric

    plot_placeholder.line_chart(data = df,x ='created_at',y = "field1", x_label="time")  # Display line chart with the DataFrame

    if st.button("Refresh Plot"):
        plot_placeholder.empty()
        st.write("Refreshing plot...")
        df = read_json_from_thingspeak(st.session_state["patientID"])  # Fetch updated data
        df['field1'] = pd.to_numeric(df['field1'], errors='coerce')  # Convert field1 to numeric
        #df['created_at'] = pd.to_datetime(df['created_at'])
        plot_placeholder.line_chart(data = df,x ='created_at',y = "field1", x_label="time")


def main_dash(patientID = 0, authenticator = None):
    """
    Main function to run the dashboard.
    """
    global catalog_url, reports_url
    
    userName = st.session_state['username']
    patient_id = username_to_id(userName)
    st.session_state['patientID'] = patient_id
    print("Patient ID:", patient_id)
    logger.info(f"Starting dashboard for user: {userName}")

    authenticator.logout_button() 
    authenticator.reset_password_button() 
    header(userName)

    df = read_json_from_thingspeak(st.session_state['patientID'], 1)
    if df is None or df.empty or 'field1' not in df:
        st.warning("No glucose data available yet.")
        last_glucose_level = None
    else:
        df['field1'] = pd.to_numeric(df['field1'], errors='coerce')
        df = df.dropna(subset=['field1'])
        last_glucose_level = df['field1'].iloc[0] if not df.empty else None  
    logger.info(f"Attempting to connect to reports generator at: {reports_url}")
    logger.info(f"Request URL: {reports_url}/generate_report?patientID={st.session_state['patientID']}")
    
    try:
        generatedReport = requests.get(
            f"{reports_url}/generate_report?patientID={st.session_state['patientID']}",
            timeout=5
        )
        logger.info(f"Report generator response status: {generatedReport.status_code}")
        logger.info(f"Report generator response content: {generatedReport.text}")
        if generatedReport.status_code == 200:
            display_metrics(generatedReport.json())
        else:
            st.warning(f"Report generator responded with status: {generatedReport.status_code}")
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to reports generator service")
    except requests.exceptions.Timeout:
        st.warning("Report generator timeout")
    except Exception as e:
        st.error(f"Error fetching report: {e}")
    
    display_user_tresholds()

    display_plot() 


# Method to convert the username to patient ID
def username_to_id(userName):
    """
    Convert username to patient ID.
    """
    global catalog_url
    try: 
        response = requests.get(f"{catalog_url}/patients", params={"username": userName})
        if response.status_code == 200:
            user_data = response.json()
            if user_data and "userID" in user_data:
                return user_data["userID"]
            else:
                st.error("User not found in the catalog.")
    except Exception as e:
        st.error(f"Error connecting to catalog: {e} - username to id")
    return None

@st.cache_resource
def start_cherrypy_once():
    # Mount your app before starting
    logger.info("Starting CherryPy REST server")
    rest_worker = Dashboard_REST_Worker()
    
    conf = {
        '/': {
            'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on': True,
        }
    }
    cherrypy.tree.mount(rest_worker, '/', conf)

    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',   # or '127.0.0.1'
        'server.socket_port': 8091,
        'engine.autoreload.on': False,     # avoid CherryPy reload in Streamlit
    })

    # Start engine only if not already running
    if not cherrypy.engine.state == cherrypy.engine.states.STARTED:
        cherrypy.engine.start()

        # Run the blocking loop in a background thread so Streamlit UI stays responsive
        t = threading.Thread(target=cherrypy.engine.block, daemon=True)
        t.start()

        # Clean shutdown when Streamlit process exits
        atexit.register(lambda: cherrypy.engine.exit())

    return True

if __name__ == "__main__":
    
    global catalog_url, reports_url, service_id, rest_endpoint
    logger.info("Dashboard application starting")
    settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_file_path, 'r') as f:
            settings = json.load(f)
        
        
        catalog_url = settings.get("catalogURL")
        reports_url = settings.get("reportsURL")
        dashboard_url = settings.get("dashboardURL")
        service_info = settings.get("serviceInfo", {})
        service_id = service_info.get("serviceID", "Dashboard")
        rest_endpoint = service_info.get("REST_endpoint", dashboard_url)
        
        logger.info(f"Catalog URL: {catalog_url}")
        logger.info(f"Reports URL: {reports_url}")
    
    except Exception as e:
        print(f"Error reading settings: {e}")
        exit(1)
        
    # Verify connection to Catalog service    
    try: 
        response = requests.get(f"{catalog_url}/config", timeout=5)
        if response.status_code == 200:
            logger.info("Successfully connected to Catalog service")
        else:
            logger.error(f"Failed to connect to Catalog service: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"Error connecting to Catalog service: {str(e)}")
        exit(1)
        
    # Set up Streamlit page configuration
    st.set_page_config(page_title="Dashboard", layout="wide")
    
    # Start CherryPy REST server (only once across reruns)
    start_cherrypy_once()
    authenticator = GlucoseIoTAuth("config.yaml")
    authenticator.login_feature() 
    if not st.session_state.get('authentication_status'):
        st.stop()  # Stop execution if not authenticated

    main_dash(authenticator= authenticator)  # Run the main dashboard function
