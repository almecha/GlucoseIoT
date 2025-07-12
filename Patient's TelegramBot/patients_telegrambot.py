# --- IMPORTS ---
import json
import requests
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler

# Import your custom MyMQTT class
from MyMQTT import MyMQTT # <--- CHANGED: Import your wrapper

class TelegramMQTTWorker:
    """
    Handles all MQTT communication for the Patient's Telegram Bot using MyMQTT wrapper.
    It subscribes to alerts and publishes meal status.
    This class now acts as the 'notifier' for the MyMQTT instance.
    """
    def __init__(self, broker_ip, broker_port, client_id, subscribe_topic, publish_topic, message_callback):
        self.broker_ip = broker_ip
        self.broker_port = broker_port
        self.client_id = client_id
        self.subscribe_topic = subscribe_topic
        self.publish_topic = publish_topic
        # message_callback is still the callback to the main bot for Telegram messages
        self.message_callback = message_callback

        # Initialize MyMQTT instance
        # 'self' (this TelegramMQTTWorker instance) is passed as the notifier,
        # so MyMQTT will call this class's 'notify' method on incoming messages.
        self.mqtt_client = MyMQTT(self.client_id, self.broker_ip, self.broker_port, self) # <--- CHANGED: Using MyMQTT

    # --- MyMQTT's 'notifier' callback ---
    # This method is called by MyMQTT.myOnMessageReceived when a message arrives.
    async def notify(self, topic: str, msg_payload_bytes: bytes): # <--- CHANGED: Renamed from _on_message and signature adapted
        """
        Processes incoming MQTT messages (e.g., alerts from Threshold Analyzer).
        The message payload is expected to be a JSON string including 'patient_id'.
        """
        print(f"MQTT Worker: Received message on topic {topic}: {msg_payload_bytes.decode()}")
        mqtt_payload_str = msg_payload_bytes.decode() # Decode bytes to string as MyMQTT passes bytes

        # Pass the full payload string to the main bot's callback
        if self.message_callback:
            await self.message_callback(mqtt_payload_str)
        else:
            print("MQTT Worker: No message_callback provided to send alert to Telegram.")

    # Note: _on_connect is no longer needed here as MyMQTT handles its own connection callback.

    def start(self):
        try:
            self.mqtt_client.start() # <--- CHANGED: Using MyMQTT's start method
            self.mqtt_client.mySubscribe(self.subscribe_topic) # <--- CHANGED: Explicitly subscribe using MyMQTT's method
            print("MQTT Worker: Attempting to connect and subscribe...")
        except Exception as e:
            print(f"MQTT Worker: Could not connect to broker: {e}")
            raise # Re-raise to indicate a critical startup failure

    def stop(self):
        if self.mqtt_client: # Added check just in case mqtt_client isn't initialized
            self.mqtt_client.stop() # <--- CHANGED: Using MyMQTT's stop method
            print("MQTT Worker: Client stopped.")

    def publish_meal_status(self, patient_id, meal_status_value):
        """Publishes the meal status to the designated MQTT topic."""
        # MyMQTT's myPublish expects a dictionary, which it then json.dumps internally.
        mqtt_payload_dict = { # <--- CHANGED: Creating a dict
            "patient_id": patient_id,
            "meal_status": meal_status_value,
            "timestamp": time.time() # Use current time for timestamp
        }
        try:
            self.mqtt_client.myPublish(self.publish_topic, mqtt_payload_dict) # <--- CHANGED: Using MyMQTT's myPublish
            print(f"MQTT Worker: Published meal status to {self.publish_topic}: {mqtt_payload_dict}")
        except Exception as e:
            print(f"MQTT Worker: Error publishing meal status: {e}")


class PatientTelegramBot:
    """
    Main class for the Patient's Telegram Bot, orchestrating Telegram and MQTT.
    Now supports multiple chat IDs by using the Catalog for persistent storage.
    """
    def __init__(self, settings_file_path):
        # Load settings
        try:
            with open(settings_file_path, 'r') as f:
                self.settings = json.load(f)
            print("Main Bot: Configuration loaded successfully.")
        except FileNotFoundError:
            print(f"Main Bot: Error: {settings_file_path} not found. Ensure it exists.")
            exit(1)
        except json.JSONDecodeError:
            print(f"Main Bot: Error: {settings_file_path} has an invalid JSON format.")
            exit(1)

        self.patient_id = self.settings.get("PATIENT_ID", "default_patient_id") # This bot instance serves THIS patient_id
        self.catalog_url = self.settings["CATALOG_URL"]
        self.service_info = {
            "service_id": self.settings["SERVICE_ID"],
            "service_type": self.settings["SERVICE_TYPE"],
            "mqtt_topics": {
                "subscribe": [self.settings["MQTT_SUBSCRIBE_TOPIC_ALERTS"]],
                "publish": [self.settings["MQTT_PUBLISH_TOPIC_MEAL_STATUS"]]
            },
            "rest_endpoints": {} # This bot instance acts as a client, not exposing REST services
        }

        # Initialize MQTT Worker
        self.mqtt_worker = TelegramMQTTWorker(
            broker_ip=self.settings["MQTT_BROKER_HOST"],
            broker_port=self.settings["MQTT_BROKER_PORT"],
            client_id=self.settings["MQTT_CLIENT_ID"],
            subscribe_topic=self.settings["MQTT_SUBSCRIBE_TOPIC_ALERTS"],
            publish_topic=self.settings["MQTT_PUBLISH_TOPIC_MEAL_STATUS"],
            message_callback=self._send_telegram_alert # This is the bridge
        )

        # Initialize Telegram Application
        self.application = Application.builder().token(self.settings["TELEGRAM_BOT_TOKEN"]).build()

        # Add Telegram Handlers
        self.application.add_handler(CommandHandler("start", self._start_command))
        self.application.add_handler(CommandHandler("meal", self._meal_command))
        self.application.add_handler(CallbackQueryHandler(self._button_callback_handler))

    # --- Methods for Telegram to send messages (used by MQTT Worker) ---
    async def _send_telegram_alert(self, mqtt_payload_str: str):
        """
        Called by the MQTT worker to send an alert to the Telegram user.
        This now dynamically fetches the chat_id from the Catalog based on patient_id.
        Expected MQTT payload: {"patient_id": "...", "alert_message": "..."}
        """
        try:
            alert_data = json.loads(mqtt_payload_str)
            target_patient_id = alert_data.get("patient_id")
            alert_message = alert_data.get("alert_message", "No specific message provided.")

            if not target_patient_id:
                print("Main Bot: MQTT alert received without a patient_id. Cannot send to specific user.")
                return

            print(f"Main Bot: Attempting to send alert for patient {target_patient_id}: {alert_message}")

            # --- FETCH CHAT_ID FROM CATALOG ---
            catalog_patient_url = f'{self.catalog_url}/users/{target_patient_id}'
            response = requests.get(catalog_patient_url)
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            patient_info = response.json()
            telegram_chat_id = patient_info.get("telegram_chat_id")

            if telegram_chat_id:
                try:
                    await self.application.bot.send_message(chat_id=telegram_chat_id, text=alert_message)
                    print(f"Main Bot: Sent Telegram alert to patient {target_patient_id} (Chat ID: {telegram_chat_id}): {alert_message}")
                except Exception as e:
                    print(f"Main Bot: Failed to send Telegram alert to patient {target_patient_id} (Chat ID: {telegram_chat_id}): {e}")
            else:
                print(f"Main Bot: Cannot send Telegram alert for patient {target_patient_id}: 'telegram_chat_id' not found in Catalog.")

        except json.JSONDecodeError:
            print(f"Main Bot: Received malformed MQTT JSON payload: {mqtt_payload_str}")
        except requests.exceptions.RequestException as e:
            print(f"Main Bot: Failed to retrieve patient info from Catalog for {target_patient_id}: {e}")
        except Exception as e:
            print(f"Main Bot: An unexpected error occurred in _send_telegram_alert: {e}")

    # --- Telegram Command Handlers (asynchronous) ---
    async def _start_command(self, update: Update, context):
        current_chat_id = update.effective_chat.id
        current_user_id = update.effective_user.id # Telegram's unique user ID

        # --- UPDATE CATALOG WITH CHAT_ID FOR THIS PATIENT ---
        # This assumes self.patient_id is the patient ID this bot instance is configured for.
        catalog_update_url = f'{self.catalog_url}/users/{self.patient_id}'
        update_payload = {"telegram_chat_id": current_chat_id}

        try:
            response = requests.put(catalog_update_url, json=update_payload)
            response.raise_for_status()
            print(f"Main Bot: Updated Catalog with chat_id {current_chat_id} for patient {self.patient_id}.")
            initial_message = (
                f"👋 Hello! I am your Smart Glucose Monitor assistant for Patient ID: **{self.patient_id}**.\n"
                "I've linked your Telegram chat to your patient record. You'll receive important alerts here.\n"
                "Use /meal to report your meal status."
            )
        except requests.exceptions.RequestException as e:
            print(f"Main Bot: Failed to update Catalog with chat_id for patient {self.patient_id}: {e}")
            initial_message = (
                f"👋 Hello! I am your Smart Glucose Monitor assistant for Patient ID: **{self.patient_id}**.\n"
                "⚠️ I could not link your Telegram chat to your patient record in the system. "
                "Please ensure your patient ID is registered and try again later."
            )

        await update.message.reply_text(initial_message)
        print(f"Main Bot: User {current_user_id} started bot. Chat ID: {current_chat_id}")

    async def _meal_command(self, update: Update, context):
        keyboard = [
            [
                InlineKeyboardButton("Pre-meal 🍽️", callback_data="meal_pre"),
                InlineKeyboardButton("Post-meal 🍎", callback_data="meal_post"),
            ],
            [
                InlineKeyboardButton("Not eating now", callback_data="meal_none"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("What is your current meal status?", reply_markup=reply_markup)
        print(f"Main Bot: User {update.effective_user.id} requested meal status.")

    async def _button_callback_handler(self, update: Update, context):
        query = update.callback_query
        await query.answer() # Acknowledge the button press to Telegram

        data = query.data
        meal_status_value = ""
        message_to_user = ""

        if data == "meal_pre":
            meal_status_value = "pre-meal"
            message_to_user = "Got it! Your 'Pre-meal' status has been recorded. 🍽️"
        elif data == "meal_post":
            meal_status_value = "post-meal"
            message_to_user = "Got it! Your 'Post-meal' status has been recorded. 🍎"
        elif data == "meal_none":
            meal_status_value = "none"
            message_to_user = "Got it! You've indicated you are not eating now."

        # Publish meal status using the MQTT Worker
        try:
            self.mqtt_worker.publish_meal_status(self.patient_id, meal_status_value)
            print(f"Main Bot: User {update.effective_user.id} reported meal status: {meal_status_value}")
        except Exception as e:
            print(f"Main Bot: Error publishing meal status via MQTT Worker: {e}")
            message_to_user += "\n⚠️ Error sending information to the system."

        await query.edit_message_text(text=message_to_user)

    # --- Catalog Communication (using requests directly in main bot class) ---
    def _register_service_with_catalog(self):
        """Registers this service with the central Catalog."""
        # The Catalog is expected to add the 'timestamp' field itself.
        # If your Catalog expects 'last_update' from the client, add it here.
        # self.service_info['last_update'] = int(time.time()) # Uncomment if Catalog requires this from client

        catalog_register_url = f'{self.catalog_url}/services'
        try:
            response = requests.post(catalog_register_url, json=self.service_info)
            response.raise_for_status() # Raises an HTTPError for bad responses (4xx or 5xx)
            print(f"Main Bot: Service '{self.service_info['service_id']}' successfully registered with Catalog.")
        except requests.exceptions.RequestException as e:
            print(f"Main Bot: Failed to register service with Catalog: {e}")
            raise # Re-raise to indicate a critical startup failure

    # --- Main Control Flow ---
    def start(self):
        # 1. Register with the Catalog (critical step)
        try:
            self._register_service_with_catalog()
        except Exception as e:
            print(f"Main Bot: Startup aborted due to Catalog registration failure: {e}")
            exit(1)

        # 2. Start the MQTT Worker
        try:
            self.mqtt_worker.start()
        except Exception as e:
            print(f"Main Bot: Startup aborted due to MQTT Worker failure: {e}")
            exit(1)

        # 3. Start the Telegram Bot polling
        print("Main Bot: Starting Telegram Bot polling...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    def stop(self):
        # Stop MQTT worker gracefully
        print("Main Bot: Stopping MQTT Worker...")
        self.mqtt_worker.stop()
        print("Main Bot: Stopped.")

# --- Main execution block ---
if __name__ == "__main__":
    # Ensure you have a 'config_patient_bot.json' file in the same directory
    # or provide the correct path.
    # IMPORTANT: The "PATIENT_ID" in this config file should match the patient
    # ID already registered by the Doctor's Bot in the Catalog.
    """
    Example content for config_patient_bot.json:
    {
      "TELEGRAM_BOT_TOKEN": "YOUR_TELEGRAM_BOT_TOKEN_HERE",
      "CATALOG_URL": "http://catalog:9080", // Use the Docker service name and port
      "MQTT_BROKER_HOST": "broker.hivemq.com", // Or your local broker's IP/hostname
      "MQTT_BROKER_PORT": 1883,
      "MQTT_CLIENT_ID": "telegram_patient_bot_1",
      "MQTT_SUBSCRIBE_TOPIC_ALERTS": "/notifications/alert",
      "MQTT_PUBLISH_TOPIC_MEAL_STATUS": "/status/meal/patient_1",
      "SERVICE_ID": "patient_telegram_bot_service",
      "SERVICE_TYPE": "user_interface",
      "PATIENT_ID": "patient_001" // <--- CRITICAL: This ties the bot instance to a specific patient
    }
    """

    bot_instance = PatientTelegramBot('config_patient_bot.json')

    try:
        print("Starting Patient Telegram Bot application...")
        bot_instance.start()
    except KeyboardInterrupt:
        print("KeyboardInterrupt received. Stopping Patient Telegram Bot.")
    except Exception as e:
        print(f"An unhandled error occurred in main execution: {e}")
    finally:
        # Ensure stop is called even if an error occurs during polling
        bot_instance.stop()
