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
import requests
import pandas as pd
import streamlit as st
from auth import GlucoseIoTAuth

catalog = json.load(open('../catalog.json', encoding='utf-8'))
patientList = catalog["patientsList"]

NUMBER_OF_ENTRIES_PER_REQUEST = 100
THINGSPEAK_USER_API_KEY = "TO BE DONE LATER"
BASE_URL = "https://api.thingspeak.com/channels"
ACCESS_CODE = "1234"

def user_api_keys(patient_id):
    """
    To extract user API keys from the catalog.
    """

    if patient_id not in range(len(patientList)):
        return "Error: Patient ID is not valid"
    
    return patientList[patient_id]["serviceDetails"]["Thingspeak"]["channelAPIkey"]

def header(userName):
    """
    Template header for the dashboard.
    """
    st.title("GlucoseIoT Dashboard")
    st.write(f"Hello, {userName} !" + " This dashboard displays your glucose levels, important metrics and time-series.")
    st.badge("GlucoseIoT", icon="🩸", color="red")

def read_json_from_thingspeak(patientID):
    """
    Read JSON data from the Thingspeak channel via REST API.
    Called on page refresh.
    """
    channel_id = user_api_keys(patientID)
    url = f"{BASE_URL}/{channel_id}/feeds.json?api_key={THINGSPEAK_USER_API_KEY}&results={NUMBER_OF_ENTRIES_PER_REQUEST}"
    response = requests.get(url, timeout=5)  # Send GET request to the URL
    
    if response.status_code == 200:
        data = response.json()  # Parse JSON response
        df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
        return df
    st.error(f"Failed to fetch data. Status code: {response.status_code}")
    return None

def display_metrics(generatedReport):
    """
    To display relevant metrics on the dashboard.
    Called on page refresh.
    WILL BE REDONE LATER WITH REPORTS GENERATOR DATA
    """
    if generatedReport is not None:
        col1, col2 = st.columns(2)  # Create a single row with two columns
        with col1:
            st.metric(label="Glucose Level (mg/dL)", value=generatedReport["glucose"])
        with col2:
            st.metric(label="Age", value=generatedReport['age'])
    else:
        st.warning("No data available to display metrics.")


def display_plot():
    """
    Handles the creation and refreshing of the line chart.
    WILL BE REDONE LATER WITH THINGSPEAK DATA
    """
    plot_placeholder = st.empty()
    df = pd.DataFrame({
        "temperature": [22.4, 22.7, 22.5],
        "humidity": [45, 46, 44]
    }, index=pd.to_datetime([
        "2025-03-28T10:00:00",
        "2025-03-28T10:01:00",
        "2025-03-28T10:02:00"
    ]))  # Create a DataFrame with dummy data

    plot_placeholder.line_chart(data=df, x_label="time")  # Display line chart with the DataFrame

    if st.button("Refresh Plot"):
        plot_placeholder.empty()
        st.write("Refreshing plot...")
        df["temperature"] = df["temperature"] + 0.1
        df["humidity"] = df["humidity"] + 0.2
        plot_placeholder.line_chart(data=df, x_label="time")

def main_dash(patientID = 0, authenticator = None):
    """
    Main function to run the dashboard.
    """
    userName = st.session_state['username']
    #patientID = username_to_id(userName)  # Convert username to patient ID

    authenticator.logout_button() 
    authenticator.reset_password_button() 
    header(userName)
    display_metrics({"glucose": 122, "age": 25})
    display_plot() 

def username_to_id(userName):
    """
    Convert username to patient ID.
    """
    for patient in patientList:
        if patient['userName'] == userName:
            return patient['patientID']
    st.error("User not found in the catalog.")
    return None

if __name__ == "__main__":
    st.set_page_config(page_title="Dashboard", layout="wide")
    authenticator = GlucoseIoTAuth("config.yaml")
    authenticator.login_feature() 
    if not st.session_state.get('authentication_status'):
        st.stop()  # Stop execution if not authenticated

    main_dash(authenticator= authenticator)  # Run the main dashboard function
