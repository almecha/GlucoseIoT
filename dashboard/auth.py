import streamlit as st
import streamlit_authenticator as st_auth
import yaml
from yaml.loader import SafeLoader

class GlucoseIoTAuth:
    def __init__(self, config_file_path):
        """
        Initializes the Streamlit authenticator with the config file.
        """
        self.config_file_path = config_file_path
        self.authenticator = self._init_authenticator()
        
        self.columns = st.columns(6, gap="large")  # Create six columns for layout

    # -------------------- Initialization Methods --------------------
    def _init_authenticator(self):
        """
        Initializes the Streamlit authenticator with the config file.
        """
        with open(self.config_file_path, encoding='utf-8') as file:
            self.config = yaml.load(file, Loader=SafeLoader)
        
        # Pre-hashing all plain text passwords once
        st_auth.Hasher.hash_passwords(self.config['credentials'])
        
        # Creating an authenticator object
        authenticator = st_auth.Authenticate(
            self.config['credentials'],
            self.config['cookie']['name'],
            self.config['cookie']['key'],
            self.config['cookie']['expiry_days'],
            None,
            False,
            None
        )
        return authenticator

    def _save_config(self):
        """
        Saves the updated configuration to the config file.
        """
        with open(self.config_file_path, 'w', encoding='utf-8') as file:
            yaml.dump(self.config, file, default_flow_style=False, allow_unicode=True)

    # -------------------- Authentication Methods --------------------
    def login_feature(self):
        """
        Displays the login widget and handles authentication.
        """
        try:
            self.authenticator.login()
            if not st.session_state.get('authentication_status'):
                st.write("New user? Please register below.")
                self.register_button()
            if st.session_state.get('authentication_status') is False:
                st.error('Username/password is incorrect')

            self._save_config()

        except Exception as e:
            st.error(e)

    def logout_button(self):
        """
        Displays the logout button and handles logout.
        """
        if st.session_state.get('authentication_status'):
            with self.columns[-1]:
                self.authenticator.logout('Logout')

    # -------------------- Registration Methods --------------------
    def register_button(self):
        """
        Displays the register button and triggers the registration form.
        """
        if 'show_register_form' not in st.session_state:
            st.session_state['show_register_form'] = False

        if not st.session_state['show_register_form']:
            st.button('Register', on_click=self._trigger_register_form)
        else:
            self.register_form()

    def register_form(self):
        """
        Displays the registration form and handles user registration.
        """
        try:
            email_of_registered_user, \
            username_of_registered_user, \
            _ = self.authenticator.register_user()
            if email_of_registered_user:
                st.success(f'User: {username_of_registered_user} registered successfully')
                self._save_config()
        except Exception as e:
            st.error(e)

    def _trigger_register_form(self):
        st.session_state['show_register_form'] = True

    # -------------------- Password Reset Methods --------------------
    def reset_password_button(self):
        """
        Displays the reset password button and handles password reset.
        """
        if st.session_state.get('authentication_status'):
            if 'show_reset_form' not in st.session_state:
                st.session_state['show_reset_form'] = False

            if not st.session_state['show_reset_form']:
                self.columns[-2].button('Reset Password', on_click=self._trigger_reset_form)
            else:
                self.reset_password_form()

    def reset_password_form(self):
        """
        Displays the reset password form and handles password reset.
        """
        try:
            if self.authenticator.reset_password(st.session_state.get('username')):
                st.success('Password modified successfully')
                self._save_config()
        except Exception as e:
            st.error(e)

    def _trigger_reset_form(self):
        st.session_state['show_reset_form'] = True