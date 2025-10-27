import streamlit as st
import stripe
import os
import uuid
from datetime import datetime, timedelta
from supabase import create_client, Client
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# -----------------------
# Variabile de mediu
# -----------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY")
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

# -----------------------
# Initialize Stripe
# -----------------------
stripe.api_key = STRIPE_SECRET_KEY

# -----------------------
# Initialize Supabase
# -----------------------
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------
# Funcții
# -----------------------
def calc_price(resolution):
    if resolution == "2-4K":
        return 70
    elif resolution == "4-6K":
        return 100
    elif resolution == "8K":
        return 120
    return 0

def calc_deadline(num_renders):
    return 3 * ((num_renders-1)//3 + 1)

def send_email(to_email, subject, content):
    if not SENDGRID_API_KEY:
        st.warning(f"EMAIL SIMULATION → To: {to_email}, Subject: {subject}")
        return
    message = Mail(
        from_email='no-reply@archirender.com',
        to_emails=to_email,
        subject=subject,
        html_content=content
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        sg.send(message)
    except Exception as e:
        st.error(f"Eroare SendGrid: {str(e)}")

# -----------------------
# App Streamlit
# -----------------------
st.set_page_config(page_title="ArchiRender", layout="centered")
st.title("ArchiRender - Test Stripe + Supabase + SendGrid")

tabs
