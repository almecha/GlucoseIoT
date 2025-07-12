# Assuming you have a Telegram Application and handlers set up for the Doctor's Bot
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, CallbackContext
from telegram import Update # Keep this if you're using Update in your function signatures
import requests
import json

# Define states for conversation if using a multi-step registration (recommended for complex inputs)
PATIENT_ID, NAME, AGE, TARGET_GLUCOSE_NORMAL, ... = range(5)

class DoctorTelegramBot:
    def __init__(self, catalog_url, token):
        self.catalog_url = catalog_url
        self.application = Application.builder().token(token).build()

        # ConversationHandler for multi-step patient registration
        self.application.add_handler(ConversationHandler(
            entry_points=[CommandHandler('register_patient', self._start_register_patient)],
            states={
                PATIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_patient_id)],
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_name)],
                AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_age)],
                # ... other states for glucose levels, insulin, etc.
                # Example: TARGET_GLUCOSE_NORMAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_target_glucose_normal)],
                # ...
            },
            fallbacks=[CommandHandler('cancel', self._cancel_register_patient)],
        ))
        self.application.add_handler(CommandHandler('start', self._start_command)) # Simple start command

    async def _start_command(self, update: Update, context: CallbackContext):
        await update.message.reply_text("Hello Doctor! Use /register_patient to add a new patient.")

    async def _start_register_patient(self, update: Update, context: CallbackContext):
        context.user_data['new_patient'] = {} # Initialize data storage for new patient
        await update.message.reply_text("Let's register a new patient. Please enter the Patient ID (Sensor ID):")
        return PATIENT_ID

    async def _get_patient_id(self, update: Update, context: CallbackContext):
        patient_id = update.message.text
        if not patient_id:
            await update.message.reply_text("Patient ID cannot be empty. Please try again.")
            return PATIENT_ID # Stay in this state
        
        context.user_data['new_patient']['userID'] = patient_id
        context.user_data['new_patient']['role'] = "Patient" # Fixed role
        context.user_data['new_patient']['patient_information'] = {}
        context.user_data['new_patient']['threshold_parameters'] = {}

        await update.message.reply_text("Now, please enter the patient's name:")
        return NAME

    async def _get_name(self, update: Update, context: CallbackContext):
        name = update.message.text
        context.user_data['new_patient']['userName'] = name
        context.user_data['new_patient']['patient_information']['name'] = name # Redundant but as per your structure

        await update.message.reply_text("Please enter the patient's age:")
        return AGE

    async def _get_age(self, update: Update, context: CallbackContext):
        age_str = update.message.text
        try:
            age = int(age_str)
            context.user_data['new_patient']['patient_information']['age'] = age
            # ... continue prompting for other fields
            await update.message.reply_text("Age recorded. Now, please enter the target normal glucose level:")
            # return TARGET_GLUCOSE_NORMAL # Return next state
            
            # --- For demonstration, let's assume we have all data after age ---
            # In a real scenario, you'd prompt for ALL fields
            context.user_data['new_patient']['threshold_parameters'] = {
                "target_glucose_level_normal": 100, # Placeholder values
                "target_glucose_level_excersise_premeal": 90,
                "target_glucose_level_excersise_postmeal": 120,
                "max_daily_amount_insulin": 50
            }
            
            await self._send_patient_to_catalog(update, context) # Call registration
            return ConversationHandler.END # End conversation
        except ValueError:
            await update.message.reply_text("Invalid age. Please enter a number:")
            return AGE # Stay in this state

    async def _send_patient_to_catalog(self, update: Update, context: CallbackContext):
        patient_data = context.user_data['new_patient']
        catalog_users_url = f"{self.catalog_url}/users"
        
        try:
            response = requests.post(catalog_users_url, json=patient_data)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            await update.message.reply_text(
                f"✅ Patient '{patient_data['userName']}' (ID: {patient_data['userID']}) successfully registered!\n"
                "Please instruct the patient to open their Patient Telegram Bot and send the `/start` command to link their account and enable alerts."
            )
            print(f"Doctor Bot: Registered patient {patient_data['userID']} to Catalog.")
        except requests.exceptions.RequestException as e:
            await update.message.reply_text(f"❌ Failed to register patient: {e}\n"
                                          "Please check the Catalog service and try again.")
            print(f"Doctor Bot: Error registering patient {patient_data['userID']}: {e}")
        finally:
            context.user_data.pop('new_patient', None) # Clean up user data
            
    async def _cancel_register_patient(self, update: Update, context: CallbackContext):
        await update.message.reply_text("Patient registration cancelled.")
        context.user_data.pop('new_patient', None)
        return ConversationHandler.END

    def run(self):
        print("Doctor Telegram Bot: Starting polling...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    # You would load these from a config file for the Doctor's Bot
    DOCTOR_BOT_TOKEN = "YOUR_DOCTOR_TELEGRAM_BOT_TOKEN" # This is a DIFFERENT token from the Patient Bot!
    CATALOG_URL = "http://catalog:9080" 

    bot = DoctorTelegramBot(CATALOG_URL, DOCTOR_BOT_TOKEN)
    bot.run()
