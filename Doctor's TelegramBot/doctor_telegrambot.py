# this code connects to Telegram, and allows a doctor to register a Patient to the catalog

import logging
import requests
import json
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Define conversation states for patient registration
(
    PATIENT_ID_STATE,
    SENSOR_ID_STATE,
    NAME_STATE,
    AGE_STATE,
    TARGET_GLUCOSE_NORMAL_STATE,
    TARGET_GLUCOSE_EXERCISE_PRE_STATE,
    TARGET_GLUCOSE_EXERCISE_POST_STATE,
    MAX_DAILY_INSULIN_STATE,
) = range(8) # 8 distinct states for the conversation flow


class DoctorTelegramBot:
    def __init__(self, catalog_url: str, telegram_token: str):
        self.catalog_url = catalog_url
        self.telegram_token = telegram_token
        # Build the Telegram bot application
        self.application = ApplicationBuilder().token(self.telegram_token).build()

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Sends a welcome message when the command /start is issued."""
        await update.message.reply_text(
            "Hello Doctor! I'm your assistant bot. Use /register_patient to add a new patient."
        )

    async def _register_patient_start(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Starts the patient registration conversation. Asks for Patient ID."""
        await update.message.reply_text(
            "Okay, let's register a new patient. "
            "Please enter the **Patient ID** (e.g., `patient_001`). This ID must be unique:"
        )
        # Initialize a dictionary to store temporary patient data during the conversation
        context.user_data["temp_patient_data"] = {}
        return PATIENT_ID_STATE

    async def _get_patient_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receives patient ID, stores it, and asks for sensor ID."""
        patient_id = update.message.text.strip()
        if not patient_id:
            await update.message.reply_text("Patient ID cannot be empty. Please enter a valid Patient ID:")
            return PATIENT_ID_STATE

        context.user_data["temp_patient_data"]["userID"] = patient_id
        await update.message.reply_text(
            "Thank you. Now, please enter the **Sensor ID** associated with this patient (e.g., `sensor_A123`):"
        )
        return SENSOR_ID_STATE

    async def _get_sensor_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receives sensor ID, stores it, and asks for patient name."""
        sensor_id = update.message.text.strip()
        if not sensor_id:
            await update.message.reply_text("Sensor ID cannot be empty. Please enter a valid Sensor ID:")
            return SENSOR_ID_STATE

        # Store connected_devices as a list, even if it's just one sensor for now
        context.user_data["temp_patient_data"]["connected_devices"] = [sensor_id]
        await update.message.reply_text("Great. What is the patient's **Name**?")
        return NAME_STATE

    async def _get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receives patient name, stores it, and asks for age."""
        name = update.message.text.strip()
        if not name:
            await update.message.reply_text("Patient name cannot be empty. Please enter the patient's Name:")
            return NAME_STATE

        context.user_data["temp_patient_data"]["userName"] = name
        await update.message.reply_text("And what is the patient's **Age**? (e.g., `30`)")
        return AGE_STATE

    async def _get_age(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Receives patient age, validates it, stores it, and asks for normal glucose target."""
        age_str = update.message.text.strip()
        try:
            age = int(age_str)
            if age <= 0:
                raise ValueError("Age must be a positive number.")
            # Store age under 'user_information' as per Catalog structure
            context.user_data["temp_patient_data"]["user_information"] = {"age": age}
            await update.message.reply_text(
                "Please enter the patient's **Target Glucose Level (Normal)** (e.g., `100` mg/dL):"
            )
            return TARGET_GLUCOSE_NORMAL_STATE
        except ValueError:
            await update.message.reply_text("Invalid age. Please enter a numerical value for age (e.g., `30`):")
            return AGE_STATE

    async def _get_target_glucose_normal(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receives normal glucose target, validates it, stores it, and asks for pre-exercise target."""
        glucose_normal_str = update.message.text.strip()
        try:
            glucose_normal = float(glucose_normal_str)
            if glucose_normal <= 0:
                raise ValueError("Glucose level must be a positive number.")
            # Use setdefault to initialize 'threshold_parameters' if it doesn't exist
            context.user_data["temp_patient_data"].setdefault("threshold_parameters", {})[
                "target_glucose_level_normal"
            ] = glucose_normal
            await update.message.reply_text(
                "Please enter the patient's **Target Glucose Level (Pre-Exercise Meal)** (e.g., `120` mg/dL):"
            )
            return TARGET_GLUCOSE_EXERCISE_PRE_STATE
        except ValueError:
            await update.message.reply_text(
                "Invalid value. Please enter a numerical value for normal glucose target (e.g., `100`):"
            )
            return TARGET_GLUCOSE_NORMAL_STATE

    async def _get_target_glucose_exercise_pre(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receives pre-exercise glucose target, validates it, stores it, and asks for post-exercise target."""
        glucose_pre_str = update.message.text.strip()
        try:
            glucose_pre = float(glucose_pre_str)
            if glucose_pre <= 0:
                raise ValueError("Glucose level must be a positive number.")
            context.user_data["temp_patient_data"].setdefault("threshold_parameters", {})[
                "target_glucose_level_excersise_premeal"
            ] = glucose_pre
            await update.message.reply_text(
                "Please enter the patient's **Target Glucose Level (Post-Exercise Meal)** (e.g., `90` mg/dL):"
            )
            return TARGET_GLUCOSE_EXERCISE_POST_STATE
        except ValueError:
            await update.message.reply_text(
                "Invalid value. Please enter a numerical value for pre-exercise glucose target (e.g., `120`):"
            )
            return TARGET_GLUCOSE_EXERCISE_PRE_STATE

    async def _get_target_glucose_exercise_post(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receives post-exercise glucose target, validates it, stores it, and asks for max daily insulin."""
        glucose_post_str = update.message.text.strip()
        try:
            glucose_post = float(glucose_post_str)
            if glucose_post <= 0:
                raise ValueError("Glucose level must be a positive number.")
            context.user_data["temp_patient_data"].setdefault("threshold_parameters", {})[
                "target_glucose_level_excersise_postmeal"
            ] = glucose_post
            await update.message.reply_text(
                "Finally, enter the patient's **Max Daily Amount of Insulin** (e.g., `50` units):"
            )
            return MAX_DAILY_INSULIN_STATE
        except ValueError:
            await update.message.reply_text(
                "Invalid value. Please enter a numerical value for post-exercise glucose target (e.g., `90`):"
            )
            return TARGET_GLUCOSE_EXERCISE_POST_STATE

    async def _get_max_daily_insulin(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> int:
        """Receives max daily insulin, validates it, stores it, and finalizes registration by sending to Catalog."""
        insulin_str = update.message.text.strip()
        try:
            max_insulin = float(insulin_str)
            if max_insulin <= 0:
                raise ValueError("Insulin amount must be a positive number.")
            context.user_data["temp_patient_data"].setdefault("threshold_parameters", {})[
                "max_daily_amount_insulin"
            ] = max_insulin

            # Add static patient role and initial telegram_chat_id (will be updated by patient bot)
            context.user_data["temp_patient_data"]["role"] = "Patient"
            context.user_data["temp_patient_data"]["telegram_chat_id"] = None

            # Prepare the complete patient data payload for the Catalog
            patient_data = context.user_data["temp_patient_data"]

            # Log the data being sent (for debugging)
            logger.info(f"Attempting to register patient with data: {json.dumps(patient_data, indent=2)}")

            # Send data to the Catalog via a POST request
            try:
                # Ensure the URL is correctly formatted for the /users endpoint
                response = requests.post(f"{self.catalog_url}/users", json=patient_data)
                response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

                await update.message.reply_text(
                    f"Patient '{patient_data['userName']}' (ID: {patient_data['userID']}) registered successfully in the Catalog!"
                )
                logger.info(f"Successfully registered patient: {patient_data['userID']}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Error registering patient with Catalog: {e}")
                error_message = (
                    "Failed to register patient in the Catalog. "
                    "This might be due to an invalid Catalog URL, network issues, or a duplicate Patient ID. "
                    "Please check the Catalog service and ensure the Patient ID is unique. "
                    f"Error details: {e}"
                )
                await update.message.reply_text(error_message)

            # Clear temporary data for the next conversation
            context.user_data.clear()
            return ConversationHandler.END
        except ValueError:
            await update.message.reply_text(
                "Invalid value. Please enter a numerical value for max daily insulin (e.g., `50`):"
            )
            return MAX_DAILY_INSULIN_STATE

    async def _cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text(
            "Patient registration cancelled.", reply_markup=ReplyKeyboardRemove()
        )
        # Clear any partial data from the cancelled conversation
        context.user_data.clear()
        return ConversationHandler.END

    async def _fallback_invalid_input(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handles any message that doesn't match the current state's expected input."""
        await update.message.reply_text(
            "Sorry, I didn't understand that. Please provide valid input for the current step or use /cancel to stop."
        )

    def run(self):
        """Sets up handlers and starts the bot's polling."""
        self.application.add_handler(CommandHandler("start", self._start_command))

        # Conversation Handler for patient registration
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("register_patient", self._register_patient_start)],
            states={
                PATIENT_ID_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_patient_id)
                ],
                SENSOR_ID_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_sensor_id)
                ],
                NAME_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_name)
                ],
                AGE_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_age)
                ],
                TARGET_GLUCOSE_NORMAL_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_target_glucose_normal)
                ],
                TARGET_GLUCOSE_EXERCISE_PRE_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_target_glucose_exercise_pre)
                ],
                TARGET_GLUCOSE_EXERCISE_POST_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_target_glucose_exercise_post)
                ],
                MAX_DAILY_INSULIN_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self._get_max_daily_insulin)
                ],
            },
            fallbacks=[
                CommandHandler("cancel", self._cancel_command),
                # If any message doesn't match a state handler, use this fallback
                MessageHandler(filters.ALL & ~filters.COMMAND, self._fallback_invalid_input),
            ],
        )

        self.application.add_handler(conv_handler)

        logger.info("Doctor Telegram Bot: Starting polling...")
        # Run the bot until the user presses Ctrl-C or the process receives SIGINT, SIGTERM or SIGABRT
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Load configuration from settings.json
    try:
        with open("settings.json", "r") as f:
            config = json.load(f)
        bot_token = config["telegram_token"]
        catalog_url = config["catalog_url"]
    except FileNotFoundError:
        logger.error(
            "Error: 'settings.json' not found. "
            "Please create it in the same directory as this script. "
            "It should contain 'telegram_token' and 'catalog_url'."
        )
        exit(1)
    except KeyError as e:
        logger.error(
            f"Error: Missing key in 'settings.json': {e}. "
            "Ensure 'telegram_token' and 'catalog_url' are present."
        )
        exit(1)
    except json.JSONDecodeError:
        logger.error("Error: 'settings.json' contains invalid JSON. Please check its content.")
        exit(1)

    # Create and run the DoctorTelegramBot instance
    doctor_bot = DoctorTelegramBot(catalog_url, bot_token)
    doctor_bot.run()
