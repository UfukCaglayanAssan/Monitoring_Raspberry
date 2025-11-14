#!/bin/bash
# Veritabanı için Ayrı Partition Kurulum Scripti

echo "=========================================="
echo "Veritabanı Partition Kurulumu"
echo "=========================================="

# 1. USB veya SD kart ikinci partition'ı kontrol et
echo "1. Mevcut diskleri kontrol ediliyor..."
lsblk

echo ""
read -p "Veritabanı için kullanılacak disk/partition'ı girin (örn: /dev/sda2 veya /dev/mmcblk0p3): " PARTITION

if [ -z "$PARTITION" ]; then
    echo "❌ Partition belirtilmedi!"
    exit 1
fi

# 2. Mount point oluştur
MOUNT_POINT="/data"
echo "2. Mount point oluşturuluyor: $MOUNT_POINT"
sudo mkdir -p $MOUNT_POINT

# 3. Partition'ı formatla (eğer formatlanmamışsa)
echo "3. Partition formatlanıyor (ext4)..."
read -p "Partition formatlanacak mı? (e/h): " format_answer
if [ "$format_answer" = "e" ] || [ "$format_answer" = "E" ]; then
    sudo mkfs.ext4 -F $PARTITION
fi

# 4. UUID'yi al
UUID=$(sudo blkid -s UUID -o value $PARTITION)
echo "UUID: $UUID"

# 5. fstab'a ekle
echo "4. /etc/fstab'a ekleniyor..."
FSTAB_ENTRY="UUID=$UUID $MOUNT_POINT ext4 defaults,noatime 0 2"

# Mevcut entry'yi kontrol et
if grep -q "$MOUNT_POINT" /etc/fstab; then
    echo "⚠️ $MOUNT_POINT zaten fstab'da mevcut!"
    read -p "Güncellemek ister misiniz? (e/h): " update_answer
    if [ "$update_answer" = "e" ] || [ "$update_answer" = "E" ]; then
        sudo sed -i "\|$MOUNT_POINT|d" /etc/fstab
        echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab
    fi
else
    echo "$FSTAB_ENTRY" | sudo tee -a /etc/fstab
fi

# 6. Mount et
echo "5. Partition mount ediliyor..."
sudo mount $MOUNT_POINT

# 7. İzinleri ayarla
echo "6. İzinler ayarlanıyor..."
sudo chown -R bms:bms $MOUNT_POINT
sudo chmod 755 $MOUNT_POINT

# 8. Veritabanı dizini oluştur
DB_DIR="$MOUNT_POINT/battery_db"
echo "7. Veritabanı dizini oluşturuluyor: $DB_DIR"
mkdir -p $DB_DIR
chmod 755 $DB_DIR

# 9. Mevcut veritabanını taşı (eğer varsa)
CURRENT_DB="$HOME/Desktop/battery_data.db"
if [ -f "$CURRENT_DB" ]; then
    echo "8. Mevcut veritabanı taşınıyor..."
    cp "$CURRENT_DB" "$DB_DIR/battery_data.db"
    chmod 644 "$DB_DIR/battery_data.db"
    echo "✅ Veritabanı kopyalandı: $DB_DIR/battery_data.db"
    echo "⚠️ Eski veritabanı hala mevcut: $CURRENT_DB"
    read -p "Eski veritabanını silmek ister misiniz? (e/h): " delete_answer
    if [ "$delete_answer" = "e" ] || [ "$delete_answer" = "E" ]; then
        rm "$CURRENT_DB"
        echo "✅ Eski veritabanı silindi"
    fi
fi

# 10. Environment variable ayarla
echo "9. Environment variable ayarlanıyor..."
ENV_FILE="$HOME/.bashrc"
if ! grep -q "BATTERY_DB_PATH" $ENV_FILE; then
    echo "" >> $ENV_FILE
    echo "# Battery Database Path" >> $ENV_FILE
    echo "export BATTERY_DB_PATH=$DB_DIR/battery_data.db" >> $ENV_FILE
    echo "✅ Environment variable eklendi: BATTERY_DB_PATH=$DB_DIR/battery_data.db"
fi

# 11. Systemd service'ler için environment variable
echo "10. Systemd environment dosyası oluşturuluyor..."
sudo mkdir -p /etc/systemd/system.conf.d
echo "[Manager]" | sudo tee /etc/systemd/system.conf.d/battery-db.conf
echo "DefaultEnvironment=\"BATTERY_DB_PATH=$DB_DIR/battery_data.db\"" | sudo tee -a /etc/systemd/system.conf.d/battery-db.conf

echo ""
echo "=========================================="
echo "✅ Kurulum Tamamlandı!"
echo "=========================================="
echo ""
echo "📋 Özet:"
echo "   - Partition: $PARTITION"
echo "   - Mount Point: $MOUNT_POINT"
echo "   - Veritabanı Yolu: $DB_DIR/battery_data.db"
echo "   - Environment Variable: BATTERY_DB_PATH"
echo ""
echo "🔄 Sistem yeniden başlatıldığında partition otomatik mount edilecek"
echo ""
echo "⚠️ Şimdi database.py dosyasını güncellemeniz gerekiyor!"
echo "   BATTERY_DB_PATH environment variable'ını kullanacak şekilde"

