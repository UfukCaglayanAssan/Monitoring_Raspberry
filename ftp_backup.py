#!/usr/bin/env python3
"""
SFTP Backup Script
Veritabanını SFTP sunucusuna yedekler (Güvenli)
"""

import sys
import os
import paramiko
import base64
from datetime import datetime

# Proje dizinini path'e ekle
sys.path.insert(0, '/home/bms/Desktop/Monitoring_Raspberry')
os.chdir('/home/bms/Desktop/Monitoring_Raspberry')

from database import BatteryDatabase

def send_database_to_sftp():
    """Veritabanını SFTP sunucusuna gönder (Güvenli)"""
    try:
        print(f"[{datetime.now()}] SFTP yedekleme başlatılıyor...")
        
        # Veritabanından SFTP ayarlarını al
        db = BatteryDatabase()
        config = db.get_ftp_config()
        
        if not config:
            print("❌ SFTP konfigürasyonu bulunamadı!")
            return False
        
        if not config.get('is_active'):
            print("⚠️ SFTP otomatik yedekleme pasif!")
            return False
        
        sftp_host = config.get('ftp_host')
        sftp_port = config.get('ftp_port', 22)  # SFTP default port 22
        sftp_username = config.get('ftp_username')
        sftp_password = config.get('ftp_password')
        
        if not all([sftp_host, sftp_username, sftp_password]):
            print("❌ SFTP ayarları eksik!")
            return False
        
        # Şifreyi decode et
        try:
            sftp_password = base64.b64decode(sftp_password.encode()).decode()
        except:
            pass  # Zaten düz metin
        
        # Veritabanı dosyası
        db_file = '/home/bms/Desktop/battery_data.db'
        
        if not os.path.exists(db_file):
            print(f"❌ Veritabanı dosyası bulunamadı: {db_file}")
            return False
        
        # Dosya boyutu
        file_size = os.path.getsize(db_file)
        file_size_mb = file_size / (1024 * 1024)
        print(f"📦 Dosya boyutu: {file_size_mb:.2f} MB")
        
        # SFTP bağlantısı
        print(f"🔌 SFTP sunucusuna bağlanılıyor: {sftp_host}:{sftp_port}")
        
        # SSH client oluştur
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Bağlan
        ssh.connect(
            hostname=sftp_host,
            port=sftp_port,
            username=sftp_username,
            password=sftp_password,
            timeout=30
        )
        
        # SFTP client aç
        sftp = ssh.open_sftp()
        
        print(f"✅ SFTP bağlantısı başarılı!")
        print(f"📂 Mevcut dizin: {sftp.getcwd() or '/'}")
        
        # Hedef klasöre git (varsa)
        try:
            sftp.chdir('bms_backup')
            print(f"📂 Hedef klasöre geçildi: {sftp.getcwd()}")
        except IOError:
            # Klasör yoksa oluşturmayı dene
            try:
                print(f"📁 Klasör bulunamadı, oluşturuluyor: bms_backup")
                sftp.mkdir('bms_backup')
                sftp.chdir('bms_backup')
                print(f"✅ Klasör oluşturuldu ve geçildi")
            except IOError:
                # İzin yoksa ana dizinde kal
                print(f"⚠️ Klasör oluşturma izni yok, ana dizine kaydedilecek")
        
        # Dosya adı (tarih ile)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        remote_filename = f'battery_data_{timestamp}.db'
        
        # Dosyayı gönder
        print(f"📤 Dosya gönderiliyor: {remote_filename}")
        sftp.put(db_file, remote_filename)
        
        print(f"✅ Dosya başarıyla gönderildi: {remote_filename}")
        
        # Bağlantıyı kapat
        sftp.close()
        ssh.close()
        
        # Son gönderim zamanını güncelle
        db.update_ftp_last_sent()
        
        print(f"[{datetime.now()}] SFTP yedekleme tamamlandı!")
        return True
        
    except paramiko.AuthenticationException as e:
        print(f"❌ SFTP kimlik doğrulama hatası: {e}")
        return False
    except paramiko.SSHException as e:
        print(f"❌ SFTP SSH hatası: {e}")
        return False
    except Exception as e:
        print(f"❌ Genel hata: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = send_database_to_sftp()
    sys.exit(0 if success else 1)

