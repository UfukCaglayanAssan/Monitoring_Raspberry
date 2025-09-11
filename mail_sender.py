# -*- coding: utf-8 -*-

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import threading
import time
from database import BatteryDatabase

class MailSender:
    def __init__(self):
        # Veritabanı bağlantısı
        self.db = BatteryDatabase()
        
        # SSL/TLS ayarları
        self.context = ssl.create_default_context()
    
    def get_mail_config(self):
        """Veritabanından mail konfigürasyonunu al"""
        try:
            config = self.db.get_mail_server_config()
            if config and config.get('is_active', False):
                return config
            return None
        except Exception as e:
            print(f"Mail konfigürasyonu alınırken hata: {e}")
            return None
        
    def send_alarm_email(self, recipients, alarm_data):
        """Alarm maili gönder"""
        try:
            # Mail konfigürasyonunu kontrol et
            config = self.get_mail_config()
            if not config:
                print("❌ Mail sunucu konfigürasyonu bulunamadı veya aktif değil")
                return False
            
            # Mail içeriği oluştur
            subject = "🚨 Akü İzleme Sistemi - Alarm Bildirimi"
            body = self.create_alarm_email_body(alarm_data)
            
            # Her alıcıya mail gönder
            for recipient in recipients:
                self.send_single_email(recipient['email'], recipient['name'], subject, body, config)
                
            print(f"✅ Alarm maili {len(recipients)} alıcıya gönderildi")
            return True
            
        except Exception as e:
            print(f"❌ Mail gönderme hatası: {e}")
            return False
    
    def send_single_email(self, recipient_email, recipient_name, subject, body, config):
        """Tek alıcıya mail gönder"""
        try:
            # Mail mesajı oluştur
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = config['smtp_username']
            message["To"] = recipient_email
            
            # HTML içerik
            html_body = MIMEText(body, "html", "utf-8")
            message.attach(html_body)
            
            # SMTP bağlantısı ve mail gönderme
            with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
                if config.get('use_tls', True):
                    server.starttls(context=self.context)
                
                # Kullanıcı adı ve şifre varsa giriş yap
                if config.get('smtp_username') and config.get('smtp_password'):
                    server.login(config['smtp_username'], config['smtp_password'])
                
                server.sendmail(config['smtp_username'], recipient_email, message.as_string())
                
            print(f"✅ Mail gönderildi: {recipient_name} ({recipient_email})")
            
        except Exception as e:
            print(f"❌ Mail gönderme hatası ({recipient_email}): {e}")
            raise
    
    def create_alarm_email_body(self, alarm_data):
        """Alarm mail içeriği oluştur"""
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        # Kol alarmları ve batarya alarmlarını ayır
        arm_alarms = [alarm for alarm in alarm_data if alarm.get('type') == 'arm']
        battery_alarms = [alarm for alarm in alarm_data if alarm.get('type') == 'battery']
        
        html = f"""
        <!DOCTYPE html>
        <html lang="tr">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Alarm Bildirimi</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 800px; margin: 0 auto; background: white; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                .header {{ background: #dc3545; color: white; padding: 20px; border-radius: 10px 10px 0 0; text-align: center; }}
                .content {{ padding: 20px; }}
                .alarm-section {{ margin-bottom: 30px; }}
                .alarm-table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
                .alarm-table th, .alarm-table td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
                .alarm-table th {{ background-color: #f8f9fa; font-weight: bold; }}
                .arm-alarm {{ background-color: #fff3cd; }}
                .battery-alarm {{ background-color: #f8d7da; }}
                .footer {{ background: #f8f9fa; padding: 15px; text-align: center; border-radius: 0 0 10px 10px; color: #6c757d; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🚨 Akü İzleme Sistemi - Alarm Bildirimi</h1>
                    <p>Tarih: {current_time}</p>
                </div>
                
                <div class="content">
                    <h2>Alarm Detayları</h2>
        """
        
        # Kol alarmları
        if arm_alarms:
            html += f"""
                    <div class="alarm-section">
                        <h3>🔧 Kol Alarmları ({len(arm_alarms)} adet)</h3>
                        <table class="alarm-table">
                            <thead>
                                <tr>
                                    <th>Kol</th>
                                    <th>Açıklama</th>
                                    <th>Tarih</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            for alarm in arm_alarms:
                html += f"""
                                <tr class="arm-alarm">
                                    <td>Kol {alarm['arm']}</td>
                                    <td>{alarm['description']}</td>
                                    <td>{alarm['timestamp']}</td>
                                </tr>
                """
            html += """
                            </tbody>
                        </table>
                    </div>
            """
        
        # Batarya alarmları
        if battery_alarms:
            html += f"""
                    <div class="alarm-section">
                        <h3>🔋 Batarya Alarmları ({len(battery_alarms)} adet)</h3>
                        <table class="alarm-table">
                            <thead>
                                <tr>
                                    <th>Kol</th>
                                    <th>Batarya</th>
                                    <th>Açıklama</th>
                                    <th>Tarih</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            for alarm in battery_alarms:
                html += f"""
                                <tr class="battery-alarm">
                                    <td>Kol {alarm['arm']}</td>
                                    <td>{alarm['battery']}</td>
                                    <td>{alarm['description']}</td>
                                    <td>{alarm['timestamp']}</td>
                                </tr>
                """
            html += """
                            </tbody>
                        </table>
                    </div>
            """
        
        html += f"""
                </div>
                
                <div class="footer">
                    <p>Bu mail otomatik olarak Akü İzleme Sistemi tarafından gönderilmiştir.</p>
                    <p>Gönderim Zamanı: {current_time}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html

# Global mail sender instance
mail_sender = MailSender()

def send_alarm_notification(recipients, alarm_data):
    """Alarm bildirimi gönder (thread-safe)"""
    def send_in_thread():
        try:
            mail_sender.send_alarm_email(recipients, alarm_data)
        except Exception as e:
            print(f"❌ Mail gönderme thread hatası: {e}")
    
    # Arka planda mail gönder
    thread = threading.Thread(target=send_in_thread)
    thread.daemon = True
    thread.start()
