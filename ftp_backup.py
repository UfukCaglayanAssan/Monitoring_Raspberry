#!/usr/bin/env python3
"""
FTP Backup Script
Veritabanını FTP sunucusuna yedekler
"""

import sys
import os
import ftplib
import base64
from datetime import datetime

# Proje dizinini path'e ekle
sys.path.insert(0, '/home/bms/Desktop/Monitoring_Raspberry')
os.chdir('/home/bms/Desktop/Monitoring_Raspberry')

from database import BatteryDatabase

def send_database_to_ftp():
    """Veritabanını FTP sunucusuna gönder"""
    try:
        print(f"[{datetime.now()}] FTP yedekleme başlatılıyor...")
        
        # Veritabanından FTP ayarlarını al
        db = BatteryDatabase()
        config = db.get_ftp_config()
        
        if not config:
            print("❌ FTP konfigürasyonu bulunamadı!")
            return False
        
        if not config.get('is_active'):
            print("⚠️ FTP otomatik yedekleme pasif!")
            return False
        
        ftp_host = config.get('ftp_host')
        ftp_port = config.get('ftp_port', 21)
        ftp_username = config.get('ftp_username')
        ftp_password = config.get('ftp_password')
        
        if not all([ftp_host, ftp_username, ftp_password]):
            print("❌ FTP ayarları eksik!")
            return False
        
        # Şifreyi decode et
        try:
            ftp_password = base64.b64decode(ftp_password.encode()).decode()
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
        
        # FTP bağlantısı
        print(f"🔌 FTP sunucusuna bağlanılıyor: {ftp_host}:{ftp_port}")
        ftp = ftplib.FTP()
        ftp.connect(ftp_host, ftp_port, timeout=30)
        ftp.login(ftp_username, ftp_password)
        
        print(f"✅ FTP bağlantısı başarılı!")
        print(f"📂 Mevcut dizin: {ftp.pwd()}")
        
        # Hedef klasöre git (varsa)
        try:
            ftp.cwd('bms_backup')  # Klasör adı
            print(f"📂 Hedef klasöre geçildi: {ftp.pwd()}")
        except ftplib.error_perm:
            # Klasör yoksa oluşturmayı dene
            try:
                print(f"📁 Klasör bulunamadı, oluşturuluyor: bms_backup")
                ftp.mkd('bms_backup')
                ftp.cwd('bms_backup')
                print(f"✅ Klasör oluşturuldu ve geçildi")
            except ftplib.error_perm:
                # İzin yoksa ana dizinde kal
                print(f"⚠️ Klasör oluşturma izni yok, ana dizine kaydedilecek: {ftp.pwd()}")
        
        # Dosya adı (tarih ile)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        remote_filename = f'battery_data_{timestamp}.db'
        
        # Dosyayı gönder
        print(f"📤 Dosya gönderiliyor: {remote_filename}")
        with open(db_file, 'rb') as file:
            ftp.storbinary(f'STOR {remote_filename}', file)
        
        print(f"✅ Dosya başarıyla gönderildi: {remote_filename}")
        
        # Bağlantıyı kapat
        ftp.quit()
        
        # Son gönderim zamanını güncelle
        db.update_ftp_last_sent()
        
        print(f"[{datetime.now()}] FTP yedekleme tamamlandı!")
        return True
        
    except ftplib.all_errors as e:
        print(f"❌ FTP hatası: {e}")
        return False
    except Exception as e:
        print(f"❌ Genel hata: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = send_database_to_ftp()
    sys.exit(0 if success else 1)

