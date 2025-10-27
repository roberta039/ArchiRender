import streamlit as st
import pandas as pd
import numpy as np
import requests
import smtplib
import os
import json
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sqlite3
from sqlite3 import Error
import time
import io
from pathlib import Path
from dotenv import load_dotenv

# Încarcă variabilele de mediu
load_dotenv()

# Configurare pagină
st.set_page_config(
    page_title="Rendering Service ARH",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Stiluri CSS personalizate
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .status-pending { background-color: #fff3cd; padding: 10px; border-radius: 5px; }
    .status-processing { background-color: #cce5ff; padding: 10px; border-radius: 5px; }
    .status-completed { background-color: #d4edda; padding: 10px; border-radius: 5px; }
    .urgent { border-left: 5px solid #dc3545; padding-left: 10px; }
</style>
""", unsafe_allow_html=True)

class RenderingService:
    def __init__(self):
        self.init_database()
    
    def init_database(self):
        """Initializează baza de date SQLite"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_name TEXT NOT NULL,
                    email TEXT NOT NULL,
                    project_link TEXT NOT NULL,
                    software TEXT NOT NULL,
                    deadline TEXT,
                    requirements TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    download_link TEXT,
                    price_estimate REAL,
                    is_urgent BOOLEAN DEFAULT FALSE,
                    file_size_mb REAL DEFAULT 0
                )
            ''')
            conn.commit()
            conn.close()
        except Error as e:
            st.error(f"❌ Eroare la initializarea bazei de date: {e}")
    
    def add_order(self, order_data):
        """Adaugă o comandă nouă în baza de date"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO orders 
                (student_name, email, project_link, software, deadline, requirements, is_urgent, file_size_mb)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_data['student_name'],
                order_data['email'],
                order_data['project_link'],
                order_data['software'],
                order_data['deadline'],
                order_data['requirements'],
                order_data.get('is_urgent', False),
                order_data.get('file_size_mb', 0)
            ))
            
            order_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Încearcă să trimiți email de confirmare (opțional)
            try:
                self.send_confirmation_email(order_data, order_id)
            except Exception as e:
                st.info("ℹ️ Comanda a fost salvată, dar notificarea email nu a putut fi trimisă.")
            
            return order_id
        except Error as e:
            st.error(f"❌ Eroare la adăugarea comenzii: {e}")
            return None
    
    def send_confirmation_email(self, order_data, order_id):
        """Trimite email de confirmare (configurabil)"""
        try:
            # Verifică dacă email-ul este activat
            email_enabled = os.getenv('EMAIL_ENABLED', 'False').lower() == 'true'
            
            if not email_enabled:
                return
                
            smtp_server = os.getenv('SMTP_SERVER', '')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            email_from = os.getenv('EMAIL_FROM', '')
            email_password = os.getenv('EMAIL_PASSWORD', '')
            
            if not all([smtp_server, email_from, email_password]):
                return
            
            # Creează mesajul
            msg = MIMEMultipart()
            msg['From'] = email_from
            msg['To'] = order_data['email']
            msg['Subject'] = f"Comanda Rendering #{order_id} - Confirmare"
            
            body = f"""
            Bună {order_data['student_name']},
            
            Comanda ta pentru rendering a fost înregistrată cu succes!
            
            📋 Detalii comanda:
            - ID Comanda: #{order_id}
            - Software: {order_data['software']}
            - Deadline: {order_data['deadline']}
            - Cerințe: {order_data['requirements'] or 'Niciune specificate'}
            - Status: În așteptare
            
            Vei fi contactat în curând cu o estimare de preț și timp.
            
            Mulțumim,
            Echipa Rendering Service ARH
            """
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Conectează și trimite email
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg)
            server.quit()
            
        except Exception as e:
            st.warning(f"⚠️ Emailul nu a putut fi trimis: {e}")
    
    def get_orders(self, status=None):
        """Returnează toate comenzile"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            
            if status:
                df = pd.read_sql_query(
                    "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", 
                    conn, params=[status]
                )
            else:
                df = pd.read_sql_query(
                    "SELECT * FROM orders ORDER BY created_at DESC", 
                    conn
                )
            
            conn.close()
            return df
        except Error as e:
            st.error(f"❌ Eroare la citirea comenzilor: {e}")
            return pd.DataFrame()
    
    def update_order_status(self, order_id, status, download_link=None):
        """Actualizează statusul unei comenzi"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            if download_link:
                cursor.execute('''
                    UPDATE orders 
                    SET status = ?, completed_at = CURRENT_TIMESTAMP, download_link = ?
                    WHERE id = ?
                ''', (status, download_link, order_id))
            else:
                cursor.execute('''
                    UPDATE orders 
                    SET status = ? 
                    WHERE id = ?
                ''', (status, order_id))
            
            conn.commit()
            conn.close()
            return True
        except Error as e:
            st.error(f"❌ Eroare la actualizarea comenzii: {e}")
            return False

def main():
    st.markdown('<h1 class="main-header">🏗️ Rendering Service ARH</h1>', unsafe_allow_html=True)
    st.markdown("### Serviciu profesional de rendering pentru studenții la arhitectură")
    
    # Inițializează serviciul
    service = RenderingService()
    
    # Sidebar pentru navigare
    with st.sidebar:
        st.markdown("""
        <div style="text-align: center;">
            <h1>🏗️</h1>
            <h3>Rendering Service</h3>
        </div>
        """, unsafe_allow_html=True)
        st.title("Navigare")
        menu = st.radio("Alege secțiunea:", [
            "📝 Comandă Rendering", 
            "📊 Dashboard Comenzi",
            "⚙️ Administrare",
            "ℹ️ Despre Serviciu"
        ])
    
    # Secțiunea de comandă nouă
    if menu == "📝 Comandă Rendering":
        st.header("📝 Comandă Rendering Nouă")
        
        with st.form("comanda_rendering", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                student_name = st.text_input("Nume complet*")
                email = st.text_input("Email*")
                project_link = st.text_area("Link descărcare proiect*", 
                                          placeholder="https://drive.google.com/... sau Wetransfer, Dropbox, etc.")
                software = st.selectbox(
                    "Software utilizat*",
                    ["SketchUp", "Revit", "3ds Max", "Blender", "Archicad", "Lumion", "Altul"]
                )
            
            with col2:
                deadline = st.date_input("Deadline preferat", 
                                       min_value=datetime.now().date(),
                                       value=datetime.now().date() + timedelta(days=3))
                
                is_urgent = st.checkbox("🔴 Comandă urgentă (+50% cost)")
                file_size = st.number_input("Dimensiunea estimată a proiectului (MB)", 
                                          min_value=0, value=100, step=10)
                
                requirements = st.text_area("Cerințe specifice rendering", 
                                          placeholder="Rezoluție, calitate, elemente speciale, etc.")
            
            st.markdown("** * Câmpuri obligatorii*")
            
            submitted = st.form_submit_button("📤 Trimite Comanda")
            
            if submitted:
                if not all([student_name, email, project_link, software]):
                    st.error("⚠️ Te rog completează toate câmpurile obligatorii!")
                else:
                    with st.spinner("Se salvează comanda..."):
                        order_data = {
                            'student_name': student_name,
                            'email': email,
                            'project_link': project_link,
                            'software': software,
                            'deadline': deadline.strftime("%Y-%m-%d"),
                            'requirements': requirements,
                            'is_urgent': is_urgent,
                            'file_size_mb': file_size
                        }
                        
                        order_id = service.add_order(order_data)
                        if order_id:
                            st.success(f"🎉 Comanda a fost înregistrată cu succes! ID: #{order_id}")
                            st.balloons()
                            
                            st.info("""
                            **📋 Următorii pași:**
                            1. Vei primi un email de confirmare (dacă este configurat)
                            2. Te voi contacta în maxim 24h cu estimarea de preț și timp
                            3. După confirmare, voi procesa rendering-ul
                            4. Vei primi link-ul de download când este gata
                            """)
    
    # Dashboard comenzi
    elif menu == "📊 Dashboard Comenzi":
        st.header("📊 Dashboard Comenzi")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("🔄 Actualizează Datele"):
                st.rerun()
        
        with col2:
            status_filter = st.selectbox("Filtrează după status:", 
                                       ["Toate", "pending", "processing", "completed"])
        
        with col3:
            # Export funcționalitate
            orders_df = service.get_orders()
            if not orders_df.empty:
                csv = orders_df.to_csv(index=False)
                st.download_button(
                    "📥 Exportă CSV",
                    data=csv,
                    file_name=f"comenzi_rendering_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
        
        # Afișează comenzile
        orders_df = service.get_orders(None if status_filter == "Toate" else status_filter)
        
        if orders_df.empty:
            st.info("📭 Nu există comenzi în sistem.")
        else:
            st.metric("Total Comenzi", len(orders_df))
            
            for _, order in orders_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.subheader(f"Comanda #{order['id']} - {order['student_name']}")
                        st.write(f"**Software:** {order['software']}")
                        st.write(f"**Deadline:** {order['deadline']}")
                        if order['requirements']:
                            st.write(f"**Cerințe:** {order['requirements']}")
                    
                    with col2:
                        status_color = {
                            'pending': 'status-pending',
                            'processing': 'status-processing', 
                            'completed': 'status-completed'
                        }.get(order['status'], '')
                        
                        st.markdown(f'<div class="{status_color}"><strong>Status:</strong> {order["status"].upper()}</div>', 
                                  unsafe_allow_html=True)
                        
                        if order['is_urgent']:
                            st.markdown('<div class="urgent"><strong>🔴 URGENT</strong></div>', 
                                      unsafe_allow_html=True)
                    
                    with col3:
                        st.write(f"**Data:** {order['created_at'][:10]}")
                        if order['download_link']:
                            st.markdown(f"[📥 Download]({order['download_link']})")
                    
                    st.divider()
    
    # Secțiunea de administrare
    elif menu == "⚙️ Administrare":
        st.header("⚙️ Administrare Comenzi")
        
        st.info("Această secțiune este pentru administrator.")
        
        # Parolă simplă pentru demo
        admin_password = st.text_input("Parolă administrare:", type="password", value="admin123")
        
        if admin_password == "admin123":  # Poți schimba parola
            st.success("✅ Acces administrativ acordat")
            
            orders_df = service.get_orders()
            
            if not orders_df.empty:
                st.subheader("Gestionare Comenzi")
                for _, order in orders_df.iterrows():
                    with st.expander(f"Comanda #{order['id']} - {order['student_name']} ({order['status']})"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**Email:** {order['email']}")
                            st.write(f"**Link proiect:** {order['project_link']}")
                            st.write(f"**Dimensiune:** {order['file_size_mb']} MB")
                            st.write(f"**Urgent:** {'Da' if order['is_urgent'] else 'Nu'}")
                        
                        with col2:
                            new_status = st.selectbox(
                                f"Schimbă status",
                                ["pending", "processing", "completed"],
                                index=["pending", "processing", "completed"].index(order['status']),
                                key=f"status_{order['id']}"
                            )
                            
                            download_link = st.text_input(
                                "Link download",
                                value=order['download_link'] or "",
                                placeholder="https://drive.google.com/...",
                                key=f"download_{order['id']}"
                            )
                            
                            if st.button(f"Actualizează #{order['id']}", key=f"btn_{order['id']}"):
                                if service.update_order_status(order['id'], new_status, download_link or None):
                                    st.success(f"✅ Comanda #{order['id']} actualizată!")
                                    time.sleep(1)
                                    st.rerun()
            
            # Statistici
            st.subheader("📈 Statistici")
            col1, col2, col3, col4 = st.columns(4)
            
            total_orders = len(orders_df)
            pending_orders = len(orders_df[orders_df['status'] == 'pending'])
            processing_orders = len(orders_df[orders_df['status'] == 'processing'])
            completed_orders = len(orders_df[orders_df['status'] == 'completed'])
            
            with col1:
                st.metric("Total Comenzi", total_orders)
            with col2:
                st.metric("În Așteptare", pending_orders)
            with col3:
                st.metric("În Procesare", processing_orders)
            with col4:
                st.metric("Finalizate", completed_orders)
        
        elif admin_password and admin_password != "admin123":
            st.error("❌ Parolă incorectă!")
    
    # Secțiunea Despre
    else:
        st.header("ℹ️ Despre Serviciu")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🏆 Servicii Oferte")
            st.markdown("""
            - ✅ **Rendering architectural** de înaltă calitate
            - ✅ **Animations și walkthroughs**
            - ✅ **Post-processing și editare** imagini
            - ✅ **Optimizare** setări rendering
            - ✅ **Support tehnic** pentru proiecte complexe
            """)
            
            st.subheader("🛠️ Software Suportat")
            st.markdown("""
            - **SketchUp** + V-Ray/Enscape
            - **Revit** + V-Ray/Enscape
            - **3ds Max** + Corona/V-Ray
            - **Blender** + Cycles/Eevee
            - **Lumion**
            - **Archicad**
            """)
        
        with col2:
            st.subheader("📋 Cum Funcționează")
            st.markdown("""
            1. **Comanzi** - Completezi formularul cu detaliile proiectului
            2. **Confirmare** - Primești estimare de preț și timp
            3. **Procesare** - Procesăm rendering-ul pe hardware profesional
            4. **Livrare** - Primești link download cu rezultatele
            5. **Support** - Asistență pentru eventuale modificări
            """)
            
            st.subheader("⏱️ Timpi de Procesare")
            st.markdown("""
            - **Standard:** 2-3 zile lucrătoare
            - **Urgent:** 24 de ore (+50% cost)
            - **Super-urgent:** 12 ore (+100% cost)
            *În funcție de complexitatea proiectului
            """)
        
        st.subheader("📞 Contact")
        st.write("**Email:** contact@renderingservice.ro")
        st.write("**Telefon:** +40 723 456 789")
        st.write("**Program:** Luni-Vineri, 9:00-18:00")

if __name__ == "__main__":
    main()
