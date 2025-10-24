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
        """Mevcut IP adresini al - sadece aktif olan IP'yi döndür"""
        try:
            # Önce NetworkManager'dan aktif IP'yi al
            result = subprocess.run(['sudo', 'nmcli', 'device', 'show', 'eth0'], capture_output=True, text=True)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'IP4.ADDRESS[1]:' in line:
                        ip = line.split(':')[1].strip().split('/')[0]
                        print(f"✓ NetworkManager'dan IP alındı: {ip}")
                        return ip
            
            # NetworkManager'dan alınamazsa hostname -I kullan
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            if result.returncode == 0:
                ips = result.stdout.strip().split()
                if ips:
                    # IPv4 adreslerini filtrele ve ilkini al
                    ipv4_ips = [ip for ip in ips if '.' in ip and ':' not in ip]
                    if ipv4_ips:
                        print(f"✓ hostname -I'dan IP alındı: {ipv4_ips[0]}")
                        return ipv4_ips[0]
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
    
    def assign_dhcp_ip(self):
        """DHCP ile IP ataması yap - NetworkManager kullanarak"""
        try:
            print("🔄 DHCP IP ataması yapılıyor...")
            
            # NetworkManager ile DHCP IP ata
            self.assign_dhcp_ip_nm()
            
            print("✅ DHCP IP ataması tamamlandı")
            return True
            
        except Exception as e:
            print(f"❌ DHCP IP ataması hatası: {e}")
            return False
    
    def assign_static_ip_nm(self, ip_address, subnet_mask, gateway, dns_servers):
        """NetworkManager ile statik IP ata - Direkt çalışan yöntem"""
        try:
            # eth0'ı yönetilebilir yap
            subprocess.run(['sudo', 'nmcli', 'device', 'set', 'eth0', 'managed', 'yes'], check=True)
            print("✓ eth0 yönetilebilir yapıldı")
            
            # Mevcut ethernet bağlantılarını kontrol et
            result = subprocess.run(['sudo', 'nmcli', 'connection', 'show'], capture_output=True, text=True)
            ethernet_connection = None
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'ethernet' in line.lower() and 'eth0' in line:
                        ethernet_connection = line.split()[0]
                        break
            
            if not ethernet_connection:
                # Yeni ethernet bağlantısı oluştur
                subprocess.run(['sudo', 'nmcli', 'connection', 'add', 'type', 'ethernet', 'con-name', 'eth0', 'ifname', 'eth0'], check=True)
                ethernet_connection = 'eth0'
                print(f"✓ Yeni ethernet bağlantısı oluşturuldu: {ethernet_connection}")
            
            # Statik IP ayarla
            subprocess.run(['sudo', 'nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.addresses', f'{ip_address}/{self.get_cidr(subnet_mask)}'], check=True)
            if gateway:
                subprocess.run(['sudo', 'nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.gateway', gateway], check=True)
            if dns_servers:
                subprocess.run(['sudo', 'nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.dns', dns_servers], check=True)
            subprocess.run(['sudo', 'nmcli', 'connection', 'modify', ethernet_connection, 'ipv4.method', 'manual'], check=True)
            subprocess.run(['sudo', 'nmcli', 'connection', 'modify', ethernet_connection, 'connection.autoconnect', 'yes'], check=True)
            print(f"✓ Statik IP ayarlandı: {ip_address}")
            
            # dhcpcd servisini etkinleştir (statik IP için)
            try:
                subprocess.run(['sudo', 'systemctl', 'enable', 'dhcpcd'], check=True)
                subprocess.run(['sudo', 'systemctl', 'start', 'dhcpcd'], check=True)
                print("✓ dhcpcd servisi etkinleştirildi")
            except Exception as e:
                print(f"⚠️ dhcpcd servisi etkinleştirilemedi: {e}")
            
            # Bağlantıyı yeniden başlat
            try:
                # Önce bağlantı durumunu kontrol et
                result = subprocess.run(['sudo', 'nmcli', 'connection', 'show', '--active'], capture_output=True, text=True)
                if result.returncode == 0 and ethernet_connection in result.stdout:
                    print(f"✓ {ethernet_connection} bağlantısı aktif, kapatılıyor...")
                    subprocess.run(['sudo', 'nmcli', 'connection', 'down', ethernet_connection], check=True)
                    time.sleep(2)
                else:
                    print(f"✓ {ethernet_connection} bağlantısı zaten kapalı")
                
                # Bağlantıyı başlat
                print(f"✓ {ethernet_connection} bağlantısı başlatılıyor...")
                subprocess.run(['sudo', 'nmcli', 'connection', 'up', ethernet_connection], check=True)
                print(f"✓ Bağlantı yeniden başlatıldı: {ethernet_connection}")
            except Exception as e:
                print(f"❌ Bağlantı yeniden başlatma hatası: {e}")
                print("⚠️ Bağlantı başlatma hatası, ancak statik IP ayarları uygulandı")
            
            print(f"✅ NetworkManager ile statik IP atama tamamlandı: {ip_address}")
            
        except Exception as e:
            print(f"❌ NetworkManager IP atama hatası: {e}")
            raise
    



    def assign_dhcp_ip_nm(self):
        """NetworkManager ile DHCP IP ata"""
        try:
            # eth0'ı yönetilebilir yap
            subprocess.run(["sudo", "nmcli", "device", "set", "eth0", "managed", "yes"], check=True)
            print("✓ eth0 yönetilebilir yapıldı")

            # Var olan ethernet bağlantısını bul
            result = subprocess.run(
                ["sudo", "nmcli", "connection", "show"],
                capture_output=True, text=True
            )
            ethernet_connection = None
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if "ethernet" in line.lower() and "eth0" in line:
                        ethernet_connection = line.split()[0]
                        break

            # Eğer yoksa yeni bağlantı oluştur
            if not ethernet_connection:
                subprocess.run(
                    ["sudo", "nmcli", "connection", "add", "type", "ethernet",
                     "con-name", "eth0", "ifname", "eth0"],
                    check=True
                )
                ethernet_connection = "eth0"
                print(f"✓ Yeni ethernet bağlantısı oluşturuldu: {ethernet_connection}")

            print("🔄 Statik IP ayarları temizleniyor...")

            # Önce DHCP modunu ayarla (manual moddayken gateway temizleme hatası olmasın)
            subprocess.run(
                ["sudo", "nmcli", "connection", "modify", "eth0", "ipv4.method", "auto"],
                check=True
            )

            # Şimdi sırasıyla gateway ve IP adreslerini temizle
            cleanup_cmds = [
                ["sudo", "nmcli", "connection", "modify", "eth0", "ipv4.gateway", ""],
                ["sudo", "nmcli", "connection", "modify", "eth0", "ipv4.addresses", ""],
                ["sudo", "nmcli", "connection", "modify", "eth0", "ipv4.dns", ""],
            ]
            for cmd in cleanup_cmds:
                subprocess.run(cmd, check=False)

            # Arayüzdeki tüm IP’leri temizle
            subprocess.run(["sudo", "ip", "addr", "flush", "dev", "eth0"], check=False)
            print("✓ Statik IP ayarları temizlendi, DHCP moda geçirildi")

            # dhcpcd varsa durdur
            subprocess.run(["sudo", "systemctl", "stop", "dhcpcd"], check=False)
            subprocess.run(["sudo", "systemctl", "disable", "dhcpcd"], check=False)
            print("✓ dhcpcd servisi devre dışı bırakıldı (varsa)")

            # Bağlantıyı yeniden başlat
            print("🔄 Bağlantı yeniden başlatılıyor...")
            subprocess.run(["sudo", "nmcli", "connection", "down", "eth0"], check=False)
            subprocess.run(["sudo", "nmcli", "connection", "up", "eth0"], check=True)
            print("✓ Bağlantı yeniden başlatıldı")

            # IP kontrolü
            time.sleep(3)
            result = subprocess.run(["hostname", "-I"], capture_output=True, text=True)
            if result.returncode == 0:
                ips = result.stdout.strip().split()
                if ips:
                    print(f"✓ Mevcut IP adresleri: {ips}")
                else:
                    print("⚠️ DHCP’den IP alınamadı")
            else:
                print("⚠️ IP kontrolü yapılamadı")

            print("✅ DHCP IP atama işlemi tamamlandı")

        except subprocess.CalledProcessError as e:
            print(f"❌ Komut hatası: {e}")
        except Exception as e:
            print(f"❌ Beklenmeyen hata: {e}")

    
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
    
    def update_ip_config(self, ip_address=None, subnet_mask=None, gateway=None, dns_servers=None, use_dhcp=False):
        """IP konfigürasyonunu güncelle"""
        try:
            if use_dhcp:
                print("🔄 DHCP IP konfigürasyonu güncelleniyor...")
                
                # Veritabanını güncelle (DHCP için - statik IP bilgilerini temizle)
                try:
                    self.db.save_ip_config(
                        ip_address=None,
                        subnet_mask=None,
                        gateway=None,
                        dns_servers=None,
                        is_assigned=True,
                        is_active=True,
                        use_dhcp=True
                    )
                    print("✅ Veritabanı güncellendi (DHCP - statik IP bilgileri temizlendi)")
                except Exception as e:
                    print(f"❌ Veritabanı güncelleme hatası: {e}")
                    return False
                
                # DHCP IP ataması yap
                try:
                    success = self.assign_dhcp_ip()
                    if success:
                        print("✅ DHCP IP konfigürasyonu güncellendi")
                        return True
                    else:
                        print("❌ DHCP IP konfigürasyonu güncelleme başarısız")
                        return False
                except Exception as e:
                    print(f"❌ DHCP IP atama hatası: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            else:
                print(f"🔄 Statik IP konfigürasyonu güncelleniyor: {ip_address}")
                
                # Veritabanını güncelle
                try:
                    self.db.save_ip_config(
                        ip_address=ip_address,
                        subnet_mask=subnet_mask,
                        gateway=gateway,
                        dns_servers=dns_servers,
                        is_assigned=True,
                        is_active=True,
                        use_dhcp=False
                    )
                    print("✅ Veritabanı güncellendi (Statik IP)")
                except Exception as e:
                    print(f"❌ Veritabanı güncelleme hatası: {e}")
                    return False
                
                # Mevcut eth0 bağlantısını güncelle
                try:
                    success = self.update_existing_connection(ip_address, subnet_mask, gateway, dns_servers)
                    if success:
                        print(f"✅ Statik IP konfigürasyonu güncellendi: {ip_address}")
                        return True
                    else:
                        print("❌ Statik IP konfigürasyonu güncelleme başarısız")
                        return False
                except Exception as e:
                    print(f"❌ Statik IP atama hatası: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
                
        except Exception as e:
            print(f"❌ IP konfigürasyonu güncelleme hatası: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def update_existing_connection(self, ip_address, subnet_mask, gateway, dns_servers):
        """Mevcut eth0 bağlantısını güncelle"""
        try:
            print(f"🔄 Mevcut eth0 bağlantısı güncelleniyor: {ip_address}")
            
            # IP adresini güncelle
            try:
                subprocess.run(['sudo', 'nmcli', 'connection', 'modify', 'eth0', 'ipv4.addresses', f'{ip_address}/{self.get_cidr(subnet_mask)}'], check=True)
                print(f"✓ IP adresi güncellendi: {ip_address}")
            except Exception as e:
                print(f"❌ IP adresi güncelleme hatası: {e}")
                return False
            
            # Gateway güncelle
            if gateway:
                try:
                    subprocess.run(['sudo', 'nmcli', 'connection', 'modify', 'eth0', 'ipv4.gateway', gateway], check=True)
                    print(f"✓ Gateway güncellendi: {gateway}")
                except Exception as e:
                    print(f"❌ Gateway güncelleme hatası: {e}")
                    return False
            
            # DNS güncelle
            if dns_servers:
                try:
                    subprocess.run(['sudo', 'nmcli', 'connection', 'modify', 'eth0', 'ipv4.dns', dns_servers], check=True)
                    print(f"✓ DNS güncellendi: {dns_servers}")
                except Exception as e:
                    print(f"❌ DNS güncelleme hatası: {e}")
                    return False
            
            # Manuel mod ayarla
            try:
                subprocess.run(['sudo', 'nmcli', 'connection', 'modify', 'eth0', 'ipv4.method', 'manual'], check=True)
                print("✓ Manuel mod ayarlandı")
            except Exception as e:
                print(f"❌ Manuel mod ayarlama hatası: {e}")
                return False
            
            # dhcpcd servisini etkinleştir (statik IP için)
            try:
                subprocess.run(['sudo', 'systemctl', 'enable', 'dhcpcd'], check=True)
                subprocess.run(['sudo', 'systemctl', 'start', 'dhcpcd'], check=True)
                print("✓ dhcpcd servisi etkinleştirildi")
            except Exception as e:
                print(f"⚠️ dhcpcd servisi etkinleştirilemedi: {e}")
            
            # Bağlantıyı yeniden başlat
            try:
                # Önce bağlantı durumunu kontrol et
                result = subprocess.run(['sudo', 'nmcli', 'connection', 'show', '--active'], capture_output=True, text=True)
                if result.returncode == 0 and 'eth0' in result.stdout:
                    print("✓ eth0 bağlantısı aktif, kapatılıyor...")
                    subprocess.run(['sudo', 'nmcli', 'connection', 'down', 'eth0'], check=True)
                    time.sleep(2)
                else:
                    print("✓ eth0 bağlantısı zaten kapalı")
                
                # Bağlantıyı başlat
                print("✓ eth0 bağlantısı başlatılıyor...")
                subprocess.run(['sudo', 'nmcli', 'connection', 'up', 'eth0'], check=True)
                print("✓ Bağlantı yeniden başlatıldı")
            except Exception as e:
                print(f"❌ Bağlantı yeniden başlatma hatası: {e}")
                # Bağlantı başlatma hatası olsa bile devam et
                print("⚠️ Bağlantı başlatma hatası, ancak IP ayarları uygulandı")
            
            print(f"✅ Mevcut bağlantı güncellendi: {ip_address}")
            return True
            
        except Exception as e:
            print(f"❌ Mevcut bağlantı güncelleme hatası: {e}")
            import traceback
            traceback.print_exc()
            return False

def main():
    """Ana fonksiyon"""
    if len(sys.argv) < 2:
        print("Kullanım: python ip_manager.py [init|update|dhcp] [ip] [subnet] [gateway] [dns]")
        sys.exit(1)
    
    command = sys.argv[1]
    ip_manager = IPManager()
    
    if command == "init":
        # İlk başlatma - varsayılan IP ataması
        success = ip_manager.initialize_default_ip()
        sys.exit(0 if success else 1)
        
    elif command == "update":
        # Statik IP güncelleme
        if len(sys.argv) < 6:
            print("Güncelleme için: python ip_manager.py update <ip> <subnet> <gateway> <dns>")
            sys.exit(1)
        
        ip_address = sys.argv[2]
        subnet_mask = sys.argv[3]
        gateway = sys.argv[4]
        dns_servers = sys.argv[5]
        
        success = ip_manager.update_ip_config(ip_address, subnet_mask, gateway, dns_servers, use_dhcp=False)
        sys.exit(0 if success else 1)
        
    elif command == "dhcp":
        # DHCP IP güncelleme
        success = ip_manager.update_ip_config(use_dhcp=True)
        sys.exit(0 if success else 1)
        
    else:
        print("Geçersiz komut. Kullanım: init, update veya dhcp")
        sys.exit(1)

if __name__ == "__main__":
    main()
