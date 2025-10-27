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
# Funcții ajutătoare
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
# Config Streamlit
# -----------------------
st.set_page_config(page_title="ArchiRender", layout="centered")
st.title("ArchiRender - Render Projects Service")

tabs = st.tabs(["Plasează comandă", "Panou Admin"])

# -----------------------
# Tab Plasează comandă
# -----------------------
with tabs[0]:
    st.header("Plasează o comandă")
    with st.form("order_form"):
        name = st.text_input("Nume complet")
        email = st.text_input("Email")
        upload_mode = st.radio("Trimite fișierul", ("Încarcă fișier", "Dă un link"))
        uploaded_file = None
        external_link = ""
        if upload_mode == "Încarcă fișier":
            uploaded_file = st.file_uploader("Alege fișierul (.zip, .blend, etc.)")
        else:
            external_link = st.text_input("Link descărcare")

        resolution = st.selectbox("Rezoluție", ["2-4K", "4-6K", "8K"])
        num_renders = st.slider("Număr randări", 1, 30, 1)
        submit = st.form_submit_button("Vezi preț și plătește")

    if submit:
        if not name or not email:
            st.error("Completează nume și email")
        elif upload_mode == "Încarcă fișier" and not uploaded_file:
            st.error("Încarcă fișierul sau alege link")
        elif upload_mode == "Dă un link" and not external_link:
            st.error("Introdu link descărcare")
        else:
            price_eur = calc_price(resolution)
            deadline_days = calc_deadline(num_renders)
            due_date = (datetime.utcnow() + timedelta(days=deadline_days)).date().isoformat()
            order_id = str(uuid.uuid4())

            # -----------------------
            # Upload fișier în Supabase
            # -----------------------
            file_path = ""
            if uploaded_file:
                file_path = f"{order_id}/{uploaded_file.name}"
                res = supabase.storage.from_("uploads").upload(file_path, uploaded_file)
                if res.get("error"):
                    st.error(f"Eroare upload: {res['error']['message']}")
                else:
                    file_path = f"https://{SUPABASE_URL.replace('https://','')}/storage/v1/object/public/uploads/{file_path}"

            # -----------------------
            # Salvează comanda în Supabase
            # -----------------------
            supabase.table("orders").insert({
                "order_id": order_id,
                "name": name,
                "email": email,
                "upload_mode": upload_mode,
                "file_path": file_path,
                "external_link": external_link,
                "resolution": resolution,
                "num_renders": num_renders,
                "price_eur": price_eur,
                "deadline_days": deadline_days,
                "due_date": due_date,
                "status": "pending",
                "created_at": datetime.utcnow().isoformat()
            }).execute()

            st.success(f"Comandă creată: {order_id}")
            st.write(f"Preț: {price_eur} EUR — Termen: {deadline_days} zile (până {due_date})")

            # -----------------------
            # Stripe Checkout Test
            # -----------------------
            try:
                checkout_session = stripe.checkout.Session.create(
                    payment_method_types=['card'],
                    line_items=[{
                        'price_data': {
                            'currency': 'eur',
                            'product_data': {'name': f'Randare {resolution}'},
                            'unit_amount': price_eur * 100,
                        },
                        'quantity': 1,
                    }],
                    mode='payment',
                    success_url='http://localhost:8501?success=true',
                    cancel_url='http://localhost:8501?canceled=true',
                    metadata={
                        'order_id': order_id,
                        'name': name,
                        'email': email,
                        'resolution': resolution,
                        'num_renders': num_renders
                    }
                )
                st.markdown(f"[Plătește acum cu Stripe]({checkout_session.url})")
            except Exception as e:
                st.error(f"Eroare Stripe: {str(e)}")

            # Email confirmare
            send_email(email, "Comanda ta ArchiRender",
                       f"Comanda {order_id} a fost înregistrată. Termen: {deadline_days} zile.")

# -----------------------
# Tab Admin
# -----------------------
with tabs[1]:
    st.header("Panou Admin")
    pwd = st.text_input("Parolă admin", type="password")
    if pwd != ADMIN_PASSWORD:
        st.warning("Introdu parola corectă")
    else:
        st.success("Acces activat")
        orders = supabase.table("orders").select("*").execute().data
        for o in orders:
            with st.expander(f"#{o['order_id']} — {o['name']} — {o['status']}"):
                st.write(o)
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Marchează ca plătită", key=f"paid_{o['order_id']}"):
                        supabase.table("orders").update({"status":"paid", "paid_at":datetime.utcnow().isoformat()}).eq("order_id", o['order_id']).execute()
                        send_email(o['email'], "Plata înregistrată", f"Comanda {o['order_id']} a fost plătită")
                        st.experimental_rerun()
                with col2:
                    link_final = st.text_input("Link randări finale", value=o.get("final_link",""), key=f"link_{o['order_id']}")
                    if st.button("Trimite link client", key=f"send_{o['order_id']}"):
                        supabase.table("orders").update({"final_link":link_final, "status":"delivered", "delivered_at":datetime.utcnow().isoformat()}).eq("order_id", o['order_id']).execute()
                        send_email(o['email'], "Randările tale sunt gata", f"Link descărcare: {link_final}")
                        st.experimental_rerun()
                with col3:
                    if st.button("Șterge comandă", key=f"del_{o['order_id']}"):
                        supabase.table("orders").delete().eq("order_id", o['order_id']).execute()
                        st.experimental_rerun()
