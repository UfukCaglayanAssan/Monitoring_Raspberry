# -*- coding: utf-8 -*-

import subprocess
import os
import sys
import time
from database import BatteryDatabase

class IPManager:
    def __init__(self):
        self.db = BatteryDatabase()
        self.default_ip = "192.168.1.100"
        self.default_subnet = "255.255.255.0"
        self.default_gateway = "192.168.1.1"
        self.default_dns = "8.8.8.8,8.8.4.4"
    
    def get_current_ip(self):
        """Mevcut IP adresini al"""
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            if result.returncode == 0:
                ips = result.stdout.strip().split()
                return ips[0] if ips else None
            return None
        except Exception as e:
            print(f"IP adresi alınırken hata: {e}")
            return None
    
    def assign_static_ip(self, ip_address, subnet_mask, gateway, dns_servers):
        """Statik IP ataması yap - NetworkManager kullanarak"""
        try:
            print(f"🔄 Statik IP ataması yapılıyor: {ip_address}")
            
            # NetworkManager ile statik IP ata
            self.assign_static_ip_nm(ip_address, subnet_mask, gateway, dns_servers)
            
            print(f"✅ Statik IP ataması tamamlandı: {ip_address}")
            return True
            
        except Exception as e:
            print(f"❌ Statik IP ataması hatası: {e}")
            return False
    
    def assign_static_ip_nm(self, ip_address, subnet_mask, gateway, dns_servers):
        """NetworkManager ile statik IP ata - Direkt çalışan yöntem"""
        try:
            # eth0'ı yönetilebilir yap
            subprocess.run(['nmcli', 'device', 'set', 'eth0', 'managed', 'yes'], check=True)
            print("✓ eth0 yönetilebilir yapıldı")
            
            # Mevcut ethernet bağlantılarını kontrol et
            result = subprocess.run(['nmcli', 'connection', 'show'], capture_output=True, text=True)
            ethernet_connection = None
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'ethernet' in line.lower() and 'eth0' in line:
                        ethernet_connection = line.split()[0]
                        break
            
            if not ethernet_connection:
                # Yeni ethernet bağlantısı oluştur
                subprocess.run(['nmcli', 'connection', 'add', 'type', 'ethernet', 'con-name', 'Static-Eth0', 'ifname', 'eth0'], check=True)
                ethernet_connection = 'Static-Eth0'
                print(f"✓ Yeni ethernet bağlantısı oluşturuldu: {ethernet_connection}")
            
            # Statik IP ayarla
            subprocess.run(['nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.addresses', f'{ip_address}/{self.get_cidr(subnet_mask)}'], check=True)
            subprocess.run(['nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.gateway', gateway], check=True)
            subprocess.run(['nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.dns', dns_servers], check=True)
            subprocess.run(['nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.method', 'manual'], check=True)
            subprocess.run(['nmcli', 'connection', 'modify', ethernet_connection, 'connection.autoconnect', 'yes'], check=True)
            print(f"✓ Statik IP ayarlandı: {ip_address}")
            
            # eth0'ı aktif et
            subprocess.run(['ip', 'link', 'set', 'eth0', 'up'], check=True)
            print("✓ eth0 aktif edildi")
            
            # Bağlantıyı aktif et
            subprocess.run(['nmcli', 'connection', 'up', ethernet_connection], check=True)
            print(f"✓ Bağlantı aktif edildi: {ethernet_connection}")
            
            print(f"✅ NetworkManager ile statik IP atama tamamlandı: {ip_address}")
            
        except Exception as e:
            print(f"❌ NetworkManager IP atama hatası: {e}")
            raise
    
    def backup_dhcpcd_conf(self):
        """dhcpcd.conf dosyasını yedekle"""
        try:
            backup_file = "/etc/dhcpcd.conf.backup"
            if not os.path.exists(backup_file):
                subprocess.run(['sudo', 'cp', '/etc/dhcpcd.conf', backup_file], check=True)
                print("✓ dhcpcd.conf yedeklendi")
        except Exception as e:
            print(f"⚠️ Yedekleme hatası: {e}")
    
    def update_dhcpcd_conf(self, ip_address, subnet_mask, gateway, dns_servers):
        """dhcpcd.conf dosyasını güncelle - sadece eth0 kısmını değiştir"""
        try:
            # Mevcut dosyayı oku
            with open('/etc/dhcpcd.conf', 'r') as f:
                lines = f.readlines()
            
            # eth0 ile ilgili satırları bul ve kaldır
            new_lines = []
            skip_until_empty = False
            
            for line in lines:
                if line.strip().startswith('interface eth0'):
                    skip_until_empty = True
                    # Yeni eth0 konfigürasyonunu ekle
                    new_lines.append(f"interface eth0\n")
                    new_lines.append(f"static ip_address={ip_address}/{self.get_cidr(subnet_mask)}\n")
                    new_lines.append(f"static routers={gateway}\n")
                    new_lines.append(f"static domain_name_servers={dns_servers}\n")
                elif skip_until_empty and line.strip() == '':
                    skip_until_empty = False
                    new_lines.append(line)
                elif not skip_until_empty:
                    new_lines.append(line)
            
            # Dosyayı yaz
            with open('/tmp/dhcpcd_temp.conf', 'w') as f:
                f.writelines(new_lines)
            
            # Dosyayı kopyala
            subprocess.run(['sudo', 'cp', '/tmp/dhcpcd_temp.conf', '/etc/dhcpcd.conf'], check=True)
            os.remove('/tmp/dhcpcd_temp.conf')
            print("✓ dhcpcd.conf güncellendi (sadece eth0 kısmı)")
            
        except Exception as e:
            print(f"❌ dhcpcd.conf güncelleme hatası: {e}")
            raise
    
    def get_cidr(self, subnet_mask):
        """Subnet mask'ı CIDR notasyonuna çevir"""
        mask_map = {
            "255.255.255.0": "24",
            "255.255.0.0": "16",
            "255.0.0.0": "8"
        }
        return mask_map.get(subnet_mask, "24")
    
    def restart_network_service(self):
        """Ağ servisini yeniden başlat"""
        try:
            print("🔄 Ağ servisi yeniden başlatılıyor...")
            
            # Farklı servis isimlerini dene
            services_to_try = [
                'dhcpcd',
                'dhcpcd5', 
                'networking',
                'NetworkManager',
                'systemd-networkd'
            ]
            
            success = False
            for service in services_to_try:
                try:
                    print(f"🔄 {service} servisi deneniyor...")
                    result = subprocess.run(['sudo', 'systemctl', 'restart', service], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0:
                        print(f"✅ {service} servisi başarıyla yeniden başlatıldı")
                        success = True
                        break
                    else:
                        print(f"❌ {service} servisi bulunamadı veya başlatılamadı")
                except subprocess.TimeoutExpired:
                    print(f"⏰ {service} servisi zaman aşımına uğradı")
                except Exception as e:
                    print(f"❌ {service} servisi hatası: {e}")
            
            if not success:
                print("⚠️ Hiçbir ağ servisi yeniden başlatılamadı, manuel kontrol gerekebilir")
                print("💡 Manuel olarak şu komutları deneyin:")
                print("   sudo systemctl restart dhcpcd")
                print("   sudo systemctl restart networking")
                print("   sudo reboot")
            else:
                time.sleep(5)  # Servisin başlaması için bekle
                print("✅ Ağ servisi yeniden başlatma tamamlandı")
                
        except Exception as e:
            print(f"❌ Ağ servisi yeniden başlatma hatası: {e}")
            print("💡 Manuel olarak şu komutları deneyin:")
            print("   sudo systemctl restart dhcpcd")
            print("   sudo reboot")
    
    def check_ip_assignment(self):
        """IP ataması yapılıp yapılmadığını kontrol et"""
        try:
            config = self.db.get_ip_config()
            if config and config.get('is_assigned', False):
                return True, config
            return False, None
        except Exception as e:
            print(f"IP ataması kontrol hatası: {e}")
            return False, None
    
    def initialize_default_ip(self):
        """Sistem ilk başladığında varsayılan IP ataması yap"""
        try:
            # Daha önce IP ataması yapılmış mı kontrol et
            is_assigned, config = self.check_ip_assignment()
            
            if not is_assigned:
                print("🔄 İlk kez çalıştırılıyor, varsayılan IP ataması yapılıyor...")
                
                # Varsayılan IP'yi veritabanına kaydet
                self.db.save_ip_config(
                    ip_address=self.default_ip,
                    subnet_mask=self.default_subnet,
                    gateway=self.default_gateway,
                    dns_servers=self.default_dns,
                    is_assigned=True,
                    is_active=True
                )
                
                # Statik IP ataması yap
                success = self.assign_static_ip(
                    self.default_ip,
                    self.default_subnet,
                    self.default_gateway,
                    self.default_dns
                )
                
                if success:
                    print(f"✅ Varsayılan IP ataması tamamlandı: {self.default_ip}")
                    return True
                else:
                    print("❌ Varsayılan IP ataması başarısız")
                    return False
            else:
                print(f"ℹ️ IP ataması zaten yapılmış: {config.get('ip_address', 'Bilinmiyor')}")
                return True
                
        except Exception as e:
            print(f"❌ Varsayılan IP ataması hatası: {e}")
            return False
    
    def update_ip_config(self, ip_address, subnet_mask, gateway, dns_servers):
        """IP konfigürasyonunu güncelle"""
        try:
            print(f"🔄 IP konfigürasyonu güncelleniyor: {ip_address}")
            
            # Veritabanını güncelle
            self.db.save_ip_config(
                ip_address=ip_address,
                subnet_mask=subnet_mask,
                gateway=gateway,
                dns_servers=dns_servers,
                is_assigned=True,
                is_active=True
            )
            
            # Statik IP ataması yap
            success = self.assign_static_ip(ip_address, subnet_mask, gateway, dns_servers)
            
            if success:
                print(f"✅ IP konfigürasyonu güncellendi: {ip_address}")
                return True
            else:
                print("❌ IP konfigürasyonu güncelleme başarısız")
                return False
                
        except Exception as e:
            print(f"❌ IP konfigürasyonu güncelleme hatası: {e}")
            return False

def main():
    """Ana fonksiyon"""
    if len(sys.argv) < 2:
        print("Kullanım: python ip_manager.py [init|update] [ip] [subnet] [gateway] [dns]")
        sys.exit(1)
    
    command = sys.argv[1]
    ip_manager = IPManager()
    
    if command == "init":
        # İlk başlatma - varsayılan IP ataması
        success = ip_manager.initialize_default_ip()
        sys.exit(0 if success else 1)
        
    elif command == "update":
        # IP güncelleme
        if len(sys.argv) < 6:
            print("Güncelleme için: python ip_manager.py update <ip> <subnet> <gateway> <dns>")
            sys.exit(1)
        
        ip_address = sys.argv[2]
        subnet_mask = sys.argv[3]
        gateway = sys.argv[4]
        dns_servers = sys.argv[5]
        
        success = ip_manager.update_ip_config(ip_address, subnet_mask, gateway, dns_servers)
        sys.exit(0 if success else 1)
        
    else:
        print("Geçersiz komut. Kullanım: init veya update")
        sys.exit(1)

if __name__ == "__main__":
    main()
