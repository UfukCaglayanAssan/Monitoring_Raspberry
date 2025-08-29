# -*- coding: utf-8 -*-

import time
import datetime
import threading
import queue
import math
import pigpio
import json
import os
from database import BatteryDatabase

# Global variables
buffer = bytearray()
data_queue = queue.Queue()
RX_PIN = 16
TX_PIN = 26
BAUD_RATE = 9600

# Periyot sistemi için global değişkenler
current_period_timestamp = None
period_active = False
last_data_received = time.time()

# Database instance
db = BatteryDatabase()

pi = pigpio.pi()
pi.set_mode(TX_PIN, pigpio.OUTPUT)

# Program başlangıç zamanı
program_start_time = int(time.time() * 1000)

def get_period_timestamp():
    """Aktif periyot için timestamp döndür"""
    global current_period_timestamp, period_active, last_data_received
    
    current_time = time.time()
    
    if not period_active:
        current_period_timestamp = int(current_time * 1000)
        period_active = True
        last_data_received = current_time
        # timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # print(f"[{timestamp}] Yeni periyot başlatıldı: {current_period_timestamp}")
    
    return current_period_timestamp

def reset_period():
    """Periyotu sıfırla"""
    global period_active, current_period_timestamp
    period_active = False
    current_period_timestamp = None
    # timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # print(f"[{timestamp}] Periyot sıfırlandı")

def Calc_SOH(x):
    if x is None:
        return None
    
    try:
        a1, b1, c1 = 85.918, 0.0181, 0.0083
        a2, b2, c2 = 85.11, 0.0324, 0.0104
        a3, b3, c3 = 0.3085, 0.0342, 0.0021
        a4, b4, c4 = 16.521, 0.0382, 0.0013
        a5, b5, c5 = -13.874, 0.0381, 0.0011
        a6, b6, c6 = 40.077, 0.0474, 0.0079
        a7, b7, c7 = 18.207, 0.0556, 0.0048

        SohSonuc = (
            a1 * math.exp(-((x - b1) / c1) ** 2) +
            a2 * math.exp(-((x - b2) / c2) ** 2) +
            a3 * math.exp(-((x - b3) / c3) ** 2) +
            a4 * math.exp(-((x - b4) / c4) ** 2) +
            a5 * math.exp(-((x - b5) / c5) ** 2) +
            a6 * math.exp(-((x - b6) / c6) ** 2) +
            a7 * math.exp(-((x - b7) / c7) ** 2)
        )
        
        if SohSonuc > 100.0:
            SohSonuc = 100.0
        
        return round(SohSonuc, 4)
    except Exception as e:
        print(f"SOH hesaplama hatası: {str(e)}")
        return None

def Calc_SOC(x):
    if x is None:
        return None
        
    a1, a2, a3, a4 = 112.1627, 14.3937, 0, 10.5555
    b1, b2, b3, b4 = 14.2601, 11.6890, 12.7872, 10.9406
    c1, c2, c3, c4 = 1.8161, 0.8211, 0.0025, 0.3866
    
    try:
        Soctahmin = (
            a1 * math.exp(-((x - b1) / c1) ** 2) +
            a2 * math.exp(-((x - b2) / c2) ** 2) +
            a3 * math.exp(-((x - b3) / c3) ** 2) +
            a4 * math.exp(-((x - b4) / c4) ** 2)
        )
        
        if Soctahmin > 100.0:
            Soctahmin = 100.0
        elif Soctahmin < 0.0:
            Soctahmin = 0.0
            
        return round(Soctahmin, 4)
    except Exception as e:
        print(f"SOC hesaplama hatası: {str(e)}")
        return None

def read_serial(pi):
    """Bit-banging ile GPIO üzerinden seri veri oku"""
    global buffer
    print("\nBit-banging UART veri alımı başladı...")
    
    buffer.clear()

    while True:
        try:
            (count, data) = pi.bb_serial_read(RX_PIN)
            if count > 0:
                print(f"Veri alındı: {buffer}")
                buffer.extend(data)
                
                while len(buffer) >= 3:
                    try:
                        # Header (0x80 veya 0x81) bul
                        header_index = -1
                        for i, byte in enumerate(buffer):
                            if byte == 0x80 or byte == 0x81:
                                header_index = i
                                break
                        
                        if header_index == -1:
                            buffer.clear()
                            break

                        if header_index > 0:
                            buffer = buffer[header_index:]

                        # Paket uzunluğunu belirle
                        if len(buffer) >= 3:
                            dtype = buffer[2]
                            
                            # 5 byte'lık missing data paketi kontrolü
                            if dtype == 0x7F and len(buffer) >= 5:
                                packet_length = 5
                            # 6 byte'lık paket kontrolü
                            elif len(buffer) >= 6 and (buffer[2] == 0x0F or buffer[1] == 0x7E or (buffer[2] == 0x7D and buffer[1] == 2)):
                                packet_length = 6
                            elif dtype == 0x7D and len(buffer) >= 7 and buffer[1] > 2:
                                packet_length = 7
                            else:
                                packet_length = 11

                            if len(buffer) >= packet_length:
                                packet = buffer[:packet_length]
                                buffer = buffer[packet_length:]
                                hex_packet = [f"{b:02x}" for b in packet]
                                print(f"Paket oluşturuldu: {hex_packet}")
                                data_queue.put(hex_packet)
                            else:
                                # Paket tamamlanmamış, daha fazla veri bekle
                                break
                        else:
                            break

                    except Exception as e:
                        print(f"Paket işleme hatası: {e}")
                        buffer.clear()
                        continue

            time.sleep(0.01)

        except Exception as e:
            print(f"Veri okuma hatası: {e}")
            time.sleep(1)

def db_worker():
    """Veritabanı işlemleri"""
    batch = []
    last_insert = time.time()
    global last_data_received
    
    while True:
        try:
            data = data_queue.get(timeout=1)
            if data is None:
                break
            
            # Veri alındığında zaman damgasını güncelle
            last_data_received = time.time()
        
            # 7 byte Batkon alarm verisi kontrolü
            if len(data) == 7:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** BATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                
                # Batkon alarm verisi işleme
                arm_value = int(data[3], 16)
                battery = int(data[2], 16)
                error_msb = int(data[4], 16)
                error_lsb = int(data[5], 16)
                alarm_timestamp = int(time.time() * 1000)
                
                # SQLite'ye kaydet
                db.insert_alarm(arm_value, battery, error_msb, error_lsb, alarm_timestamp)
                print("✓ Batkon alarm SQLite'ye kaydedildi")
                continue

            # 5 byte'lık missing data verisi kontrolü
            if len(data) == 5:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** MISSING DATA VERİSİ ALGILANDI - {timestamp} ***")
                
                # Missing data kaydı hazırla
                arm_value = raw_bytes[3]
                slave_value = raw_bytes[1]
                status_value = raw_bytes[4]
                missing_timestamp = int(time.time() * 1000)
                
                # SQLite'ye kaydet
                db.insert_missing_data(arm_value, slave_value, status_value, missing_timestamp)
                print("✓ Missing data SQLite'ye kaydedildi")
                continue

            # 11 byte'lık veri kontrolü
            if len(data) == 11:
                arm_value = int(data[3], 16)
                dtype = int(data[2], 16)
                k_value = int(data[1], 16)
                
                # k_value 2 geldiğinde yeni periyot başlat
                if k_value == 2:
                    reset_period()
                    get_period_timestamp()
                
                # Arm değeri kontrolü
                if arm_value not in [1, 2, 3, 4]:
                    print(f"\nHATALI ARM DEĞERİ: {arm_value}")
                    continue
                
                # Salt data hesapla
                if dtype == 11 and k_value == 2:  # Nem hesapla
                    onlar = int(data[5], 16)
                    birler = int(data[6], 16)
                    kusurat1 = int(data[7], 16)
                    kusurat2 = int(data[8], 16)
                    
                    tam_kisim = (onlar * 10 + birler)
                    kusurat_kisim = (kusurat1 * 0.1 + kusurat2 * 0.01)
                    salt_data = tam_kisim + kusurat_kisim
                    salt_data = round(salt_data, 4)
                else:
                    # Normal hesaplama
                    saltData = int(data[4], 16) * 100 + int(data[5], 16) * 10 + int(data[6], 16) + int(data[7], 16) * 0.1 + int(data[8], 16) * 0.01 + int(data[9], 16) * 0.001
                    salt_data = round(saltData, 4)
                
                # Veri tipine göre log mesajı - KALDIRILDI
                
                # Veri işleme ve kayıt (tek tabloya)
                if dtype == 10:  # SOC
                    if k_value != 2:  # k_value 2 değilse SOC hesapla
                        soc_value = Calc_SOC(salt_data)
                        
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 126,
                            "data": soc_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                    
                    # Her durumda ham veriyi kaydet
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": 10,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)
                
                elif dtype == 11:  # SOH veya Nem
                    if k_value == 2:  # Nem verisi
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,
                            "data": salt_data,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                    else:  # SOH verisi
                        if int(data[4], 16) == 1:  # Eğer data[4] 1 ise SOH 100'dür
                            soh_value = 100.0
                        else:
                            onlar = int(data[5], 16)
                            birler = int(data[6], 16)
                            kusurat1 = int(data[7], 16)
                            kusurat2 = int(data[8], 16)
                            
                            tam_kisim = (onlar * 10 + birler)
                            kusurat_kisim = (kusurat1 * 0.1 + kusurat2 * 0.01)
                            soh_value = tam_kisim + kusurat_kisim
                            soh_value = round(soh_value, 4)
                        
                        record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 11,
                            "data": soh_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(record)
                        
                        # SOH verisi için ek kayıt (dtype=126)
                        soh_record = {
                            "Arm": arm_value,
                            "k": k_value,
                            "Dtype": 126,  # SOH için özel dtype
                            "data": soh_value,
                            "timestamp": get_period_timestamp()
                        }
                        batch.append(soh_record)
                
                else:  # Diğer Dtype değerleri için
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": dtype,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)

            # 6 byte'lık balans komutu veya armslavecounts kontrolü
            elif len(data) == 6:
                raw_bytes = [int(b, 16) for b in data]
                
                # Slave sayısı verisi: 2. byte (index 1) 0x7E ise
                if raw_bytes[1] == 0x7E:
                    arm1, arm2, arm3, arm4 = raw_bytes[2], raw_bytes[3], raw_bytes[4], raw_bytes[5]
                    print(f"armslavecounts verisi tespit edildi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                    
                    try:
                        updated_at = int(time.time() * 1000)
                        # Her arm için ayrı kayıt oluştur
                        db.insert_arm_slave_counts(1, arm1, updated_at)
                        db.insert_arm_slave_counts(2, arm2, updated_at)
                        db.insert_arm_slave_counts(3, arm3, updated_at)
                        db.insert_arm_slave_counts(4, arm4, updated_at)
                        print("✓ Armslavecounts SQLite'ye kaydedildi")
                        
                    except Exception as e:
                        print(f"armslavecounts kayıt hatası: {e}")
                    continue
                
                # Balans verisi: 3. byte (index 2) 0x0F ise
                elif raw_bytes[2] == 0x0F:
                    try:
                        updated_at = int(time.time() * 1000)
                        global program_start_time
                        if updated_at > program_start_time:
                            slave_value = raw_bytes[1]
                            arm_value = raw_bytes[3]
                            status_value = raw_bytes[4]
                            balance_timestamp = updated_at
                            
                            db.insert_passive_balance(arm_value, slave_value, status_value, balance_timestamp)
                            print(f"✓ Balans SQLite'ye kaydedildi: Arm={arm_value}, Slave={slave_value}, Status={status_value}")
                            program_start_time = updated_at
                    except Exception as e:
                        print(f"Balans kayıt hatası: {e}")
                    continue
                
                # Hatkon alarmı: 3. byte (index 2) 0x7D ise
                elif raw_bytes[2] == 0x7D:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"\n*** HATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")

                    arm_value = raw_bytes[3]
                    error_msb = raw_bytes[4]
                    error_lsb = 9
                    alarm_timestamp = int(time.time() * 1000)
                    
                    db.insert_alarm(arm_value, 2, error_msb, error_lsb, alarm_timestamp)
                    print("✓ Hatkon alarm SQLite'ye kaydedildi")
                    continue

            # Batch kontrolü ve kayıt
            if len(batch) >= 100 or (time.time() - last_insert) > 5:
                db.insert_battery_data_batch(batch)
                batch = []
                last_insert = time.time()

            data_queue.task_done()
            
        except queue.Empty:
            if batch:
                db.insert_battery_data_batch(batch)
                batch = []
                last_insert = time.time()
        except Exception as e:
            print(f"\ndb_worker'da beklenmeyen hata: {e}")
            continue

def initialize_config_tables():
    """Konfigürasyon tablolarını oluştur ve varsayılan verileri yükle"""
    try:
        db.execute_query('''
            CREATE TABLE IF NOT EXISTS batconfigs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                armValue INTEGER NOT NULL,
                Vmin REAL NOT NULL,
                Vmax REAL NOT NULL,
                Vnom REAL NOT NULL,
                Rintnom INTEGER NOT NULL,
                Tempmin_D INTEGER NOT NULL,
                Tempmax_D INTEGER NOT NULL,
                Tempmin_PN INTEGER NOT NULL,
                Tempmaks_PN INTEGER NOT NULL,
                Socmin INTEGER NOT NULL,
                Sohmin INTEGER NOT NULL,
                time INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        db.execute_query('''
            CREATE TABLE IF NOT EXISTS armconfigs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                armValue INTEGER NOT NULL,
                akimKats INTEGER NOT NULL,
                akimMax INTEGER NOT NULL,
                nemMax INTEGER NOT NULL,
                nemMin INTEGER NOT NULL,
                tempMax INTEGER NOT NULL,
                tempMin INTEGER NOT NULL,
                time INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        print("✓ Konfigürasyon tabloları oluşturuldu")
        load_default_configs()
    except Exception as e:
        print(f"Konfigürasyon tabloları oluşturulurken hata: {e}")

def load_default_configs():
    """Varsayılan konfigürasyon değerlerini yükle"""
    try:
        # 4 kol için varsayılan batarya konfigürasyonları
        for arm in range(1, 5):
            db.execute_query('''
                INSERT OR IGNORE INTO batconfigs 
                (armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, Tempmin_PN, Tempmaks_PN, Socmin, Sohmin, time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (arm, 10.12, 13.95, 11.00, 150, 15, 55, 15, 30, 30, 30, int(time.time() * 1000)))
        
        # 4 kol için varsayılan kol konfigürasyonları
        for arm in range(1, 5):
            db.execute_query('''
                INSERT OR IGNORE INTO armconfigs 
                (armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (arm, 150, 1000, 100, 0, 65, 15, int(time.time() * 1000)))
        
        print("✓ Varsayılan konfigürasyon değerleri yüklendi")
    except Exception as e:
        print(f"Varsayılan konfigürasyon yüklenirken hata: {e}")

def save_batconfig_to_db(config_data):
    """Batarya konfigürasyonunu veritabanına kaydet ve cihaza gönder"""
    try:
        db.execute_query('''
            INSERT OR REPLACE INTO batconfigs 
            (armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, Tempmin_PN, Tempmaks_PN, Socmin, Sohmin, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (config_data['armValue'], config_data['Vmin'], config_data['Vmax'], config_data['Vnom'], 
              config_data['Rintnom'], config_data['Tempmin_D'], config_data['Tempmax_D'], 
              config_data['Tempmin_PN'], config_data['Tempmaks_PN'], config_data['Socmin'], 
              config_data['Sohmin'], config_data['time']))
        
        print(f"✓ Kol {config_data['armValue']} batarya konfigürasyonu veritabanına kaydedildi")
        send_batconfig_to_device(config_data)
    except Exception as e:
        print(f"Batarya konfigürasyonu kaydedilirken hata: {e}")

def save_armconfig_to_db(config_data):
    """Kol konfigürasyonunu veritabanına kaydet ve cihaza gönder"""
    try:
        db.execute_query('''
            INSERT OR REPLACE INTO armconfigs 
            (armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (config_data['armValue'], config_data['akimKats'], config_data['akimMax'], 
              config_data['nemMax'], config_data['nemMin'], config_data['tempMax'], 
              config_data['tempMin'], config_data['time']))
        
        print(f"✓ Kol {config_data['armValue']} konfigürasyonu veritabanına kaydedildi")
        send_armconfig_to_device(config_data)
    except Exception as e:
        print(f"Kol konfigürasyonu kaydedilirken hata: {e}")

def send_batconfig_to_device(config_data):
    """Batarya konfigürasyonunu cihaza gönder"""
    try:
        # UART paketi hazırla: Header(0x81) + Arm + Dtype(0x7C) + tüm parametreler + CRC
        config_packet = bytearray([0x81])  # Header
        
        # Arm değerini ekle
        arm_value = int(config_data['armValue']) & 0xFF
        config_packet.append(arm_value)
        
        # Dtype ekle
        config_packet.append(0x7C)
        
        # Float değerleri 2 byte olarak hazırla (1 byte tam kısım, 1 byte ondalık kısım)
        vnom = float(str(config_data['Vnom']))
        vmax = float(str(config_data['Vmax']))
        vmin = float(str(config_data['Vmin']))
        
        # Float değerleri ekle (Vnom, Vmax, Vmin)
        config_packet.extend([
            int(vnom) & 0xFF,                # Vnom tam kısım
            int((vnom % 1) * 100) & 0xFF,    # Vnom ondalık kısım
            int(vmax) & 0xFF,                # Vmax tam kısım
            int((vmax % 1) * 100) & 0xFF,    # Vmax ondalık kısım
            int(vmin) & 0xFF,                # Vmin tam kısım
            int((vmin % 1) * 100) & 0xFF     # Vmin ondalık kısım
        ])
        
        # 1 byte değerleri ekle
        config_packet.extend([
            int(config_data['Rintnom']) & 0xFF,
            int(config_data['Tempmin_D']) & 0xFF,
            int(config_data['Tempmax_D']) & 0xFF,
            int(config_data['Tempmin_PN']) & 0xFF,
            int(config_data['Tempmaks_PN']) & 0xFF,
            int(config_data['Socmin']) & 0xFF,
            int(config_data['Sohmin']) & 0xFF
        ])
        
        # CRC hesapla (tüm byte'ların toplamı)
        crc = sum(config_packet) & 0xFF
        config_packet.append(crc)
        
        # Detaylı log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"\n*** BATARYA KONFİGÜRASYONU GÖNDERİLİYOR - {timestamp} ***")
        print(f"Kol: {config_data['armValue']}")
        print(f"Vnom: {vnom} (2 byte: {int(vnom) & 0xFF}, {int((vnom % 1) * 100) & 0xFF})")
        print(f"Vmax: {vmax} (2 byte: {int(vmax) & 0xFF}, {int((vmax % 1) * 100) & 0xFF})")
        print(f"Vmin: {vmin} (2 byte: {int(vmin) & 0xFF}, {int((vmin % 1) * 100) & 0xFF})")
        print(f"Rintnom: {config_data['Rintnom']}")
        print(f"Tempmin_D: {config_data['Tempmin_D']}")
        print(f"Tempmax_D: {config_data['Tempmax_D']}")
        print(f"Tempmin_PN: {config_data['Tempmin_PN']}")
        print(f"Tempmaks_PN: {config_data['Tempmaks_PN']}")
        print(f"Socmin: {config_data['Socmin']}")
        print(f"Sohmin: {config_data['Sohmin']}")
        print(f"CRC: 0x{crc:02X}")
        print(f"UART Paketi: {[f'0x{b:02X}' for b in config_packet]}")
        print(f"Paket Uzunluğu: {len(config_packet)} byte")
        
        # Paketi gönder
        wave_uart_send(pi, TX_PIN, config_packet, int(1e6 / BAUD_RATE))
        print(f"✓ Kol {config_data['armValue']} batarya konfigürasyonu cihaza gönderildi")
        print("*** BATARYA KONFİGÜRASYONU TAMAMLANDI ***\n")
        
    except Exception as e:
        print(f"Batarya konfigürasyonu cihaza gönderilirken hata: {e}")

def send_armconfig_to_device(config_data):
    """Kol konfigürasyonunu cihaza gönder"""
    try:
        # UART paketi hazırla: Header(0x81) + Arm + Dtype(0x7B) + tüm parametreler + CRC
        config_packet = bytearray([0x81])  # Header
        
        # Arm değerini ekle
        arm_value = int(config_data['armValue']) & 0xFF
        config_packet.append(arm_value)
        
        # Dtype ekle (0x7B)
        config_packet.append(0x7B)
        
        # akimMax değerini 3 haneli formata çevir
        akimMax = int(config_data['akimMax'])
        akimMax_str = f"{akimMax:03d}"  # 3 haneli string formatı (örn: 045, 126)
        
        # ArmConfig değerlerini ekle
        config_packet.extend([
            int(config_data['akimKats']) & 0xFF,    # akimKats
            int(akimMax_str[0]) & 0xFF,            # akimMax1 (ilk hane)
            int(akimMax_str[1]) & 0xFF,            # akimMax2 (ikinci hane)
            int(akimMax_str[2]) & 0xFF,            # akimMax3 (üçüncü hane)
            int(config_data['nemMax']) & 0xFF,      # nemMax
            int(config_data['nemMin']) & 0xFF,      # nemMin
            int(config_data['tempMax']) & 0xFF,     # tempMax
            int(config_data['tempMin']) & 0xFF      # tempMin
        ])
        
        # CRC hesapla (tüm byte'ların toplamı)
        crc = sum(config_packet) & 0xFF
        config_packet.append(crc)
        
        # Detaylı log
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(f"\n*** KOL KONFİGÜRASYONU GÖNDERİLİYOR - {timestamp} ***")
        print(f"Kol: {config_data['armValue']}")
        print(f"Akım Katsayısı: {config_data['akimKats']}")
        print(f"Maksimum Akım: {akimMax} (3 haneli: {akimMax_str})")
        print(f"akimMax1: {akimMax_str[0]} (ilk hane)")
        print(f"akimMax2: {akimMax_str[1]} (ikinci hane)")
        print(f"akimMax3: {akimMax_str[2]} (üçüncü hane)")
        print(f"Nem Max: {config_data['nemMax']}%")
        print(f"Nem Min: {config_data['nemMin']}%")
        print(f"Sıcaklık Max: {config_data['tempMax']}°C")
        print(f"Sıcaklık Min: {config_data['tempMin']}°C")
        print(f"CRC: 0x{crc:02X}")
        print(f"UART Paketi: {[f'0x{b:02X}' for b in config_packet]}")
        print(f"Paket Uzunluğu: {len(config_packet)} byte")
        
        # Paketi gönder
        wave_uart_send(pi, TX_PIN, config_packet, int(1e6 / BAUD_RATE))
        print(f"✓ Kol {config_data['armValue']} konfigürasyonu cihaza gönderildi")
        print("*** KOL KONFİGÜRASYONU TAMAMLANDI ***\n")
        
    except Exception as e:
        print(f"Kol konfigürasyonu cihaza gönderilirken hata: {e}")

def wave_uart_send(pi, gpio_pin, data_bytes, bit_time):
    """Bit-banging UART ile veri gönder"""
    try:
        # Start bit (0) + data bits + stop bit (1)
        wave_data = []
        
        for byte in data_bytes:
            # Start bit
            wave_data.append(pigpio.pulse(0, 1 << gpio_pin, bit_time))
            # Data bits (LSB first)
            for i in range(8):
                bit = (byte >> i) & 1
                if bit:
                    wave_data.append(pigpio.pulse(1 << gpio_pin, 0, bit_time))
                else:
                    wave_data.append(pigpio.pulse(0, 1 << gpio_pin, bit_time))
            # Stop bit
            wave_data.append(pigpio.pulse(1 << gpio_pin, 0, bit_time))
        
        # Wave oluştur ve gönder
        pi.wave_clear()
        pi.wave_add_generic(wave_data)
        wave_id = pi.wave_create()
        pi.wave_send_once(wave_id)
        
        # Wave'i temizle
        pi.wave_delete(wave_id)
        
        # UART gönderim log'u
        print(f"  → UART Gönderim: GPIO{TX_PIN}, {len(data_bytes)} byte, {BAUD_RATE} baud")
        print(f"  → Wave ID: {wave_id}, Wave Data: {len(wave_data)} pulse")
        
    except Exception as e:
        print(f"UART gönderim hatası: {e}")

def config_worker():
    """Konfigürasyon değişikliklerini işle"""
    while True:
        try:
            config_file = "pending_config.json"
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                    os.remove(config_file)
                    
                    if config_data.get('type') == 'batconfig':
                        save_batconfig_to_db(config_data['data'])
                    elif config_data.get('type') == 'armconfig':
                        save_armconfig_to_db(config_data['data'])
                    
                except Exception as e:
                    print(f"Konfigürasyon dosyası işlenirken hata: {e}")
                    if os.path.exists(config_file):
                        os.remove(config_file)
            time.sleep(1)
        except Exception as e:
            print(f"Config worker hatası: {e}")
            time.sleep(1)

def main():
    try:
        # Konfigürasyon tablolarını başlat
        initialize_config_tables()
        
        if not pi.connected:
            print("pigpio bağlantısı sağlanamadı!")
            return
            
        pi.write(TX_PIN, 1)

        BIT_TIME = int(1e6 / BAUD_RATE)

        # Okuma thread'i
        pi.bb_serial_read_open(RX_PIN, BAUD_RATE)
        print(f"GPIO{RX_PIN} bit-banging UART başlatıldı @ {BAUD_RATE} baud.")

        # Okuma thread'i
        read_thread = threading.Thread(target=read_serial, args=(pi,), daemon=True)
        read_thread.start()
        print("read_serial thread'i başlatıldı.")

        # Veritabanı işlemleri
        db_thread = threading.Thread(target=db_worker, daemon=True)
        db_thread.start()
        print("db_worker thread'i başlatıldı.")

        # Konfigürasyon işlemleri
        config_thread = threading.Thread(target=config_worker, daemon=True)
        config_thread.start()
        print("Config worker thread'i başlatıldı.")

        print(f"\nSistem başlatıldı.")
        print("Program çalışıyor... (Ctrl+C ile durdurun)")

        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nProgram sonlandırılıyor...")

    finally:
        if 'pi' in locals():
            try:
                pi.bb_serial_read_close(RX_PIN)
                print("Bit-bang UART kapatıldı.")
            except pigpio.error:
                print("Bit-bang UART zaten kapalı.")
            pi.stop()

if __name__ == '__main__':
    print("Program başlatıldı ==>")
    main()