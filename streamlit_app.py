import streamlit as st
import pandas as pd
from datetime import datetime

st.title("🎨 Serviciu Rendering pentru Studenți")

with st.form("comanda_rendering"):
    email = st.text_input("Email")
    link_proiect = st.text_input("Link descărcare proiect")
    cerinte = st.text_area("Cerințe speciale")
    submitted = st.form_submit_button("Trimite comanda")
    
    if submitted:
        # Salvează într-un CSV
        new_order = {
            'email': email,
            'link': link_proiect,
            'cerinte': cerinte,
            'data': datetime.now(),
            'status': 'în așteptare'
        }
        
        df = pd.DataFrame([new_order])
        df.to_csv('comenzi.csv', mode='a', header=False, index=False)
        st.success("Comanda a fost înregistrată! Te voi contacta în curând.")
