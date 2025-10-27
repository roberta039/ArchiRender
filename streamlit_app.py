# streamlit_app.py

import streamlit as st
import altair as alt
import pandas as pd
import stripe

# --- Stripe setup ---
stripe.api_key = "sk_test_your_stripe_secret_key_here"  # înlocuiește cu cheia ta

st.set_page_config(page_title="Demo App", page_icon=":sparkles:")

st.title("Bine ai venit la Streamlit App!")
st.write("Aceasta este o aplicație demo cu Streamlit, Altair și Stripe.")

# --- Exemplu Altair chart ---
st.header("Exemplu grafic Altair")
data = pd.DataFrame({
    'Categorie': ['A', 'B', 'C', 'D'],
    'Valoare': [10, 20, 30, 40]
})

chart = alt.Chart(data).mark_bar().encode(
    x='Categorie',
    y='Valoare',
    color='Categorie'
)
st.altair_chart(chart, use_container_width=True)

# --- Exemplu Stripe Payment ---
st.header("Plată Stripe demo")
amount = st.number_input("Introdu suma în lei:", min_value=1, value=10)
if st.button("Plătește cu Stripe"):
    try:
        payment_intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # Stripe folosește cea mai mică unitate (bani în bani)
            currency='ron',
            payment_method_types=['card'],
        )
        st.success(f"PaymentIntent creat! ID: {payment_intent['id']}")
    except Exception as e:
        st.error(f"A apărut o eroare: {e}")

st.write("🎉 Totul funcționează corect!")
