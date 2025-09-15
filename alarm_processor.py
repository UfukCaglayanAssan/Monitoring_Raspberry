# -*- coding: utf-8 -*-

import time
import threading
from datetime import datetime
from database import BatteryDatabase
from mail_sender import send_alarm_notification

class AlarmProcessor:
    def __init__(self):
        self.db = BatteryDatabase()
        self.pending_alarms = []  # Bekleyen alarmlar
        self.pending_resolves = []  # Bekleyen düzeltmeler
        self.lock = threading.Lock()
        
    def add_alarm(self, arm, battery, error_msb, error_lsb, timestamp):
        """Yeni alarm ekle (periyot bitiminde işlenecek)"""
        with self.lock:
            alarm_data = {
                'arm': arm,
                'battery': battery,
                'error_code_msb': error_msb,
                'error_code_lsb': error_lsb,
                'timestamp': timestamp,
                'type': 'battery' if error_lsb != 9 else 'arm'  # 9 = kol alarmı
            }
            self.pending_alarms.append(alarm_data)
            print(f"📝 Alarm eklendi (beklemede): Kol {arm}, Batarya {battery}, MSB {error_msb}, LSB {error_lsb}")
    
    def add_resolve(self, arm, battery):
        """Alarm düzeltme ekle (periyot bitiminde işlenecek)"""
        with self.lock:
            resolve_data = {
                'arm': arm,
                'battery': battery,
                'timestamp': int(time.time() * 1000)
            }
            self.pending_resolves.append(resolve_data)
            print(f"🔧 Alarm düzeltme eklendi (beklemede): Kol {arm}, Batarya {battery}")
    
    def process_period_end(self):
        """Periyot bitiminde tüm bekleyen alarmları işle"""
        with self.lock:
            if not self.pending_alarms and not self.pending_resolves:
                print("ℹ️ İşlenecek alarm/düzeltme yok")
                return
            
            print(f"🔄 Periyot bitimi - {len(self.pending_alarms)} alarm, {len(self.pending_resolves)} düzeltme işleniyor...")
            
            # Alarmları kaydet
            if self.pending_alarms:
                success = self.db.batch_insert_alarms(self.pending_alarms)
                if success:
                    # Mail gönder
                    self.send_alarm_emails(self.pending_alarms)
                    self.pending_alarms.clear()
            
            # Düzeltmeleri işle
            if self.pending_resolves:
                self.process_resolves()
                self.pending_resolves.clear()
    
    def process_resolves(self):
        """Bekleyen düzeltmeleri işle"""
        try:
            for resolve in self.pending_resolves:
                arm = resolve['arm']
                battery = resolve['battery']
                
                # Veritabanından aktif alarmları bul ve düzelt
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # Kol alarmı mı batarya alarmı mı kontrol et
                    if battery == 0:  # Kol alarmı
                        cursor.execute('''
                            SELECT id FROM alarms 
                            WHERE arm = ? AND battery = 0 AND status = 'active'
                        ''', (arm,))
                    else:  # Batarya alarmı
                        cursor.execute('''
                            SELECT id FROM alarms 
                            WHERE arm = ? AND battery = ? AND status = 'active'
                        ''', (arm, battery))
                    
                    alarm_ids = [row[0] for row in cursor.fetchall()]
                    
                    if alarm_ids:
                        success = self.db.batch_resolve_alarms(alarm_ids)
                        if success:
                            print(f"✅ {len(alarm_ids)} alarm düzeltildi: Kol {arm}, Batarya {battery}")
                        else:
                            print(f"❌ Alarm düzeltme hatası: Kol {arm}, Batarya {battery}")
                    else:
                        print(f"⚠️ Düzeltilecek aktif alarm bulunamadı: Kol {arm}, Batarya {battery}")
                        
        except Exception as e:
            print(f"❌ Düzeltme işleme hatası: {e}")
    
    def send_alarm_emails(self, alarms):
        """Alarm maili gönder"""
        try:
            # Mail alıcılarını al
            recipients = self.db.get_mail_recipients()
            if not recipients:
                print("⚠️ Mail alıcısı bulunamadı")
                return
            
            # Alarm verilerini işle ve seviyelerine göre grupla
            critical_alarms = []
            normal_alarms = []
            
            for alarm in alarms:
                processed_alarm = self.process_alarm_for_email(alarm)
                if processed_alarm:
                    # Alarm seviyesini belirle
                    severity = self.db.determine_alarm_severity(alarm['error_code_msb'], alarm['error_code_lsb'])
                    processed_alarm['severity'] = severity
                    
                    if severity == 'critical':
                        critical_alarms.append(processed_alarm)
                    else:
                        normal_alarms.append(processed_alarm)
            
            if not critical_alarms and not normal_alarms:
                print("⚠️ İşlenecek alarm bulunamadı")
                return
            
            # Kritik alarmlar için mail gönder
            if critical_alarms:
                critical_recipients = [r for r in recipients if r.get('receive_critical_alarms', True)]
                if critical_recipients:
                    from mail_sender import send_alarm_notification
                    send_alarm_notification(critical_recipients, critical_alarms)
                    print(f"✅ {len(critical_alarms)} kritik alarm için mail gönderildi ({len(critical_recipients)} alıcıya)")
            
            # Normal alarmlar için mail gönder
            if normal_alarms:
                normal_recipients = [r for r in recipients if r.get('receive_normal_alarms', True)]
                if normal_recipients:
                    from mail_sender import send_alarm_notification
                    send_alarm_notification(normal_recipients, normal_alarms)
                    print(f"✅ {len(normal_alarms)} normal alarm için mail gönderildi ({len(normal_recipients)} alıcıya)")
                
        except Exception as e:
            print(f"❌ Mail gönderme hatası: {e}")
    
    def process_alarm_for_email(self, alarm):
        """Alarm verisini mail için işle"""
        try:
            arm = alarm['arm']
            battery = alarm['battery']
            error_msb = alarm['error_code_msb']
            error_lsb = alarm['error_code_lsb']
            timestamp = alarm['timestamp']
            
            # Timestamp'i formatla
            formatted_time = datetime.fromtimestamp(timestamp / 1000).strftime('%d.%m.%Y %H:%M:%S')
            
            # Alarm açıklaması oluştur
            if error_lsb == 9:  # Kol alarmı
                description = self.get_arm_alarm_description(error_msb)
                return {
                    'type': 'arm',
                    'arm': arm,
                    'battery': 'Kol Alarmı',
                    'description': description,
                    'timestamp': formatted_time
                }
            else:  # Batarya alarmı
                description = self.get_battery_alarm_description(error_msb, error_lsb)
                if description:  # Geçerli alarm ise
                    return {
                        'type': 'battery',
                        'arm': arm,
                        'battery': str(battery - 2) if battery > 2 else '',
                        'description': description,
                        'timestamp': formatted_time
                    }
            
            return None
            
        except Exception as e:
            print(f"❌ Alarm işleme hatası: {e}")
            return None
    
    def get_arm_alarm_description(self, error_msb):
        """Kol alarm açıklaması"""
        descriptions = {
            0: "Kol alarmı düzeldi",
            1: "Kol sıcaklık alarmı",
            2: "Kol nem alarmı",
            3: "Kol bağlantı hatası",
            4: "Kol güç hatası"
        }
        return descriptions.get(error_msb, f"Bilinmeyen kol alarmı (Kod: {error_msb})")
    
    def get_battery_alarm_description(self, error_msb, error_lsb):
        """Batarya alarm açıklaması oluştur"""
        description_parts = []
        
        # MSB kontrolü
        if error_msb >= 1:
            if error_msb == 1:
                description_parts.append("Pozitif kutup başı alarmı")
            elif error_msb == 2:
                description_parts.append("Negatif kutup başı sıcaklık alarmı")
        
        # LSB kontrolü
        if error_lsb == 4:
            description_parts.append("Düşük batarya gerilim uyarısı")
        elif error_lsb == 8:
            description_parts.append("Düşük batarya gerilimi alarmı")
        elif error_lsb == 16:
            description_parts.append("Yüksek batarya gerilimi uyarısı")
        elif error_lsb == 32:
            return "Yüksek batarya gerilimi alarmı"
        elif error_lsb == 64:
            description_parts.append("Modül sıcaklık alarmı")
        
        return " + ".join(description_parts) if description_parts else None

# Global alarm processor instance
alarm_processor = AlarmProcessor()
