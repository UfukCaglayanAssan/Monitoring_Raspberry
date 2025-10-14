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
        self.check_interval = 60  # 3 dakika
        self.max_retries = 3
        self.retry_delay = 10  # 10 saniye
        
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
    
    def check_wifi_interface(self):
        """WiFi interface'ini kontrol et"""
        success, stdout, stderr = self.run_command("iwconfig wlan0")
        if not success:
            self.log("wlan0 interface bulunamadı", "ERROR")
            return False
            
        if "ESSID" in stdout and "off/any" not in stdout:
            # ESSID var ve bağlı
            essid = stdout.split('ESSID:"')[1].split('"')[0] if 'ESSID:"' in stdout else "Unknown"
            self.log(f"WiFi bağlı: {essid}")
            return True
        else:
            self.log("WiFi bağlı değil", "WARNING")
            return False
    
    def check_internet_ping(self):
        """Ping testi yap"""
        self.log(f"Ping testi başlatılıyor: {self.ping_host}")
        
        success, stdout, stderr = self.run_command(f"ping -c 3 -W 5 {self.ping_host}")
        
        if success:
            self.log(f"✅ Ping başarılı: {self.ping_host}")
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
        
        # Eğer bağlantı yoksa, otomatik bağlanmayı dene
        success, stdout, stderr = self.run_command("nmcli device wifi list")
        if success and "SSID" in stdout:
            self.log("WiFi ağları taranıyor...")
            # Ağ tarama fonksiyonunu çağır
            self.scan_and_connect_wifi()
        
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
    
    def scan_and_connect_wifi(self):
        """WiFi ağlarını tara ve bağlan"""
        self.log("🔍 WiFi ağları taranıyor...")
        
        # WiFi ağlarını listele
        success, stdout, stderr = self.run_command("nmcli device wifi list")
        if not success:
            self.log("WiFi ağları taranamadı", "ERROR")
            return False
        
        # Ağları parse et ve en güçlü sinyalli olanı bul
        lines = stdout.split('\n')
        available_networks = []
        
        for line in lines[1:]:  # İlk satır başlık
            if line.strip() and 'SSID' in line:
                parts = line.split()
                if len(parts) >= 4:
                    ssid = parts[1] if parts[1] != '--' else parts[0]
                    signal = parts[0] if parts[0].isdigit() else '0'
                    security = parts[2] if len(parts) > 2 else 'Open'
                    
                    if ssid and ssid != '--':
                        available_networks.append({
                            'ssid': ssid,
                            'signal': int(signal) if signal.isdigit() else 0,
                            'security': security
                        })
        
        if not available_networks:
            self.log("Kullanılabilir WiFi ağı bulunamadı", "WARNING")
            return False
        
        # Sinyal gücüne göre sırala
        available_networks.sort(key=lambda x: x['signal'], reverse=True)
        
        self.log(f"Bulunan ağlar: {[net['ssid'] for net in available_networks[:3]]}")
        
        # En güçlü sinyalli ağa bağlanmayı dene
        best_network = available_networks[0]
        self.log(f"En güçlü ağ: {best_network['ssid']} (Sinyal: {best_network['signal']}%)")
        
        # Bağlantıyı dene
        if best_network['security'] == 'Open':
            # Açık ağ
            success, stdout, stderr = self.run_command(f"sudo nmcli device wifi connect '{best_network['ssid']}'")
        else:
            # Şifreli ağ - önce kayıtlı bağlantıları kontrol et
            success, stdout, stderr = self.run_command(f"sudo nmcli connection up '{best_network['ssid']}'")
            if not success:
                self.log(f"Kayıtlı bağlantı bulunamadı: {best_network['ssid']}", "WARNING")
                return False
        
        if success:
            self.log(f"✅ WiFi bağlantısı başarılı: {best_network['ssid']}")
            return True
        else:
            self.log(f"❌ WiFi bağlantısı başarısız: {best_network['ssid']}", "ERROR")
            return False
    
    def monitor_loop(self):
        """Ana kontrol döngüsü"""
        self.log("🚀 WiFi Monitor başlatıldı")
        self.log(f"Kontrol aralığı: {self.check_interval} saniye")
        self.log(f"Ping hedefi: {self.ping_host}")
        
        consecutive_failures = 0
        
        while True:
            try:
                self.log("=" * 50)
                self.log("WiFi kontrolü başlatılıyor...")
                
                # 1. WiFi interface kontrolü
                wifi_connected = self.check_wifi_interface()
                
                if not wifi_connected:
                    self.log("WiFi bağlı değil, yeniden bağlanmaya çalışılıyor...", "WARNING")
                    self.restart_wifi()
                    
                    # Yeniden başlatma sonrası WiFi kontrolü
                    time.sleep(10)
                    wifi_connected = self.check_wifi_interface()
                    
                    if not wifi_connected:
                        self.log("WiFi yeniden başlatma sonrası bağlantı yok, ağ tarama yapılıyor...", "WARNING")
                        self.scan_and_connect_wifi()
                        time.sleep(5)
                        wifi_connected = self.check_wifi_interface()
                    
                    if not wifi_connected:
                        consecutive_failures += 1
                        time.sleep(10)
                        continue
                
                # 2. Internet bağlantı kontrolü (ping)
                internet_ok = self.check_internet_ping()
                
                if not internet_ok:
                    # Curl ile tekrar dene
                    self.log("Ping başarısız, curl ile tekrar deneniyor...")
                    internet_ok = self.check_internet_curl()
                
                if internet_ok:
                    self.log("✅ Internet bağlantısı OK")
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1
                    self.log(f"❌ Internet bağlantısı yok (Ardışık hata: {consecutive_failures})", "WARNING")
                    
                    if consecutive_failures >= self.max_retries:
                        self.log(f"⚠️ {self.max_retries} ardışık hata, WiFi yeniden başlatılıyor...", "WARNING")
                        self.get_wifi_info()  # Debug için
                        self.restart_wifi()
                        
                        # Yeniden başlatma sonrası ağ tarama
                        time.sleep(10)
                        wifi_connected = self.check_wifi_interface()
                        if not wifi_connected:
                            self.log("Yeniden başlatma sonrası bağlantı yok, ağ tarama yapılıyor...", "WARNING")
                            self.scan_and_connect_wifi()
                        
                        consecutive_failures = 0
                        time.sleep(15)  # Yeniden başlatma sonrası bekle
                        continue
                
                # Başarılı kontrol sonrası bekle
                self.log(f"Sonraki kontrol {self.check_interval} saniye sonra...")
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
