#!/bin/bash

echo "🧹 Mevcut ethernet bağlantılarını temizliyor..."

# Tüm ethernet bağlantılarını sil
echo "📋 Mevcut bağlantılar:"
nmcli connection show | grep ethernet

echo ""
echo "🗑️  Tüm ethernet bağlantılarını siliyor..."

# Static-Eth0 bağlantılarını sil
nmcli connection delete "Static-Eth0" 2>/dev/null || true
nmcli connection delete "Static-Eth0-1" 2>/dev/null || true
nmcli connection delete "Static-Eth0-2" 2>/dev/null || true
nmcli connection delete "Static-Eth0-3" 2>/dev/null || true
nmcli connection delete "Static-Eth0-4" 2>/dev/null || true
nmcli connection delete "Static-Eth0-5" 2>/dev/null || true

# Kablolu bağlantı 1'i sil
nmcli connection delete "Kablolu bağlantı 1" 2>/dev/null || true

echo "✅ Temizlik tamamlandı!"

echo ""
echo "🔧 eth0'ı yönetilebilir yapıyor..."
sudo nmcli device set eth0 managed yes

echo ""
echo "📡 Yeni ethernet bağlantısı oluşturuyor..."
sudo nmcli connection add type ethernet con-name "Eth0-Static" ifname eth0

echo ""
echo "⚙️  Statik IP ayarlıyor..."
sudo nmcli connection modify "Eth0-Static" ipv4.addresses 192.168.137.3/24
sudo nmcli connection modify "Eth0-Static" ipv4.gateway 192.168.137.1
sudo nmcli connection modify "Eth0-Static" ipv4.dns "8.8.8.8,8.8.4.4"
sudo nmcli connection modify "Eth0-Static" ipv4.method manual
sudo nmcli connection modify "Eth0-Static" connection.autoconnect yes

echo ""
echo "🚀 Bağlantıyı aktif ediyor..."
sudo nmcli connection up "Eth0-Static"

echo ""
echo "📊 Durum kontrolü:"
echo "🔍 eth0 durumu:"
ip link show eth0

echo ""
echo "🔍 IP adresleri:"
ip addr show eth0

echo ""
echo "🔍 Aktif bağlantılar:"
nmcli connection show --active

echo ""
echo "🔍 Cihaz durumu:"
nmcli device status

echo ""
echo "🌐 IP kontrolü:"
hostname -I

echo ""
echo "✅ Kurulum tamamlandı!"
echo "📝 Yeni bağlantı: Eth0-Static"
echo "🌐 IP: 192.168.137.3"
