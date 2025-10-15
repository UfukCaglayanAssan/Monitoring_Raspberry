#!/usr/bin/env python3
"""
WiFi Monitor Service
- WiFi bağlantısını kontrol eder
- Ping testi yapar (8.8.8.8)
- Bağlantı yoksa yeniden bağlanır
- Systemd service olarak çalışır
"""

import subprocess
import time
import logging
import sys
import os
from datetime import datetime

# Logging ayarları
log_file = '/home/bms/Desktop/Monitoring_Raspberry/wifi_monitor.log'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class WiFiMonitor:
    def __init__(self):
        self.ping_host = "8.8.8.8"
        self.check_interval = 60  # 60 saniye
        self.max_retries = 3
        self.retry_delay = 10  # 10 saniye
        self.disconnection_count = 0
        self.last_connection_time = None
        self.start_time = time.time()
        
    def log(self, message, level="INFO"):
        """Log mesajı yaz"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}"
        
        if level == "ERROR":
            logger.error(log_msg)
        elif level == "WARNING":
            logger.warning(log_msg)
        else:
            logger.info(log_msg)
    
    def run_command(self, command, timeout=30):
        """Komut çalıştır ve sonucu döndür"""
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self.log(f"Komut timeout: {command}", "ERROR")
            return False, "", "Timeout"
        except Exception as e:
            self.log(f"Komut hatası: {command} - {e}", "ERROR")
            return False, "", str(e)
    
    
    def check_internet_ping(self):
        """Ping testi yap"""
        success, stdout, stderr = self.run_command(f"ping -c 3 -W 5 {self.ping_host}")
        
        if success:
            return True
        else:
            self.log(f"❌ Ping başarısız: {self.ping_host}", "WARNING")
            return False
    
    def check_internet_curl(self):
        """Curl ile internet kontrolü (yedek)"""
        self.log("Curl ile internet kontrolü")
        
        success, stdout, stderr = self.run_command("curl -s --connect-timeout 10 http://www.google.com")
        
        if success and "google" in stdout.lower():
            self.log("✅ Curl başarılı")
            return True
        else:
            self.log("❌ Curl başarısız", "WARNING")
            return False
    
    def restart_wifi(self):
        """WiFi'yi yeniden başlat - NetworkManager ile"""
        self.log("🔄 WiFi yeniden başlatılıyor...")
        
        # Önce mevcut bağlantıları kontrol et
        success, stdout, stderr = self.run_command("nmcli connection show")
        if success:
            self.log(f"Mevcut bağlantılar: {stdout}")
        
        # WiFi'yi kapat
        self.run_command("sudo nmcli radio wifi off")
        time.sleep(3)
        
        # WiFi'yi aç
        self.run_command("sudo nmcli radio wifi on")
        time.sleep(5)
        
        # Mevcut WiFi bağlantısını yeniden başlat
        self.run_command("sudo nmcli connection up wlan0")
        time.sleep(5)
        
        # WiFi yeniden başlatma tamamlandı
        
        self.log("WiFi yeniden başlatma tamamlandı")
    
    def restart_network_manager(self):
        """NetworkManager'ı yeniden başlat (alternatif)"""
        self.log("🔄 NetworkManager yeniden başlatılıyor...")
        
        self.run_command("sudo systemctl restart NetworkManager")
        time.sleep(10)
        
        self.log("NetworkManager yeniden başlatma tamamlandı")
    
    def get_wifi_info(self):
        """WiFi bilgilerini al"""
        success, stdout, stderr = self.run_command("iwconfig wlan0")
        if success:
            self.log(f"WiFi durumu: {stdout}")
        
        success, stdout, stderr = self.run_command("ip addr show wlan0")
        if success:
            self.log(f"IP durumu: {stdout}")
    
    def connect_to_default_wifi(self):
        """Varsayılan WiFi ağına bağlan"""
        self.log("🔍 Varsayılan WiFi ağına bağlanmaya çalışılıyor...")
        
        # Önce kayıtlı bağlantıları kontrol et
        success, stdout, stderr = self.run_command("nmcli connection show")
        if not success:
            self.log("Kayıtlı bağlantılar alınamadı", "ERROR")
            return False
        
        # xIOT01 ağını öncelikli olarak ara
        xiot_connection = None
        other_connections = []
        
        for line in stdout.split('\n'):
            if 'wifi' in line and '--' in line:  # Aktif olmayan WiFi bağlantıları
                parts = line.split()
                if len(parts) >= 2:
                    connection_name = parts[0]
                    if 'xIOT' in connection_name or 'xIOT01' in connection_name:
                        xiot_connection = connection_name
                    else:
                        other_connections.append(connection_name)
        
        # Önce xIOT01'i dene
        if xiot_connection:
            self.log(f"xIOT01 bağlantısı deneniyor: {xiot_connection}")
            success, stdout, stderr = self.run_command(f"sudo nmcli connection up '{xiot_connection}'")
            if success:
                self.log(f"✅ xIOT01 bağlantısı başarılı: {xiot_connection}")
                return True
            else:
                self.log(f"❌ xIOT01 bağlantısı başarısız: {xiot_connection}", "WARNING")
        
        # xIOT01 başarısızsa diğer bağlantıları dene
        all_connections = [xiot_connection] + other_connections if xiot_connection else other_connections
        all_connections = [conn for conn in all_connections if conn]  # None'ları temizle
        
        if not all_connections:
            self.log("Kayıtlı WiFi bağlantısı bulunamadı", "WARNING")
            return False
        
        for connection in all_connections:
            if connection != xiot_connection:  # xIOT01'i tekrar deneme
                self.log(f"Alternatif bağlantı deneniyor: {connection}")
                success, stdout, stderr = self.run_command(f"sudo nmcli connection up '{connection}'")
                if success:
                    self.log(f"✅ WiFi bağlantısı başarılı: {connection}")
                    return True
                else:
                    self.log(f"❌ WiFi bağlantısı başarısız: {connection}", "WARNING")
        
        return False
    
    def monitor_loop(self):
        """Ana kontrol döngüsü"""
        self.log("🚀 WiFi Monitor başlatıldı")
        self.log(f"Kontrol aralığı: {self.check_interval} saniye")
        self.log(f"Ping hedefi: {self.ping_host}")
        
        consecutive_failures = 0
        
        while True:
            try:
                # Internet bağlantı kontrolü (ping)
                internet_ok = self.check_internet_ping()
                
                if not internet_ok:
                    self.disconnection_count += 1
                    current_time = time.time()
                    uptime = current_time - self.start_time
                    disconnection_rate = (self.disconnection_count / (uptime / 60)) if uptime > 0 else 0
                    
                    self.log(f"❌ Internet bağlantısı yok (Kesilme #{self.disconnection_count}, Sıklık: {disconnection_rate:.2f}/dakika)", "WARNING")
                    
                    # İlk başarısızlıkta hemen WiFi'yi yeniden başlat
                    self.log("🔄 WiFi yeniden başlatılıyor...")
                    self.get_wifi_info()  # Debug için
                    self.restart_wifi()
                    
                    # Varsayılan WiFi'ye bağlanmayı dene
                    time.sleep(10)
                    self.log("Varsayılan WiFi'ye bağlanmaya çalışılıyor...")
                    self.connect_to_default_wifi()
                    
                    time.sleep(15)  # Yeniden başlatma sonrası bekle
                    continue
                
                # Başarılı kontrol sonrası bekle
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                self.log("🛑 WiFi Monitor durduruldu (Ctrl+C)")
                break
            except Exception as e:
                self.log(f"❌ Beklenmeyen hata: {e}", "ERROR")
                time.sleep(30)  # Hata durumunda 30 saniye bekle

def main():
    """Ana fonksiyon"""
    # Root kontrolü (opsiyonel - normal kullanıcı da çalışabilir)
    # if os.geteuid() != 0:
    #     print("❌ Bu script root yetkisi ile çalıştırılmalı!")
    #     print("Kullanım: sudo python3 wifi_monitor.py")
    #     sys.exit(1)
    
    # WiFi Monitor başlat
    monitor = WiFiMonitor()
    monitor.monitor_loop()

if __name__ == "__main__":
    main()
