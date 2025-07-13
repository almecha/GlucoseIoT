# this partially works, it can register doctors and its having troubles to register patients

import logging
import asyncio
import httpx
import json
import os
import bcrypt
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
(
    REGISTER_OR_LOGIN,
    LOGIN_USERNAME,
    LOGIN_PASSWORD,
    REGISTER_USERNAME,
    REGISTER_PASSWORD,
    REGISTER_ROLE_MASTER,
    REGISTER_PATIENT_NAME,
    REGISTER_PATIENT_AGE,
    REGISTER_PATIENT_DEVICE,
    REGISTER_PATIENT_THRESHOLDS,
    REGISTER_PATIENT_DOCTOR_ID,
    DOCTOR_MENU,
    MASTER_DOCTOR_MENU,
    LIST_PATIENTS,
    DELETE_USER_SELECT_ID,
    DELETE_USER_CONFIRM,
    VIEW_USER_SELECT_ID,
    EDIT_PATIENT_SELECT_ID,
    EDIT_PATIENT_FIELD,
    EDIT_PATIENT_NEW_VALUE,
) = range(20) # Aumentado el rango para nuevos estados si es necesario

# Keyboard layouts
MAIN_MENU_KEYBOARD_DOCTOR = [
    ["Register New Patient", "List My Patients"],
    ["View Patient Info", "Edit Patient Info"],
    ["Delete User"],
]

MAIN_MENU_KEYBOARD_MASTER_DOCTOR = [
    ["Register New Doctor", "Register New Patient"],
    ["List All Doctors", "List My Patients"],
    ["View User Info", "Edit User Info"],
    ["Delete User"],
]

# Helper function to send requests to the Catalog service
async def send_catalog_request(method, endpoint, data=None, params=None):
    catalog_url = os.getenv("CATALOG_URL", "http://catalog:9080")
    url = f"{catalog_url}/{endpoint}"
    logger.info(f"Sending {method} request to {url} with data: {data} and params: {params}")
    try:
        async with httpx.AsyncClient() as client:
            if method == "GET":
                response = await client.get(url, params=params)
            elif method == "POST":
                response = await client.post(url, json=data)
            elif method == "PUT":
                response = await client.put(url, json=data)
            elif method == "DELETE":
                response = await client.delete(url, params=params)
            else:
                raise ValueError("Unsupported HTTP method")

            response.raise_for_status() # Raise an HTTPStatusError for bad responses (4xx or 5xx)
            logger.info(f"Response from {url}: {response.status_code} - {response.text}")
            return response.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error occurred: {e.response.status_code} - {e.response.text}")
        raise
    except httpx.RequestError as e:
        logger.error(f"An error occurred while requesting {e.request.url!r}: {e}")
        raise
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON response from {url}: {response.text}")
        raise


class DoctorTelegramBot:
    def __init__(self, token, catalog_url):
        self.catalog_url = catalog_url
        self.application = Application.builder().token(token).build()

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                REGISTER_OR_LOGIN: [
                    MessageHandler(filters.Regex("^Register$"), self.register_start),
                    MessageHandler(filters.Regex("^Login$"), self.login_start),
                ],
                LOGIN_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.login_username)],
                LOGIN_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.login_password)],
                REGISTER_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_username)],
                REGISTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_password)],
                REGISTER_ROLE_MASTER: [MessageHandler(filters.Regex("^(Doctor|MasterDoctor)$"), self.register_role_master)],
                REGISTER_PATIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_patient_name)],
                REGISTER_PATIENT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_patient_age)],
                REGISTER_PATIENT_DEVICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_patient_device)],
                REGISTER_PATIENT_THRESHOLDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_patient_thresholds)],
                REGISTER_PATIENT_DOCTOR_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.register_patient_doctor_id)],
                DOCTOR_MENU: [
                    MessageHandler(filters.Regex("^Register New Patient$"), self.register_patient_start),
                    MessageHandler(filters.Regex("^List My Patients$"), self.list_patients),
                    MessageHandler(filters.Regex("^View Patient Info$"), self.view_user_select_id),
                    MessageHandler(filters.Regex("^Edit Patient Info$"), self.edit_patient_select_id),
                    MessageHandler(filters.Regex("^Delete User$"), self.delete_user_select_id),
                    MessageHandler(filters.Regex("^Return to Main Menu$"), self.return_to_master_doctor_menu_or_end),
                    MessageHandler(filters.ALL, self._debug_unmatched), # Fallback for this state
                ],
                MASTER_DOCTOR_MENU: [
                    MessageHandler(filters.Regex("^Register New Doctor$"), self.register_doctor_start),
                    MessageHandler(filters.Regex("^Register New Patient$"), self.register_patient_start),
                    MessageHandler(filters.Regex("^List All Doctors$"), self.list_doctors),
                    MessageHandler(filters.Regex("^List My Patients$"), self.list_patients),
                    MessageHandler(filters.Regex("^View User Info$"), self.view_user_select_id),
                    MessageHandler(filters.Regex("^Edit User Info$"), self.edit_patient_select_id), # Assuming this can edit any user
                    MessageHandler(filters.Regex("^Delete User$"), self.delete_user_select_id),
                    MessageHandler(filters.ALL, self._debug_unmatched), # Fallback for this state
                ],
                LIST_PATIENTS: [
                    MessageHandler(filters.Regex("^Return to Doctor Menu$"), self.return_to_doctor_menu),
                    MessageHandler(filters.Regex("^Return to Master Doctor Menu$"), self.return_to_master_doctor_menu),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
                DELETE_USER_SELECT_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.delete_user_confirm),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
                DELETE_USER_CONFIRM: [
                    MessageHandler(filters.Regex("^Yes$"), self.delete_user),
                    MessageHandler(filters.Regex("^No$"), self.cancel_delete_user),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
                VIEW_USER_SELECT_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.view_user_info),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
                EDIT_PATIENT_SELECT_ID: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.edit_patient_field),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
                EDIT_PATIENT_FIELD: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.edit_patient_new_value),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
                EDIT_PATIENT_NEW_VALUE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.save_edited_patient_info),
                    MessageHandler(filters.ALL, self._debug_unmatched),
                ],
            },
            fallbacks=[CommandHandler("cancel", self.cancel), MessageHandler(filters.ALL, self._debug_unmatched)],
        )

        self.application.add_handler(conv_handler)
        # Global fallback for messages not handled by the conversation handler
        # self.application.add_handler(MessageHandler(filters.ALL, self._debug_unmatched)) # This might conflict or cause issues if conv_handler handles all.
                                                                                        # If conv_handler has a final fallback it should catch all.

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        context.user_data['user_id'] = str(user_id) # Store user_id as string for consistency with Catalog service
        logger.info(f"[STATE] start: User {user_id} started the bot.")

        # Check if user already exists in the catalog
        try:
            response = await send_catalog_request("GET", "users", params={"userID": str(user_id)})
            user_data = response.get("user")
            if user_data:
                context.user_data['role'] = user_data.get('role')
                context.user_data['username'] = user_data.get('userName')
                await update.message.reply_text(f"Welcome back, {user_data.get('userName')}! You are logged in as a {user_data.get('role')}.")
                if user_data.get('role') == "Doctor":
                    context.user_data['state'] = DOCTOR_MENU # Store current state
                    return DOCTOR_MENU
                elif user_data.get('role') == "MasterDoctor":
                    context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                    return MASTER_DOCTOR_MENU
            else:
                # This part should ideally not be reached if the GET user call returns 404 and is caught.
                # If a 404 is raised, the `except` block will handle it.
                pass
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.info(f"User {user_id} not found in catalog. Proceeding to registration/login options.")
            else:
                await update.message.reply_text(f"An error occurred while checking user status: {e.response.status_code} - {e.response.text}")
                logger.error(f"Error checking user in catalog: {e}")
                context.user_data['state'] = ConversationHandler.END # Store current state
                return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in start function: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

        keyboard = [["Register", "Login"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Welcome to GlucoseIoT! Please choose an option:", reply_markup=reply_markup)
        context.user_data['state'] = REGISTER_OR_LOGIN # Store current state
        return REGISTER_OR_LOGIN

    async def register_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("[STATE] register_start: User chose Register")
        await update.message.reply_text("Please enter your desired username:")
        context.user_data['state'] = REGISTER_USERNAME # Store current state
        return REGISTER_USERNAME

    async def register_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        username = update.message.text
        context.user_data['username'] = username
        logger.info(f"[STATE] register_username: User {username} entered username for registration.")

        # Check if username (userID) already exists
        try:
            response = await send_catalog_request("GET", "users", params={"username": username})
            if response.get("user"):
                await update.message.reply_text("This username is already taken. Please choose a different one.")
                context.user_data['state'] = REGISTER_USERNAME # Stay in this state
                return REGISTER_USERNAME
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Username not found, proceed with registration
                await update.message.reply_text("Please enter your password:")
                context.user_data['state'] = REGISTER_PASSWORD # Store current state
                return REGISTER_PASSWORD
            else:
                await update.message.reply_text(f"An error occurred while checking username: {e.response.status_code} - {e.response.text}")
                logger.error(f"Error checking username in catalog: {e}")
                context.user_data['state'] = ConversationHandler.END # Store current state
                return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in register_username: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def register_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        password = update.message.text
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        context.user_data['password_hash'] = hashed_password
        logger.info("[STATE] register_password: User entered password.")

        keyboard = [["Doctor", "MasterDoctor"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        await update.message.reply_text("Please select your role:", reply_markup=reply_markup)
        context.user_data['state'] = REGISTER_ROLE_MASTER # Store current state
        return REGISTER_ROLE_MASTER

    async def register_role_master(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        role = update.message.text
        username = context.user_data['username']
        hashed_password = context.user_data['password_hash']
        chat_id = update.effective_chat.id # Get Telegram chat ID

        payload = {
            "userID": username, # Use username as userID for consistency with bot's internal handling
            "userName": username, # Display name can also be username for simplicity
            "password_hash": hashed_password,
            "role": role,
            "telegram_chat_id": chat_id # Store Telegram chat ID
        }

        try:
            response = await send_catalog_request("POST", "users", data=payload)
            logger.info(f"User {username} registered successfully with role {role}.")
            await update.message.reply_text(f"Successfully registered as a {role}!")

            context.user_data['role'] = role # Store role in user_data
            if role == "Doctor":
                context.user_data['state'] = DOCTOR_MENU # Store current state
                await update.message.reply_text("Successfully registered as a Doctor! What would you like to do next?",
                    reply_markup=ReplyKeyboardMarkup(MAIN_MENU_KEYBOARD_DOCTOR, resize_keyboard=True, one_time_keyboard=False),)
                logger.info("[STATE] registration_success returning DOCTOR_MENU")
                return DOCTOR_MENU
            elif role == "MasterDoctor":
                context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                await update.message.reply_text(
                    "Successfully registered as a Master Doctor! What would you like to do next?",
                    reply_markup=ReplyKeyboardMarkup(
                        MAIN_MENU_KEYBOARD_MASTER_DOCTOR, resize_keyboard=True, one_time_keyboard=False
                    ),
                )
                logger.info("[STATE] registration_success returning MASTER_DOCTOR_MENU")
                return MASTER_DOCTOR_MENU
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                await update.message.reply_text(f"Registration failed: User with ID '{username}' already exists. Please try /start to login.")
                logger.error(f"Registration failed for {username}: {e.response.text}")
            else:
                await update.message.reply_text(f"Registration failed: {e.response.status_code} - {e.response.text}")
                logger.error(f"Registration failed for {username}: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred during registration: {e}")
            logger.error(f"Unexpected error during registration: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def login_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("[STATE] login_start: User chose Login")
        await update.message.reply_text("Please enter your username:")
        context.user_data['state'] = LOGIN_USERNAME # Store current state
        return LOGIN_USERNAME

    async def login_username(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        username = update.message.text
        context.user_data['username'] = username
        logger.info(f"[STATE] login_username: User {username} entered username for login.")
        await update.message.reply_text("Please enter your password:")
        context.user_data['state'] = LOGIN_PASSWORD # Store current state
        return LOGIN_PASSWORD

    async def login_password(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        username = context.user_data.get('username')
        password = update.message.text
        logger.info(f"[STATE] login_password: User {username} entered password.")

        if not username:
            await update.message.reply_text("Username not found in context. Please start over with /start.")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

        payload = {
            "userID": username,
            "password": password
        }

        try:
            response = await send_catalog_request("POST", "login", data=payload)
            user_data = response.get('user')
            if user_data:
                context.user_data['role'] = user_data.get('role')
                context.user_data['user_id'] = user_data.get('userID') # Ensure user_id is updated for logged in user
                await update.message.reply_text(f"Login successful! Welcome back, {user_data.get('userName')}!")
                if user_data.get('role') == "Doctor":
                    context.user_data['state'] = DOCTOR_MENU # Store current state
                    return DOCTOR_MENU
                elif user_data.get('role') == "MasterDoctor":
                    context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                    return MASTER_DOCTOR_MENU
                else:
                    await update.message.reply_text("Your role does not have an associated menu in this bot. Please contact support.")
                    context.user_data['state'] = ConversationHandler.END # Store current state
                    return ConversationHandler.END
            else:
                await update.message.reply_text("Login failed. Invalid username or password.")
                context.user_data['state'] = LOGIN_USERNAME # Back to username for retry
                return LOGIN_USERNAME # Or perhaps back to LOGIN_USERNAME to retry
        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"Login failed: {e.response.text}")
            logger.error(f"Login failed for {username}: {e}")
            context.user_data['state'] = LOGIN_USERNAME # Back to username for retry
            return LOGIN_USERNAME
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred during login: {e}")
            logger.error(f"Unexpected error during login: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def register_patient_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("[STATE] register_patient_start: User chose Register New Patient")
        await update.message.reply_text("Please enter the patient's name:")
        context.user_data['state'] = REGISTER_PATIENT_NAME # Store current state
        return REGISTER_PATIENT_NAME
    
    async def register_patient_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        patient_name = update.message.text
        context.user_data['patient_name'] = patient_name
        context.user_data['patient_id'] = f"patient_{patient_name.replace(' ', '_').lower()}_{datetime.now().strftime('%f')}" # Generate a simple ID
        await update.message.reply_text("Please enter the patient's age:")
        context.user_data['state'] = REGISTER_PATIENT_AGE # Store current state
        return REGISTER_PATIENT_AGE

    async def register_patient_age(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            patient_age = int(update.message.text)
            context.user_data['patient_age'] = patient_age
            await update.message.reply_text("Please enter the connected device ID (e.g., 'device_001'):")
            context.user_data['state'] = REGISTER_PATIENT_DEVICE # Store current state
            return REGISTER_PATIENT_DEVICE
        except ValueError:
            await update.message.reply_text("Invalid age. Please enter a number.")
            context.user_data['state'] = REGISTER_PATIENT_AGE # Stay in this state
            return REGISTER_PATIENT_AGE

    async def register_patient_device(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        device_id = update.message.text
        context.user_data['connected_devices'] = [{"deviceID": device_id, "status": "active"}] # Assuming one device for now
        await update.message.reply_text("Please enter threshold parameters as JSON (e.g., {\"glucose_min\": 70, \"glucose_max\": 180}):")
        context.user_data['state'] = REGISTER_PATIENT_THRESHOLDS # Store current state
        return REGISTER_PATIENT_THRESHOLDS

    async def register_patient_thresholds(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        try:
            threshold_params = json.loads(update.message.text)
            context.user_data['threshold_parameters'] = threshold_params
            
            # If the current user is a Doctor, the doctorID is their own userID
            # If the current user is a MasterDoctor, they will be prompted for doctorID
            if context.user_data.get('role') == "Doctor":
                context.user_data['doctor_id'] = context.user_data.get('user_id')
                return await self._register_patient_finalize(update, context)
            else: # MasterDoctor
                await update.message.reply_text("Please enter the Doctor ID who will be assigned to this patient:")
                context.user_data['state'] = REGISTER_PATIENT_DOCTOR_ID # Store current state
                return REGISTER_PATIENT_DOCTOR_ID

        except json.JSONDecodeError:
            await update.message.reply_text("Invalid JSON format for thresholds. Please try again.")
            context.user_data['state'] = REGISTER_PATIENT_THRESHOLDS # Stay in this state
            return REGISTER_PATIENT_THRESHOLDS
    
    async def register_patient_doctor_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        doctor_id = update.message.text
        # Optional: Validate if doctor_id exists in Catalog
        try:
            response = await send_catalog_request("GET", "users", params={"userID": doctor_id, "role": "Doctor"})
            if not response.get("user"):
                await update.message.reply_text("Doctor ID not found or is not a Doctor. Please enter a valid Doctor ID:")
                context.user_data['state'] = REGISTER_PATIENT_DOCTOR_ID # Stay in this state
                return REGISTER_PATIENT_DOCTOR_ID
            context.user_data['doctor_id'] = doctor_id
            return await self._register_patient_finalize(update, context)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await update.message.reply_text("Doctor ID not found. Please enter a valid Doctor ID:")
            else:
                await update.message.reply_text(f"An error occurred while validating Doctor ID: {e.response.status_code} - {e.response.text}")
            logger.error(f"Error validating doctor ID {doctor_id}: {e}")
            context.user_data['state'] = REGISTER_PATIENT_DOCTOR_ID # Stay in this state
            return REGISTER_PATIENT_DOCTOR_ID
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in register_patient_doctor_id: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END


    async def _register_patient_finalize(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        patient_id = context.user_data['patient_id']
        patient_name = context.user_data['patient_name']
        patient_age = context.user_data['patient_age']
        connected_devices = context.user_data['connected_devices']
        threshold_parameters = context.user_data['threshold_parameters']
        doctor_id = context.user_data['doctor_id']
        
        patient_payload = {
            "userID": patient_id,
            "userName": patient_name,
            "role": "Patient",
            "connected_devices": connected_devices,
            "user_information": {"age": patient_age}, # Store age within user_information
            "threshold_parameters": threshold_parameters,
            "doctorID": doctor_id # Assign the doctor
        }

        try:
            await send_catalog_request("POST", "users", data=patient_payload)
            await update.message.reply_text(f"Patient {patient_name} registered successfully!")

            # Determine which menu to return to based on the current user's role
            current_user_role = context.user_data.get('role')
            if current_user_role == "Doctor":
                context.user_data['state'] = DOCTOR_MENU # Store current state
                return DOCTOR_MENU
            elif current_user_role == "MasterDoctor":
                context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                return MASTER_DOCTOR_MENU
            else:
                # Fallback if role is not set or unexpected
                context.user_data['state'] = ConversationHandler.END # Store current state
                return ConversationHandler.END

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                await update.message.reply_text(f"Registration failed: Patient with ID '{patient_id}' already exists.")
            else:
                await update.message.reply_text(f"Registration failed: {e.response.status_code} - {e.response.text}")
            logger.error(f"Patient registration failed for {patient_id}: {e}")
            # Return to the correct menu after failure
            current_user_role = context.user_data.get('role')
            if current_user_role == "Doctor":
                context.user_data['state'] = DOCTOR_MENU # Store current state
                return DOCTOR_MENU
            elif current_user_role == "MasterDoctor":
                context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                return MASTER_DOCTOR_MENU
            else:
                context.user_data['state'] = ConversationHandler.END # Store current state
                return ConversationHandler.END
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred during patient registration: {e}")
            logger.error(f"Unexpected error during patient registration: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END
        
    async def list_patients(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_role = context.user_data.get('role')
        user_id = context.user_data.get('user_id')
        logger.info(f"[STATE] list_patients: User {user_id} ({user_role}) requested list of patients.")
        
        patients_data = []
        try:
            if user_role == "Doctor":
                # A doctor lists only their patients
                response = await send_catalog_request("GET", "users", params={"role": "Patient", "doctorID": user_id})
                patients_data = response.get("users", [])
            elif user_role == "MasterDoctor":
                # A master doctor lists all patients
                response = await send_catalog_request("GET", "users", params={"role": "Patient"})
                patients_data = response.get("users", [])
            else:
                await update.message.reply_text("You do not have permission to view patients.")
                context.user_data['state'] = ConversationHandler.END # Store current state
                return ConversationHandler.END

            if patients_data:
                message = "Your Patients:\n"
                for patient in patients_data:
                    message += (f"- ID: {patient.get('userID')}, Name: {patient.get('userName')}, "
                                f"Age: {patient.get('user_information', {}).get('age')}, "
                                f"Doctor: {patient.get('doctorID')}\n")
                await update.message.reply_text(message)
            else:
                await update.message.reply_text("No patients found.")
            
        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"Failed to fetch patients: {e.response.status_code} - {e.response.text}")
            logger.error(f"Failed to fetch patients: {e}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in list_patients: {e}")

        # Return to the correct menu based on role
        if user_role == "Doctor":
            context.user_data['state'] = DOCTOR_MENU # Store current state
            return DOCTOR_MENU
        elif user_role == "MasterDoctor":
            context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
            return MASTER_DOCTOR_MENU
        else:
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def register_doctor_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("[STATE] register_doctor_start: Master Doctor chose Register New Doctor")
        await update.message.reply_text("Please enter the new doctor's desired username:")
        context.user_data['state'] = REGISTER_USERNAME # Re-use registration flow, will set role later
        context.user_data['registering_doctor'] = True # Flag to differentiate doctor registration
        return REGISTER_USERNAME

    async def list_doctors(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_role = context.user_data.get('role')
        user_id = context.user_data.get('user_id')
        logger.info(f"[STATE] list_doctors: User {user_id} ({user_role}) requested list of doctors.")

        if user_role != "MasterDoctor":
            await update.message.reply_text("You do not have permission to view doctors.")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

        try:
            response = await send_catalog_request("GET", "users", params={"role": "Doctor"})
            doctors_data = response.get("users", [])

            if doctors_data:
                message = "List of Doctors:\n"
                for doctor in doctors_data:
                    message += f"- ID: {doctor.get('userID')}, Name: {doctor.get('userName')}\n"
                await update.message.reply_text(message)
            else:
                await update.message.reply_text("No doctors found.")

        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"Failed to fetch doctors: {e.response.status_code} - {e.response.text}")
            logger.error(f"Failed to fetch doctors: {e}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in list_doctors: {e}")
        
        context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
        return MASTER_DOCTOR_MENU

    async def delete_user_select_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_role = context.user_data.get('role')
        if user_role not in ["Doctor", "MasterDoctor"]:
            await update.message.reply_text("You do not have permission to delete users.")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END
        
        await update.message.reply_text("Please enter the User ID (Doctor or Patient) to delete:")
        context.user_data['state'] = DELETE_USER_SELECT_ID # Store current state
        return DELETE_USER_SELECT_ID

    async def delete_user_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_to_delete_id = update.message.text
        context.user_data['user_to_delete_id'] = user_to_delete_id
        
        # Optional: Fetch user details to confirm before deleting
        try:
            response = await send_catalog_request("GET", "users", params={"userID": user_to_delete_id})
            user_data = response.get("user")
            if user_data:
                confirm_message = (f"Are you sure you want to delete user:\n"
                                   f"ID: {user_data.get('userID')}, Name: {user_data.get('userName')}, Role: {user_data.get('role')}?\n"
                                   f"Type 'Yes' to confirm or 'No' to cancel.")
                keyboard = [["Yes", "No"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
                await update.message.reply_text(confirm_message, reply_markup=reply_markup)
                context.user_data['state'] = DELETE_USER_CONFIRM # Store current state
                return DELETE_USER_CONFIRM
            else:
                await update.message.reply_text("User not found. Please try again.")
                context.user_data['state'] = DELETE_USER_SELECT_ID # Stay in this state
                return DELETE_USER_SELECT_ID
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await update.message.reply_text("User not found. Please try again.")
            else:
                await update.message.reply_text(f"An error occurred: {e.response.status_code} - {e.response.text}")
            logger.error(f"Error finding user {user_to_delete_id}: {e}")
            context.user_data['state'] = DELETE_USER_SELECT_ID # Stay in this state
            return DELETE_USER_SELECT_ID
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in delete_user_confirm: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def delete_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_to_delete_id = context.user_data.get('user_to_delete_id')
        user_role = context.user_data.get('role') # Role of the bot user (Doctor/MasterDoctor)
        
        if not user_to_delete_id:
            await update.message.reply_text("No user ID found for deletion. Please start over.")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

        # MasterDoctor can delete any user. Doctor can only delete their own patients.
        can_delete = False
        try:
            target_user_response = await send_catalog_request("GET", "users", params={"userID": user_to_delete_id})
            target_user_data = target_user_response.get("user")
            
            if not target_user_data:
                await update.message.reply_text("User to delete not found in catalog.")
                can_delete = False # Explicitly set to false
            elif user_role == "MasterDoctor":
                can_delete = True
            elif user_role == "Doctor" and target_user_data.get('role') == "Patient" and \
                 target_user_data.get('doctorID') == context.user_data.get('user_id'):
                can_delete = True
            else:
                await update.message.reply_text(f"You do not have permission to delete user {user_to_delete_id}.")
                can_delete = False

            if can_delete:
                await send_catalog_request("DELETE", f"users/{user_to_delete_id}")
                await update.message.reply_text(f"User {user_to_delete_id} deleted successfully.")
            
        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"Failed to delete user: {e.response.status_code} - {e.response.text}")
            logger.error(f"Failed to delete user {user_to_delete_id}: {e}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in delete_user: {e}")
            
        # Clear the ID from context regardless of success/failure
        if 'user_to_delete_id' in context.user_data:
            del context.user_data['user_to_delete_id']

        # Return to the correct menu based on role
        if user_role == "Doctor":
            context.user_data['state'] = DOCTOR_MENU # Store current state
            return DOCTOR_MENU
        elif user_role == "MasterDoctor":
            context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
            return MASTER_DOCTOR_MENU
        else:
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def cancel_delete_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        if 'user_to_delete_id' in context.user_data:
            del context.user_data['user_to_delete_id']
        await update.message.reply_text("User deletion cancelled.")
        user_role = context.user_data.get('role')
        if user_role == "Doctor":
            context.user_data['state'] = DOCTOR_MENU # Store current state
            return DOCTOR_MENU
        elif user_role == "MasterDoctor":
            context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
            return MASTER_DOCTOR_MENU
        else:
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def view_user_select_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Please enter the User ID (Doctor, MasterDoctor, or Patient) to view:")
        context.user_data['state'] = VIEW_USER_SELECT_ID # Store current state
        return VIEW_USER_SELECT_ID

    async def view_user_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id_to_view = update.message.text
        user_role = context.user_data.get('role')
        current_user_id = context.user_data.get('user_id')

        try:
            response = await send_catalog_request("GET", "users", params={"userID": user_id_to_view})
            user_data = response.get("user")

            if not user_data:
                await update.message.reply_text("User not found. Please try again.")
            elif user_role == "MasterDoctor":
                # MasterDoctor can view any user's info
                pass
            elif user_role == "Doctor" and user_data.get('role') == "Patient" and user_data.get('doctorID') == current_user_id:
                # Doctor can view their own patients
                pass
            elif user_role == "Doctor" and user_data.get('userID') == current_user_id:
                # Doctor can view their own info
                pass
            else:
                await update.message.reply_text(f"You do not have permission to view user {user_id_to_view}.")
                user_data = None # Clear data to prevent displaying unauthorized info

            if user_data:
                # Remove password hash for security before displaying
                user_data_display = user_data.copy()
                user_data_display.pop("password_hash", None)
                await update.message.reply_text(f"User Info:\n{json.dumps(user_data_display, indent=2)}")
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await update.message.reply_text("User not found. Please try again.")
            else:
                await update.message.reply_text(f"An error occurred: {e.response.status_code} - {e.response.text}")
            logger.error(f"Error viewing user {user_id_to_view}: {e}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in view_user_info: {e}")

        # Return to the correct menu based on role
        if user_role == "Doctor":
            context.user_data['state'] = DOCTOR_MENU # Store current state
            return DOCTOR_MENU
        elif user_role == "MasterDoctor":
            context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
            return MASTER_DOCTOR_MENU
        else:
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def edit_patient_select_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        await update.message.reply_text("Please enter the Patient ID to edit:")
        context.user_data['state'] = EDIT_PATIENT_SELECT_ID # Store current state
        return EDIT_PATIENT_SELECT_ID

    async def edit_patient_field(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        patient_id_to_edit = update.message.text
        context.user_data['patient_id_to_edit'] = patient_id_to_edit
        
        user_role = context.user_data.get('role')
        current_user_id = context.user_data.get('user_id')

        try:
            response = await send_catalog_request("GET", "users", params={"userID": patient_id_to_edit})
            patient_data = response.get("user")

            if not patient_data or patient_data.get('role') != "Patient":
                await update.message.reply_text("Patient not found. Please try again.")
                context.user_data['state'] = EDIT_PATIENT_SELECT_ID # Stay in this state
                return EDIT_PATIENT_SELECT_ID
            
            # Authorization check
            if user_role == "MasterDoctor":
                pass # MasterDoctor can edit any patient
            elif user_role == "Doctor" and patient_data.get('doctorID') == current_user_id:
                pass # Doctor can edit their own patients
            else:
                await update.message.reply_text(f"You do not have permission to edit patient {patient_id_to_edit}.")
                context.user_data['state'] = DOCTOR_MENU if user_role == "Doctor" else MASTER_DOCTOR_MENU
                return context.user_data['state']

            # Store current patient data for reference during edit
            context.user_data['current_patient_data'] = patient_data 
            
            await update.message.reply_text("Which field would you like to edit (e.g., 'userName', 'age', 'glucose_min')?")
            context.user_data['state'] = EDIT_PATIENT_FIELD # Store current state
            return EDIT_PATIENT_FIELD

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                await update.message.reply_text("Patient not found. Please try again.")
            else:
                await update.message.reply_text(f"An error occurred: {e.response.status_code} - {e.response.text}")
            logger.error(f"Error finding patient {patient_id_to_edit} for edit: {e}")
            context.user_data['state'] = EDIT_PATIENT_SELECT_ID # Stay in this state
            return EDIT_PATIENT_SELECT_ID
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in edit_patient_field: {e}")
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END


    async def edit_patient_new_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        field_to_edit = update.message.text
        context.user_data['field_to_edit'] = field_to_edit
        
        await update.message.reply_text(f"Please enter the new value for '{field_to_edit}':")
        context.user_data['state'] = EDIT_PATIENT_NEW_VALUE # Store current state
        return EDIT_PATIENT_NEW_VALUE

    async def save_edited_patient_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        patient_id = context.user_data.get('patient_id_to_edit')
        field = context.user_data.get('field_to_edit')
        new_value = update.message.text
        
        current_patient_data = context.user_data.get('current_patient_data')

        if not patient_id or not field or not current_patient_data:
            await update.message.reply_text("Missing information for update. Please start over.")
            # Determine which menu to return to based on the current user's role
            current_user_role = context.user_data.get('role')
            if current_user_role == "Doctor":
                context.user_data['state'] = DOCTOR_MENU # Store current state
                return DOCTOR_MENU
            elif current_user_role == "MasterDoctor":
                context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                return MASTER_DOCTOR_MENU
            else:
                context.user_data['state'] = ConversationHandler.END # Store current state
                return ConversationHandler.END

        update_payload = {}
        try:
            if field in ["userName", "telegram_chat_id", "doctorID"]:
                update_payload[field] = new_value
            elif field == "age": # Nested under user_information
                if 'user_information' not in current_patient_data:
                    current_patient_data['user_information'] = {}
                current_patient_data['user_information']['age'] = int(new_value)
                update_payload['user_information'] = current_patient_data['user_information']
            elif field in ["glucose_min", "glucose_max", "heart_rate_min", "heart_rate_max"]: # Nested under threshold_parameters
                if 'threshold_parameters' not in current_patient_data:
                    current_patient_data['threshold_parameters'] = {}
                current_patient_data['threshold_parameters'][field] = float(new_value) # Assuming thresholds can be floats
                update_payload['threshold_parameters'] = current_patient_data['threshold_parameters']
            else:
                await update.message.reply_text(f"Editing field '{field}' is not supported or not recognized.")
                # Return to the correct menu after failure
                current_user_role = context.user_data.get('role')
                if current_user_role == "Doctor":
                    context.user_data['state'] = DOCTOR_MENU # Store current state
                    return DOCTOR_MENU
                elif current_user_role == "MasterDoctor":
                    context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
                    return MASTER_DOCTOR_MENU
                else:
                    context.user_data['state'] = ConversationHandler.END # Store current state
                    return ConversationHandler.END

            await send_catalog_request("PUT", f"users/{patient_id}", data=update_payload)
            await update.message.reply_text(f"Patient {patient_id}'s {field} updated successfully to {new_value}.")
            
        except ValueError:
            await update.message.reply_text(f"Invalid value for '{field}'. Please enter a valid number.")
        except httpx.HTTPStatusError as e:
            await update.message.reply_text(f"Failed to update patient: {e.response.status_code} - {e.response.text}")
            logger.error(f"Failed to update patient {patient_id}: {e}")
        except Exception as e:
            await update.message.reply_text(f"An unexpected error occurred: {e}")
            logger.error(f"Unexpected error in save_edited_patient_info: {e}")
        
        # Clear editing context
        context.user_data.pop('patient_id_to_edit', None)
        context.user_data.pop('field_to_edit', None)
        context.user_data.pop('current_patient_data', None)

        # Return to the correct menu based on role
        current_user_role = context.user_data.get('role')
        if current_user_role == "Doctor":
            context.user_data['state'] = DOCTOR_MENU # Store current state
            return DOCTOR_MENU
        elif current_user_role == "MasterDoctor":
            context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
            return MASTER_DOCTOR_MENU
        else:
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def return_to_doctor_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("[STATE] return_to_doctor_menu returning DOCTOR_MENU")
        await update.message.reply_text(
            "What would you like to do next?",
            reply_markup=ReplyKeyboardMarkup(
                MAIN_MENU_KEYBOARD_DOCTOR, resize_keyboard=True, one_time_keyboard=False
            ),
        )
        context.user_data['state'] = DOCTOR_MENU # Store current state
        return DOCTOR_MENU

    async def return_to_master_doctor_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        logger.info("[STATE] return_to_master_doctor_menu returning MASTER_DOCTOR_MENU")
        await update.message.reply_text(
            "What would you like to do next?",
            reply_markup=ReplyKeyboardMarkup(
                MAIN_MENU_KEYBOARD_MASTER_DOCTOR, resize_keyboard=True, one_time_keyboard=False
            ),
        )
        context.user_data['state'] = MASTER_DOCTOR_MENU # Store current state
        return MASTER_DOCTOR_MENU
        
    async def return_to_master_doctor_menu_or_end(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_role = context.user_data.get('role')
        if user_role == "MasterDoctor":
            return await self.return_to_master_doctor_menu(update, context)
        elif user_role == "Doctor":
            return await self.return_to_doctor_menu(update, context)
        else:
            await update.message.reply_text("Returning to main options.", reply_markup=ReplyKeyboardRemove())
            context.user_data['state'] = ConversationHandler.END # Store current state
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user = update.message.from_user
        logger.info("User %s canceled the conversation.", user.first_name)
        await update.message.reply_text(
            "Operation cancelled. Type /start to begin again.", reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear() # Clear all user data on cancel
        context.user_data['state'] = ConversationHandler.END # Store current state
        return ConversationHandler.END
        
    async def _debug_unmatched(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        user_id = update.effective_user.id
        logger.info(f"Unmatched message received from {user_id}: {update.message.text}")
        await update.message.reply_text("I didn't understand that. Please use the menu options or type /start.")
        
        # Attempt to return to the last known state, or end the conversation
        current_state = context.user_data.get('state')
        if current_state is not None:
            logger.info(f"Returning to last known state: {current_state}")
            return current_state
        else:
            logger.info("No last known state, ending conversation.")
            return ConversationHandler.END

    def run(self):
        logger.info("Doctor Telegram Bot is starting...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    # Load settings from settings.json
    settings_file_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    try:
        with open(settings_file_path, 'r') as f:
            settings = json.load(f)
        telegram_bot_token = settings.get("telegram_token")
        catalog_url = settings.get("catalog_url")
        
        if not telegram_bot_token or not catalog_url:
            raise ValueError("telegram_token or catalog_url not found in settings.json")

    except FileNotFoundError:
        logger.error(f"settings.json not found at {settings_file_path}")
        exit(1)
    except json.JSONDecodeError:
        logger.error(f"Error decoding settings.json at {settings_file_path}. Please ensure it's valid JSON.")
        exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading settings: {e}")
        exit(1)

    bot = DoctorTelegramBot(telegram_bot_token, catalog_url)
    bot.run()
