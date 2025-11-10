#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USB Otomatik Güncelleme Scripti
USB cihazında UPDATE klasörünü bulur ve dosyaları proje dizinine kopyalar
"""

import os
import sys
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Log dosyası yolu
LOG_FILE = "/home/bms/usb_updater.log"
UPDATE_MARKER = "UPDATE"  # USB'de aranacak klasör adı
BACKUP_DIR = "/home/bms/usb_update_backups"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# Güncellenebilen dosya uzantıları
ALLOWED_EXTENSIONS = {
    '.py', '.html', '.js', '.css', '.json', '.md', 
    '.mib', '.sh', '.service', '.txt', '.yml', '.yaml',
    '.conf', '.ini', '.cfg'
}

# Hariç tutulan dosya/klasör pattern'leri
EXCLUDED_PATTERNS = [
    '__pycache__',
    '.git',
    '.pyc',
    '.pyo',
    '.DS_Store',
    'usb_updater.py',  # Kendisini güncelleme
    'database.db',
    '*.log',
    '.env',
    'venv',
    'env',
]

# Yeniden başlatılacak servisler
SERVICES_TO_RESTART = [
    'tescom-bms.service',
    'web_app.service',
    'snmp-agent.service',
]

def log_message(message, level="INFO"):
    """Log mesajı yaz"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
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

def should_exclude(file_path):
    """Dosyanın hariç tutulup tutulmayacağını kontrol et"""
    file_name = os.path.basename(file_path)
    file_path_str = str(file_path)
    
    for pattern in EXCLUDED_PATTERNS:
        if pattern in file_name or pattern in file_path_str:
            return True
    return False

def is_allowed_file(file_path):
    """Dosyanın güncellenebilir olup olmadığını kontrol et"""
    if should_exclude(file_path):
        return False
    
    ext = os.path.splitext(file_path)[1].lower()
    return ext in ALLOWED_EXTENSIONS or ext == ''

def find_usb_device():
    """USB cihazını bul (mount edilmemiş olabilir)"""
    try:
        # lsblk çıktısını al
        result = subprocess.run(['lsblk', '-n', '-o', 'NAME,TYPE,MOUNTPOINT'], 
                              capture_output=True, text=True, timeout=5)
        
        if result.returncode != 0:
            log_message(f"lsblk komutu başarısız: {result.stderr}", "ERROR")
            return None
        
        log_message(f"lsblk çıktısı: {result.stdout}")
        
        # USB cihazlarını bul (disk ve part, mount edilmemiş)
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if not line.strip():
                continue
            parts = line.split()
            if len(parts) >= 2:
                name = parts[0]
                device_type = parts[1]
                mountpoint = parts[2] if len(parts) > 2 else ''
                
                log_message(f"Kontrol ediliyor: name={name}, type={device_type}, mountpoint={mountpoint}")
                
                # USB disk veya partition bul (sda, sdb, sdc gibi)
                # Partition'ı tercih et (sda1, sdb1 gibi)
                if device_type == 'part' and name.startswith('sd') and not mountpoint:
                    device_path = f"/dev/{name}"
                    if os.path.exists(device_path):
                        log_message(f"USB cihazı bulundu: {device_path}")
                        return device_path
        
        log_message("Mount edilmemiş USB cihazı bulunamadı")
        return None
    except Exception as e:
        log_message(f"USB cihazı aranırken hata: {e}", "ERROR")
        import traceback
        log_message(traceback.format_exc(), "ERROR")
        return None

def check_mount_command():
    """Mount komutunun var olup olmadığını kontrol et"""
    try:
        result = subprocess.run(['which', 'mount'], 
                              capture_output=True, text=True, timeout=2)
        return result.returncode == 0
    except:
        return False

def mount_usb_device(device_path, mount_point="/media/usb_update"):
    """USB cihazını mount et"""
    try:
        # Mount komutunun var olup olmadığını kontrol et
        if not check_mount_command():
            log_message("Mount komutu bulunamadı. util-linux paketi yüklü olmalı.", "ERROR")
            log_message("Yüklemek için: sudo apt install util-linux", "ERROR")
            return None
        
        # Mount noktası oluştur
        os.makedirs(mount_point, exist_ok=True)
        
        # Mount et
        result = subprocess.run(['mount', device_path, mount_point],
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            log_message(f"USB cihazı mount edildi: {device_path} -> {mount_point}")
            return mount_point
        else:
            log_message(f"USB mount edilemedi: {result.stderr}", "ERROR")
            return None
    except FileNotFoundError:
        log_message("Mount komutu bulunamadı. util-linux paketi yüklü olmalı.", "ERROR")
        log_message("Yüklemek için: sudo apt install util-linux", "ERROR")
        return None
    except Exception as e:
        log_message(f"USB mount edilirken hata: {e}", "ERROR")
        return None

def find_update_folder(max_retries=10, retry_delay=1):
    """USB cihazlarında UPDATE klasörünü bul (mount edilene kadar bekler)"""
    # Önce mount edilmiş USB'leri kontrol et
    mount_points = [
        '/media',
        '/mnt',
        '/run/media',
    ]
    
    # Mount edilene kadar bekle (maksimum max_retries deneme)
    for attempt in range(max_retries):
        if attempt > 0:
            log_message(f"UPDATE klasörü aranıyor... (Deneme {attempt + 1}/{max_retries})")
            time.sleep(retry_delay)
        
        # Önce mevcut mount noktalarını kontrol et
        for mount_point in mount_points:
            if not os.path.exists(mount_point):
                continue
            
            try:
                # Tüm alt dizinleri kontrol et
                for root, dirs, files in os.walk(mount_point):
                    # UPDATE klasörünü ara
                    if UPDATE_MARKER in dirs:
                        update_path = os.path.join(root, UPDATE_MARKER)
                        if os.path.isdir(update_path):
                            log_message(f"UPDATE klasörü bulundu: {update_path}")
                            return update_path
            except PermissionError:
                continue
            except Exception as e:
                log_message(f"Mount noktası kontrol edilirken hata: {mount_point} - {e}", "ERROR")
                continue
        
        # İlk denemede mount edilmemiş USB varsa mount et
        if attempt == 0:
            usb_device = find_usb_device()
            if usb_device:
                mounted_path = mount_usb_device(usb_device)
                if mounted_path:
                    # Mount edildi, tekrar ara
                    update_path = os.path.join(mounted_path, UPDATE_MARKER)
                    if os.path.isdir(update_path):
                        log_message(f"UPDATE klasörü bulundu (yeni mount): {update_path}")
                        return update_path
    
    return None

def create_backup():
    """Mevcut dosyaların backup'ını oluştur"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, timestamp)
    
    try:
        os.makedirs(backup_path, exist_ok=True)
        log_message(f"Backup dizini oluşturuldu: {backup_path}")
        
        # Proje dizinindeki dosyaları backup'la
        copied_files = 0
        for root, dirs, files in os.walk(PROJECT_DIR):
            # Hariç tutulan klasörleri atla
            dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]
            
            for file in files:
                src_file = os.path.join(root, file)
                if not is_allowed_file(src_file):
                    continue
                
                # Proje dizinine göre relative path
                rel_path = os.path.relpath(src_file, PROJECT_DIR)
                dst_file = os.path.join(backup_path, rel_path)
                
                # Dizin yapısını oluştur
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                
                # Dosyayı kopyala
                shutil.copy2(src_file, dst_file)
                copied_files += 1
        
        log_message(f"Backup tamamlandı: {copied_files} dosya kopyalandı")
        return backup_path
    except Exception as e:
        log_message(f"Backup oluşturulurken hata: {e}", "ERROR")
        return None

def copy_files(source_dir, dest_dir):
    """UPDATE klasöründeki dosyaları proje dizinine kopyala"""
    copied_files = []
    skipped_files = []
    errors = []
    
    try:
        for root, dirs, files in os.walk(source_dir):
            # Hariç tutulan klasörleri atla
            dirs[:] = [d for d in dirs if not should_exclude(os.path.join(root, d))]
            
            for file in files:
                src_file = os.path.join(root, file)
                
                if not is_allowed_file(src_file):
                    skipped_files.append(src_file)
                    continue
                
                # Proje dizinine göre relative path
                rel_path = os.path.relpath(src_file, source_dir)
                dst_file = os.path.join(dest_dir, rel_path)
                
                try:
                    # Dizin yapısını oluştur
                    os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                    
                    # Dosyayı kopyala
                    shutil.copy2(src_file, dst_file)
                    copied_files.append(rel_path)
                    log_message(f"Dosya kopyalandı: {rel_path}")
                except Exception as e:
                    error_msg = f"{rel_path}: {e}"
                    errors.append(error_msg)
                    log_message(error_msg, "ERROR")
        
        log_message(f"Kopyalama tamamlandı: {len(copied_files)} dosya kopyalandı, {len(skipped_files)} dosya atlandı")
        if errors:
            log_message(f"Hatalar: {len(errors)} dosya kopyalanamadı", "ERROR")
        
        return copied_files, skipped_files, errors
    except Exception as e:
        log_message(f"Dosya kopyalama hatası: {e}", "ERROR")
        return [], [], [str(e)]

def restart_services():
    """Güncellenen servisleri yeniden başlat"""
    restarted = []
    failed = []
    
    for service in SERVICES_TO_RESTART:
        try:
            # Servisin var olup olmadığını kontrol et
            result = subprocess.run(
                ['systemctl', 'is-active', service],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                # Servis aktif, yeniden başlat
                log_message(f"Servis yeniden başlatılıyor: {service}")
                result = subprocess.run(
                    ['systemctl', 'restart', service],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    restarted.append(service)
                    log_message(f"Servis yeniden başlatıldı: {service}")
                else:
                    failed.append(service)
                    log_message(f"Servis yeniden başlatılamadı: {service} - {result.stderr}", "ERROR")
            else:
                log_message(f"Servis aktif değil, atlanıyor: {service}")
        except subprocess.TimeoutExpired:
            failed.append(service)
            log_message(f"Servis yeniden başlatma zaman aşımı: {service}", "ERROR")
        except Exception as e:
            failed.append(service)
            log_message(f"Servis yeniden başlatma hatası: {service} - {e}", "ERROR")
    
    if restarted:
        log_message(f"Yeniden başlatılan servisler: {', '.join(restarted)}")
    if failed:
        log_message(f"Yeniden başlatılamayan servisler: {', '.join(failed)}", "ERROR")
    
    return restarted, failed

def main():
    """Ana fonksiyon"""
    log_message("=" * 60)
    log_message("USB Güncelleme Scripti Başlatıldı")
    log_message("=" * 60)
    
    # Debug: Mount noktalarını listele
    log_message(f"Proje dizini: {PROJECT_DIR}")
    log_message("Mount noktaları kontrol ediliyor...")
    
    # UPDATE klasörünü bul
    update_folder = find_update_folder()
    
    if not update_folder:
        log_message("UPDATE klasörü bulunamadı. USB mount edilmemiş olabilir veya UPDATE klasörü yok.", "WARNING")
        log_message("Kontrol edilen mount noktaları: /media, /mnt, /run/media")
        log_message("USB mount edildi mi kontrol edin: mount | grep -i usb")
        log_message("Not: USB mount edilmesi birkaç saniye sürebilir.")
        return 0  # Hata değil, sadece UPDATE klasörü yok
    
    log_message(f"UPDATE klasörü: {update_folder}")
    
    # Backup oluştur
    log_message("Backup oluşturuluyor...")
    backup_path = create_backup()
    
    if not backup_path:
        log_message("Backup oluşturulamadı, devam ediliyor...", "WARNING")
    
    # Dosyaları kopyala
    log_message("Dosyalar kopyalanıyor...")
    copied, skipped, errors = copy_files(update_folder, PROJECT_DIR)
    
    if not copied:
        log_message("Kopyalanacak dosya bulunamadı.", "WARNING")
        return 0
    
    # Servisleri yeniden başlat
    log_message("Servisler yeniden başlatılıyor...")
    restarted, failed = restart_services()
    
    log_message("=" * 60)
    log_message("USB Güncelleme Tamamlandı")
    log_message(f"Kopyalanan dosyalar: {len(copied)}")
    log_message(f"Yeniden başlatılan servisler: {len(restarted)}")
    log_message("=" * 60)
    
    return 0 if not errors else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log_message("Script kullanıcı tarafından durduruldu.", "WARNING")
        sys.exit(1)
    except Exception as e:
        log_message(f"Beklenmeyen hata: {e}", "ERROR")
        import traceback
        log_message(traceback.format_exc(), "ERROR")
        sys.exit(1)
