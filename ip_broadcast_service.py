#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Raspberry Pi IP Broadcast Service
Bu servis, Raspberry Pi'nin IP adresini UDP broadcast ile yayınlar.
Windows IP bulucu uygulaması bu broadcast'leri dinleyerek IP'yi öğrenebilir.
"""

import socket
import json
import time
import threading
import subprocess
import sys
import os

# Broadcast ayarları
BROADCAST_PORT = 9999
BROADCAST_INTERVAL = 5  # saniye

def get_current_ip():
    """Mevcut IP adresini al"""
    try:
        # Önce NetworkManager'dan aktif IP'yi al
        result = subprocess.run(['sudo', 'nmcli', 'device', 'show', 'eth0'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'IP4.ADDRESS[1]:' in line:
                    ip = line.split(':')[1].strip().split('/')[0]
                    return ip
        
        # NetworkManager'dan alınamazsa hostname -I kullan
        result = subprocess.run(['hostname', '-I'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ips = result.stdout.strip().split()
            if ips:
                # IPv4 adreslerini filtrele ve ilkini al
                ipv4_ips = [ip for ip in ips if '.' in ip and ':' not in ip]
                if ipv4_ips:
                    return ipv4_ips[0]
        
        # Son çare: socket ile bağlantı yaparak IP'yi öğren
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Bağlantı yapmadan sadece IP'yi öğrenmek için
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            return ip
        except:
            pass
        finally:
            s.close()
        
        return None
    except Exception as e:
        print(f"⚠️ IP adresi alınırken hata: {e}")
        return None

def get_hostname():
    """Hostname'i al"""
    try:
        return socket.gethostname()
    except:
        return "raspberrypi"

def get_web_port():
    """Web uygulamasının portunu al (varsayılan 80)"""
    return 80

def create_broadcast_message():
    """Broadcast mesajı oluştur"""
    ip = get_current_ip()
    if not ip:
        return None
    
    message = {
        'type': 'tescom_bms_discovery',
        'ip': ip,
        'hostname': get_hostname(),
        'port': get_web_port(),
        'timestamp': int(time.time()),
        'version': '1.0'
    }
    
    return json.dumps(message).encode('utf-8')

def broadcast_loop():
    """Broadcast döngüsü - thread olarak çalışır"""
    print("🚀 IP Broadcast Servisi başlatılıyor...")
    
    try:
        # UDP socket oluştur
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # Socket'i bağla
        sock.bind(('', 0))  # Herhangi bir port
        
        print(f"✅ Broadcast socket oluşturuldu")
        print(f"📡 Broadcast portu: {BROADCAST_PORT}")
        print(f"⏱️  Broadcast aralığı: {BROADCAST_INTERVAL} saniye")
        
        last_ip = None
        
        while True:
            try:
                # Broadcast mesajı oluştur
                message = create_broadcast_message()
                
                if message:
                    # Broadcast adresine gönder
                    sock.sendto(message, ('<broadcast>', BROADCAST_PORT))
                    
                    # IP değiştiyse logla
                    current_ip = get_current_ip()
                    if current_ip != last_ip:
                        print(f"📡 IP yayınlanıyor: {current_ip} (Port: {get_web_port()})")
                        last_ip = current_ip
                else:
                    print("⚠️ IP adresi alınamadı, broadcast atlanıyor...")
                
                # Belirli aralıklarla bekle
                time.sleep(BROADCAST_INTERVAL)
                
            except Exception as e:
                print(f"❌ Broadcast hatası: {e}")
                time.sleep(BROADCAST_INTERVAL)
                
    except Exception as e:
        print(f"❌ Broadcast servisi hatası: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            sock.close()
        except:
            pass

def main():
    """Ana fonksiyon"""
    print("=" * 50)
    print("🔍 TESCOM BMS IP Broadcast Servisi")
    print("=" * 50)
    
    # İlk IP'yi göster
    ip = get_current_ip()
    if ip:
        print(f"✅ Mevcut IP: {ip}")
    else:
        print("⚠️ IP adresi alınamadı!")
    
    # Broadcast servisini thread olarak başlat
    broadcast_thread = threading.Thread(target=broadcast_loop, daemon=True)
    broadcast_thread.start()
    
    print("\n✅ Broadcast servisi çalışıyor...")
    print("⏹️  Durdurmak için Ctrl+C basın\n")
    
    try:
        # Ana thread'i canlı tut
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Broadcast servisi durduruluyor...")
        sys.exit(0)

if __name__ == '__main__':
    main()



