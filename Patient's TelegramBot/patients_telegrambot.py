import logging
import asyncio
import requests
import json
import os
import time
from datetime import datetime
import functools
from typing import Union

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
)
from telegram.constants import ParseMode
import httpx
from telegram.error import TelegramError
from MyMQTT import MyMQTT

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    INITIAL_PATIENT_STATE,
    GET_PATIENT_NAME,
    CONFIRM_PATIENT_LINK,
    PATIENT_MAIN_MENU,
) = range(4)

def _escape_markdown_v2(text: str) -> str:
    """Escapes characters that have special meaning in MarkdownV2."""
    special_chars = '_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def send_catalog_request_sync(method: str, endpoint: str, data: dict = None, params: dict = None, max_retries=5, retry_delay=3):
    catalog_url = os.getenv("CATALOG_URL", "http://catalog:9080")
    url = f"{catalog_url}/{endpoint}"
    
    for attempt in range(max_retries):
        logger.info(f"Attempt {attempt + 1}/{max_retries}: Sending {method} request to {url} with data: {data} and params: {params}")
        try:
            if method == "GET":
                response = requests.get(url, params=params, timeout=5)
            elif method == "POST":
                response = requests.post(url, json=data, timeout=5)
            elif method == "PUT":
                response = requests.put(url, json=data, timeout=5)
            elif method == "DELETE":
                response = requests.delete(url, params=params, timeout=5)
            else:
                raise ValueError("Unsupported HTTP method")

            response.raise_for_status()
            logger.info(f"Response from {url}: {response.status_code} - {response.text}")
            return response.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
            if attempt < max_retries - 1:
                logger.warning(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error occurred: {e.request.url!r}: {e}")
            if attempt < max_retries - 1:
                logger.warning(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                raise
        except json.JSONDecodeError:
            logger.error(f"Error decoding JSON response from {url}: {response.text}")
            if attempt < max_retries - 1:
                logger.warning(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                raise
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            if attempt < max_retries - 1:
                logger.warning(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                raise
    return None

class TelegramMQTTWorker:
    def __init__(self, broker_ip: str, broker_port: int, client_id: str, subscribe_topic: str, publish_topic: str, message_callback):
        self.broker_ip = broker_ip
        self.broker_port = broker_port
        self.client_id = client_id
        self.subscribe_topic = subscribe_topic
        self.publish_topic = publish_topic
        self.message_callback = message_callback
        self.mqtt_client = MyMQTT(self.client_id, self.broker_ip, self.broker_port, self)
        logger.info(f"MQTT Worker initialized for client {self.client_id}")

    async def notify(self, topic: str, msg_payload_bytes: bytes):
        try:
            mqtt_payload_str = msg_payload_bytes.decode()
            logger.info(f"MQTT message received on topic {topic}: {mqtt_payload_str}")
            if self.message_callback:
                await self.message_callback(mqtt_payload_str)
        except Exception as e:
            logger.error(f"MQTT Error in notify: {e}")

    def start(self):
        self.mqtt_client.start()
        time.sleep(1)
        self.mqtt_client.mySubscribe(self.subscribe_topic)
        logger.info(f"MQTT Worker started and subscribed to {self.subscribe_topic}")

    def stop(self):
        self.mqtt_client.stop()
        logger.info("MQTT Worker stopped.")

    def publish_status(self, patient_id: str, status_type: str, status_value: str):
        payload = {
            "patient_id": patient_id,
            "type": status_type,
            "value": status_value,
            "timestamp": time.time()
        }
        self.mqtt_client.myPublish(self.publish_topic, payload)
        logger.info(f"MQTT Worker: Published status to {self.publish_topic}: {payload}")

class PatientTelegramBot:
    def __init__(self, token: str, catalog_url: str, broker_ip: str, broker_port: int,
                 service_id: str, mqtt_sub_template: str, mqtt_pub_template: str, client_id_template: str):
        
        self.catalog_url = catalog_url
        self.telegram_token = token
        self.broker_ip = broker_ip
        self.broker_port = broker_port
        self.service_id = service_id
        self.mqtt_sub_template = mqtt_sub_template
        self.mqtt_pub_template = mqtt_pub_template
        self.client_id_template = client_id_template
        self.thingspeak_api_url = "https://api.thingspeak.com/update"
        self.mqtt_worker = None

        self.ensure_catalog_connection()
        self.register_service()

        self.application = Application.builder().token(self.telegram_token).build()

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start_command)],
            states={
                INITIAL_PATIENT_STATE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.ask_patient_name)
                ],
                GET_PATIENT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_patient_name)
                ],
                CONFIRM_PATIENT_LINK: [
                    CallbackQueryHandler(self.confirm_patient_link, pattern=r'^link_patient_.*$'),
                    CallbackQueryHandler(self.cancel_linking, pattern='^cancel_linking$'),
                    MessageHandler(filters.ALL, self._debug_unmatched)
                ],
                PATIENT_MAIN_MENU: [
                    CommandHandler("meal", self.meal_command),
                    CommandHandler("exercise", self.exercise_command),
                    CommandHandler("report", self.report_command),
                    CallbackQueryHandler(self.button_handler),
                    MessageHandler(filters.ALL, self._debug_unmatched)
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel_command), MessageHandler(filters.ALL, self._debug_unmatched)],
            allow_reentry=True
        )

        self.application.add_handler(conv_handler)
        logger.info("Patient Telegram Bot handlers configured.")

    def ensure_catalog_connection(self):
        max_retries = 10
        retry_delay = 3
        for attempt in range(max_retries):
            try:
                response = requests.get(f"{self.catalog_url}/config", timeout=3)
                if response.status_code == 200:
                    logger.info("Successfully connected to Catalog service.")
                    return True
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries}: Catalog not ready yet - {e}. Retrying in {retry_delay}s...")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.error("Failed to connect to Catalog service after multiple attempts.")
                    return False
        return False

    def register_service(self):
        service_info = {
            "serviceID": self.service_id,
            "REST_endpoint": "",
            "MQTT_sub": [self.mqtt_sub_template.format(PATIENT_ID="#")],
            "MQTT_pub": [self.mqtt_pub_template.format(PATIENT_ID="#")],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "description": "Telegram interface for patients"
        }
        
        max_retries = 5
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                response = requests.get(f"{self.catalog_url}/services", params={"serviceID": service_info["serviceID"]}, timeout=5)
                existing_service_list = response.json().get("services", []) if response.status_code == 200 else []

                if existing_service_list:
                    logger.info(f"Service {service_info['serviceID']} already registered in Catalog. Attempting to update timestamp.")
                    response = requests.put(f"{self.catalog_url}/services/{service_info['serviceID']}", json={"timestamp": service_info["timestamp"]}, timeout=5)
                    response.raise_for_status()
                    logger.info(f"Service {service_info['serviceID']} timestamp updated successfully.")
                    return True
                else:
                    logger.info(f"Service {service_info['serviceID']} not found in Catalog. Attempting to register.")
                    response = requests.post(f"{self.catalog_url}/services", json=service_info, timeout=5)
                    response.raise_for_status()
                    logger.info(f"Service {service_info['serviceID']} registered successfully with Catalog.")
                    return True
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 409:
                    logger.warning(f"Service {service_info['serviceID']} already exists (409 Conflict). Skipping registration.")
                    return True
                logger.error(f"HTTP error during service registration: {e.response.status_code} - {e.response.text}")
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error during service registration: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Error during service registration: {e}", exc_info=True)
            
            if attempt < max_retries - 1:
                logger.warning(f"Retrying service registration in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.error("Failed to register service after multiple attempts.")
                return False
        return False

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        chat_id = update.effective_chat.id
        context.user_data['chat_id'] = chat_id

        logger.info(f"[STATE] start_command: User {chat_id} started the bot.")

        try:
            response_data = send_catalog_request_sync("GET", "patients", params={"telegram_chat_id": chat_id})
            
            linked_patient = []
            if isinstance(response_data, list):
                linked_patient = [p for p in response_data if p.get('telegram_chat_id') == chat_id]
            
            if linked_patient:
                linked_patient = linked_patient[0]
            else:
                linked_patient = None

            if linked_patient and linked_patient.get('userID'):
                context.user_data['patient_id'] = linked_patient['userID']
                context.user_data['patient_name'] = linked_patient.get('user_information', {}).get('userName', 'Unknown')
                context.user_data['thingspeak_info'] = linked_patient.get('thingspeak_info', {})
                
                await self._initialize_mqtt_worker(context)

                await update.message.reply_text(
                    f"👋 Welcome back, {context.user_data['patient_name']}! (ID: `{context.user_data['patient_id']}`)\n"
                    "How can I help you today?",
                    parse_mode="Markdown"
                )
                return await self._send_patient_main_menu(update, context)
            else:
                await update.message.reply_text(
                    "👋 Welcome to the Patient Bot! To link your account, please enter your full patient name:"
                )
                return GET_PATIENT_NAME

        except Exception as e:
            logger.error(f"Error in start_command: {e}", exc_info=True)
            await update.message.reply_text(
                "An error occurred while checking your account. Please try again later."
            )
            return ConversationHandler.END

    async def ask_patient_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Please enter your full patient name:")
        return GET_PATIENT_NAME

    async def process_patient_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        patient_name_input = update.message.text.strip()
        logger.info(f"[STATE] process_patient_name: User entered name: {patient_name_input}")

        try:
            response_data = send_catalog_request_sync("GET", "patients")
            all_patients = response_data if isinstance(response_data, list) else []

            matching_patients = [
                p for p in all_patients 
                if p.get('user_information', {}).get('userName', '').lower() == patient_name_input.lower()
            ]

            if not matching_patients:
                await update.message.reply_text(
                    f"Patient '{patient_name_input}' not found. Please check your spelling or contact your doctor to ensure you are registered. "
                    "Please enter your full patient name again, or type /cancel."
                )
                return GET_PATIENT_NAME
            elif len(matching_patients) == 1:
                patient_data = matching_patients[0]
                context.user_data['patient_id'] = patient_data['userID']
                context.user_data['patient_name'] = patient_data.get('user_information', {}).get('userName', 'Unknown')
                context.user_data['thingspeak_info'] = patient_data.get('thingspeak_info', {})

                return await self._link_patient_account(update, context, patient_data['userID'], update.effective_chat.id)
            else:
                keyboard = []
                message_text = "Multiple patients found with that name. Please select your exact ID:\n\n"
                for patient in matching_patients:
                    patient_display_name = patient.get('user_information', {}).get('userName', 'Unknown')
                    message_text += f"- Name: {patient_display_name}, ID: `{patient.get('userID')}`\n"
                    keyboard.append([InlineKeyboardButton(patient.get('userID'), callback_data=f"link_patient_{patient.get('userID')}")])
                
                keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_linking")])
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    message_text,
                    reply_markup=reply_markup,
                    parse_mode="Markdown"
                )
                return CONFIRM_PATIENT_LINK

        except Exception as e:
            logger.error(f"Error in process_patient_name: {e}", exc_info=True)
            await update.message.reply_text(
                "An error occurred while searching for your patient account. Please try again later."
            )
            return ConversationHandler.END

    async def confirm_patient_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("link_patient_"):
            patient_id_to_link = query.data.replace("link_patient_", "")
            logger.info(f"[STATE] confirm_patient_link: User selected patient ID: {patient_id_to_link}")
            
            try:
                response_data = send_catalog_request_sync("GET", "patients", params={"userID": patient_id_to_link})
                
                patient_data_list = response_data if isinstance(response_data, list) else []
                if patient_data_list:
                    patient_data = patient_data_list[0]
                else:
                    patient_data = None

                if not patient_data:
                    await query.edit_message_text("Selected patient ID not found. Please try again or /start.")
                    return ConversationHandler.END
                
                context.user_data['patient_id'] = patient_data['userID']
                context.user_data['patient_name'] = patient_data.get('user_information', {}).get('userName', 'Unknown')
                context.user_data['thingspeak_info'] = patient_data.get('thingspeak_info', {})
                
                return await self._link_patient_account(update, context, patient_data['userID'], update.effective_chat.id)

            except Exception as e:
                logger.error(f"Error in confirm_patient_link: {e}", exc_info=True)
                await query.edit_message_text("An unexpected error occurred. Please try again.")
                return ConversationHandler.END
        else:
            await query.edit_message_text("Invalid selection. Please try again or /cancel.")
            return GET_PATIENT_NAME

    async def _link_patient_account(self, update: Update, context: ContextTypes.DEFAULT_TYPE, patient_id: str, chat_id: int) -> int:
        try:
            send_catalog_request_sync("PUT", f"patients/{patient_id}", data={"telegram_chat_id": chat_id})
            logger.info(f"Updated Catalog with chat_id {chat_id} for patient {patient_id}.")

            await self._initialize_mqtt_worker(context)

            message_target = update.callback_query.message if update.callback_query else update.message
            try:
                await message_target.edit_text(
                    f"✅ Account successfully linked! Welcome, {context.user_data['patient_name']}! (ID: `{context.user_data['patient_id']}`)\n"
                    "How can I help you today?",
                    parse_mode="Markdown"
                )
            except Exception:
                 await update.effective_chat.send_message(
                    f"✅ Account successfully linked! Welcome, {context.user_data['patient_name']}! (ID: `{context.user_data['patient_id']}`)\n"
                    "How can I help you today?",
                    parse_mode="Markdown"
                )
            return await self._send_patient_main_menu(update, context)

        except Exception as e:
            logger.error(f"Error in _link_patient_account: {e}", exc_info=True)
            error_message = "An unexpected error occurred during account linking. Please try again."
            message_target = update.callback_query.message if update.callback_query else update.message
            try:
                await message_target.edit_text(error_message)
            except Exception:
                await update.effective_chat.send_message(error_message)
            return ConversationHandler.END

    async def _initialize_mqtt_worker(self, context: ContextTypes.DEFAULT_TYPE):
        if self.mqtt_worker is None:
            patient_id = context.user_data['patient_id']
            mqtt_sub_topic = self.mqtt_sub_template.format(PATIENT_ID=patient_id)
            mqtt_pub_topic = self.mqtt_pub_template.format(PATIENT_ID=patient_id)
            mqtt_client_id = self.client_id_template.format(PATIENT_ID=patient_id)

            self.mqtt_worker = TelegramMQTTWorker(
                self.broker_ip,
                self.broker_port,
                mqtt_client_id,
                mqtt_sub_topic,
                mqtt_pub_topic,
                self.handle_mqtt_alert
            )
            self.mqtt_worker.start()
            logger.info(f"MQTT Worker started for patient {patient_id}")
        else:
            logger.info("MQTT Worker already initialized.")

    async def _send_patient_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        keyboard = [
            [InlineKeyboardButton("🍽️ Report Meal", callback_data="command_meal")],
            [InlineKeyboardButton("🏃 Report Exercise", callback_data="command_exercise")],
            [InlineKeyboardButton("📊 View Report", callback_data="command_report")],
            [InlineKeyboardButton("🚪 Logout", callback_data="command_logout")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = f"Hello {context.user_data.get('patient_name', 'Patient')}! What would you like to do?"

        if update.callback_query:
            try:
                await update.callback_query.message.edit_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
            except Exception:
                await update.callback_query.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="Markdown")
        
        return PATIENT_MAIN_MENU

    async def meal_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            message_target = update.message
        elif update.callback_query:
            await update.callback_query.answer()
            message_target = update.callback_query.message
        else:
            logger.warning("meal_command received an update without message or callback_query.")
            return PATIENT_MAIN_MENU

        if not context.user_data.get('patient_id'):
            await message_target.reply_text("Please link your patient account first using /start.")
            return INITIAL_PATIENT_STATE
            
        await message_target.reply_text(
            "Select meal status:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Eating now", callback_data="meal_eating")],
                [InlineKeyboardButton("Not eating", callback_data="meal_none")]
            ])
        )
        return PATIENT_MAIN_MENU

    async def exercise_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            message_target = update.message
        elif update.callback_query:
            await update.callback_query.answer()
            message_target = update.callback_query.message
        else:
            logger.warning("exercise_command received an update without message or callback_query.")
            return PATIENT_MAIN_MENU

        if not context.user_data.get('patient_id'):
            await message_target.reply_text("Please link your patient account first using /start.")
            return INITIAL_PATIENT_STATE

        await message_target.reply_text(
            "Select exercise status:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Exercising now", callback_data="exercise_active")],
                [InlineKeyboardButton("Not exercising", callback_data="exercise_none")]
            ])
        )
        return PATIENT_MAIN_MENU

    async def report_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message:
            message_target = update.message
        elif update.callback_query:
            await update.callback_query.answer()
            message_target = update.callback_query.message
        else:
            logger.warning("report_command received an update without message or callback_query.")
            return PATIENT_MAIN_MENU

        if not context.user_data.get('patient_id'):
            await message_target.reply_text("Please link your patient account first using /start.")
            return INITIAL_PATIENT_STATE

        report_url = f"https://example.com/reports/{context.user_data['patient_id']}"
        message_text = "📊 Your report is available:"
        await message_target.reply_text(
            message_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("View Report", url=report_url)]
            ]),
            parse_mode=None
        )
        return PATIENT_MAIN_MENU

    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        patient_id = context.user_data.get('patient_id')
        if not patient_id:
            await query.edit_message_text("Your session expired. Please /start again.")
            return INITIAL_PATIENT_STATE

        logger.info(f"Button pressed by patient {patient_id}: {query.data}")

        if query.data.startswith("meal_"):
            status = query.data.replace("meal_", "")
            self.mqtt_worker.publish_status(patient_id, "meal", status)
            await self._send_to_thingspeak_direct(context, "field1", 1 if status == "eating" else 0)
            await query.edit_message_text(f"Meal status: `{status}` recorded.", parse_mode="Markdown")
            return await self._send_patient_main_menu(update, context)

        elif query.data.startswith("exercise_"):
            status = query.data.replace("exercise_", "")
            self.mqtt_worker.publish_status(patient_id, "exercise", status)
            await self._send_to_thingspeak_direct(context, "field2", 1 if status == "active" else 0)
            await query.edit_message_text(f"Exercise status: `{status}` recorded.", parse_mode="Markdown")
            return await self._send_patient_main_menu(update, context)
            
        elif query.data == "alert_done":
            await query.edit_message_text("¡Alerta reconocida! Gracias por tu confirmación.")
            return await self._send_patient_main_menu(update, context)
        
        elif query.data == "alert_not_yet":
            await query.edit_message_text("Entendido. Recuerda seguir las indicaciones de tu médico.")
            return await self._send_patient_main_menu(update, context)

        elif query.data == "command_meal":
            return await self.meal_command(update, context)
        elif query.data == "command_exercise":
            return await self.exercise_command(update, context)
        elif query.data == "command_report":
            return await self.report_command(update, context)
        elif query.data == "command_logout":
            return await self.cancel_command(update, context)

        else:
            logger.warning(f"Unhandled callback_data: {query.data}")
            await query.edit_message_text("No entendí esa opción. Por favor, elige del menú.")
            return await self._send_patient_main_menu(update, context)

    async def _send_to_thingspeak_direct(self, context: ContextTypes.DEFAULT_TYPE, field_name: str, value: Union[int, float]):
        patient_id = context.user_data.get('patient_id')
        thingspeak_info = context.user_data.get('thingspeak_info', {})
        thingspeak_url = self.thingspeak_api_url

        api_keys = thingspeak_info.get('apikeys', [])
        channel_id = thingspeak_info.get('channel')

        if not api_keys or not channel_id:
            logger.warning(f"ThingSpeak API keys or channel ID missing for patient {patient_id}. Cannot send data to ThingSpeak.")
            return

        api_key = api_keys[0]
        params = {
            "api_key": api_key,
            field_name: value
        }
        logger.info(f"Attempting to send directly to ThingSpeak for patient {patient_id}. Params: {params}")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(thingspeak_url, params=params, timeout=10)
                response.raise_for_status()
                logger.info(f"Successfully sent data directly to ThingSpeak for patient {patient_id}: {response.status_code} - {response.text}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error sending directly to ThingSpeak for patient {patient_id}: {e.response.status_code} - {e.response.text}", exc_info=True)
        except httpx.RequestError as e:
            logger.error(f"Network error sending directly to ThingSpeak for patient {patient_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"An unexpected error occurred sending directly to ThingSpeak for patient {patient_id}: {e}", exc_info=True)

    async def handle_mqtt_alert(self, mqtt_payload_str: str):
        try:
            alert = json.loads(mqtt_payload_str)
            patient_id_from_alert = alert.get("patient_id")
            alert_message = alert.get("alert_message", "New alert")

            response_data = send_catalog_request_sync("GET", "patients", params={"userID": patient_id_from_alert})
            patient_data = response_data if isinstance(response_data, dict) and response_data.get('userID') == patient_id_from_alert else None
            
            logger.info(f"handle_mqtt_alert: patient_data retrieved from Catalog: {patient_data}")

            if patient_data and patient_data.get("telegram_chat_id"):
                chat_id = patient_data["telegram_chat_id"]
                logger.info(f"handle_mqtt_alert: Attempting to send message to chat ID: {chat_id} for patient {patient_id_from_alert}")
                try:
                    escaped_patient_id = _escape_markdown_v2(patient_id_from_alert)
                    escaped_alert_message = _escape_markdown_v2(alert_message)

                    await self.application.bot.send_message(
                        chat_id=chat_id,
                        text=f"🚨 ALERTA para {escaped_patient_id}: {escaped_alert_message}",
                        parse_mode=ParseMode.MARKDOWN_V2,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✅ Hecho", callback_data="alert_done")],
                            [InlineKeyboardButton("❌ Todavía no", callback_data="alert_not_yet")]
                        ])
                    )
                    logger.info(f"Sent alert to patient {patient_id_from_alert} (chat ID: {chat_id})")
                except TelegramError as e:
                    logger.error(f"Telegram API error sending alert to {chat_id} for patient {patient_id_from_alert}: {e}", exc_info=True)
                except Exception as e:
                    logger.error(f"Unexpected error sending alert to {chat_id} for patient {patient_id_from_alert}: {e}", exc_info=True)
            else:
                logger.warning(f"Could not send alert for patient {patient_id_from_alert}: Chat ID not found or patient not linked in Catalog, or patient_data is invalid.")
        except Exception as e:
            logger.error(f"Error handling MQTT alert: {e}", exc_info=True)

    async def cancel_linking(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Vinculación de cuenta cancelada. Escribe /start para empezar de nuevo.")
        context.user_data.clear()
        return ConversationHandler.END

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = update.effective_user
        logger.info(f"User {user.id} canceled the conversation.")
        if update.message:
            message_target = update.message
        elif update.callback_query:
            await update.callback_query.answer()
            message_target = update.callback_query.message
        else:
            logger.warning("cancel_command received an update without message or callback_query.")
            if update.effective_chat:
                await update.effective_chat.send_message("Operación cancelada. Escribe /start para empezar de nuevo.")
            context.user_data.clear()
            return ConversationHandler.END

        await message_target.reply_text(
            "Operación cancelada. Escribe /start para empezar de nuevo.", reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END
        
    async def _debug_unmatched(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        if update.message:
            received_content = update.message.text
        elif update.callback_query:
            received_content = update.callback_query.data
            await update.callback_query.answer()
        else:
            received_content = "Unknown update type"

        logger.info(f"Unmatched message received from {user_id}: {received_content}")
        
        message_target = update.effective_chat
        
        if context.user_data.get('patient_id'):
            await message_target.send_message("No entendí eso. Por favor, usa las opciones del menú.")
            return await self._send_patient_main_menu(update, context)
        else:
            await message_target.send_message("No entendí eso. Por favor, escribe tu nombre de paciente para vincular tu cuenta, o /start.")
            return GET_PATIENT_NAME

    def run(self):
        logger.info("Starting Patient Telegram Bot application...")
        
        if not self.ensure_catalog_connection():
            logger.critical("Failed to connect to Catalog. Bot cannot start.")
            return

        if not self.register_service():
            logger.critical("Failed to register service with Catalog. Bot cannot start.")
            return

        logger.info("Patient Telegram Bot: Starting polling...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    def stop(self):
        if self.mqtt_worker:
            self.mqtt_worker.stop()
        logger.info("Patient bot stopped.")

if __name__ == "__main__":
    settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_file_path, 'r') as f:
            settings = json.load(f)
        
        catalog_url = settings.get("catalogURL")
        broker_ip = settings.get("brokerIP")
        broker_port = settings.get("brokerPort")

        service_info = settings.get("serviceInfo", {})
        telegram_token = service_info.get("telegram_token")
        service_id = service_info.get("serviceID", "PatientTelegramBot")
        mqtt_sub_template = service_info.get("MQTT_sub", "/notifications/alert/patient_{PATIENT_ID}")
        mqtt_pub_template = service_info.get("MQTT_pub", "/status/meal/patient_{PATIENT_ID}")
        client_id_template = service_info.get("clientID", "telegram_patient_bot_{PATIENT_ID}")

        telegram_token = os.getenv("TELEGRAM_TOKEN", telegram_token)
        catalog_url = os.getenv("CATALOG_URL", catalog_url)
        broker_ip = os.getenv("BROKER_IP", broker_ip)
        broker_port = int(os.getenv("BROKER_PORT", broker_port or 1883))
        service_id = os.getenv("SERVICE_ID", service_id)
        mqtt_sub_template = os.getenv("MQTT_SUB_TOPIC_TEMPLATE", mqtt_sub_template)
        mqtt_pub_template = os.getenv("MQTT_PUB_TOPIC_TEMPLATE", mqtt_pub_template)
        client_id_template = os.getenv("MQTT_CLIENT_ID_TEMPLATE", client_id_template)

        if not telegram_token:
            raise ValueError("Telegram token not found in settings.json or environment variables.")
        if not catalog_url:
            raise ValueError("Catalog URL not found in settings.json or environment variables.")
        if not broker_ip or not broker_port:
            raise ValueError("MQTT Broker IP or Port not found in settings.json or environment variables.")

    except FileNotFoundError:
        logger.error(f"settings.json not found at {settings_file_path}. Please create it.")
        exit(1)
    except json.JSONDecodeError:
        logger.error(f"Error decoding settings.json at {settings_file_path}. Please ensure it's valid JSON.")
        exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading settings: {e}")
        exit(1)

    bot = PatientTelegramBot(telegram_token, catalog_url, broker_ip, broker_port,
                             service_id, mqtt_sub_template, mqtt_pub_template, client_id_template)
    try:
        bot.run()
    except KeyboardInterrupt:
        pass
    finally:
        bot.stop()
