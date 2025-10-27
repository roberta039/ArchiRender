import streamlit as st
import stripe

# Setează cheia Stripe (folosește cheia ta secretă)
stripe.api_key = "sk_test_your_key_here"

# ----------------------------
# HEADER
# ----------------------------
st.set_page_config(
    page_title="ArchiRender",
    page_icon="🏛️",
    layout="centered",
)

st.title("🏛️ ArchiRender")
st.markdown("""
Bine ai venit la **ArchiRender**!  
Aici poți vizualiza și gestiona proiectele tale arhitecturale și testa plăți demo.
""")

# ----------------------------
# SECTIUNE PROIECTE
# ----------------------------
st.header("Proiecte Demo")
projects = ["Casa modernă", "Birou corporativ", "Apartament minimal"]
selected_project = st.selectbox("Alege un proiect", projects)
st.write(f"Ai selectat proiectul: **{selected_project}**")

# ----------------------------
# SECTIUNE PLATA DEMO
# ----------------------------
st.header("Plată demo")
amount = st.number_input("Sumă (în cenți)", min_value=100, value=500, step=100)
currency = st.selectbox("Monedă", ["usd", "eur"])

if st.button("Plătește"):
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount),
            currency=currency
        )
        st.success(f"Payment Intent creat cu ID: {payment_intent['id']}")
    except Exception as e:
        st.error(f"A apărut o eroare: {e}")

# ----------------------------
# SECTIUNE INFO
# ----------------------------
st.markdown("---")
st.info("Aceasta este o aplicație demo ArchiRender folosind Streamlit și Stripe. "
        "Nu folosi cheia secretă reală pentru demo-uri publice!")

# ----------------------------
# FOOTER
# ----------------------------
st.caption("© 2025 ArchiRender. Toate drepturile rezervate.")
