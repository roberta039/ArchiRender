import streamlit as st
import json
import uuid
from datetime import datetime, timedelta
import os

# Folder pentru salvarea comenzilor (simulare DB)
DB_FILE = "orders_test.json"
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w") as f:
        json.dump([], f)

st.set_page_config(page_title="ArchiRender", layout="centered")
st.title("ArchiRender - Test Local")
st.markdown("Simulare aplicație de randare. Panou admin inclus.")

# Functii
def calc_price(resolution: str):
    if resolution == "2-4K":
        return 70
    if resolution == "4-6K":
        return 100
    if resolution == "8K":
        return 120
    return 0

def calc_deadline(num_renders: int):
    return 3 * ((num_renders-1)//3 + 1)

def load_orders():
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_orders(orders):
    with open(DB_FILE, "w") as f:
        json.dump(orders, f, indent=2)

def send_email_simulation(to_email, subject, message):
    st.info(f"EMAIL SIMULATION → To: {to_email}, Subject: {subject}\n{message}")

# Tabs
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
            uploaded_file = st.file_uploader("Alege fișierul (.zip, .blend, ...)")
        else:
            external_link = st.text_input("Link descărcare (Google Drive/WeTransfer)")

        resolution = st.selectbox("Rezoluție", ["2-4K", "4-6K", "8K"])
        num_renders = st.slider("Număr randări", 1, 30, 1)
        note = st.text_area("Observații (opțional)")
        submit = st.form_submit_button("Vezi preț și plătește")

    if submit:
        if not name or not email:
            st.error("Completează nume și email")
        elif upload_mode == "Încarcă fișier" and not uploaded_file:
            st.error("Încarcă fișierul sau alege link")
        elif upload_mode == "Dă un link" and not external_link:
            st.error("Introdu link descărcare")
        else:
            price = calc_price(resolution)
            deadline_days = calc_deadline(num_renders)
            due_date = (datetime.utcnow() + timedelta(days=deadline_days)).date().isoformat()
            order_id = str(uuid.uuid4())

            file_name = uploaded_file.name if uploaded_file else ""
            # Salvează comanda în "DB"
            orders = load_orders()
            orders.append({
                "order_id": order_id,
                "name": name,
                "email": email,
                "upload_mode": upload_mode,
                "file_name": file_name,
                "external_link": external_link,
                "resolution": resolution,
                "num_renders": num_renders,
                "price": price,
                "deadline_days": deadline_days,
                "due_date": due_date,
                "note": note,
                "status": "pending"
            })
            save_orders(orders)

            st.success(f"Comandă creată: {order_id}")
            st.write(f"Preț: {price} EUR — Termen: {deadline_days} zile (până {due_date})")

            # Simulare email
            send_email_simulation(email, "Comanda ta ArchiRender", f"Comanda {order_id} înregistrată. Termen: {deadline_days} zile")

# -----------------------
# Tab Admin
# -----------------------
with tabs[1]:
    st.header("Panou Admin")
    pwd = st.text_input("Parolă admin", type="password")
    if pwd != "admin123":
        st.warning("Introdu parola corectă")
    else:
        st.success("Acces activat")
        orders = load_orders()
        for o in orders:
            with st.expander(f"#{o['order_id']} — {o['name']} — {o['status']}"):
                st.write(o)
                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("Marchează ca plătită", key=f"paid_{o['order_id']}"):
                        o["status"] = "paid"
                        save_orders(orders)
                        send_email_simulation(o["email"], "Plata înregistrată", f"Comanda {o['order_id']} a fost plătită")
                        st.experimental_rerun()
                with col2:
                    link_final = st.text_input("Link randări finale", value=o.get("final_link",""), key=f"link_{o['order_id']}")
                    if st.button("Trimite link client", key=f"send_{o['order_id']}"):
                        o["final_link"] = link_final
                        o["status"] = "delivered"
                        save_orders(orders)
                        send_email_simulation(o["email"], "Randările tale sunt gata", f"Link descărcare: {link_final}")
                        st.experimental_rerun()
                with col3:
                    if st.button("Șterge comandă", key=f"del_{o['order_id']}"):
                        orders.remove(o)
                        save_orders(orders)
                        st.experimental_rerun()
