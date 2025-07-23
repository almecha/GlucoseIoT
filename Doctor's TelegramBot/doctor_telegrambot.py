import logging
import json
import requests
import time
import bcrypt
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler, CallbackQueryHandler
)
from datetime import datetime

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
ASK_NAME, ASK_ROLE = range(2)  # Doctor registration
PATIENT_NAME, PATIENT_ID, AGE,SENSOR_ID, GLUCOSE_NORMAL, GLUCOSE_PREMEAL, GLUCOSE_POSTMEAL, INSULIN_MAX = range(2, 10)
EDIT_CHOICE, EDIT_VALUE = range(10, 12)  # Patient editing states

class DoctorBot:
    def __init__(self, token: str, catalog_url: str):
        self.token = token
        self.catalog_url = catalog_url
        self.service_id = "doctor_bot_service"
        self.max_retries = 5
        self.retry_delay = 5  # seconds
        self.ensure_catalog_connection()
        self.register_service()
        self.application = Application.builder().token(self.token).build()
    
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
            "serviceID": self.service_id,
            "REST_endpoint": "",  # Not applicable for bot
            "MQTT_sub": [],
            "MQTT_pub": [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        for attempt in range(self.max_retries):
            try:
                response = requests.put(
                    f"{self.catalog_url}/services/doctor_bot_service",
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

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        
        try:
            # Check if doctor is already registered
            response = requests.get(
                f"{self.catalog_url}/doctors",
                params={"telegram_chat_id": chat_id},
                timeout=5
            )
            
            if response.status_code == 200:
                doctors = response.json()
                if isinstance(doctors, list) and doctors:
                    doctor = doctors[0]
                    name = doctor.get("userName", "Doctor")
                    role = doctor.get("role", "Doctor")
                    
                    # Check if this is a Master Doctor
                    is_master = (role == "MasterDoctor")
                    
                    await update.message.reply_text(
                        f"👋 Welcome back, Dr. {name} ({role})!",
                        reply_markup=self.main_menu(is_master)
                    )
                    return ConversationHandler.END
            
            # Not registered - begin registration
            context.user_data['telegram_chat_id'] = chat_id  # ← save early
            await update.message.reply_text(
                "👨⚕️ Welcome to Glucose Monitoring System!\n\n"
                "You are not registered yet. Please enter your full name to register as a doctor:"
            )
            return ASK_NAME
            
        except requests.RequestException as e:
            logger.error(f"Catalog error: {e}")
            await update.message.reply_text("❌ Service unavailable. Try again later.")
            return ConversationHandler.END

    async def receive_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        name = update.message.text.strip()
        context.user_data['doctor_name'] = name

        keyboard = [
            [InlineKeyboardButton("Doctor", callback_data="Doctor"),
             InlineKeyboardButton("Master Doctor", callback_data="MasterDoctor")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Select your role:",
            reply_markup=reply_markup
        )
        return ASK_ROLE

    async def receive_role(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        role = query.data
        name = context.user_data.get("doctor_name")
        chat_id = query.message.chat.id

        # Generate a secure password hash
        password = str(chat_id)[-6:]  # Simple default password
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        doctor_data = {
            "userID": f"doctor_{chat_id}",
            "userName": name,
            "role": role,
            "telegram_chat_id": chat_id,
            "password_hash": password_hash,
            "patients_id": []
        }

        try:
            response = requests.post(
                f"{self.catalog_url}/doctors",
                json=doctor_data,
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                await query.edit_message_text(
                    f"✅ Registration successful!\nWelcome, Dr. {name} ({role})\n\n"
                    f"Your temporary password is: {password}\n"
                    "Please change it using /changepassword"
                )
                await query.message.reply_text(
                    "What would you like to do?",
                    reply_markup=self.main_menu(role == "MasterDoctor")
                )
            else:
                await query.edit_message_text(f"❌ Registration failed: {response.text}")
                
        except requests.RequestException as e:
            logger.error(f"Catalog error: {e}")
            await query.edit_message_text("❌ Service unavailable. Try again later.")

        return ConversationHandler.END

    def main_menu(self, is_master=False):
        buttons = [
            [InlineKeyboardButton("👨⚕️ My Patients", callback_data="my_patients")],
            [InlineKeyboardButton("➕ Register New Patient", callback_data="register_patient")],
            [InlineKeyboardButton("👥 List Doctors", callback_data="list_doctors")]
        ]
        
        if is_master:
            buttons.insert(1, [InlineKeyboardButton("🌍 All Patients", callback_data="all_patients")])
        
        buttons.append([InlineKeyboardButton("🔄 Refresh", callback_data="refresh")])
        
        return InlineKeyboardMarkup(buttons)

    async def start_patient_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        # Get doctor ID from chat ID
        chat_id = query.message.chat.id
        try:
            response = requests.get(
                f"{self.catalog_url}/doctors",
                params={"telegram_chat_id": chat_id},
                timeout=5
            )
            
            if response.status_code == 200 and response.json():
                context.user_data['doctor_id'] = response.json()[0]["userID"]
                await query.edit_message_text("Please enter the patient's full name:")
                return PATIENT_NAME
            else:
                await query.edit_message_text("❌ Doctor not found in system")
                return ConversationHandler.END
                
        except requests.RequestException as e:
            logger.error(f"Error fetching doctor: {e}")
            await query.edit_message_text("❌ Service unavailable. Try again later.")
            return ConversationHandler.END

    async def get_patient_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['patient_name'] = update.message.text
        await update.message.reply_text("Please enter the patient ID (e.g., patient_001):")
        return PATIENT_ID

    async def get_patient_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        patient_id = update.message.text.strip()
        if not patient_id.startswith("patient_"):
            await update.message.reply_text("❌ Patient ID must start with 'patient_'. Please try again:")
            return PATIENT_ID
            
        context.user_data['patient_id'] = patient_id
        await update.message.reply_text("Please enter the sensor ID (e.g., sensor_001):")
        return SENSOR_ID
    
    async def ask_patient_age(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['name'] = update.message.text
        await update.message.reply_text("📅 Please enter the patient's age:")
        return AGE


    async def get_sensor_id(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data['sensor_id'] = update.message.text
        await update.message.reply_text("Please enter the normal glucose threshold (e.g., 100):")
        return GLUCOSE_NORMAL

    async def get_glucose_normal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            value = float(update.message.text)
            context.user_data['glucose_normal'] = value
            await update.message.reply_text("Please enter the pre-meal exercise glucose threshold (e.g., 90):")
            return GLUCOSE_PREMEAL
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number:")
            return GLUCOSE_NORMAL

    async def get_glucose_premeal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            value = float(update.message.text)
            context.user_data['glucose_premeal'] = value
            await update.message.reply_text("Please enter the post-meal exercise glucose threshold (e.g., 120):")
            return GLUCOSE_POSTMEAL
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number:")
            return GLUCOSE_PREMEAL

    async def get_glucose_postmeal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            value = float(update.message.text)
            context.user_data['glucose_postmeal'] = value
            await update.message.reply_text("Please enter the maximum daily insulin amount (e.g., 50):")
            return INSULIN_MAX
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number:")
            return GLUCOSE_POSTMEAL

    async def complete_patient_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            value = float(update.message.text)
            context.user_data['insulin_max'] = value
            
            # Prepare patient data
            patient_data = {
                "userID": context.user_data['patient_id'],
                "role": "Patient",
                "doctorID": context.user_data['doctor_id'],
                "user_information": {
                    "userName": context.user_data['patient_name'],
                    "age": context.user_data.get("age",""),  # Can be updated later
                    "ID_of_the_sensor": context.user_data['sensor_id']
                },
                "threshold_parameters": {
                    "target_glucose_level_normal": context.user_data['glucose_normal'],
                    "target_glucose_level_excersise_premeal": context.user_data['glucose_premeal'],
                    "target_glucose_level_excersise_postmeal": context.user_data['glucose_postmeal'],
                    "max_daily_amount_insulin": context.user_data['insulin_max']
                },
                "connected_devices": [{"deviceID": context.user_data['sensor_id']}],
                "telegram_chat_id": None,
                "thingspeak_info": {"apikeys": [], "channel": ""},
                "dashboard_info": {
                    "dashboard_username": f"{context.user_data['patient_id']}_dashboard",
                    "dashboard_password": None
                }
            }

            # Register patient
            response = requests.post(
                f"{self.catalog_url}/patients",
                json=patient_data,
                timeout=10
            )
            
            if response.status_code == 201:
                await update.message.reply_text(
                    f"✅ Patient registered successfully!\n\n"
                    f"Name: {context.user_data['patient_name']}\n"
                    f"ID: {context.user_data['patient_id']}\n"
                    f"Sensor: {context.user_data['sensor_id']}\n"
                    f"Thresholds:\n"
                    f"- Normal: {context.user_data['glucose_normal']}\n"
                    f"- Pre-meal exercise: {context.user_data['glucose_premeal']}\n"
                    f"- Post-meal exercise: {context.user_data['glucose_postmeal']}\n"
                    f"- Max insulin: {context.user_data['insulin_max']}",
                    reply_markup=self.main_menu(False)  # Adjust if master doctor
                )
            else:
                error = response.json().get("error", "Unknown error")
                await update.message.reply_text(
                    f"❌ Failed to register patient: {error}",
                    reply_markup=self.main_menu(False)
                )
                
        except requests.RequestException as e:
            logger.error(f"Patient registration error: {e}")
            await update.message.reply_text(
                "❌ Service unavailable. Please try again later.",
                reply_markup=self.main_menu(False)
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await update.message.reply_text(
                "❌ An unexpected error occurred. Please try again.",
                reply_markup=self.main_menu(False)
            )
        
        # Clear conversation data
        context.user_data.clear()
        return ConversationHandler.END

    async def cancel_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        if query:
            await query.answer()
            await query.edit_message_text("Operation cancelled.")
        else:
            await update.message.reply_text("Operation cancelled.")
        
        context.user_data.clear()
        return ConversationHandler.END

    async def show_patients(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        chat_id = query.message.chat.id
        try:
            # Get doctor info
            doctor_response = requests.get(
                f"{self.catalog_url}/doctors",
                params={"telegram_chat_id": chat_id},
                timeout=5
            )
            
            if doctor_response.status_code != 200 or not doctor_response.json():
                await query.edit_message_text("❌ Doctor not found")
                return
            
            doctor = doctor_response.json()[0]
            is_master = (doctor.get("role") == "MasterDoctor")
            
            # Get patients
            if query.data == "my_patients":
                patient_ids = doctor.get("patients_id", [])
                patients = []
                for pid in patient_ids:
                    response = requests.get(f"{self.catalog_url}/patients/{pid}")
                    if response.status_code == 200:
                        patients.append(response.json())
                
                if not patients:
                    await query.edit_message_text("You have no patients assigned yet.")
                    return
                
                message = "📋 Your Patients:\n\n"
            else:  # all_patients (for master doctors)
                if not is_master:
                    await query.edit_message_text("❌ Only Master Doctors can view all patients")
                    return
                
                response = requests.get(f"{self.catalog_url}/patients")
                patients = response.json() if response.status_code == 200 else []
                message = "📋 All Patients:\n\n"
            
            # Create patient list
            keyboard = []
            for patient in patients:
                patient_name = patient.get("user_information", {}).get("userName", patient["userID"])
                keyboard.append([
                    InlineKeyboardButton(
                        patient_name,
                        callback_data= patient['userID']
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")])
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except requests.RequestException as e:
            logger.error(f"Error fetching patients: {e}")
            await query.edit_message_text("❌ Service unavailable. Try again later.")

    async def show_patient_options(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        patient_id = query.data
        
        try:
            # Get patient details
            logger.info(f"🔍 Looking up patient ID: {patient_id}")
            response = requests.get(f"{self.catalog_url}/patients/{patient_id}")
            if response.status_code != 200:
                await query.edit_message_text("❌ Patient not found")
                return
                
            patient = response.json()
            
            keyboard = [
                [InlineKeyboardButton("📝 Edit Information", callback_data=f"edit_{patient_id}")],
                [InlineKeyboardButton("📊 View Reports", callback_data=f"reports_{patient_id}")],
                [InlineKeyboardButton("❌ Delete Patient", callback_data=f"delete_{patient_id}")],
                [InlineKeyboardButton("🔙 Back", callback_data="my_patients")]
            ]
            
            thingspeak_info = patient.get('thingspeak_info', {})
            patient_name = patient.get('user_information', {}).get('userName', patient_id)
            await query.edit_message_text(
                f"👤 Patient: {patient_name}\n"
                f"📅 Age: {patient.get('user_information', {}).get('age', 'N/A')}\n"
                f"📟 Sensor: {patient.get('user_information', {}).get('ID_of_the_sensor', 'N/A')}\n"
                f"🩸 Glucose Thresholds:\n"
                f"  - Normal: {patient.get('threshold_parameters', {}).get('target_glucose_level_normal', 'N/A')}\n"
                f"  - Pre-meal: {patient.get('threshold_parameters', {}).get('target_glucose_level_excersise_premeal', 'N/A')}\n"
                f"  - Post-meal: {patient.get('threshold_parameters', {}).get('target_glucose_level_excersise_postmeal', 'N/A')}\n"
                f"💉 Max Insulin: {patient.get('threshold_parameters', {}).get('max_daily_amount_insulin', 'N/A')}\n"
                f"📊 ThingSpeak Info:\n"
                f"  - API Keys: {thingspeak_info.get('apikeys', 'N/A')}\n"
                f"  - Channel: {thingspeak_info.get('channel', 'N/A')}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except requests.RequestException as e:
            logger.error(f"Error fetching patient: {e}")
            await query.edit_message_text("❌ Service unavailable. Try again later.")

    async def handle_patient_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data 
        
        if data.startswith("edit_"):
            patient_id = data.replace("edit_", "")
            context.user_data['edit_patient'] = patient_id
            return await self.edit_patient_info(update, context)

        elif data.startswith("reports_"):
            patient_id = data.replace("reports_", "")
            report_url = f"https://your-report-service.com/reports/{patient_id}"
            await query.edit_message_text(
                f"📊 Patient reports available at:\n{report_url}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Open Report", url=report_url)],
                    [InlineKeyboardButton("🔙 Back", callback_data="my_patients")]
                ])
            )

        elif data.startswith("delete_"):
            patient_id = data.replace("delete_", "")
            keyboard = [
                [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"confirm_delete_{patient_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data="my_patients")]
            ]
            await query.edit_message_text(
                "⚠️ Are you sure you want to delete this patient?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif data.startswith("confirm_delete_"):
            patient_id = data.replace("confirm_delete_", "")
            try:
                response = requests.delete(f"{self.catalog_url}/patients/{patient_id}")
                if response.status_code == 200:
                    await query.edit_message_text("✅ Patient successfully deleted.")
                else:
                    await query.edit_message_text("❌ Failed to delete patient.")
            except Exception as e:
                logger.error(f"Error deleting patient: {e}")
                await query.edit_message_text("❌ Service error. Try again.")
        
        
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == "register_patient":
            await self.start_patient_registration(update, context)
        elif query.data in ["my_patients", "all_patients"]:
            await self.show_patients(update, context)
        elif query.data.startswith("patient_"):
            await self.show_patient_options(update, context)
        elif query.data.startswith("edit_"):
            await self.start_editing(update, context)
        elif query.data.startswith("reports_"):
            patient_id = query.data.replace("reports_", "")
            report_url = f"https://your-report-service.com/reports/{patient_id}"
            await query.edit_message_text(
                f"📊 Patient reports available at:\n{report_url}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Open Report", url=report_url)],
                    [InlineKeyboardButton("🔙 Back", callback_data=f"patient_{patient_id}")]
                ])
            )
        elif query.data.startswith("delete_"):
            patient_id = query.data.replace("delete_", "")
            keyboard = [
                [InlineKeyboardButton("✅ Confirm Delete", callback_data=f"confirm_delete_{patient_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"patient_{patient_id}")]
            ]
            await query.edit_message_text(
                "⚠️ Are you sure you want to delete this patient?",
                reply_markup=InlineKeyboardMarkup(keyboard))
        elif query.data.startswith("confirm_delete_"):
            patient_id = query.data.replace("confirm_delete_", "")
            try:
                response = requests.delete(f"{self.catalog_url}/patients/{patient_id}")
                if response.status_code == 200:
                    await query.edit_message_text("✅ Patient successfully deleted.")
                else:
                    await query.edit_message_text("❌ Failed to delete patient.")
            except Exception as e:
                logger.error(f"Error deleting patient: {e}")
                await query.edit_message_text("❌ Service error. Try again.")
        elif query.data == "list_doctors":
            await self.list_doctors(update, context)
        elif query.data == "refresh":
            # Check if user is master doctor
            chat_id = query.message.chat.id
            response = requests.get(
                f"{self.catalog_url}/doctors",
                params={"telegram_chat_id": chat_id},
                timeout=5
            )
            is_master = False
            if response.status_code == 200 and response.json():
                is_master = (response.json()[0].get("role") == "MasterDoctor")
            
            await query.edit_message_text(
                "🔄 Menu refreshed:",
                reply_markup=self.main_menu(is_master))
        elif query.data == "back_to_menu":
            chat_id = query.message.chat.id
            try:
                response = requests.get(
                    f"{self.catalog_url}/doctors",
                    params={"telegram_chat_id": chat_id},
                    timeout=5
                )
                if response.status_code == 200 and response.json():
                    doctor = response.json()[0]
                    is_master = (doctor.get("role") == "MasterDoctor")
                    await query.edit_message_text(
                        text=f"👋 Welcome back, {doctor['userName']}! What would you like to do?",
                        reply_markup=self.main_menu(is_master)
                    )
                else:
                    await query.edit_message_text("⚠️ Could not retrieve doctor info.")
            except Exception as e:
                logger.error(f"Error on back_to_menu: {e}")
                await query.edit_message_text("❌ Service error. Try again.")
        else:
            await query.edit_message_text("Unknown command. Please try again.")
    
    # --- Aditional    
    async def list_doctors(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        try:
            response = requests.get(f"{self.catalog_url}/doctors")
            if response.status_code != 200:
                await query.edit_message_text("❌ Could not fetch doctors list")
                return
                
            doctors = response.json()
            message = "👨⚕️ Registered Doctors:\n\n"
            
            for doctor in doctors:
                role = doctor.get("role", "Doctor")
                message += f"- {doctor.get('userName', 'Unknown')} ({role})\n"
            
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")]
                ])
            )
            
        except requests.RequestException as e:
            logger.error(f"Error fetching doctors: {e}")
            await query.edit_message_text("❌ Service unavailable. Try again later.")
            
    # START EDIT CONVERSATION
    async def edit_patient_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        patient_id = query.data.replace("edit_", "")
        context.user_data['editing_patient'] = patient_id

        try:
            # Load patient data
            response = requests.get(f"{self.catalog_url}/patients/{patient_id}")
            if response.status_code == 200:
                patient = response.json()
                context.user_data['current_patient'] = patient
            else:
                await query.edit_message_text("❌ Could not load patient data")
                return ConversationHandler.END

            # Show edit menu directly
            await query.edit_message_text(
                f"✏️ Editing patient: {patient.get('user_information', {}).get('userName', patient_id)}",
                reply_markup=self.get_edit_menu(patient_id)
            )
            return EDIT_CHOICE

        except requests.RequestException as e:
            logger.error(f"Error loading patient data: {e}")
            await query.edit_message_text("❌ Service unavailable. Try again later.")
            return ConversationHandler.END
    
    def get_edit_menu(self, patient_id):
        """Generate the edit menu for a patient"""
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Name", callback_data=f"edit_name_{patient_id}")],
            [InlineKeyboardButton("📅 Age", callback_data=f"edit_age_{patient_id}")],
            [InlineKeyboardButton("📟 Sensor ID", callback_data=f"edit_sensor_{patient_id}")],
            [InlineKeyboardButton("🩸 Glucose Thresholds", callback_data=f"edit_glucose_{patient_id}")],
            [InlineKeyboardButton("💉 Max Insulin", callback_data=f"edit_insulin_{patient_id}")],
            [InlineKeyboardButton("📊 ThingSpeak Info", callback_data=f"edit_thingspeak_{patient_id}")],  # New button
            [InlineKeyboardButton("✅ Finish Editing", callback_data=f"finish_edit_{patient_id}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"patient_{patient_id}")]
        ])
        
    async def start_editing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        patient_id = query.data.replace("edit_", "")
        context.user_data['editing_patient'] = patient_id
        
        # Load patient data if not already loaded
        if 'current_patient' not in context.user_data:
            try:
                response = requests.get(f"{self.catalog_url}/patients/{patient_id}")
                if response.status_code == 200:
                    context.user_data['current_patient'] = response.json()
            except requests.RequestException as e:
                logger.error(f"Error loading patient data: {e}")
                await query.edit_message_text("❌ Could not load patient data")
                return ConversationHandler.END
        
        await query.edit_message_text(
            "✏️ What would you like to edit?",
            reply_markup=self.get_edit_menu(patient_id)
        )
        return EDIT_CHOICE


    async def edit_choice_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        data = query.data
        patient_id = context.user_data['editing_patient']
        
        try:
            if data.startswith("edit_name_"):
                await query.edit_message_text("✏️ Enter new name for the patient:")
                context.user_data['edit_field'] = 'name'
                return EDIT_VALUE
                
            elif data.startswith("edit_age_"):
                await query.edit_message_text("📅 Enter new age for the patient:")
                context.user_data['edit_field'] = 'age'
                return EDIT_VALUE
                
            elif data.startswith("edit_sensor_"):
                await query.edit_message_text("📟 Enter new sensor ID for the patient:")
                context.user_data['edit_field'] = 'sensor'
                return EDIT_VALUE
                
            elif data.startswith("edit_glucose_"):
                # Get current values
                patient = context.user_data.get('current_patient', {})
                thresholds = patient.get('threshold_parameters', {})
                
                await query.edit_message_text(
                    "🩸 Enter new glucose thresholds in format:\n"
                    "Normal Pre-meal Post-meal\n\n"
                    f"Current values: {thresholds.get('target_glucose_level_normal', 'N/A')} "
                    f"{thresholds.get('target_glucose_level_excersise_premeal', 'N/A')} "
                    f"{thresholds.get('target_glucose_level_excersise_postmeal', 'N/A')}\n\n"
                    "Example: 100 90 120"
                )
                context.user_data['edit_field'] = 'glucose_thresholds'
                return EDIT_VALUE
                
            elif data.startswith("edit_insulin_"):
                await query.edit_message_text("💉 Enter new maximum daily insulin amount:")
                context.user_data['edit_field'] = 'insulin_max'
                return EDIT_VALUE
                
            elif data.startswith("edit_thingspeak_"):  # New case
                patient = context.user_data.get('current_patient', {})
                thingspeak = patient.get('thingspeak_info', {})
                
                await query.edit_message_text(
                    "📊 Enter new ThingSpeak info in format:\n"
                    "API_KEY CHANNEL_ID\n\n"
                    f"Current values:\n"
                    f"API Keys: {thingspeak.get('apikeys', [])}\n"
                    f"Channel: {thingspeak.get('channel', '')}\n\n"
                    "Example: ABC123 987654"
                )
                context.user_data['edit_field'] = 'thingspeak_info'
                return EDIT_VALUE
                
            elif data.startswith("finish_edit_"):
                return await self.finish_editing(update, context)
                
            elif data.startswith("patient_"):
                return await self.show_patient_options(update, context)
                
            else:
                await query.edit_message_text("Unknown command. Please try again.")
                return EDIT_CHOICE
                
        except Exception as e:
            logger.error(f"Error in edit_choice_handler: {e}")
            await query.edit_message_text("❌ An error occurred. Please try again.")
            return EDIT_CHOICE

    async def handle_edit_value(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        new_value = update.message.text
        field = context.user_data['edit_field']
        patient_id = context.user_data['editing_patient']
        patient = context.user_data.get('current_patient', {})
        
        try:
            if field == 'name':
                patient['user_information']['userName'] = new_value
            elif field == 'age':
                patient['user_information']['age'] = new_value
            elif field == 'sensor':
                patient['user_information']['ID_of_the_sensor'] = new_value
            elif field == 'glucose_thresholds':
                # Parse three values from input
                try:
                    normal, premeal, postmeal = map(float, new_value.split())
                    patient['threshold_parameters']['target_glucose_level_normal'] = normal
                    patient['threshold_parameters']['target_glucose_level_excersise_premeal'] = premeal
                    patient['threshold_parameters']['target_glucose_level_excersise_postmeal'] = postmeal
                except ValueError:
                    await update.message.reply_text("❌ Invalid format. Please enter three numbers separated by spaces.")
                    return EDIT_VALUE
            elif field == 'insulin_max':
                patient['threshold_parameters']['max_daily_amount_insulin'] = float(new_value)
            elif field == 'thingspeak_info':  # New case
                try:
                    # Expecting format: API_KEY CHANNEL_ID
                    parts = new_value.split()
                    if len(parts) != 2:
                        raise ValueError("Need exactly 2 values")
                    
                    api_key, channel_id = parts
                    patient['thingspeak_info'] = {
                        "apikeys": [api_key],
                        "channel": channel_id
                    }
                except ValueError:
                    await update.message.reply_text("❌ Invalid format. Please enter API key and channel ID separated by space.")
                    return EDIT_VALUE
            
            context.user_data['current_patient'] = patient
            
            await update.message.reply_text(
                f"✅ {field.replace('_', ' ').title()} updated successfully!",
                reply_markup=self.get_edit_menu(patient_id)
            )
            return EDIT_CHOICE
            
        except Exception as e:
            logger.error(f"Error in handle_edit_value: {e}")
            await update.message.reply_text("❌ Invalid input. Please try again.")
            return EDIT_VALUE

    async def finish_editing(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        patient_id = context.user_data['editing_patient']
        patient = context.user_data['current_patient']
        
        try:
            # Send the updated patient data to the catalog
            response = requests.put(
                f"{self.catalog_url}/patients/{patient_id}",
                json=patient,
                timeout=10
            )
            
            if response.status_code == 200:
                await query.edit_message_text(
                    "✅ Patient information updated successfully!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back to Patient", callback_data=f"patient_{patient_id}")],
                        [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_menu")]
                    ])
                )
            else:
                await query.edit_message_text("❌ Failed to update patient in catalog.")
        except requests.RequestException as e:
            logger.error(f"Error updating patient: {e}")
            await query.edit_message_text("❌ Service error while updating patient.")
        
        # Clean up
        context.user_data.pop('editing_patient', None)
        context.user_data.pop('current_patient', None)
        context.user_data.pop('edit_field', None)
        
        return ConversationHandler.END


            
    async def update_service_timestamp(self):
        while True:
            try:
                requests.put(
                    f"{self.catalog_url}/services/{self.service_id}",
                    json={"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                    timeout=5
                )
            except requests.RequestException:
                logger.warning("Failed to update service timestamp")
            await asyncio.sleep(300)  # Update every 5 minutes
    
    def run(self):
        # Only start if we have catalog connection
        if not self.ensure_catalog_connection():
            logger.error("Cannot start bot without Catalog connection")
            return
        
        # Doctor registration handler
        reg_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_name)],
                ASK_ROLE: [CallbackQueryHandler(self.receive_role)]
            },
            fallbacks=[]
        )
        
        # Patient registration handler
        patient_reg_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_patient_registration, pattern="^register_patient$")],
            states={
                PATIENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_patient_name)],
                PATIENT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_patient_id)],
                AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.ask_patient_age)],
                SENSOR_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_sensor_id)],
                GLUCOSE_NORMAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_glucose_normal)],
                GLUCOSE_PREMEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_glucose_premeal)],
                GLUCOSE_POSTMEAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_glucose_postmeal)],
                INSULIN_MAX: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.complete_patient_registration)]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_registration),
                CallbackQueryHandler(self.cancel_registration, pattern="^cancel$")
            ]
        )
        
        #
        edit_handler = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.start_editing, pattern="^edit_")],
            states={
                EDIT_CHOICE: [CallbackQueryHandler(self.edit_choice_handler)],
                EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_edit_value)]
            },
            fallbacks=[
                CommandHandler('cancel', self.cancel_registration),
                CallbackQueryHandler(self.finish_editing, pattern="^finish_edit_")
            ]
        )

        # Register handlers
        self.application.add_handler(reg_handler)
        self.application.add_handler(patient_reg_handler)
        self.application.add_handler(edit_handler)
        self.application.add_handler(CallbackQueryHandler(self.button_handler))
        
        logger.info("Starting Doctor Bot...")
        self.application.run_polling()


if __name__ == "__main__":
    import time
    time.sleep(10)  # Allow time for any previous logs to flush
    logger.info("Starting Doctor Bot...")
    try:
        with open("settings.json") as f:
            config = json.load(f)
            
        bot = DoctorBot(
            token=config["telegram_token"],
            catalog_url=config["catalog_url"]
        )
        bot.run()
    except FileNotFoundError:
        logger.error("settings.json file not found")
    except json.JSONDecodeError:
        logger.error("Error parsing settings.json")
    except KeyError as e:
        logger.error(f"Missing required key in settings.json: {e}")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
