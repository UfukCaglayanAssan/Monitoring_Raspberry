#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB Otomatik Güncelleme Scripti
USB cihazı takıldığında otomatik olarak dosyaları günceller
"""

import os
import sys
import shutil
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Log dosyası yolu
LOG_FILE = "/home/bms/usb_updater.log"
UPDATE_MARKER = "UPDATE"  # USB'de aranacak klasör adı
BACKUP_DIR = "/home/bms/usb_update_backups"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Güncellenmesi gereken dosya uzantıları (None ise tüm dosyalar)
ALLOWED_EXTENSIONS = {'.py', '.html', '.js', '.css', '.json', '.md', '.mib', '.sh', '.service'}

# Güncellenmemesi gereken dosyalar/klasörler
EXCLUDED_PATTERNS = [
    '__pycache__',
    '.git',
    '*.pyc',
    '*.pyo',
    '.DS_Store',
    'usb_updater.py',  # Kendisini güncelleme
    'database.db',  # Veritabanı dosyası
    '*.log'
]

def log_message(message, level="INFO"):
    """Log mesajı yaz"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    
    # Konsola yazdır
    print(log_entry.strip())
    
    # Log dosyasına yaz
    try:
        log_dir = os.path.dirname(LOG_FILE)
        if log_dir:  # Eğer dizin belirtilmişse
            os.makedirs(log_dir, exist_ok=True)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Log yazma hatası: {e}")

def find_usb_devices():
    """Bağlı USB cihazlarını bul"""
    usb_devices = []
    
    try:
        # /media ve /mnt dizinlerinde USB cihazlarını ara
        for mount_dir in ['/media', '/mnt']:
            if os.path.exists(mount_dir):
                for item in os.listdir(mount_dir):
                    path = os.path.join(mount_dir, item)
                    if os.path.isdir(path) and os.access(path, os.R_OK):
                        usb_devices.append(path)
        
        # /dev/sd* ve /dev/mmcblk* cihazlarını kontrol et
        # (mount edilmiş olabilir)
        result = subprocess.run(['mount'], capture_output=True, text=True)
        for line in result.stdout.split('\n'):
            if '/dev/sd' in line or '/dev/mmcblk' in line:
                parts = line.split()
                if len(parts) >= 3:
                    mount_point = parts[2]
                    if mount_point not in usb_devices and os.path.exists(mount_point):
                        usb_devices.append(mount_point)
    
    except Exception as e:
        log_message(f"USB cihazları bulunurken hata: {e}", "ERROR")
    
    return usb_devices

def find_update_directory(usb_path):
    """USB'de UPDATE klasörünü bul"""
    update_path = os.path.join(usb_path, UPDATE_MARKER)
    if os.path.exists(update_path) and os.path.isdir(update_path):
        return update_path
    
    # Alt dizinlerde de ara
    try:
        for root, dirs, files in os.walk(usb_path):
            if UPDATE_MARKER in dirs:
                return os.path.join(root, UPDATE_MARKER)
    except Exception as e:
        log_message(f"UPDATE klasörü aranırken hata: {e}", "ERROR")
    
    return None

def should_update_file(file_path):
    """Dosyanın güncellenip güncellenmeyeceğini kontrol et"""
    file_name = os.path.basename(file_path)
    
    # Hariç tutulan pattern'leri kontrol et
    for pattern in EXCLUDED_PATTERNS:
        if pattern in file_name or pattern in file_path:
            return False
    
    # Uzantı kontrolü
    if ALLOWED_EXTENSIONS:
        ext = os.path.splitext(file_name)[1]
        if ext not in ALLOWED_EXTENSIONS:
            return False
    
    return True

def create_backup():
    """Güncelleme öncesi backup oluştur"""
    backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, backup_timestamp)
    
    try:
        os.makedirs(backup_path, exist_ok=True)
        log_message(f"Backup oluşturuluyor: {backup_path}")
        
        # Proje dizinindeki dosyaları kopyala
        files_copied = 0
        for root, dirs, files in os.walk(PROJECT_DIR):
            # Hariç tutulan dizinleri atla
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'node_modules']]
            
            for file in files:
                if should_update_file(file):
                    src = os.path.join(root, file)
                    rel_path = os.path.relpath(src, PROJECT_DIR)
                    dst = os.path.join(backup_path, rel_path)
                    
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)
                    files_copied += 1
        
        log_message(f"Backup tamamlandı: {files_copied} dosya kopyalandı")
        return backup_path
    
    except Exception as e:
        log_message(f"Backup oluşturulurken hata: {e}", "ERROR")
        return None

def copy_files(source_dir, dest_dir):
    """Dosyaları kopyala"""
    updated_files = []
    failed_files = []
    
    try:
        for root, dirs, files in os.walk(source_dir):
            # Hariç tutulan dizinleri atla
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git']]
            
            for file in files:
                if not should_update_file(file):
                    continue
                
                src = os.path.join(root, file)
                rel_path = os.path.relpath(src, source_dir)
                dst = os.path.join(dest_dir, rel_path)
                
                try:
                    # Hedef dizini oluştur
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    
                    # Dosyayı kopyala
                    shutil.copy2(src, dst)
                    updated_files.append(rel_path)
                    log_message(f"Güncellendi: {rel_path}")
                
                except Exception as e:
                    failed_files.append((rel_path, str(e)))
                    log_message(f"Güncellenemedi: {rel_path} - {e}", "ERROR")
    
    except Exception as e:
        log_message(f"Dosya kopyalama hatası: {e}", "ERROR")
    
    return updated_files, failed_files

def restart_services():
    """Güncelleme sonrası servisleri yeniden başlat"""
    services = [
        'tescom-bms.service',  # Ana servis (varsa)
        'web_app.service',     # Web uygulaması servisi (varsa)
    ]
    
    restarted = []
    for service in services:
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                subprocess.run(['systemctl', 'restart', service], check=True)
                restarted.append(service)
                log_message(f"Servis yeniden başlatıldı: {service}")
        except Exception as e:
            log_message(f"Servis yeniden başlatılamadı: {service} - {e}", "WARNING")
    
    return restarted

def main():
    """Ana güncelleme fonksiyonu"""
    log_message("=" * 60)
    log_message("USB Güncelleme Başlatıldı")
    log_message("=" * 60)
    
    # USB cihazlarını bul
    usb_devices = find_usb_devices()
    
    if not usb_devices:
        log_message("USB cihazı bulunamadı", "WARNING")
        return False
    
    log_message(f"Bulunan USB cihazları: {', '.join(usb_devices)}")
    
    # Her USB cihazında UPDATE klasörünü ara
    update_found = False
    for usb_path in usb_devices:
        update_dir = find_update_directory(usb_path)
        
        if update_dir:
            log_message(f"UPDATE klasörü bulundu: {update_dir}")
            update_found = True
            
            # Backup oluştur
            backup_path = create_backup()
            
            # Dosyaları kopyala
            updated_files, failed_files = copy_files(update_dir, PROJECT_DIR)
            
            # Sonuçları logla
            log_message(f"Güncellenen dosyalar: {len(updated_files)}")
            log_message(f"Başarısız dosyalar: {len(failed_files)}")
            
            if failed_files:
                log_message("Başarısız dosyalar:", "ERROR")
                for file, error in failed_files:
                    log_message(f"  - {file}: {error}", "ERROR")
            
            # Servisleri yeniden başlat
            if updated_files:
                restarted = restart_services()
                if restarted:
                    log_message(f"Yeniden başlatılan servisler: {', '.join(restarted)}")
            
            # Güncelleme tamamlandı
            log_message("=" * 60)
            log_message("USB Güncelleme Tamamlandı")
            log_message("=" * 60)
            
            return True
    
    if not update_found:
        log_message(f"Hiçbir USB cihazında '{UPDATE_MARKER}' klasörü bulunamadı", "WARNING")
    
    return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        log_message(f"Kritik hata: {e}", "ERROR")
        import traceback
        log_message(traceback.format_exc(), "ERROR")
        sys.exit(1)

