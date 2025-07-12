Our Smart Glucose Monitor system helps people with Type 1 Diabetes manage their blood sugar. These Telegram Bots are like the "front door" to that system, making it easy to:
✨ What Can They Do?
Patient's Bot: This bot is for the person managing their glucose levels. Get important messages and send information about their meals.
       - Talk to the System: You can send messages to our system directly from Telegram.
       - Get Alerts: The bot will tell you if your blood sugar is too high or too low, and even suggest how much insulin you might need.
       - Tell Us About Meals: You can tell the bot if you're eating before or after a meal. This helps the system give better insulin advice.

Doctor's Bot: This bot is for the doctor managing their patients. Check on their patients, adjust settings, and add new patients.
       - Check Patient Info: Doctors can see and update their patients' glucose data and settings. Ask for reports about a patient's glucose history.
       - Adjust Settings: Doctors can change things like the "normal" glucose levels for a patient.
       - Add New Patients: When a new patient joins, the doctor can add them to the system through the bot, including their details like age, name, and target glucose levels.
       - See Patient Status: Doctors can keep an eye on how their patients are doing. See live updates on patient signals.

📡 How Do They Talk to the System?
Our bots talk to the main glucose monitoring system in two main ways, like sending different types of messages:
"Ask and Answer" (REST): This is like asking a question and getting an immediate reply. Doctors use this to change settings or add new patients.
"Broadcast News" (MQTT): This is like shouting news for anyone who wants to hear. Patients get alerts this way.

When a bot first starts, it asks a special "Catalog" service for all the necessary addresses and topics it needs to talk to the other parts of the system.

🛠️ How to Set Them Up
Telegram Bot Token: A special code from Telegram that gives the bot its identity.
System Access: Our bots need to know where the other parts of our system are located (like the "Catalog" and "Message Broker").
Configuration Files: We use special text files (like config_patient_bot.json) to store important details like the Telegram Bot Token and system addresses. This way, we don't hardcode sensitive info directly into the code.

