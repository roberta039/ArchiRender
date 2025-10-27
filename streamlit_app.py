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
    .price-estimate { background-color: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #28a745; }
    .payment-box { background-color: #e8f5e8; padding: 20px; border-radius: 10px; border: 2px solid #28a745; }
    .countdown { background-color: #fff3cd; padding: 15px; border-radius: 8px; text-align: center; font-weight: bold; }
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
                    project_file TEXT,
                    project_link TEXT,
                    software TEXT NOT NULL,
                    resolution TEXT NOT NULL,
                    render_count INTEGER NOT NULL,
                    deadline TEXT,
                    requirements TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    download_link TEXT,
                    price_euro REAL NOT NULL,
                    payment_status TEXT DEFAULT 'pending',
                    payment_date TIMESTAMP,
                    receipt_sent BOOLEAN DEFAULT FALSE,
                    estimated_days INTEGER NOT NULL,
                    is_urgent BOOLEAN DEFAULT FALSE,
                    contact_phone TEXT,
                    faculty TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Error as e:
            st.error(f"❌ Eroare la initializarea bazei de date: {e}")
    
    def calculate_price_and_days(self, resolution, render_count, is_urgent=False):
        """Calculează prețul și timpul de livrare"""
        # Prețuri după rezoluție
        price_map = {
            "2-4K": 70,
            "4-6K": 100, 
            "8K+": 120
        }
        
        # Zile de livrare după numărul de randări
        days_map = {
            1: 3, 2: 3, 3: 3,
            4: 6, 5: 6, 6: 6, 7: 6,
            8: 9, 9: 9, 10: 9,
            11: 12, 12: 12, 13: 12,
            14: 15, 15: 15
        }
        
        # Calcul zile (din 3 în 3 peste 15)
        if render_count > 15:
            estimated_days = ((render_count - 1) // 3) * 3 + 3
        else:
            estimated_days = days_map.get(render_count, 3)
        
        # Ajustare pentru urgent
        if is_urgent:
            estimated_days = max(1, estimated_days // 2)  # Reduce timpul la jumătate
            urgent_surcharge = 0.5  # +50% pentru urgent
        else:
            urgent_surcharge = 0
        
        base_price = price_map.get(resolution, 70)
        final_price = base_price * (1 + urgent_surcharge)
        
        return round(final_price), estimated_days
    
    def add_order(self, order_data):
        """Adaugă o comandă nouă în baza de date"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO orders 
                (student_name, email, project_file, project_link, software, resolution, 
                 render_count, deadline, requirements, price_euro, estimated_days,
                 is_urgent, contact_phone, faculty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                order_data['student_name'],
                order_data['email'],
                order_data.get('project_file'),
                order_data.get('project_link'),
                order_data['software'],
                order_data['resolution'],
                order_data['render_count'],
                order_data['deadline'],
                order_data['requirements'],
                order_data['price_euro'],
                order_data['estimated_days'],
                order_data.get('is_urgent', False),
                order_data.get('contact_phone', ''),
                order_data.get('faculty', '')
            ))
            
            order_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Trimite email cu chitanță
            self.send_receipt_email(order_data, order_id)
            
            return order_id
        except Error as e:
            st.error(f"❌ Eroare la adăugarea comenzii: {e}")
            return None
    
    def send_receipt_email(self, order_data, order_id):
        """Trimite email cu chitanță și detalii comanda"""
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            email_from = os.getenv('EMAIL_FROM', '')
            email_password = os.getenv('EMAIL_PASSWORD', '')
            
            if not all([smtp_server, email_from, email_password]):
                st.warning("⚠️ Configurația email nu este completă. Verifică fișierul .env")
                return
            
            # Email către client
            msg_client = MIMEMultipart()
            msg_client['From'] = email_from
            msg_client['To'] = order_data['email']
            msg_client['Subject'] = f"🧾 Chitanță Rendering #{order_id} - {order_data['price_euro']} EUR"
            
            delivery_date = datetime.now() + timedelta(days=order_data['estimated_days'])
            
            body_client = f"""
            🧾 CHIȚANȚĂ PLATĂ RENDERING SERVICE

            Mulțumim pentru comanda ta, {order_data['student_name']}!
            
            📋 DETALII COMANDA:
            • ID Comandă: #{order_id}
            • Data: {datetime.now().strftime('%d.%m.%Y %H:%M')}
            • Sumă plătită: {order_data['price_euro']} EUR
            • Rezoluție: {order_data['resolution']}
            • Număr randări: {order_data['render_count']}
            • Software: {order_data['software']}
            
            💳 DETALII PLATĂ:
            • Beneficiar: STEFANIA BOSTIOG
            • IBAN: RO49BTRL01301202XXXXXXX
            • Banca: Transilvania
            • Sumă: {order_data['price_euro']} EUR
            • PayPal: bostiogstefania@gmail.com
            
            ⏰ DETALII LIVRARE:
            • Timp estimat: {order_data['estimated_days']} zile lucrătoare
            • Data estimată livrare: {delivery_date.strftime('%d.%m.%Y')}
            • Status: ⏳ În așteptare procesare
            
            📋 SPECIFICAȚII:
            {order_data['requirements'] or 'Niciune specificate'}
            
            🔔 URMEAZĂ:
            • Vei primi confirmarea procesării în 24h
            • Vei primi update-uri de progres
            • Link download va fi trimis la finalizare
            
            📞 SUPPORT:
            • Email: bostiogstefania@gmail.com
            • Telefon: +40 743 678 901
            
            Mulțumim pentru încredere!
            🏗️ Echipa Rendering Service ARH
            """
            
            msg_client.attach(MIMEText(body_client, 'plain'))
            
            # Email către administrator
            msg_admin = MIMEMultipart()
            msg_admin['From'] = email_from
            msg_admin['To'] = "bostiogstefania@gmail.com"
            msg_admin['Subject'] = f"💰 COMANDA NOUĂ #{order_id} - {order_data['price_euro']} EUR"
            
            body_admin = f"""
            💰 COMANDA NOUĂ PLĂTITĂ!

            📋 DETALII CLIENT:
            • Nume: {order_data['student_name']}
            • Email: {order_data['email']}
            • Telefon: {order_data.get('contact_phone', 'Nespecificat')}
            • Facultate: {order_data.get('faculty', 'Nespecificată')}
            
            💶 DETALII FINANCIARE:
            • ID Comandă: #{order_id}
            • Sumă: {order_data['price_euro']} EUR
            • Rezoluție: {order_data['resolution']}
            • Randări: {order_data['render_count']}
            • Zile estimare: {order_data['estimated_days']}
            • Urgent: {'DA' if order_data.get('is_urgent') else 'NU'}
            
            🛠️ DETALII PROIECT:
            • Software: {order_data['software']}
            • Cerințe: {order_data['requirements'] or 'Niciune'}
            • Fișier: {'Încărcat' if order_data.get('project_file') else 'Link: ' + order_data.get('project_link', 'N/A')}
            
            ⚡ ACȚIUNE NECESARĂ:
            1. Verifică fișierul/link-ul proiectului
            2. Confirmă clientului primirea
            3. Începe procesarea
            
            ⏰ Termen limită: {delivery_date.strftime('%d.%m.%Y')}
            """
            
            msg_admin.attach(MIMEText(body_admin, 'plain'))
            
            # Trimite ambele email-uri
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg_client)
            server.send_message(msg_admin)
            server.quit()
            
            # Marchează chitanța trimisă
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            cursor.execute('UPDATE orders SET receipt_sent = 1 WHERE id = ?', (order_id,))
            conn.commit()
            conn.close()
            
            st.success("📧 Chitanță trimisă pe email!")
            
        except Exception as e:
            st.warning(f"⚠️ Emailurile nu au putut fi trimise: {e}")
    
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
            <p><em>Profesional • Rapid • Calitate</em></p>
        </div>
        """, unsafe_allow_html=True)
        
        st.title("Navigare")
        menu = st.radio("Alege secțiunea:", [
            "📝 Comandă Rendering", 
            "📊 Dashboard Comenzi",
            "⚙️ Administrare",
            "💰 Prețuri & Termene",
            "📞 Contact"
        ])
        
        st.markdown("---")
        st.markdown("**📞 Contact rapid:**")
        st.markdown("📧 bostiogstefania@gmail.com")
        st.markdown("📱 +40 743 678 901")
    
    # Secțiunea de comandă nouă
    if menu == "📝 Comandă Rendering":
        st.header("🎨 Comandă Rendering Nouă")
        
        # Folosim session state pentru a gestiona starea formularului
        if 'order_submitted' not in st.session_state:
            st.session_state.order_submitted = False
        if 'form_data' not in st.session_state:
            st.session_state.form_data = {}
        
        if not st.session_state.order_submitted:
            # FORMULAR INITIAL
            with st.form("comanda_rendering"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("👤 Date Personale")
                    student_name = st.text_input("Nume complet*")
                    email = st.text_input("Email*")
                    contact_phone = st.text_input("Număr de telefon*")
                    faculty = st.text_input("Facultate/Universitate")
                    
                    st.subheader("📤 Încarcă Proiectul")
                    upload_option = st.radio("Alege metoda de upload:", 
                                           ["📎 Încarcă fișier", "🔗 Link extern"])
                    
                    if upload_option == "📎 Încarcă fișier":
                        project_file = st.file_uploader("Încarcă fișierul proiectului", 
                                                      type=['skp', 'rvt', 'max', 'blend', 'dwg', 'zip', 'rar'],
                                                      help="Suportă: SketchUp, Revit, 3ds Max, Blender, etc.")
                        project_link = None
                    else:
                        project_link = st.text_input("Link descărcare proiect*", 
                                                   placeholder="https://drive.google.com/... sau Wetransfer, Dropbox, etc.")
                        project_file = None
                
                with col2:
                    st.subheader("🎯 Specificații Rendering")
                    software = st.selectbox(
                        "Software utilizat*",
                        ["SketchUp", "Revit", "3ds Max", "Blender", "Archicad", "Lumion", "Altul"]
                    )
                    
                    resolution = st.selectbox(
                        "Rezoluție rendering*",
                        ["2-4K", "4-6K", "8K+"]
                    )
                    
                    render_count = st.slider("Număr de randări*", 1, 20, 1, 
                                           help="1-3 randări = 3 zile, 4-7 = 6 zile, 8-10 = 9 zile, etc.")
                    
                    is_urgent = st.checkbox("🚀 Comandă urgentă (+50% cost)", 
                                          help="Timp de procesare redus la jumătate")
                    
                    requirements = st.text_area("Cerințe specifice rendering", 
                                              placeholder="Unghi cameră, iluminare, materiale, stil preferat, etc.")
                
                # Calcul preț și timp
                if resolution and render_count:
                    price_euro, estimated_days = service.calculate_price_and_days(
                        resolution, render_count, is_urgent
                    )
                    
                    delivery_date = datetime.now() + timedelta(days=estimated_days)
                    
                    st.markdown("---")
                    st.markdown(f"""
                    <div class="price-estimate">
                        <h3>💰 Total: {price_euro} EUR</h3>
                        <p><strong>⏰ Timp de livrare:</strong> {estimated_days} zile lucrătoare</p>
                        <p><strong>📅 Data estimată:</strong> {delivery_date.strftime('%d %B %Y')}</p>
                        <p><strong>🎯 Rezoluție:</strong> {resolution}</p>
                        <p><strong>🖼️ Randări:</strong> {render_count}</p>
                        <p><strong>⚡ Urgent:</strong> {'Da (+50%)' if is_urgent else 'Nu'}</p>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("** * Câmpuri obligatorii*")
                
                submitted = st.form_submit_button("🚀 Continuă la Plată")
                
                if submitted:
                    if not all([student_name, email, contact_phone, software, resolution]):
                        st.error("⚠️ Te rog completează toate câmpurile obligatorii!")
                    elif upload_option == "📎 Încarcă fișier" and project_file is None:
                        st.error("⚠️ Te rog încarcă fișierul proiectului!")
                    elif upload_option == "🔗 Link extern" and not project_link:
                        st.error("⚠️ Te rog adaugă link-ul de descărcare!")
                    else:
                        # Salvează datele în session state
                        st.session_state.form_data = {
                            'student_name': student_name,
                            'email': email,
                            'contact_phone': contact_phone,
                            'faculty': faculty,
                            'project_file': project_file.name if project_file else None,
                            'project_link': project_link,
                            'software': software,
                            'resolution': resolution,
                            'render_count': render_count,
                            'is_urgent': is_urgent,
                            'requirements': requirements,
                            'price_euro': price_euro,
                            'estimated_days': estimated_days,
                            'delivery_date': delivery_date
                        }
                        st.session_state.order_submitted = True
                        st.rerun()
        
        else:
            # PAGINA DE PLATĂ (după submit formular)
            form_data = st.session_state.form_data
            
            st.markdown(f"""
            <div class="payment-box">
                <h2>💳 Finalizează Comanda</h2>
                <h3>Total de plată: {form_data['price_euro']} EUR</h3>
                
                <h4>📋 Detalii plată:</h4>
                <p><strong>Transfer bancar:</strong></p>
                <p>• Beneficiar: STEFANIA BOSTIOG</p>
                <p>• IBAN: RO49BTRL01301202XXXXXXX</p>
                <p>• Banca: Transilvania</p>
                <p>• Sumă: {form_data['price_euro']} EUR</p>
                <p>• Descriere: Rendering #{form_data['student_name'][:10]}</p>

                <p><strong>Sau PayPal:</strong> bostiogstefania@gmail.com</p>
            </div>
            """, unsafe_allow_html=True)
            
            # Afișează detalii comanda
            st.subheader("📋 Detalii Comanda")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**👤 Nume:** {form_data['student_name']}")
                st.write(f"**📧 Email:** {form_data['email']}")
                st.write(f"**📱 Telefon:** {form_data['contact_phone']}")
                st.write(f"**🏫 Facultate:** {form_data['faculty']}")
            with col2:
                st.write(f"**🛠️ Software:** {form_data['software']}")
                st.write(f"**🎯 Rezoluție:** {form_data['resolution']}")
                st.write(f"**🖼️ Randări:** {form_data['render_count']}")
                st.write(f"**⚡ Urgent:** {'Da' if form_data['is_urgent'] else 'Nu'}")
            
            # Confirmare plată
            payment_confirmed = st.checkbox("✅ Confirm că am efectuat plata")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                if st.button("🔄 Modifică Comanda"):
                    st.session_state.order_submitted = False
                    st.rerun()
            
            with col2:
                if st.button("📨 Finalizează Comanda și Primește Chitanța", type="primary"):
                    if not payment_confirmed:
                        st.error("⚠️ Te rog confirmă efectuarea plății!")
                    else:
                        with st.spinner("Se procesează comanda și se trimite chitanța..."):
                            order_data = {
                                'student_name': form_data['student_name'],
                                'email': form_data['email'],
                                'project_file': form_data['project_file'],
                                'project_link': form_data['project_link'],
                                'software': form_data['software'],
                                'resolution': form_data['resolution'],
                                'render_count': form_data['render_count'],
                                'deadline': form_data['delivery_date'].strftime("%Y-%m-%d"),
                                'requirements': form_data['requirements'],
                                'price_euro': form_data['price_euro'],
                                'estimated_days': form_data['estimated_days'],
                                'is_urgent': form_data['is_urgent'],
                                'contact_phone': form_data['contact_phone'],
                                'faculty': form_data['faculty']
                            }
                            
                            order_id = service.add_order(order_data)
                            if order_id:
                                st.success(f"🎉 Comanda #{order_id} a fost finalizată cu succes!")
                                st.balloons()
                                
                                # Afișează countdown
                                st.markdown(f"""
                                <div class="countdown">
                                    <h3>⏳ Timp rămas până la livrare</h3>
                                    <h2>{form_data['estimated_days']} zile lucrătoare</h2>
                                    <p>Data estimată: {form_data['delivery_date'].strftime('%d %B %Y')}</p>
                                </div>
                                """, unsafe_allow_html=True)
                                
                                st.info(f"""
                                **📧 Ce urmează:**
                                1. ✅ Ai primit chitanța pe email
                                2. 📞 Vei fi contactat în 24h pentru confirmare
                                3. 🚀 Vom începe procesarea rendering-ului
                                4. 📥 Vei primi link de download la finalizare
                                
                                **📞 Pentru întrebări:** bostiogstefania@gmail.com
                                """)
                                
                                # Reset form
                                st.session_state.order_submitted = False
                                st.session_state.form_data = {}

    # Restul codului rămâne la fel...
    # [Secțiunile pentru Dashboard, Administrare, Prețuri, Contact]
    
    # Secțiunea prețuri
    elif menu == "💰 Prețuri & Termene":
        st.header("💰 Prețuri & Termene de Livrare")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("💶 Prețuri pe Rezoluție")
            st.markdown("""
            | Rezoluție | Preț EUR |
            |-----------|----------|
            | 2-4K | 70 EUR |
            | 4-6K | 100 EUR |
            | 8K+ | 120 EUR |
            
            *+50% pentru comenzi urgente*
            """)
            
            st.subheader("🚀 Opțiune Urgentă")
            st.markdown("""
            • **+50%** din prețul base
            • **Timp de procesare redus la jumătate**
            • **Procesare prioritară**
            """)
        
        with col2:
            st.subheader("⏰ Termene de Livrare")
            st.markdown("""
            | Randări | Zile Lucrătoare |
            |---------|-----------------|
            | 1-3 | 3 zile |
            | 4-7 | 6 zile |
            | 8-10 | 9 zile |
            | 11-13 | 12 zile |
            | 14-15 | 15 zile |
            | 16+ | din 3 în 3 zile |
            """)
            
            st.subheader("💳 Metode de Plată")
            st.markdown("""
            • **Transfer Bancar** (RON/EUR)
            • **PayPal** 
            • **Revolut**
            • **Card Bancar**
            """)
    
    # Dashboard comenzi
    elif menu == "📊 Dashboard Comenzi":
        st.header("📊 Dashboard Comenzi")
        
        orders_df = service.get_orders()
        
        if not orders_df.empty:
            # Statistici
            total_orders = len(orders_df)
            total_revenue = orders_df['price_euro'].sum()
            pending_orders = len(orders_df[orders_df['status'] == 'pending'])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Comenzi", total_orders)
            with col2:
                st.metric("Venit Total", f"{total_revenue:.0f} EUR")
            with col3:
                st.metric("În Așteptare", pending_orders)
            
            # Filtre
            col1, col2 = st.columns(2)
            with col1:
                status_filter = st.selectbox("Filtrează după status:", 
                                           ["Toate", "pending", "processing", "completed"])
            with col2:
                if st.button("🔄 Actualizează"):
                    st.rerun()
            
            # Afișează comenzile
            filtered_df = orders_df if status_filter == "Toate" else orders_df[orders_df['status'] == status_filter]
            
            for _, order in filtered_df.iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.subheader(f"#{order['id']} - {order['student_name']}")
                        st.write(f"**📧 {order['email']}** • **📱 {order.get('contact_phone', 'Nespecificat')}**")
                        st.write(f"**🎯 {order['resolution']}** • **🖼️ {order['render_count']} randări** • **💰 {order['price_euro']} EUR**")
                        st.write(f"**⏰ {order['estimated_days']} zile** • **📅 {order['deadline']}**")
                    
                    with col2:
                        status_color = {
                            'pending': 'status-pending',
                            'processing': 'status-processing', 
                            'completed': 'status-completed'
                        }.get(order['status'], '')
                        
                        st.markdown(f'<div class="{status_color}"><strong>Status:</strong> {order["status"].upper()}</div>', 
                                  unsafe_allow_html=True)
                        
                        if order['is_urgent']:
                            st.markdown('<div class="urgent"><strong>🚀 URGENT</strong></div>', 
                                      unsafe_allow_html=True)
                        
                        st.write(f"**💳 Plata:** {order.get('payment_status', 'pending')}")
                    
                    with col3:
                        if order['download_link']:
                            st.markdown(f"[📥 Download]({order['download_link']})")
                        created = datetime.strptime(order['created_at'][:10], '%Y-%m-%d')
                        days_passed = (datetime.now() - created).days
                        days_left = max(0, order['estimated_days'] - days_passed)
                        st.markdown(f"**⏳ {days_left}z rămase**")
                    
                    st.divider()
        else:
            st.info("📭 Nu există comenzi în sistem.")
    
    # Secțiunea de administrare
    elif menu == "⚙️ Administrare":
        st.header("⚙️ Administrare Comenzi")
        
        # Verificare parolă
        try:
            correct_password = st.secrets["ADMIN_PASSWORD"]
        except:
            correct_password = os.getenv('ADMIN_PASSWORD', 'Admin123!')
        
        admin_password = st.text_input("Parolă administrare:", type="password")
        
        if admin_password == correct_password:
            st.success("✅ Acces administrativ acordat")
            
            orders_df = service.get_orders()
            
            if not orders_df.empty:
                # Gestionare comenzi
                for _, order in orders_df.iterrows():
                    with st.expander(f"#{order['id']} - {order['student_name']} - {order['price_euro']} EUR"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write(f"**📧 Email:** {order['email']}")
                            st.write(f"**📱 Telefon:** {order.get('contact_phone', 'Nespecificat')}")
                            st.write(f"**💶 Preț:** {order['price_euro']} EUR")
                            st.write(f"**📦 Fișier:** {order.get('project_file', 'Link: ' + order.get('project_link', 'N/A'))}")
                        
                        with col2:
                            new_status = st.selectbox(
                                f"Status #{order['id']}",
                                ["pending", "processing", "completed"],
                                index=["pending", "processing", "completed"].index(order['status']),
                                key=f"status_{order['id']}"
                            )
                            
                            download_link = st.text_input(
                                "🔗 Link download",
                                value=order['download_link'] or "",
                                key=f"download_{order['id']}"
                            )
                            
                            if st.button(f"💾 Salvează #{order['id']}", key=f"btn_{order['id']}"):
                                if service.update_order_status(order['id'], new_status, download_link or None):
                                    st.success(f"✅ Comanda #{order['id']} actualizată!")
                                    time.sleep(1)
                                    st.rerun()
                
                # Statistici
                st.subheader("📈 Statistici Avansate")
                total_revenue = orders_df['price_euro'].sum()
                completed_orders = len(orders_df[orders_df['status'] == 'completed'])
                urgent_orders = len(orders_df[orders_df['is_urgent'] == True])
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Venit Total", f"{total_revenue:.0f} EUR")
                with col2:
                    st.metric("Comenzi Finalizate", completed_orders)
                with col3:
                    st.metric("Comenzi Urgente", urgent_orders)
                with col4:
                    avg_price = total_revenue / len(orders_df) if len(orders_df) > 0 else 0
                    st.metric("Preț Mediu", f"{avg_price:.0f} EUR")
        
        elif admin_password and admin_password != correct_password:
            st.error("❌ Parolă incorectă!")
    
    # Secțiunea contact
    else:
        st.header("📞 Contact")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📧 Contactează-ne")
            st.markdown("""
            **📧 Email:** bostiogstefania@gmail.com
            **📱 Telefon:** +40 743 678 901
            **💬 WhatsApp:** +40 743 678 901
            
            **🏦 Detalii Bancare:**
            • Beneficiar: STEFANIA BOSTIOG
            • IBAN: RO49BTRL01301202XXXXXXX
            • Banca: Transilvania

            **🕒 Program:**
            Luni - Vineri: 9:00 - 18:00
            Sâmbătă: 10:00 - 14:00
            Duminică: Închis
            """)
        
        with col2:
            st.subheader("📍 Despre Noi")
            st.markdown("""
            **🏗️ Rendering Service ARH**
            
            Servicii profesionale de rendering pentru:
            • Studenți la Arhitectură
            • Arhitecți
            • Designeri
            
            **🎯 Calitate garantată**
            • Renderings foto-realiste
            • Timp de livrare rapid
            • Support dedicat
            • Revisions incluse
            """)

if __name__ == "__main__":
    main()
