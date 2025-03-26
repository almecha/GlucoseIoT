# Description: This file contains the code for the dashboard of the GlucoseIoT project.
# The dashboard will display the glucose levels of the patient in real-time and the time series
# data will be fetched from the Thingspeak channel. The dashboard will be built using Streamlit.

# QUESTIONS: 
# 1. How to implement the user feature? (So each patient have the access only to his dashboard -> Authentication)
import streamlit as st
import json
import requests
import pandas as pd

catalog = json.load(open('../catalog.json'))
patientList = catalog["patientsList"]

NUMBER_OF_ENTRIES_PER_REQUEST = 100
THINGSPEAK_USER_API_KEY = "TO BE DONE LATER"
THINGSPEAK_CHANNEL_API_KEY = patientList[0]["serviceDetails"]["Thingspeak"]["channelAPIkey"]

def header():
    st.title("GlucoseIoT Dashboard")
    st.write("This dashboard will display the glucose levels of the patient in real-time.")

def read_json_from_thingspeak(channel_id):
    url = f"https://api.thingspeak.com/channels/{channel_id}/feeds.json?api_key={THINGSPEAK_USER_API_KEY}&results={NUMBER_OF_ENTRIES_PER_REQUEST}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()  # Parse JSON response
        df = pd.DataFrame(data['feeds'])  # Convert 'feeds' to DataFrame
        return df
    else:
        st.error(f"Failed to fetch data. Status code: {response.status_code}")
        return None

def display_metrics(data):
    if data is not None:
        col1, col2 = st.columns(2)  # Create a single row with two columns
        with col1:
            st.metric(label="Glucose Level (mg/dL)", value=data["glucose"])
        with col2:
            st.metric(label="Age", value=data['age'])
    else:
        st.warning("No data available to display metrics.")

if __name__ == "__main__":
    header()
    display_metrics({"glucose": 122, "age": 25})
