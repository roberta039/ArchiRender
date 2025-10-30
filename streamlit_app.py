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
import threading
from queue import Queue

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
    .deleted { background-color: #f8d7da; padding: 10px; border-radius: 5px; text-decoration: line-through; }
    .progress-bar { background-color: #f0f0f0; border-radius: 10px; margin: 10px 0; }
    .progress-fill { background-color: #28a745; height: 20px; border-radius: 10px; text-align: center; color: white; font-weight: bold; }
    .notification { background-color: #e7f3ff; padding: 15px; border-radius: 10px; border-left: 5px solid #1f77b4; margin: 10px 0; }
    .notification-success { background-color: #d4edda; border-left: 5px solid #28a745; }
    .notification-warning { background-color: #fff3cd; border-left: 5px solid #ffc107; }
    .notification-error { background-color: #f8d7da; border-left: 5px solid #dc3545; }
    .admin-hidden {
        background: transparent;
        border: none;
        color: #1f77b4;
        cursor: pointer;
        text-decoration: none;
        font-weight: bold;
    }
    .admin-hidden:hover {
        text-decoration: underline;
    }
</style>
""", unsafe_allow_html=True)

class NotificationService:
    def __init__(self):
        self.notification_queue = Queue()
    
    def add_notification(self, order_id, message, type="info", recipient_email=None):
        """Adaugă o notificare în coadă"""
        notification = {
            'order_id': order_id,
            'message': message,
            'type': type,
            'recipient_email': recipient_email,
            'timestamp': datetime.now(),
            'read': False
        }
        self.notification_queue.put(notification)
        self.save_notification_to_db(notification)
    
    def save_notification_to_db(self, notification):
        """Salvează notificarea în baza de date"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO notifications 
                (order_id, message, type, recipient_email, timestamp, read)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                notification['order_id'],
                notification['message'],
                notification['type'],
                notification['recipient_email'],
                notification['timestamp'],
                notification['read']
            ))
            
            conn.commit()
            conn.close()
        except Error as e:
            print(f"Eroare la salvarea notificării: {e}")
    
    def get_notifications(self, order_id=None, unread_only=False):
        """Returnează notificările"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            
            if order_id:
                if unread_only:
                    df = pd.read_sql_query(
                        "SELECT * FROM notifications WHERE order_id = ? AND read = 0 ORDER BY timestamp DESC", 
                        conn, params=[order_id]
                    )
                else:
                    df = pd.read_sql_query(
                        "SELECT * FROM notifications WHERE order_id = ? ORDER BY timestamp DESC", 
                        conn, params=[order_id]
                    )
            else:
                if unread_only:
                    df = pd.read_sql_query(
                        "SELECT * FROM notifications WHERE read = 0 ORDER BY timestamp DESC", 
                        conn
                    )
                else:
                    df = pd.read_sql_query(
                        "SELECT * FROM notifications ORDER BY timestamp DESC", 
                        conn
                    )
            
            conn.close()
            return df
        except Error as e:
            print(f"Eroare la citirea notificărilor: {e}")
            return pd.DataFrame()
    
    def mark_as_read(self, notification_id):
        """Marchează o notificare ca citită"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('UPDATE notifications SET read = 1 WHERE id = ?', (notification_id,))
            
            conn.commit()
            conn.close()
            return True
        except Error as e:
            print(f"Eroare la marcarea notificării ca citită: {e}")
            return False

class RenderingService:
    def __init__(self):
        self.init_database()
        self.notification_service = NotificationService()
    
    def init_database(self):
        """Initializează baza de date SQLite"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            # Tabela pentru comenzi
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
                    faculty TEXT,
                    is_deleted BOOLEAN DEFAULT FALSE,
                    deleted_at TIMESTAMP,
                    deletion_reason TEXT,
                    progress INTEGER DEFAULT 0,
                    current_stage TEXT DEFAULT 'În așteptare',
                    stages_completed INTEGER DEFAULT 0,
                    total_stages INTEGER DEFAULT 6,
                    progress_email_sent BOOLEAN DEFAULT FALSE,
                    completed_email_sent BOOLEAN DEFAULT FALSE,
                    status_email_sent BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Tabela pentru notificări
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    type TEXT DEFAULT 'info',
                    recipient_email TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    read BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (order_id) REFERENCES orders (id)
                )
            ''')
            
            # Tabela pentru istoricul progresului
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS progress_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    FOREIGN KEY (order_id) REFERENCES orders (id)
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
                 is_urgent, contact_phone, faculty, total_stages)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                order_data.get('faculty', ''),
                6  # total_stages
            ))
            
            order_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Adaugă notificare pentru noua comandă
            self.notification_service.add_notification(
                order_id,
                f"🎉 Comanda #{order_id} a fost plasată cu succes! Timp de procesare estimat: {order_data['estimated_days']} zile.",
                "success",
                order_data['email']
            )
            
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
                st.warning("""
                ⚠️ **Configurația email nu este completă.** 
                
                Pentru a activa notificările email, adaugă următoarele variabile în fișierul `.env`:
                ```
                SMTP_SERVER=smtp.gmail.com
                SMTP_PORT=587
                EMAIL_FROM=emailul.tau@gmail.com
                EMAIL_PASSWORD=parola_ta_de_aplicatie
                ```
                """)
                return
            
            # Email către client
            msg_client = MIMEMultipart()
            msg_client.attach(MIMEText(f"""
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
            • Revolut: https://revolut.me/stefanxuhy
            • Transfer Bancar:
              - Beneficiar: STEFANIA BOSTIOG
              - IBAN: RO60 BREL 0002 0036 6187 0100
              - Bancă: Libra Bank
              - Sumă: {order_data['price_euro']} EUR
            
            ⏰ DETALII LIVRARE:
            • Timp estimat: {order_data['estimated_days']} zile lucrătoare
            • Data estimată livrare: {(datetime.now() + timedelta(days=order_data['estimated_days'])).strftime('%d.%m.%Y')}
            • Status: ⏳ În așteptare procesare
            
            🔔 NOTIFICĂRI:
            • Vei primi o notificare când începe procesarea
            • Vei primi o notificare când rendering-ul este gata
            • Link download va fi trimis la finalizare
            
            📋 SPECIFICAȚII:
            {order_data['requirements'] or 'Niciune specificate'}
            
            📞 SUPPORT:
            • Email: bostiogstefania@gmail.com
            • Telefon: +40 724 911 299
            
            Mulțumim pentru încredere!
            🏗️ Echipa Rendering Service ARH
            """, 'plain', 'utf-8'))
            
            msg_client['From'] = email_from
            msg_client['To'] = order_data['email']
            msg_client['Subject'] = f"🧾 Chitanță Rendering #{order_id} - {order_data['price_euro']} EUR"
            
            # Email către administrator
            msg_admin = MIMEMultipart()
            msg_admin.attach(MIMEText(f"""
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
            
            ⏰ Termen limită: {(datetime.now() + timedelta(days=order_data['estimated_days'])).strftime('%d.%m.%Y')}
            """, 'plain', 'utf-8'))
            
            msg_admin['From'] = email_from
            msg_admin['To'] = "bostiogstefania@gmail.com"
            msg_admin['Subject'] = f"💰 COMANDA NOUĂ #{order_id} - {order_data['price_euro']} EUR"
            
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

    def send_status_email(self, order_data, old_status, new_status):
        """Trimite email cu notificare schimbare status"""
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            email_from = os.getenv('EMAIL_FROM', '')
            email_password = os.getenv('EMAIL_PASSWORD', '')
            
            if not all([smtp_server, email_from, email_password]):
                return False
            
            status_messages = {
                'pending': '⏳ În așteptare procesare',
                'processing': '🚀 Procesare în curs', 
                'completed': '✅ Finalizat'
            }
            
            msg = MIMEMultipart()
            msg.attach(MIMEText(f"""
            🔔 ACTUALIZARE STATUS - Rendering #{order_data['id']}

            Bună {order_data['student_name']},
            
            Statusul comenzii tale s-a actualizat!
            
            📊 **STATUS NOU:**
            • De la: {status_messages.get(old_status, old_status)}
            • La: {status_messages.get(new_status, new_status)}
            
            🎯 **DETALII COMANDA:**
            • ID Comandă: #{order_data['id']}
            • Software: {order_data['software']}
            • Rezoluție: {order_data['resolution']}
            • Număr randări: {order_data['render_count']}
            • Progres curent: {order_data['progress']}%
            
            ⏰ **TERMEN ESTIMAT:**
            Data estimată de finalizare: {order_data['deadline']}
            
            {'📥 **DESCĂRCARE:**' + chr(10) + 'Proiectul tău este gata! Poți descărca fișierele de aici:' + chr(10) + order_data['download_link'] if new_status == 'completed' and order_data.get('download_link') else ''}
            
            📞 **SUPPORT:**
            • Email: bostiogstefania@gmail.com
            • Telefon: +40 724 911 299
            
            Mulțumim pentru încredere!
            🏗️ Echipa Rendering Service ARH
            """, 'plain', 'utf-8'))
            
            msg['From'] = email_from
            msg['To'] = order_data['email']
            msg['Subject'] = f"🔔 Status Actualizat - Rendering #{order_data['id']} - {status_messages.get(new_status, new_status)}"
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg)
            server.quit()
            
            return True
        except Exception as e:
            print(f"⚠️ Eroare la trimiterea email-ului de status: {e}")
            return False

    def send_progress_email(self, order_data, progress, current_stage, notes=""):
        """Trimite email cu notificare progres către client"""
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            email_from = os.getenv('EMAIL_FROM', '')
            email_password = os.getenv('EMAIL_PASSWORD', '')
            
            if not all([smtp_server, email_from, email_password]):
                return False
            
            msg = MIMEMultipart()
            msg.attach(MIMEText(f"""
            🚀 PROCESARE ÎN CURS - Rendering #{order_data['id']}

            Bună {order_data['student_name']},
            
            Procesarea rendering-ului tău a început!
            
            📊 **STADIUL ACTUAL:**
            • Progres: {progress}%
            • Etapă: {current_stage}
            • Status: Procesare în curs
            
            🎯 **DETALII COMANDA:**
            • ID Comandă: #{order_data['id']}
            • Software: {order_data['software']}
            • Rezoluție: {order_data['resolution']}
            • Număr randări: {order_data['render_count']}
            
            ⏰ **TERMEN ESTIMAT:**
            Data estimată de finalizare: {order_data['deadline']}
            
            📝 **DETALII PROIECT:**
            {notes or 'Procesare în conformitate cu specificațiile tale'}
            
            🔔 **URMĂTOAREA NOTIFICARE:**
            Vei primi un email când rendering-ul va fi complet finalizat și gata pentru descărcare.
            
            📞 **SUPPORT:**
            • Email: bostiogstefania@gmail.com
            • Telefon: +40 724 911 299
            
            Mulțumim pentru încredere!
            🏗️ Echipa Rendering Service ARH
            """, 'plain', 'utf-8'))
            
            msg['From'] = email_from
            msg['To'] = order_data['email']
            msg['Subject'] = f"🚀 Procesare Rendering #{order_data['id']} - În curs"
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg)
            server.quit()
            
            return True
        except Exception as e:
            print(f"⚠️ Eroare la trimiterea email-ului de progres: {e}")
            return False

    def send_completion_email(self, order_data, download_link=None):
        """Trimite email cu notificare finalizare către client"""
        try:
            smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
            smtp_port = int(os.getenv('SMTP_PORT', 587))
            email_from = os.getenv('EMAIL_FROM', '')
            email_password = os.getenv('EMAIL_PASSWORD', '')
            
            if not all([smtp_server, email_from, email_password]):
                return False
            
            download_section = ""
            if download_link:
                download_section = f"""
                📥 **DESCĂRCARE:**
                Proiectul tău este gata! Poți descărca fișierele de aici:
                {download_link}
                """
            else:
                download_section = """
                📥 **DESCĂRCARE:**
                Proiectul tău este gata! Vei primi link-ul de descărcare în scurt timp.
                """
            
            msg = MIMEMultipart()
            msg.attach(MIMEText(f"""
            ✅ RENDERING FINALIZAT - #{order_data['id']}

            Bună {order_data['student_name']},
            
            Rendering-ul tău este finalizat și gata!
            
            🎉 **PROIECT FINALIZAT:**
            • Status: 100% Complet
            • Data finalizare: {datetime.now().strftime('%d.%m.%Y %H:%M')}
            • Calitate: Conform specificațiilor
            
            🎯 **DETALII COMANDA:**
            • ID Comandă: #{order_data['id']}
            • Software: {order_data['software']}
            • Rezoluție: {order_data['resolution']}
            • Număr randări: {order_data['render_count']}
            
            {download_section}
            
            📋 **SPECIFICAȚII PROCESATE:**
            {order_data['requirements'] or 'Toate specificațiile au fost respectate'}
            
            ⭐ **FEEDBACK:**
            Dacă ești mulțumit de rezultat, te rugăm să ne lași un review!
            
            📞 **SUPPORT:**
            • Email: bostiogstefania@gmail.com
            • Telefon: +40 724 911 299
            
            Mulțumim că ai ales serviciile noastre!
            🏗️ Echipa Rendering Service ARH
            """, 'plain', 'utf-8'))
            
            msg['From'] = email_from
            msg['To'] = order_data['email']
            msg['Subject'] = f"✅ Rendering Finalizat #{order_data['id']} - Gata pentru descărcare"
            
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg)
            server.quit()
            
            return True
        except Exception as e:
            print(f"⚠️ Eroare la trimiterea email-ului de finalizare: {e}")
            return False
    
    def get_orders(self, status=None, include_deleted=False):
        """Returnează toate comenzile"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            
            if status:
                if include_deleted:
                    df = pd.read_sql_query(
                        "SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", 
                        conn, params=[status]
                    )
                else:
                    df = pd.read_sql_query(
                        "SELECT * FROM orders WHERE status = ? AND is_deleted = 0 ORDER BY created_at DESC", 
                        conn, params=[status]
                    )
            else:
                if include_deleted:
                    df = pd.read_sql_query(
                        "SELECT * FROM orders ORDER BY created_at DESC", 
                        conn
                    )
                else:
                    df = pd.read_sql_query(
                        "SELECT * FROM orders WHERE is_deleted = 0 ORDER BY created_at DESC", 
                        conn
                    )
            
            conn.close()
            return df
        except Error as e:
            st.error(f"❌ Eroare la citirea comenzilor: {e}")
            return pd.DataFrame()
    
    def update_order_status(self, order_id, status, download_link=None):
        """Actualizează statusul unei comenzi și trimite notificări"""
        try:
            # Obține starea anterioară
            order = self.get_order_by_id(order_id)
            if order.empty:
                return False
                
            old_status = order.iloc[0]['status']
            order_data = order.iloc[0]
            
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
            
            # Adaugă notificare pentru schimbarea statusului
            self.notification_service.add_notification(
                order_id,
                f"📊 Status comanda actualizat: {old_status.upper()} → {status.upper()}",
                "info",
                order_data['email']
            )
            
            # Trimite email de notificare status DOAR dacă statusul s-a schimbat
            if old_status != status:
                # Verifică dacă email-ul de status a fost deja trimis pentru această schimbare
                if not order_data.get('status_email_sent', False) or True:  # Forțează trimiterea pentru testare
                    email_sent = self.send_status_email(order_data, old_status, status)
                    
                    # Marchează că email-ul de status a fost trimis
                    if email_sent:
                        conn = sqlite3.connect('rendering_orders.db')
                        cursor = conn.cursor()
                        cursor.execute('UPDATE orders SET status_email_sent = 1 WHERE id = ?', (order_id,))
                        conn.commit()
                        conn.close()
            
            return True
        except Error as e:
            st.error(f"❌ Eroare la actualizarea comenzii: {e}")
            return False

    def update_progress(self, order_id, progress, current_stage, notes=""):
        """Actualizează progresul unei comenzi și trimite notificări"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            # Obține starea anterioară pentru a verifica dacă trebuie să trimitem email
            order = self.get_order_by_id(order_id)
            if order.empty:
                return False
                
            previous_progress = order.iloc[0]['progress']
            progress_email_sent = order.iloc[0]['progress_email_sent']
            completed_email_sent = order.iloc[0]['completed_email_sent']
            
            # Calculează numărul de etape completate
            stages_completed = int((progress / 100) * 6)  # 6 etape totale
            
            cursor.execute('''
                UPDATE orders 
                SET progress = ?, current_stage = ?, stages_completed = ?
                WHERE id = ?
            ''', (progress, current_stage, stages_completed, order_id))
            
            # Salvează în istoricul progresului
            cursor.execute('''
                INSERT INTO progress_history (order_id, stage, progress, notes)
                VALUES (?, ?, ?, ?)
            ''', (order_id, current_stage, progress, notes))
            
            conn.commit()
            conn.close()
            
            # Obține datele complete ale comenzii pentru email
            order = self.get_order_by_id(order_id)
            if not order.empty:
                order_data = order.iloc[0]
                
                # Adaugă notificare pentru progres
                self.notification_service.add_notification(
                    order_id,
                    f"📈 Progres actualizat: {progress}% - {current_stage}",
                    "info",
                    order_data['email']
                )
                
                # NOTIFICARE 1: Procesare începută (doar o dată)
                if progress >= 10 and not progress_email_sent and previous_progress < 10:
                    success = self.send_progress_email(order_data, progress, current_stage, notes)
                    if success:
                        # Marchează că email-ul de progres a fost trimis
                        conn = sqlite3.connect('rendering_orders.db')
                        cursor = conn.cursor()
                        cursor.execute('UPDATE orders SET progress_email_sent = 1 WHERE id = ?', (order_id,))
                        conn.commit()
                        conn.close()
                        print(f"✅ Email progres trimis pentru comanda #{order_id}")
                
                # NOTIFICARE 2: Finalizare (doar o dată)
                if progress == 100 and not completed_email_sent:
                    download_link = order_data['download_link']
                    success = self.send_completion_email(order_data, download_link)
                    if success:
                        # Marchează că email-ul de finalizare a fost trimis
                        conn = sqlite3.connect('rendering_orders.db')
                        cursor = conn.cursor()
                        cursor.execute('UPDATE orders SET completed_email_sent = 1 WHERE id = ?', (order_id,))
                        conn.commit()
                        conn.close()
                        print(f"✅ Email finalizare trimis pentru comanda #{order_id}")
            
            return True
        except Error as e:
            st.error(f"❌ Eroare la actualizarea progresului: {e}")
            return False

    def get_order_by_id(self, order_id):
        """Returnează o comandă după ID"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            df = pd.read_sql_query(
                "SELECT * FROM orders WHERE id = ?", 
                conn, params=[order_id]
            )
            conn.close()
            return df
        except Error as e:
            st.error(f"❌ Eroare la citirea comenzii: {e}")
            return pd.DataFrame()

    def get_progress_history(self, order_id):
        """Returnează istoricul progresului pentru o comandă"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            df = pd.read_sql_query(
                "SELECT * FROM progress_history WHERE order_id = ? ORDER BY timestamp DESC", 
                conn, params=[order_id]
            )
            conn.close()
            return df
        except Error as e:
            st.error(f"❌ Eroare la citirea istoricului: {e}")
            return pd.DataFrame()

    def delete_order(self, order_id, reason=""):
        """Marchează o comandă ca ștearsă"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE orders 
                SET is_deleted = 1, deleted_at = CURRENT_TIMESTAMP, deletion_reason = ?
                WHERE id = ?
            ''', (reason, order_id))
            
            conn.commit()
            conn.close()
            return True
        except Error as e:
            st.error(f"❌ Eroare la ștergerea comenzii: {e}")
            return False

    def restore_order(self, order_id):
        """Restabilește o comandă ștearsă"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE orders 
                SET is_deleted = 0, deleted_at = NULL, deletion_reason = NULL
                WHERE id = ?
            ''', (order_id,))
            
            conn.commit()
            conn.close()
            return True
        except Error as e:
            st.error(f"❌ Eroare la restabilirea comenzii: {e}")
            return False

    def permanently_delete_order(self, order_id):
        """Șterge definitiv o comandă din baza de date"""
        try:
            conn = sqlite3.connect('rendering_orders.db')
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM orders WHERE id = ?', (order_id,))
            
            conn.commit()
            conn.close()
            return True
        except Error as e:
            st.error(f"❌ Eroare la ștergerea definitivă a comenzii: {e}")
            return False

def display_progress_bar(progress, current_stage):
    """Afișează o bară de progres"""
    st.markdown(f"""
    <div class="progress-bar">
        <div class="progress-fill" style="width: {progress}%">
            {progress}% - {current_stage}
        </div>
    </div>
    """, unsafe_allow_html=True)

def display_notification(message, type="info"):
    """Afișează o notificare"""
    css_class = {
        "info": "notification",
        "success": "notification-success", 
        "warning": "notification-warning",
        "error": "notification-error"
    }.get(type, "notification")
    
    st.markdown(f"""
    <div class="{css_class}">
        {message}
    </div>
    """, unsafe_allow_html=True)

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
            <p><em>
                <button class="admin-hidden" onclick="this.parentNode.querySelector('input').value='admin'">Profesional</button> • Rapid • Calitate
            </em></p>
            <input type="text" style="display: none;">
        </div>
        """, unsafe_allow_html=True)
        
        # Verifică dacă butonul de administrare a fost apăsat
        if st.session_state.get('admin_clicked'):
            menu = st.radio("Alege secțiunea:", [
                "📝 Comandă Rendering", 
                "⚙️ Administrare",
                "💰 Prețuri & Termene",
                "📞 Contact",
                "🔔 Notificări",
                "📊 Tracking Progres"
            ])
        else:
            menu = st.radio("Alege secțiunea:", [
                "📝 Comandă Rendering", 
                "💰 Prețuri & Termene",
                "📞 Contact",
                "🔔 Notificări",
                "📊 Tracking Progres"
            ])
        
        st.markdown("---")
        st.markdown("**📞 Contact rapid:**")
        st.markdown("📧 bostiogstefania@gmail.com")
        st.markdown("📱 +40 724 911 299")
        
        # JavaScript pentru a detecta click-ul pe butonul ascuns
        st.markdown("""
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            const adminButton = document.querySelector('.admin-hidden');
            if (adminButton) {
                adminButton.addEventListener('click', function() {
                    // Trimite o cerere către Streamlit pentru a seta session state
                    fetch('/streamlit', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            'admin_clicked': true
                        })
                    }).then(() => {
                        window.location.reload();
                    });
                });
            }
        });
        </script>
        """, unsafe_allow_html=True)
    
    # Secțiunea de comandă nouă
    if menu == "📝 Comandă Rendering":
        st.header("🎨 Comandă Rendering Nouă")
        
        # Folosim session state pentru a gestiona starea formularului
        if 'order_submitted' not in st.session_state:
            st.session_state.order_submitted = False
        if 'form_data' not in st.session_state:
            st.session_state.form_data = {}
        if 'upload_option' not in st.session_state:
            st.session_state.upload_option = "📎 Încarcă fișier"
        
        if not st.session_state.order_submitted:
            # Folosim columns pentru a separa logica de afișare
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("👤 Date Personale")
                student_name = st.text_input("Nume complet*")
                email = st.text_input("Email*")
                contact_phone = st.text_input("Număr de telefon*")
                faculty = st.text_input("Facultate/Universitate")
                
                st.subheader("📤 Încarcă Proiectul")
                
                # Radio button cu callback pentru a forța re-run
                upload_option = st.radio(
                    "Alege metoda de upload:", 
                    ["📎 Încarcă fișier", "🔗 Link extern"],
                    index=0 if st.session_state.upload_option == "📎 Încarcă fișier" else 1,
                    key="upload_radio"
                )
                
                # Actualizează session state când se schimbă opțiunea
                if upload_option != st.session_state.upload_option:
                    st.session_state.upload_option = upload_option
                    st.rerun()
                
                # Afișează câmpul corespunzător în funcție de selecție
                if st.session_state.upload_option == "📎 Încarcă fișier":
                    project_file = st.file_uploader(
                        "Încarcă fișierul proiectului", 
                        type=['skp', 'rvt', 'max', 'blend', 'dwg', 'zip', 'rar'],
                        help="Suportă: SketchUp, Revit, 3ds Max, Blender, etc."
                    )
                    project_link = None
                    st.info("💡 **Formate acceptate:** .skp, .rvt, .max, .blend, .dwg, .zip, .rar")
                else:
                    project_link = st.text_input(
                        "Link descărcare proiect*", 
                        placeholder="https://drive.google.com/... sau Wetransfer, Dropbox, etc.",
                        help="Adaugă un link de descărcare de pe Google Drive, WeTransfer, Dropbox etc."
                    )
                    project_file = None
                    st.info("💡 **Servicii acceptate:** Google Drive, WeTransfer, Dropbox, OneDrive, etc.")
            
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
                                          placeholder="Unghi cameră, iluminare, materiale, stil preferat, etc.",
                                          height=100)
            
            # Calcul preț și timp
            if resolution and render_count:
                price_euro, estimated_days = service.calculate_price_and_days(
                    resolution, render_count, is_urgent
                )
                
                delivery_date = datetime.now() + timedelta(days=estimated_days)
                
                st.markdown("---")
                st.markdown(
                    f"""
                    <div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px; border-left: 4px solid #28a745; margin: 15px 0;">
                        <h3 style="color: #28a745;">💰 Total: {price_euro} EUR</h3>
                        <p><strong>⏰ Timp de livrare:</strong> {estimated_days} zile lucrătoare</p>
                        <p><strong>📅 Data estimată:</strong> {delivery_date.strftime('%d %B %Y')}</p>
                        <p><strong>🎯 Rezoluție:</strong> {resolution}</p>
                        <p><strong>🖼️ Randări:</strong> {render_count}</p>
                        <p><strong>⚡ Urgent:</strong> {'Da (+50%)' if is_urgent else 'Nu'}</p>
                    </div>
                    """, 
                    unsafe_allow_html=True
                )
            
            st.markdown("** * Câmpuri obligatorii*")
            
            # Buton de submit în afara coloanelor
            submitted = st.button("🚀 Continuă la Plată", type="primary", use_container_width=True)
            
            if submitted:
                if not all([student_name, email, contact_phone, software, resolution]):
                    st.error("⚠️ Te rog completează toate câmpurile obligatorii!")
                elif st.session_state.upload_option == "📎 Încarcă fișier" and project_file is None:
                    st.error("⚠️ Te rog încarcă fișierul proiectului!")
                elif st.session_state.upload_option == "🔗 Link extern" and not project_link:
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
            
            st.markdown("### 💳 Finalizează Comanda")
            st.markdown(f"#### Total de plată: {form_data['price_euro']} EUR")
            
            st.markdown("#### 📋 Alege metoda de plată:")

            # Revolut Link
            st.markdown(
                f"""
                <div style="background-color: #0075eb; color: white; padding: 20px; border-radius: 10px; text-align: center; margin: 15px 0;">
                    <h3 style="color: white; margin-bottom: 15px;">🚀 Plată Rapidă cu Revolut</h3>
                    <p style="font-size: 1.1em;"><strong>Click pe link pentru a plăti:</strong></p>
                    <a href="https://revolut.me/stefanxuhy" target="_blank" style="color: white; text-decoration: none; font-size: 1.3em; font-weight: bold;">
                        https://revolut.me/stefanxuhy
                    </a>
                    <p style="margin-top: 10px;"><em>Sumă: {form_data['price_euro']} EUR</em></p>
                </div>
                """, 
                unsafe_allow_html=True
            )

            # Bank Details
            st.markdown(
                f"""
                <div style="background-color: #f0f8ff; padding: 20px; border-radius: 10px; border-left: 4px solid #1f77b4; margin: 15px 0;">
                    <h3 style="color: #1f77b4; margin-bottom: 15px;">🏦 Transfer Bancar</h3>
                    <p><strong>Beneficiar:</strong> STEFANIA BOSTIOG</p>
                    <p><strong>IBAN:</strong> RO60 BREL 0002 0036 6187 0100</p>
                    <p><strong>Bancă:</strong> Libra Bank</p>
                    <p><strong>Sumă:</strong> {form_data['price_euro']} EUR</p>
                    <p><strong>Descriere:</strong> Rendering #{form_data['student_name'][:10]}</p>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
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
                                st.markdown(
                                    f"""
                                    <div style="background-color: #fff3cd; padding: 20px; border-radius: 10px; text-align: center; margin: 15px 0;">
                                        <h3>⏳ Timp rămas până la livrare</h3>
                                        <h2>{form_data['estimated_days']} zile lucrătoare</h2>
                                        <p>Data estimată: {form_data['delivery_date'].strftime('%d %B %Y')}</p>
                                    </div>
                                    """, 
                                    unsafe_allow_html=True
                                )
                                
                                st.info(f"""
                                **📧 Ce urmează:**
                                1. ✅ Ai primit chitanța pe email
                                2. 🔔 Vei primi o notificare când începe procesarea
                                3. 🔔 Vei primi o notificare când rendering-ul este gata
                                4. 📊 Poți urmări progresul în secțiunea "Tracking Progres"
                                5. 📥 Vei primi link de download la finalizare
                                
                                **📞 Pentru întrebări:** bostiogstefania@gmail.com
                                """)
                                
                                # Reset form
                                st.session_state.order_submitted = False
                                st.session_state.form_data = {}
                                st.session_state.upload_option = "📎 Încarcă fișier"

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
            • **Revolut** - [revolut.me/stefanxuhy](https://revolut.me/stefanxuhy)
            • **Transfer Bancar** - Libra Bank
            • **PayPal** - bostiogstefania@gmail.com
            """)

    # Secțiunea notificări
    elif menu == "🔔 Notificări":
        st.header("🔔 Notificări și Alertă")
        
        # Căutare comanda pentru notificări
        st.subheader("📋 Caută Comanda")
        col1, col2 = st.columns([2, 1])
        with col1:
            order_search = st.text_input("Introdu ID-ul comenzii sau email-ul:")
        with col2:
            search_type = st.radio("Caută după:", ["ID Comandă", "Email"], horizontal=True)
        
        if order_search:
            if search_type == "ID Comandă":
                try:
                    order_id = int(order_search)
                    orders = service.get_orders()
                    order = orders[orders['id'] == order_id]
                    if not order.empty:
                        notifications = service.notification_service.get_notifications(order_id=order_id)
                    else:
                        st.error("❌ Comanda nu a fost găsită!")
                        notifications = pd.DataFrame()
                except:
                    st.error("❌ ID invalid! Te rog introdu un număr valid.")
                    notifications = pd.DataFrame()
            else:
                orders = service.get_orders()
                order = orders[orders['email'] == order_search]
                if not order.empty:
                    order_id = order.iloc[0]['id']
                    notifications = service.notification_service.get_notifications(order_id=order_id)
                else:
                    st.error("❌ Nu s-au găsit comenzi pentru acest email!")
                    notifications = pd.DataFrame()
            
            if not notifications.empty:
                st.subheader(f"📬 Notificări pentru Comanda #{order_id}")
                
                for _, notification in notifications.iterrows():
                    col1, col2 = st.columns([4, 1])
                    with col1:
                        display_notification(
                            f"**{notification['timestamp']}** - {notification['message']}",
                            notification['type']
                        )
                    with col2:
                        if not notification['read']:
                            if st.button("✓ Marchează citită", key=f"read_{notification['id']}"):
                                service.notification_service.mark_as_read(notification['id'])
                                st.rerun()
            else:
                st.info("ℹ️ Nu există notificări pentru această comandă.")
        
        # Notificări generale pentru administrator
        st.subheader("📢 Notificări Sistem")
        all_notifications = service.notification_service.get_notifications(unread_only=True)
        if not all_notifications.empty:
            for _, notification in all_notifications.iterrows():
                display_notification(
                    f"**Comanda #{notification['order_id']}** - {notification['message']}",
                    notification['type']
                )
        else:
            st.info("🎉 Nu există notificări noi!")

    # Secțiunea tracking progres
    elif menu == "📊 Tracking Progres":
        st.header("📊 Tracking Progres Rendering")
        
        # Căutare comanda pentru tracking
        st.subheader("🔍 Caută Comanda pentru Tracking")
        col1, col2 = st.columns([2, 1])
        with col1:
            track_order_id = st.text_input("Introdu ID-ul comenzii:")
        with col2:
            if st.button("🔍 Caută Comanda"):
                if track_order_id:
                    try:
                        order_id = int(track_order_id)
                        order = service.get_order_by_id(order_id)
                        if not order.empty and order.iloc[0]['is_deleted'] == 0:
                            st.session_state.track_order_id = order_id
                            st.rerun()
                        else:
                            st.error("❌ Comanda nu a fost găsită sau a fost ștearsă!")
                    except:
                        st.error("❌ ID invalid! Te rog introdu un număr valid.")
        
        # Afișare progres pentru comanda selectată
        if 'track_order_id' in st.session_state:
            order_id = st.session_state.track_order_id
            order = service.get_order_by_id(order_id)
            
            if not order.empty:
                order_data = order.iloc[0]
                
                st.subheader(f"📈 Progres Comanda #{order_id}")
                st.write(f"**👤 Client:** {order_data['student_name']}")
                st.write(f"**📧 Email:** {order_data['email']}")
                st.write(f"**🛠️ Software:** {order_data['software']}")
                st.write(f"**🎯 Rezoluție:** {order_data['resolution']}")
                
                # Bară de progres
                progress = order_data['progress']
                current_stage = order_data['current_stage']
                
                st.markdown("### 🎯 Stadiu Curent")
                display_progress_bar(progress, current_stage)
                
                # Etapele procesului
                st.markdown("### 📋 Etape Proces")
                stages = [
                    {"name": "📥 Prelucrare fișier", "progress": 17},
                    {"name": "🎨 Setup scenă", "progress": 33},
                    {"name": "💡 Configurare iluminare", "progress": 50},
                    {"name": "🛠️ Optimizare materiale", "progress": 67},
                    {"name": "🚀 Rendering", "progress": 83},
                    {"name": "✅ Finalizare și verificare", "progress": 100}
                ]
                
                for i, stage in enumerate(stages):
                    completed = i < order_data['stages_completed']
                    current = i == order_data['stages_completed'] - 1
                    
                    icon = "✅" if completed else "⏳"
                    if current: icon = "🎯"
                    
                    st.write(f"{icon} {stage['name']} {'***(Curent)***' if current else ''}")
                
                # Istoric progres
                st.markdown("### 📊 Istoric Progres")
                progress_history = service.get_progress_history(order_id)
                if not progress_history.empty:
                    for _, history in progress_history.iterrows():
                        st.write(f"**{history['timestamp']}** - {history['stage']} ({history['progress']}%)")
                        if history['notes']:
                            st.write(f"*Notițe: {history['notes']}*")
                        st.divider()
                else:
                    st.info("📝 Încă nu există istoric de progres.")
                
                # Buton pentru refresh
                if st.button("🔄 Actualizează Progres"):
                    st.rerun()
            
            else:
                st.error("❌ Comanda nu a fost găsită!")
                if 'track_order_id' in st.session_state:
                    del st.session_state.track_order_id

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
            
            # Submeniu în administrare
            admin_menu = st.radio("Alege secțiunea:", 
                                ["📊 Dashboard Comenzi", "🎯 Gestionare Comenzi", "📈 Statistici", "🗑️ Comenzi Șterse", "🚀 Management Progres"],
                                horizontal=True)
            
            if admin_menu == "🚀 Management Progres":
                st.subheader("🚀 Management Progres Rendering")
                
                orders_df = service.get_orders()
                active_orders = orders_df[orders_df['status'].isin(['pending', 'processing'])]
                
                if not active_orders.empty:
                    for _, order in active_orders.iterrows():
                        with st.expander(f"#{order['id']} - {order['student_name']} - Progres: {order['progress']}%"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write(f"**📧 Email:** {order['email']}")
                                st.write(f"**🛠️ Software:** {order['software']}")
                                st.write(f"**🎯 Rezoluție:** {order['resolution']}")
                                st.write(f"**🖼️ Randări:** {order['render_count']}")
                                st.write(f"**📊 Progres curent:** {order['progress']}%")
                                st.write(f"**🎯 Stadiu curent:** {order['current_stage']}")
                                st.write(f"**📧 Notificare progres:** {'✅ Trimis' if order['progress_email_sent'] else '❌ Nepreluat'}")
                                st.write(f"**📧 Notificare finalizare:** {'✅ Trimis' if order['completed_email_sent'] else '❌ Nepreluat'}")
                            
                            with col2:
                                # Actualizare progres
                                new_progress = st.slider(f"Progres #{order['id']}", 0, 100, order['progress'])
                                stages = [
                                    "În așteptare",
                                    "📥 Prelucrare fișier",
                                    "🎨 Setup scenă", 
                                    "💡 Configurare iluminare",
                                    "🛠️ Optimizare materiale",
                                    "🚀 Rendering",
                                    "✅ Finalizare și verificare"
                                ]
                                new_stage = st.selectbox(f"Stadiu #{order['id']}", stages, 
                                                       index=stages.index(order['current_stage']) if order['current_stage'] in stages else 0)
                                notes = st.text_area(f"Notițe #{order['id']}", placeholder="Detalii despre progres...")
                                
                                if st.button(f"💾 Actualizează Progres #{order['id']}"):
                                    if service.update_progress(order['id'], new_progress, new_stage, notes):
                                        st.success(f"✅ Progresul pentru comanda #{order['id']} a fost actualizat!")
                                        time.sleep(1)
                                        st.rerun()
                                
                                # Dacă progresul este 100%, oferă opțiunea de a marca ca completat
                                if new_progress == 100:
                                    if st.button(f"🎉 Finalizează Comanda #{order['id']}"):
                                        if service.update_order_status(order['id'], 'completed'):
                                            service.notification_service.add_notification(
                                                order['id'],
                                                "🎉 Rendering finalizat! Proiectul este gata pentru descărcare.",
                                                "success",
                                                order['email']
                                            )
                                            st.success(f"✅ Comanda #{order['id']} a fost finalizată!")
                                            time.sleep(1)
                                            st.rerun()
                
                else:
                    st.info("📭 Nu există comenzi active pentru managementul progresului.")
            
            elif admin_menu == "🎯 Gestionare Comenzi":
                st.subheader("🎯 Gestionare Comenzi")
                
                orders_df = service.get_orders()
                
                if not orders_df.empty:
                    for _, order in orders_df.iterrows():
                        with st.expander(f"#{order['id']} - {order['student_name']} - {order['price_euro']} EUR - {order['status']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write(f"**📧 Email:** {order['email']}")
                                st.write(f"**📱 Telefon:** {order.get('contact_phone', 'Nespecificat')}")
                                st.write(f"**💶 Preț:** {order['price_euro']} EUR")
                                st.write(f"**🏫 Facultate:** {order.get('faculty', 'Nespecificată')}")
                                st.write(f"**📊 Progres:** {order['progress']}%")
                                st.write(f"**🎯 Stadiu:** {order['current_stage']}")
                                st.write(f"**📧 Notificare progres:** {'✅ Trimis' if order['progress_email_sent'] else '❌ Nepreluat'}")
                                st.write(f"**📧 Notificare finalizare:** {'✅ Trimis' if order['completed_email_sent'] else '❌ Nepreluat'}")
                                
                                # Afișare corectă fișier/link
                                project_file = order.get('project_file')
                                project_link = order.get('project_link')
                                
                                if project_file and project_file != 'None':
                                    st.write(f"**📦 Fișier încărcat:** {project_file}")
                                elif project_link and project_link != 'None':
                                    st.write(f"**🔗 Link proiect:** {project_link}")
                                else:
                                    st.write("**📦 Proiect:** Niciun fișier/link furnizat")
                                
                                st.write(f"**📋 Cerințe:** {order['requirements'] or 'Niciune specificată'}")
                            
                            with col2:
                                # Actualizare status
                                new_status = st.selectbox(
                                    f"Status #{order['id']}",
                                    ["pending", "processing", "completed"],
                                    index=["pending", "processing", "completed"].index(order['status']),
                                    key=f"status_{order['id']}"
                                )
                                
                                # Link download
                                download_link = st.text_input(
                                    "🔗 Link download",
                                    value=order['download_link'] or "",
                                    placeholder="https://drive.google.com/...",
                                    key=f"download_{order['id']}"
                                )
                                
                                # Butoane acțiune
                                col_btn1, col_btn2 = st.columns(2)
                                with col_btn1:
                                    if st.button(f"💾 Salvează", key=f"btn_save_{order['id']}"):
                                        if service.update_order_status(order['id'], new_status, download_link or None):
                                            st.success(f"✅ Comanda #{order['id']} actualizată!")
                                            time.sleep(1)
                                            st.rerun()
                                
                                with col_btn2:
                                    # Gestionare ștergere
                                    if f"show_del_manage_{order['id']}" not in st.session_state:
                                        st.session_state[f"show_del_manage_{order['id']}"] = False
                                        
                                    if not st.session_state[f"show_del_manage_{order['id']}"]:
                                        if st.button(f"🗑️ Șterge", key=f"del_btn_{order['id']}"):
                                            st.session_state[f"show_del_manage_{order['id']}"] = True
                                            st.rerun()
                                    else:
                                        reason = st.text_input(
                                            f"Motiv ștergere:", 
                                            placeholder="ex: anulat de client",
                                            key=f"del_reason_{order['id']}"
                                        )
                                        col_del_confirm, col_del_cancel = st.columns(2)
                                        with col_del_confirm:
                                            if st.button(f"✅ Confirm ștergere", key=f"del_confirm_{order['id']}"):
                                                if reason.strip():
                                                    if service.delete_order(order['id'], reason):
                                                        st.success(f"✅ Comanda #{order['id']} ștearsă!")
                                                        st.session_state[f"show_del_manage_{order['id']}"] = False
                                                        time.sleep(1)
                                                        st.rerun()
                                                else:
                                                    st.error("⚠️ Te rog introdu un motiv pentru ștergere!")
                                        with col_del_cancel:
                                            if st.button("❌ Anulează", key=f"del_cancel_{order['id']}"):
                                                st.session_state[f"show_del_manage_{order['id']}"] = False
                                                st.rerun()
                
                else:
                    st.info("📭 Nu există comenzi în sistem.")
            
            elif admin_menu == "📊 Dashboard Comenzi":
                st.subheader("📊 Dashboard Comenzi")
                
                orders_df = service.get_orders()
                
                if not orders_df.empty:
                    # Statistici extinse
                    total_orders = len(orders_df)
                    total_revenue = orders_df['price_euro'].sum()
                    pending_orders = len(orders_df[orders_df['status'] == 'pending'])
                    processing_orders = len(orders_df[orders_df['status'] == 'processing'])
                    completed_orders = len(orders_df[orders_df['status'] == 'completed'])
                    
                    # Progres mediu
                    avg_progress = orders_df['progress'].mean()
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Total Comenzi", total_orders)
                    with col2:
                        st.metric("Venit Total", f"{total_revenue:.0f} EUR")
                    with col3:
                        st.metric("În Așteptare", pending_orders)
                    with col4:
                        st.metric("În Procesare", processing_orders)
                    with col5:
                        st.metric("Progres Mediu", f"{avg_progress:.1f}%")
                    
                    # Filtre
                    col1, col2 = st.columns(2)
                    with col1:
                        status_filter = st.selectbox("Filtrează după status:", 
                                                   ["Toate", "pending", "processing", "completed"])
                    with col2:
                        if st.button("🔄 Actualizează Dashboard"):
                            st.rerun()
                    
                    # Afișare comenzi cu progres
                    filtered_df = orders_df if status_filter == "Toate" else orders_df[orders_df['status'] == status_filter]
                    
                    for _, order in filtered_df.iterrows():
                        with st.container():
                            col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                            
                            with col1:
                                st.subheader(f"#{order['id']} - {order['student_name']}")
                                st.write(f"**📧 {order['email']}** • **📱 {order.get('contact_phone', 'Nespecificat')}**")
                                st.write(f"**🎯 {order['resolution']}** • **🖼️ {order['render_count']} randări** • **💰 {order['price_euro']} EUR**")
                                
                                # Bară de progres inline
                                progress = order['progress']
                                st.write(f"**📊 Progres:** {progress}% - {order['current_stage']}")
                                st.progress(progress / 100)
                            
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
                            
                            with col3:
                                if order['download_link']:
                                    st.markdown(f"[📥 Download]({order['download_link']})")
                                created = datetime.strptime(order['created_at'][:10], '%Y-%m-%d')
                                days_passed = (datetime.now() - created).days
                                days_left = max(0, order['estimated_days'] - days_passed)
                                st.markdown(f"**⏳ {days_left}z rămase**")
                            
                            with col4:
                                # Buton ștergere
                                if f"show_delete_{order['id']}" not in st.session_state:
                                    st.session_state[f"show_delete_{order['id']}"] = False
                                
                                if not st.session_state[f"show_delete_{order['id']}"]:
                                    if st.button("🗑️", key=f"delete_btn_{order['id']}"):
                                        st.session_state[f"show_delete_{order['id']}"] = True
                                        st.rerun()
                                else:
                                    reason = st.text_input(
                                        f"Motiv ștergere #{order['id']}:", 
                                        placeholder="ex: anulat de client, eroare, etc.",
                                        key=f"reason_{order['id']}"
                                    )
                                    if st.button("✅ Confirmă ștergere", key=f"confirm_del_{order['id']}"):
                                        if reason.strip():
                                            if service.delete_order(order['id'], reason):
                                                st.success(f"✅ Comanda #{order['id']} a fost ștearsă!")
                                                st.session_state[f"show_delete_{order['id']}"] = False
                                                time.sleep(1)
                                                st.rerun()
                                        else:
                                            st.error("⚠️ Te rog introdu un motiv pentru ștergere!")
                                    
                                    if st.button("❌ Anulează", key=f"cancel_del_{order['id']}"):
                                        st.session_state[f"show_delete_{order['id']}"] = False
                                        st.rerun()
                            
                            st.divider()
                
                else:
                    st.info("📭 Nu există comenzi în sistem.")
            
            elif admin_menu == "📈 Statistici":
                st.subheader("📈 Statistici Avansate")
                
                orders_df = service.get_orders()
                
                if not orders_df.empty:
                    total_revenue = orders_df['price_euro'].sum()
                    completed_orders = len(orders_df[orders_df['status'] == 'completed'])
                    urgent_orders = len(orders_df[orders_df['is_urgent'] == True])
                    processing_orders = len(orders_df[orders_df['status'] == 'processing'])
                    avg_progress = orders_df['progress'].mean()
                    
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("Venit Total", f"{total_revenue:.0f} EUR")
                    with col2:
                        st.metric("Comenzi Finalizate", completed_orders)
                    with col3:
                        st.metric("Comenzi Urgente", urgent_orders)
                    with col4:
                        st.metric("În Procesare", processing_orders)
                    with col5:
                        st.metric("Progres Mediu", f"{avg_progress:.1f}%")
                    
                    # Statistici pe software
                    st.subheader("📊 Statistici pe Software")
                    software_stats = orders_df['software'].value_counts()
                    st.bar_chart(software_stats)
                    
                    # Statistici pe rezoluție
                    st.subheader("🎯 Statistici pe Rezoluție")
                    resolution_stats = orders_df['resolution'].value_counts()
                    st.bar_chart(resolution_stats)
                    
                    # Export date
                    st.subheader("📤 Export Date")
                    csv = orders_df.to_csv(index=False)
                    st.download_button(
                        "📥 Exportă CSV cu toate comenzile",
                        data=csv,
                        file_name=f"comenzi_rendering_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                else:
                    st.info("📭 Nu există comenzi în sistem.")
            
            elif admin_menu == "🗑️ Comenzi Șterse":
                st.subheader("🗑️ Comenzi Șterse")
                
                # Obține toate comenzile inclusiv cele șterse
                orders_df = service.get_orders(include_deleted=True)
                deleted_orders = orders_df[orders_df['is_deleted'] == 1]
                
                if not deleted_orders.empty:
                    st.info(f"📭 Sunt {len(deleted_orders)} comenzi șterse în sistem.")
                    
                    for _, order in deleted_orders.iterrows():
                        with st.container():
                            col1, col2, col3 = st.columns([3, 2, 1])
                            
                            with col1:
                                st.markdown(f'<div class="deleted"><h4>#{order["id"]} - {order["student_name"]}</h4></div>', 
                                          unsafe_allow_html=True)
                                st.write(f"**📧 {order['email']}** • **📱 {order.get('contact_phone', 'Nespecificat')}**")
                                st.write(f"**🎯 {order['resolution']}** • **🖼️ {order['render_count']} randări** • **💰 {order['price_euro']} EUR**")
                                st.write(f"**🗑️ Ștearsă la:** {order['deleted_at']}")
                                if order['deletion_reason']:
                                    st.write(f"**📝 Motiv:** {order['deletion_reason']}")
                            
                            with col2:
                                col_restore, col_permanent = st.columns(2)
                                with col_restore:
                                    if st.button(f"🔄 Restabilește", key=f"restore_{order['id']}"):
                                        if service.restore_order(order['id']):
                                            st.success(f"✅ Comanda #{order['id']} a fost restabilită!")
                                            time.sleep(1)
                                            st.rerun()
                                with col_permanent:
                                    if st.button(f"🗑️ Șterge definitiv", key=f"perm_{order['id']}"):
                                        # Folosim session state pentru a gestiona confirmarea
                                        if f"confirm_perm_{order['id']}" not in st.session_state:
                                            st.session_state[f"confirm_perm_{order['id']}"] = False
                                        
                                        if st.session_state[f"confirm_perm_{order['id']}"]:
                                            if service.permanently_delete_order(order['id']):
                                                st.success(f"✅ Comanda #{order['id']} a fost ștearsă definitiv!")
                                                st.session_state[f"confirm_perm_{order['id']}"] = False
                                                time.sleep(1)
                                                st.rerun()
                                        else:
                                            st.session_state[f"confirm_perm_{order['id']}"] = True
                                            st.warning(f"❌ Sigur vrei să ștergi definitiv comanda #{order['id']}?")
                            
                            st.divider()
                    
                    # Buton pentru ștergerea tuturor comenzilor șterse
                    if st.button("🗑️ Șterge toate comenzile șterse definitiv", type="secondary"):
                        if "confirm_all_deleted" not in st.session_state:
                            st.session_state.confirm_all_deleted = False
                        
                        if st.session_state.confirm_all_deleted:
                            success_count = 0
                            for order_id in deleted_orders['id']:
                                if service.permanently_delete_order(order_id):
                                    success_count += 1
                            st.success(f"✅ {success_count} comenzi șterse definitiv!")
                            st.session_state.confirm_all_deleted = False
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.session_state.confirm_all_deleted = True
                            st.error("❌ CONFIRM: Sigur vrei să ștergi definitiv TOATE comenzile marcate ca șterse?")
                
                else:
                    st.info("🎉 Nu există comenzi șterse în sistem.")
        
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
            **📱 Telefon:** +40 724 911 299
            **💬 WhatsApp:** +40 724 911 299
            
            **💳 Metode de Plată:**
            • **Revolut:** [revolut.me/stefanxuhy](https://revolut.me/stefanxuhy)
            • **Transfer Bancar:** 
              - Beneficiar: STEFANIA BOSTIOG
              - IBAN: RO60 BREL 0002 0036 6187 0100
              - Bancă: Libra Bank

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
            • Tracking progres în timp real
            • Notificări automate
            """)

if __name__ == "__main__":
    main()
