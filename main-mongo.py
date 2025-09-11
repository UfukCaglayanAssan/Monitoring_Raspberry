# -*- coding: utf-8 -*-

import serial
import select
import time
import datetime
import threading
import queue
import math
import struct
import subprocess
import os
import signal
import json
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne
from pymongo.server_api import ServerApi
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from pymongo.mongo_client import MongoClient
from serial.tools import list_ports  # Port listesi için eklendi
import pigpio

def save_reset_count(count):
    """Reset sayısını dosyaya kaydet"""
    try:
        with open("reset_count.txt", "w") as f:
            f.write(str(count))
    except Exception as e:
        print(f"Reset sayısı kaydedilemedi: {e}")

def load_reset_count():
    """Reset sayısını dosyadan yükle"""
    try:
        with open("reset_count.txt", "r") as f:
            return int(f.read().strip())
    except:
        return 0

def clear_reset_count():
    """Reset sayısını sıfırla"""
    save_reset_count(0)

# Global variables
buffer = bytearray()  # Global buffer değişkeni
data_queue = queue.Queue()  # Thread-safe veri kuyruğu
RX_PIN = 16  # UART RX GPIO pini
TX_PIN = 26 
BAUD_RATE = 9600
last_armslavecounts_data = None  # Son güncellenen armslavecounts verisi

# Periyot sistemi için global değişkenler
current_period_timestamp = None
period_active = False
last_data_received = time.time()

# Arm başlangıç ve bitiş değişkenleri
# startArm = 2
# endArm = 3

# Bekleyen veriler için global değişkenler
pending_data = []  # DB için bekleyen veriler
pending_data_lock = threading.Lock()  # Thread-safe erişim için

# WiFi bağlantı kontrolü için global değişkenler
last_successful_db_operation = time.time()
connection_monitor_active = True
CONNECTION_TIMEOUT = 330  # 5.5 dakika = 330 saniye
reset_count = load_reset_count()  # Dosyadan yükle
MAX_RESET_ATTEMPTS = 3  # Maksimum reset denemesi
last_reset_time = 0  # Son reset zamanı
RESET_COOLDOWN = 1800  # 30 dakika reset bekleme süresi

# MongoDB bağlantı bilgileri
uri = "mongodb+srv://ufukcaglayangnl:cJK2NeX54PNhzWii@batterymanagement.aidfjia.mongodb.net/BatteryManagement?retryWrites=true&w=majority"

pi = pigpio.pi()
pi.set_mode(TX_PIN, pigpio.OUTPUT)

# Program başlangıç zamanı (global)
program_start_time = int(time.time() * 1000)

# Mevcut portları listele
print("Mevcut Seri Portlar:")
ports = list_ports.comports()
for port in ports:
    print(f"Port: {port.device}, Açıklama: {port.description}")

def check_wifi_connection():
    """WiFi bağlantısını kontrol et"""
    try:
        # ping testi ile internet bağlantısını kontrol et
        result = subprocess.run(['ping', '-c', '1', '8.8.8.8'], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        print(f"WiFi bağlantı kontrolü hatası: {e}")
        return False

def check_mongodb_connection():
    """MongoDB bağlantısını test et"""
    try:
        client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=5000)
        client.admin.command('ping')
        client.close()
        return True
    except Exception as e:
        print(f"MongoDB bağlantı hatası: {e}")
        return False

def restart_system():
    """Sistemi yeniden başlat"""
    global reset_count, last_reset_time
    
    current_time = time.time()
    
    # Reset sayısını kontrol et
    if reset_count >= MAX_RESET_ATTEMPTS:
        print("\n" + "="*60)
        print("UYARI: Maksimum reset denemesi sayısına ulaşıldı!")
        print(f"Son {MAX_RESET_ATTEMPTS} denemede WiFi bağlantısı kurulamadı.")
        print("Sistem reset atmayı durduruyor. Manuel müdahale gerekli.")
        print("="*60)
        
        # Reset sayısını sıfırla (30 dakika sonra tekrar deneme)
        if current_time - last_reset_time > RESET_COOLDOWN:
            reset_count = 0
            save_reset_count(0)
            print("30 dakika geçti. Reset denemeleri tekrar aktif.")
            return
        
        return
    
    # Reset sayısını artır
    reset_count += 1
    save_reset_count(reset_count)
    last_reset_time = current_time
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "="*60)
    print(f"[{timestamp}] BAĞLANTI HATASI: 5.5 dakika boyunca veri aktarımı yapılamadı!")
    print(f"[{timestamp}] Reset denemesi: {reset_count}/{MAX_RESET_ATTEMPTS}")
    
    # Reset öncesi bekleyen verileri JSON'a kaydet
    save_pending_data_to_json()
    
    print(f"[{timestamp}] Sistem yeniden başlatılıyor...")
    print("="*60)
    
    try:
        # Önce pigpio'yu temizle
        if 'pi' in globals() and pi.connected:
            try:
                pi.bb_serial_read_close(RX_PIN)
                pi.stop()
            except:
                pass
        
        # 5 saniye bekle
        time.sleep(5)
        
        # Sistemi yeniden başlat
        os.system('sudo reboot')
        
    except Exception as e:
        print(f"Sistem yeniden başlatma hatası: {e}")
        os._exit(1)

def connection_monitor():
    """Bağlantı durumunu sürekli izle"""
    global last_successful_db_operation, connection_monitor_active, reset_count
    
    print("Bağlantı izleme sistemi başlatıldı...")
    
    while connection_monitor_active:
        try:
            current_time = time.time()
            time_since_last_operation = current_time - last_successful_db_operation
            
            # 5.5 dakika geçti mi kontrol et
            if time_since_last_operation > CONNECTION_TIMEOUT:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{timestamp}] UYARI: Son başarılı veri aktarımından {time_since_last_operation:.1f} saniye geçti!")
                print(f"[{timestamp}] Bekleyen veriler işleniyor...")
                
                # Önce bekleyen verileri işle
                process_pending_data()
                
                # WiFi bağlantısını kontrol et
                wifi_ok = check_wifi_connection()
                
                print(f"[{timestamp}] WiFi bağlantısı: {'OK' if wifi_ok else 'HATA'}")
                
                if not wifi_ok:
                    print(f"[{timestamp}] WiFi bağlantısı kesildi. Reset kontrolü yapılıyor...")
                    restart_system()
                else:
                    print(f"[{timestamp}] WiFi bağlantısı normal. Network sorunu olabilir.")
                    # WiFi bağlantısı varsa zaman damgasını güncelle
                    last_successful_db_operation = current_time
                    # Başarılı bağlantıda reset sayısını sıfırla
                    reset_count = 0
                    save_reset_count(0)
                    print(f"[{timestamp}] Reset sayacı sıfırlandı.")
            
            time.sleep(10)  # 10 saniye bekle
            
        except Exception as e:
            print(f"Bağlantı izleme hatası: {e}")
            time.sleep(30)

def update_last_db_operation():
    """Son başarılı veri aktarım zamanını güncelle"""
    global last_successful_db_operation
    last_successful_db_operation = time.time()

def get_period_timestamp():
    """Aktif periyot için timestamp döndür, yoksa yeni periyot başlat"""
    global current_period_timestamp, period_active, last_data_received
    
    current_time = time.time()
    
    # Eğer periyot aktif değilse yeni periyot başlat
    if not period_active:
        current_period_timestamp = int(current_time * 1000)
        period_active = True
        last_data_received = current_time
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Yeni periyot başlatıldı: {current_period_timestamp}")
    
    return current_period_timestamp

def reset_period():
    """Periyotu sıfırla"""
    global period_active, current_period_timestamp
    period_active = False
    current_period_timestamp = None
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Periyot sıfırlandı")

def check_period_timeout():
    """Periyot timeout kontrolü - Artık kullanılmıyor"""
    return False

def log_error(error_msg, raw_data=None, process_step=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"\n--- Hata Zamanı: {timestamp} ---\n"
    log_message += f"Hata Mesajı: {error_msg}\n"
    if process_step:
        log_message += f"İşlem Adımı: {process_step}\n"
    if raw_data:
        log_message += f"Ham Veri: {raw_data}\n"
    log_message += "-" * 50 + "\n"
    
    # Konsola yazdır
    print("\033[93m" + log_message + "\033[0m")  # Sarı renkte yazdır
    
    # Dosyaya yaz
    with open("error_log.txt", "a", encoding="utf-8") as f:
        f.write(log_message)

def get_last_temperature(arm_value):
    try:
        client = MongoClient(uri, server_api=ServerApi('1'))
        db = client["BatteryManagement"]
        collection = db["clusters"]
        
        # Son sıcaklık değerini bul
        temp_query = {
            "Arm": arm_value,
            "Dtype": {"$in": [13, 14]}  # NTC değerleri
        }
        temp_doc = collection.find_one(temp_query, sort=[("timestamp", -1)])
        
        if temp_doc:
            return temp_doc["data"]
        return None
    except Exception as e:
        log_error(f"Sıcaklık verisi okuma hatası: {str(e)}", None, "Sıcaklık Okuma")
        return None
    finally:
        client.close()

def Calc_SOH(x):
    if x is None:
        log_error("SOH hesaplaması için geçersiz değer: None", None, "SOH Hesaplama")
        return None
    
    try:
        
        # C kodundaki değerler
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
        
        # Sonucu 100 ile sınırla
        if SohSonuc > 100.0:
            SohSonuc = 100.0
        
        final_result = round(SohSonuc, 4)
        
        return final_result
    except Exception as e:
        log_error(f"SOH hesaplama hatası: {str(e)}", {"x": x}, "SOH Hesaplama")
        return None

def Calc_SOC(x):
    if x is None:
        log_error("SOC hesaplaması için geçersiz değer: None", None, "SOC Hesaplama")
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
        log_error(f"SOC hesaplama hatası: {str(e)}", {"x": x}, "SOC Hesaplama")
        return None

def insert_to_db(database, collection, data, max_retries=3):
    """MongoDB'ye veri yazma"""
    client = None
    
    for attempt in range(max_retries):
        try:
            client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
            
            db = client[database]
            coll = db[collection]

            if isinstance(data, list):
                result = coll.bulk_write([UpdateOne({'_id': {"Arm":item["Arm"],"k":item['k'],"Dtype":item['Dtype'],"timestamp":item['timestamp']}}, {'$set': item}, upsert=True) for item in data])
            else:
                result = coll.update_one({'_id': data.get('timestamp', int(time.time()*1000))}, {'$set': data}, upsert=True)
            
            # Başarılı veri aktarımında zaman damgasını güncelle
            update_last_db_operation()
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] Bağlantı hatası: {e}")
            print(f"[{timestamp}] URI: {uri}")
            print(f"[{timestamp}] Database: {database}")
            print(f"[{timestamp}] Collection: {collection}")
            print(f"[{timestamp}] Yeniden deneniyor... ({attempt + 1}/{max_retries})")
            time.sleep(2)
        except Exception as e:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] Veri kaydetme hatası: {e}")
            print(f"[{timestamp}] Veri tipi: {type(data)}")
            return False
        finally:
            if client:
                client.close()
                print("İşlem tamamlandı.")
    print("\nMaksimum yeniden deneme sayısına ulaşıldı. Veri eklenemedi.")
    return False

def insert_to_db_simple(database, collection, data, max_retries=3):
    """MongoDB'ye veri yazma - Basit versiyon"""
    success = insert_to_db(database, collection, data, max_retries)
    
    if not success:
        add_to_pending_data(database, collection, data)
    
    return success
"""
def update_period_start_end(field_type, timestamp):
     # periodstartend tablosunda start veya end tarihini güncelle
    try:
        # MongoDB bağlantısı
        client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
        db = client['BatteryManagement']
        collection = db['periodstartend']
        
        # Tek kaydı güncelle (field_type = "start" veya "end")
        result = collection.update_one(
            {},  # Tüm kayıtları bul (tek kayıt olduğu varsayılıyor)
            {'$set': {field_type: timestamp}}
        )
        
        if result.modified_count > 0:
            print(f"✓ {field_type} tarihi başarıyla güncellendi: {timestamp}")
            return True
        else:
            print(f"⚠ {field_type} tarihi güncellenmedi (kayıt bulunamadı veya değişiklik yok)")
            return False
            
    except Exception as e:
        print(f"✗ {field_type} tarihi güncellenirken hata: {e}")
        return False
    finally:
        if 'client' in locals() and client is not None:
            client.close()
"""
def read_serial(pi):
    """Bit-banging ile GPIO üzerinden seri veri oku"""
    global buffer
    print("\nBit-banging UART veri alımı başladı...")
    
    # Başlangıçta buffer'ı temizle
    buffer.clear()

    while True:
        try:
            (count, data) = pi.bb_serial_read(RX_PIN)
            if count > 0:
                # Yeni verileri buffer'a ekle
                buffer.extend(data)
                while len(buffer) > 0:
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

                        if len(buffer) >= 3:
                            dtype = buffer[2]
                            
                            # Buffer içeriğini detaylı logla
                            hex_buffer = ' '.join([f'{b:02X}' for b in buffer])
                            
                            # 5 byte'lık missing data paketi kontrolü (dtype = 0x7F)
                            if dtype == 0x7F and len(buffer) >= 5:
                                packet_length = 5
                                # 5 byte'lık missing data paketi tespit edildiğinde logla
                                hex_buffer_5 = ' '.join([f'{b:02X}' for b in buffer[:5]])
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                            
                            # 6 byte'lık armslavecounts, balans paketi veya Hatkon alarmı kontrolü
                            elif len(buffer) >= 6 and (buffer[2] == 0x0F or buffer[1] == 0x7E or (buffer[2] == 0x7D and buffer[1] == 2)):
                                packet_length = 6
                                # 6 byte'lık paket tespit edildiğinde logla
                                hex_buffer_6 = ' '.join([f'{b:02X}' for b in buffer[:6]])
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                                
                            elif dtype == 0x7D and len(buffer) >= 7 and buffer[1] > 2:
                                packet_length = 7
                            else:
                                packet_length = 11

                            if len(buffer) >= packet_length:
                                packet = buffer[:packet_length]
                                buffer = buffer[packet_length:]
                                hex_packet = [f"{b:02x}" for b in packet]
                                data_queue.put(hex_packet)
                            else:
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
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** BATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                print(f"Ham Veri (HEX): {' '.join([f'{b:02X}' for b in raw_bytes])}")
                print(f"Header: 0x{raw_bytes[0]:02X}")
                print(f"k: 0x{raw_bytes[1]:02X}")
                print(f"Dtype: 0x{raw_bytes[2]:02X}")
                print(f"Arm: 0x{raw_bytes[3]:02X}")
                print(f"Error Code MSB: 0x{raw_bytes[4]:02X}")
                print(f"Error Code LSB: 0x{raw_bytes[5]:02X}")
                print(f"CRC: 0x{raw_bytes[6]:02X}")
                
                # Dtype kontrolü
                if raw_bytes[2] != 0x7D:
                    print(f"UYARI: Dtype 0x7D değil! Gelen: 0x{raw_bytes[2]:02X}")
                
                # Batkon alarm verisi işleme
                alarm_record = {
                    "header": int(data[0], 16),
                    "k": int(data[1], 16),
                    "Dtype": int(data[2], 16),
                    "Arm": int(data[3], 16),
                    "error_code_msb": int(data[4], 16),
                    "error_code_lsb": int(data[5], 16),
                    "crc": int(data[6], 16),
                    "timestamp": int(time.time() * 1000),  # Her alarm için benzersiz zaman damgası
                    "code": 200,
                    "emailSent": False
                }
                
                print(f"Batkon alarm kaydı hazırlandı: {alarm_record}")
                
                # DB'ye kaydet
                success = insert_to_db_simple("BatteryManagement", "alarms", alarm_record)
                if success:
                    print("✓ Batkon alarm DB'ye başarıyla kaydedildi")
                    # Başarılı alarm kaydında zaman damgasını güncelle
                    update_last_db_operation()
                else:
                    print("✗ Batkon alarm DB'ye kaydedilemedi!")
                
                # Log kaydı
                log_success = insert_to_db_simple("BatteryManagement", "logs", {"data": [alarm_record], "Code": 200, "timestamp": int(time.time() * 1000)})
                if log_success:
                    print("✓ Batkon alarm log kaydı başarılı")
                    # Başarılı log kaydında zaman damgasını güncelle
                    update_last_db_operation()
                else:
                    print("✗ Batkon alarm log kaydı başarısız!")
                
                print("*** BATKON ALARM İŞLEME TAMAMLANDI ***\n")
                continue

            # 5 byte'lık missing data verisi kontrolü
            if len(data) == 5:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** MISSING DATA VERİSİ ALGILANDI - {timestamp} ***")
                print(f"Ham Veri (HEX): {' '.join([f'{b:02X}' for b in raw_bytes])}")
                print(f"Header: 0x{raw_bytes[0]:02X}")
                print(f"Slave: 0x{raw_bytes[1]:02X}")
                print(f"Dtype: 0x{raw_bytes[2]:02X}")
                print(f"Arm: 0x{raw_bytes[3]:02X}")
                print(f"CRC: 0x{raw_bytes[4]:02X}")
                
                # Dtype kontrolü
                if raw_bytes[2] != 0x7F:
                    print(f"UYARI: Dtype 0x7F değil! Gelen: 0x{raw_bytes[2]:02X}")
                
                # Missing data kaydı hazırla
                missing_data_record = {
                    "arm": raw_bytes[3],
                    "slave": raw_bytes[1],
                    "status": raw_bytes[4],  # status = arm değeri
                    "timestamp": int(time.time() * 1000)  # O anki tarih
                }
                
                print(f"Missing data kaydı hazırlandı: {missing_data_record}")
                
                # Start ve end tarihlerini güncelle (5 byte veri için)
                # current_timestamp = int(time.time() * 1000)
                
                # startArm kontrolü (raw_bytes[1] = 2 ve arm = startArm)
                # if raw_bytes[1] == 2 and raw_bytes[3] == startArm:
                #     try:
                #         # periodstartend tablosunda start tarihini güncelle
                #         success = update_period_start_end("start", current_timestamp)
                #         if success:
                #             print(f"✓ 5 byte veri - startArm={startArm} için start tarihi güncellendi: {current_timestamp}")
                #         else:
                #             print(f"✗ 5 byte veri - startArm={startArm} için start tarihi güncellenemedi!")
                #     except Exception as e:
                #             print(f"5 byte veri - Start tarihi güncellenirken hata: {e}")
                
                # endArm kontrolü (raw_bytes[1] = 2 ve arm = endArm)
                # if raw_bytes[1] == 2 and raw_bytes[3] == endArm:
                #     try:
                #         # periodstartend tablosunda end tarihini güncelle
                #         success = update_period_start_end("end", current_timestamp)
                #         if success:
                #             print(f"✓ 5 byte veri - endArm={endArm} için end tarihi güncellendi: {current_timestamp}")
                #         else:
                #             print(f"✗ 5 byte veri - endArm={endArm} için end tarihi güncellenemedi!")
                #     except Exception as e:
                #             print(f"5 byte veri - End tarihi güncellenirken hata: {e}")
                
                # DB'ye kaydet
                success = insert_to_db_simple("BatteryManagement", "missingdatas", missing_data_record)
                if success:
                    print("✓ Missing data DB'ye başarıyla kaydedildi")
                    # Başarılı kayıtta zaman damgasını güncelle
                    update_last_db_operation()
                else:
                    print("✗ Missing data DB'ye kaydedilemedi!")
                
                # Log kaydı
                log_success = insert_to_db_simple("BatteryManagement", "logs", {"data": [missing_data_record], "Code": 200, "timestamp": int(time.time() * 1000)})
                if log_success:
                    print("✓ Missing data log kaydı başarılı")
                    # Başarılı log kaydında zaman damgasını güncelle
                    update_last_db_operation()
                else:
                    print("✗ Missing data log kaydı başarısız!")
                
                print("*** MISSING DATA İŞLEME TAMAMLANDI ***\n")
                continue

            # 11 byte'lık veri kontrolü
            if len(data) == 11:
                # raw_bytes = [int(b, 16) for b in data]
                arm_value = int(data[3], 16)
                dtype = int(data[2], 16)
                k_value = int(data[1], 16)
                
                # dtype = 13 ve dtype = 10 için detaylı loglama
                if dtype == 13 or dtype == 10:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    
                    # Salt data hesaplama detayları
                    if dtype == 11 and k_value == 2:
                        # Nem hesaplaması
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
                
                # k_value 2 geldiğinde yeni periyot başlat ve start/end tarihlerini güncelle
                if k_value == 2:
                    reset_period()
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # Yeni periyot timestamp'ini al
                    get_period_timestamp()
                    
                    # Start ve end tarihlerini güncelle
                    # current_timestamp = int(time.time() * 1000)
                    
                    # startArm kontrolü
                    # if arm_value == startArm:
                    #     try:
                    #         # periodstartend tablosunda start tarihini güncelle
                    #         success = update_period_start_end("start", current_timestamp)
                    #         if success:
                    #             print(f"✓ startArm={startArm} için start tarihi güncellendi: {current_timestamp}")
                    #         else:
                    #             print(f"✗ startArm={startArm} için start tarihi güncellenemedi!")
                    #     except Exception as e:
                    #             print(f"Start tarihi güncellenirken hata: {e}")
                    
                    # endArm kontrolü
                    # if arm_value == endArm:
                    #     try:
                    #         # periodstartend tablosunda end tarihini güncelle
                    #         success = update_period_start_end("end", current_timestamp)
                    #         if success:
                    #             print(f"✓ endArm={endArm} için end tarihi güncellendi: {current_timestamp}")
                    #         else:
                    #             print(f"✗ endArm={endArm} için end tarihi güncellenemedi!")
                    #     except Exception as e:
                    #             print(f"End tarihi güncellenirken hata: {e}")
                
                # Arm değeri kontrolü
                if arm_value not in [1, 2, 3, 4]:
                    print(f"\nHATALI ARM DEĞERİ: {arm_value}")
                    error_record = {
                        "error_type": "Geçersiz Arm Değeri",
                        "raw_data": data,
                        "timestamp": int(time.time()*1000),
                        "error_message": f"Geçersiz arm değeri: {arm_value}. Arm değeri 1, 2, 3 veya 4 olmalıdır.",
                        "code": 400
                    }
                    if insert_to_db_simple("BatteryManagement", "error_logs", error_record):
                        # Başarılı hata kaydında zaman damgasını güncelle
                        update_last_db_operation()
                    continue
                
                # Salt data hesapla
                if dtype == 11 and k_value == 2:  # Dtype 11 ve k değeri 2 ise nem hesapla
                    # Onlar ve birler basamağı (5. ve 6. byte)
                    onlar = int(data[5], 16)
                    birler = int(data[6], 16)
                    # Küsürat (7. ve 8. byte)
                    kusurat1 = int(data[7], 16)
                    kusurat2 = int(data[8], 16)
                    
                    
                    
                    # Nem değerini hesapla
                    tam_kisim = (onlar * 10 + birler)
                    kusurat_kisim = (kusurat1 * 0.1 + kusurat2 * 0.01)
                    salt_data = tam_kisim + kusurat_kisim
                    salt_data = round(salt_data, 4)
                    
                   
                else:
                    
                    # Diğer durumlar için normal hesaplama
                    saltData = int(data[4], 16) * 100 + int(data[5], 16) * 10 + int(data[6], 16) + int(data[7], 16) * 0.1 + int(data[8], 16) * 0.01 + int(data[9], 16) * 0.001
                    salt_data = round(saltData, 4)
                   
                
                # Veri işleme ve kayıt
                if dtype == 10:  # SOC
                    if k_value != 2:  # k_value 2 değilse SOC hesapla
                        soc_value = Calc_SOC(salt_data)
                        
                        record = {
                            "header": int(data[0], 16),
                            "k": k_value,
                            "Dtype": 126,
                            "Arm": arm_value,
                            "data": soc_value,
                            "crc": int(data[-1], 16),
                            "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                            "code": 200
                        }
                        batch.append(record)
                    
                    # Her durumda ham veriyi kaydet
                    record = {
                        "header": int(data[0], 16),
                        "k": k_value,
                        "Dtype": 10,
                        "Arm": arm_value,
                        "data": salt_data,
                        "crc": int(data[-1], 16),
                        "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                        "code": 200
                    }
                    batch.append(record)
            
                elif dtype == 11:  # SOH veya Nem
                    if k_value == 2:  # Nem verisi
                        record = {
                            "header": int(data[0], 16),
                            "k": k_value,
                            "Dtype": 11,
                            "Arm": arm_value,
                            "data": salt_data,
                            "crc": int(data[-1], 16),
                            "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                            "code": 200
                        }
                        batch.append(record)
                    else:  # SOH verisi
                        # SOH için özel kontrol
                        if int(data[4], 16) == 1:  # Eğer data[4] 1 ise SOH 100'dür
                            soh_value = 100.0
                        else:
                            # Nem hesaplamasına benzer şekilde SOH hesaplama
                            onlar = int(data[5], 16)
                            birler = int(data[6], 16)
                            kusurat1 = int(data[7], 16)
                            kusurat2 = int(data[8], 16)
                            
                            tam_kisim = (onlar * 10 + birler)
                            kusurat_kisim = (kusurat1 * 0.1 + kusurat2 * 0.01)
                            soh_value = tam_kisim + kusurat_kisim
                            soh_value = round(soh_value, 4)
                        
                        record = {
                            "header": int(data[0], 16),
                            "k": k_value,
                            "Dtype": 11,
                            "Arm": arm_value,
                            "data": soh_value,
                            "crc": int(data[-1], 16),
                            "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                            "code": 200
                        }
                        batch.append(record)
                    
                else:  # Diğer Dtype değerleri için
                    record = {
                        "header": int(data[0], 16),
                        "k": k_value,
                        "Dtype": dtype,
                        "Arm": arm_value,
                        "data": salt_data,
                        "crc": int(data[-1], 16),
                        "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                        "code": 200
                    }
                    batch.append(record)



                
                # Batch kontrolü ve kayıt
                if len(batch) >= 100 or (time.time() - last_insert) > 5:
                    if insert_to_db_simple("BatteryManagement", "clusters", batch):
                        # Başarılı batch kaydında zaman damgasını güncelle
                        update_last_db_operation()
                    if insert_to_db_simple("BatteryManagement", "logs", {"data": batch, "Code": 200, "timestamp": get_period_timestamp()}):
                        # Başarılı log kaydında zaman damgasını güncelle
                        update_last_db_operation()
                    batch = []
                    last_insert = time.time()

            # 6 byte'lık balans komutu veya armslavecounts kontrolü
            elif len(data) == 6:
                raw_bytes = [int(b, 16) for b in data]
                # Slave sayısı verisi: 2. byte (index 1) 0x7E ise
                if raw_bytes[1] == 0x7E:
                    arm1, arm2, arm3, arm4 = raw_bytes[2], raw_bytes[3], raw_bytes[4], raw_bytes[5]
                    print(f"armslavecounts verisi tespit edildi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                    
                    # Son güncellenen veriyi kontrol et (tekrar güncellemeyi önlemek için)
                    global last_armslavecounts_data
                    current_data = (arm1, arm2, arm3, arm4)
                    
                    if hasattr(last_armslavecounts_data, '__iter__') and current_data == last_armslavecounts_data:
                        print("Aynı armslavecounts verisi, güncelleme atlanıyor")
                        continue
                    
                    try:
                        updated_at = int(time.time() * 1000)
                        success = False
                        
                        # MongoDB'de güncelleme
                        try:
                            client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
                            db = client["BatteryManagement"]
                            collection = db["armslavecounts"]
                            first_doc = collection.find_one()
                            if first_doc:
                                print(f"armslavecounts koleksiyonunda mevcut doküman bulundu: {first_doc['_id']}")
                                result = collection.update_one(
                                    {"_id": first_doc["_id"]},
                                    {"$set": {
                                        "arm1": arm1,
                                        "arm2": arm2,
                                        "arm3": arm3,
                                        "arm4": arm4,
                                        "updatedAt": updated_at,
                                        "timestamp": updated_at
                                    }},
                                    upsert=False
                                )
                                if result.modified_count > 0:
                                    print(f"armslavecounts güncellendi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                                    success = True
                                    # Başarılı güncellemede zaman damgasını güncelle
                                    update_last_db_operation()
                                else:
                                    print(f"armslavecounts güncellenmedi. Modified count: {result.modified_count}")
                            else:
                                print("armslavecounts koleksiyonunda doküman bulunamadı!")
                            client.close()
                        except Exception as e:
                            print(f"MongoDB armslavecounts güncelleme hatası: {e}")
                        
                        if success:
                            # Son güncellenen veriyi kaydet
                            last_armslavecounts_data = current_data
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print(f"[{timestamp}] Armslavecounts başarıyla güncellendi")
                        
                    except Exception as e:
                        print(f"armslavecounts güncelleme hatası: {e}")
                    continue
                # Balans verisi: 3. byte (index 2) 0x0F ise
                elif raw_bytes[2] == 0x0F:
                    try:
                        updated_at = int(time.time() * 1000)
                        global program_start_time
                        if updated_at > program_start_time:
                            # Balans verisi hazırla
                            balance_record = {
                                "slave": raw_bytes[1],
                                "arm": raw_bytes[3],
                                "status": raw_bytes[4],
                                "updatedAt": updated_at,
                                "timestamp": updated_at
                            }
                            success = False
                            # MongoDB'de güncelleme
                            try:
                                client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
                                db = client["BatteryManagement"]
                                collection = db["passivebalances"]
                                first_doc = collection.find_one()
                                if first_doc:
                                    result = collection.update_one(
                                        {"_id": first_doc["_id"]},
                                        {"$set": balance_record},
                                        upsert=False
                                    )
                                    if result.modified_count > 0:
                                        success = True
                                        update_last_db_operation()
                                client.close()
                            except Exception as e:
                                print(f"MongoDB balans güncelleme hatası: {e}")
                            if success:
                                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                print(f"[{timestamp}] Balans güncellendi: Arm={raw_bytes[3]}, Slave={raw_bytes[1]}, Status={raw_bytes[4]}")
                            program_start_time = updated_at
                    except Exception as e:
                        print(f"Balans güncelleme hatası: {e}")
                    continue
                # Hatkon alarmı: 3. byte (index 2) 0x7D ise
                elif raw_bytes[2] == 0x7D:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(data)
                    print(f"\n*** HATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")
                    print(f"Ham Veri (HEX): {' '.join([f'{b:02X}' for b in raw_bytes])}")
                    print(f"Header: 0x{raw_bytes[0]:02X}")
                    print(f"k: 0x{raw_bytes[1]:02X}")
                    print(f"Dtype: 0x{raw_bytes[2]:02X}")
                    print(f"Arm: 0x{raw_bytes[3]:02X}")
                    print(f"Error Code MSB: 0x{raw_bytes[4]:02X}")
                    print(f"Error Code LSB: 0x09 (sabit)")
                    print(f"CRC: 0x{raw_bytes[5]:02X}")

                    alarm_record = {
                        "header": raw_bytes[0],
                        "k": raw_bytes[1],
                        "Dtype": raw_bytes[2],
                        "Arm": raw_bytes[3],
                        "error_code_msb": raw_bytes[4],
                        "error_code_lsb": 9,
                        "crc": raw_bytes[5],
                        "timestamp": int(time.time() * 1000),
                        "code": 200,
                        "emailSent": False
                    }
                    print(f"Hatkon alarm kaydı hazırlandı: {alarm_record}")
                    success = insert_to_db_simple("BatteryManagement", "alarms", alarm_record)
                    if success:
                        print("✓ Hatkon alarm DB'ye başarıyla kaydedildi")
                        update_last_db_operation()
                    else:
                        print("✗ Hatkon alarm DB'ye kaydedilemedi!")
                    log_success = insert_to_db_simple("BatteryManagement", "logs", {"data": [alarm_record], "Code": 200, "timestamp": int(time.time() * 1000)})
                    if log_success:
                        print("✓ Hatkon alarm log kaydı başarılı")
                        update_last_db_operation()
                    else:
                        print("✗ Hatkon alarm log kaydı başarısız!")
                    print("*** HATKON ALARM İŞLEME TAMAMLANDI ***\n")
                    continue
            # Eksik veri kontrolü
            if len(data) != 7 and len(data) != 11 and len(data) != 6:
                print("\nEksik veri tespit edildi!")
                error_record = {
                    "error_type": "Eksik Veri",
                    "raw_data": data,
                    "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                    "error_message": "Eksik veri paketi",
                    "code": 400
                }
                if insert_to_db_simple("BatteryManagement", "error_logs", error_record):
                    # Başarılı hata kaydında zaman damgasını güncelle
                    update_last_db_operation()
                continue

            data_queue.task_done()
            
        except queue.Empty:
            # Queue boş olduğunda batch kontrolü
            
            if batch:
                if insert_to_db_simple("BatteryManagement", "clusters", batch):
                    # Başarılı batch kaydında zaman damgasını güncelle
                    update_last_db_operation()
                if insert_to_db_simple("BatteryManagement", "logs", {"data": batch, "Code": 200, "timestamp": get_period_timestamp()}):
                    # Başarılı log kaydında zaman damgasını güncelle
                    update_last_db_operation()
                batch = []
                last_insert = time.time()
        except Exception as e:
            print(f"\ndb_worker'da beklenmeyen hata: {e}")
            error_record = {
                "error_type": "Genel İşlem",
                "raw_data": data,
                "timestamp": get_period_timestamp(),  # Periyot timestamp'i kullan
                "error_message": f"db_worker fonksiyonunda beklenmeyen hata: {str(e)}",
                "code": 400
            }
            if insert_to_db_simple("BatteryManagement", "error_logs", error_record):
                # Başarılı hata kaydında zaman damgasını güncelle
                update_last_db_operation()
            continue

input_event = threading.Event()
def send_data_uart(port='/dev/serial0', baudrate=115200, data_to_send=(131, 10)):
    try:
        with serial.Serial(port, baudrate, timeout=1) as ser:
            while True:
                if input_event.wait():
                    two_byte_data = struct.pack('>BB', data_to_send[0], data_to_send[1])
                    ser.write(two_byte_data)
                    #print(f"Gonderilen veri: {data_to_send} (hex: {two_byte_data.hex()})")
                    input_event.clear()
    except serial.SerialException as e:
        print(f"UART hatasi: {e}")
    except KeyboardInterrupt:
        print("Program kullanici tarafindan durduruldu.")

def check_input():
    while True:
        input()  # Enter bekle
        input_event.set()

def insert_manual_data(arm, k, dtype, data_value):
    try:
        # Veri doğrulama
        if arm not in [1, 2, 3, 4]:
            print("HATA: Geçersiz Arm değeri. 1, 2, 3 veya 4 olmalı.")
            return False
            
        if dtype not in [10, 11]:
            print("HATA: Geçersiz Dtype değeri. 10 veya 11 olmalı.")
            return False
            
        # Veri hazırlama
        record = {
            "header": 0x80,  # Varsayılan header değeri
            "k": k,
            "Dtype": dtype,
            "Arm": arm,
            "data": data_value,
            "timestamp": int(time.time()*1000),
            "code": 200
        }
        
        # MongoDB'ye kaydetme
        insert_to_db_simple("BatteryManagement", "BatteryData", record)
        return True
        
    except Exception as e:
        print(f"HATA: Veri kaydedilirken hata oluştu: {str(e)}")
        return False

def list_available_ports():
    """Mevcut seri portları listele"""
    ports = list_ports.comports()
    if not ports:
        print("Hiçbir seri port bulunamadı!")
        return None
    
    print("\nMevcut Seri Portlar:")
    for i, port in enumerate(ports, 1):
        print(f"{i}. Port: {port.device}")
        print(f"   Açıklama: {port.description}")
        print(f"   Donanım ID: {port.hwid}")
        print("-" * 50)
    
    return ports

def select_port():
    """Raspberry Pi için otomatik port seçimi"""
    try:
        # Raspberry Pi için GPIO seri port
        port = "/dev/serial0"
        return port
    except Exception as e:
        print(f"Port seçimi hatası: {e}")
        return None



def wave_uart_send(pi, gpio_pin, data_bytes, bit_time):
    """Verilen byte dizisini wave kullanarak GPIO üzerinden UART formatında gönder"""
    pulses = []

    for byte in data_bytes:
        bits = [0]  # Start bit
        bits.extend([(byte >> i) & 1 for i in range(8)])  # Data bits (LSB first)
        bits.append(1)  # Stop bit

        for bit in bits:
            if bit == 1:
                pulses.append(pigpio.pulse(1 << gpio_pin, 0, bit_time))
            else:
                pulses.append(pigpio.pulse(0, 1 << gpio_pin, bit_time))

    pi.wave_clear()
    pi.wave_add_generic(pulses)
    wave_id = pi.wave_create()

    if wave_id >= 0:
        pi.wave_send_once(wave_id)
        while pi.wave_tx_busy():
            time.sleep(0.001)
        pi.wave_delete(wave_id)
    else:
        print("Wave gönderimi başarısız!")

def watch_datagets_collection(pi, gpio_pin, bit_time):
    """Datagets koleksiyonundaki değişiklikleri izle"""
    try:
        print("\nDatagets izleme başlatılıyor...")
        
        # MongoDB bağlantısı
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                print(f"MongoDB bağlantısı deneniyor... (Deneme {retry_count + 1}/{max_retries})")
                client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
                # Bağlantıyı test et
                client.admin.command('ping')
                print("MongoDB bağlantısı başarılı!")
                # Başarılı MongoDB bağlantısında zaman damgasını güncelle
                update_last_db_operation()
                break
            except Exception as e:
                retry_count += 1
                print(f"Bağlantı hatası: {e}")
                if retry_count < max_retries:
                    print("5 saniye sonra tekrar deneniyor...")
                    time.sleep(5)
                else:
                    print("Maksimum deneme sayısına ulaşıldı.")
                    return
        
        db = client["BatteryManagement"]
        datagets_collection = db["datagets"]
        
        # Program başlangıç zamanını kaydet (timestamp olarak)
        program_start_time = int(time.time() * 1000)
        print(f"Program başlangıç zamanı (timestamp): {program_start_time}")
        
        while True:
            try:
                # Program başlangıcından sonraki datagetleri kontrol et
                new_datagets = datagets_collection.find({
                    'time': {
                        '$gt': str(program_start_time)
                    }
                }).sort('time', 1)
                
                for dataget in new_datagets:
                    try:
                        print("\nYeni dataget algılandı!")
                        print(f"Dataget verisi: {dataget}")
                        
                        # Tarih kontrolü
                        try:
                            dataget_time = str(dataget.get('time', '0')).strip('"')
                            print(f"Veri zamanı: {dataget_time}")
                            print(f"Program başlangıç zamanı: {program_start_time}")
                            
                            if int(dataget_time) <= program_start_time:
                                print(f"Eski veri, atlanıyor. Veri zamanı: {dataget_time}, Program başlangıç: {program_start_time}")
                                continue
                        except (ValueError, TypeError) as e:
                            print(f"HATA: Tarih dönüşüm hatası: {e}")
                            continue
                            
                        # Veri doğrulama
                        if not all(key in dataget for key in ['slaveAddress', 'slaveCommand', 'armValue']):
                            print("HATA: Eksik dataget alanları!")
                            continue
                            
                        # Sadece 3 byte'lık veri oluştur (arm, batarya, komut sırasıyla)
                        dataget_bytes = bytearray([
                            int(dataget["armValue"]),      # Kol numarası
                            int(dataget["slaveAddress"]),  # Slave adresi
                            int(dataget["slaveCommand"])   # Slave komutu
                        ])
                        
                        # Gönderilen veriyi detaylı logla
                        print("\nGönderilecek Dataget Verisi:")
                        print(f"Arm Value: 0x{dataget_bytes[0]:02X}")
                        print(f"Slave Address: 0x{dataget_bytes[1]:02X}")
                        print(f"Slave Command: 0x{dataget_bytes[2]:02X}")
                        print(f"Toplam paket (HEX): {' '.join([f'{b:02X}' for b in dataget_bytes])}")
                        
                        # Seri porta gönder
                        wave_uart_send(pi, gpio_pin, dataget_bytes, bit_time)
                        print("Dataget verisi başarıyla gönderildi!")
                        
                        # Başarılı veri gönderiminde zaman damgasını güncelle
                        update_last_db_operation()
                        
                        # Gönderim sonrası kısa bekleme
                        time.sleep(0.1)
                        
                        # Program başlangıç zamanını güncelle
                        program_start_time = int(dataget_time)
                        print(f"Program başlangıç zamanı güncellendi: {program_start_time}")
                        
                    except Exception as e:
                        print(f"Dataget işleme hatası: {e}")
                        print(f"Hatalı dataget: {dataget}")
                    
                    print("-" * 50)
                
                # Kısa bir bekleme
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("\nDataget izleme sonlandırılıyor...")
                break
            except Exception as e:
                print(f"Dataget izleme hatası: {e}")
                time.sleep(1)
                continue
                
    except Exception as e:
        print(f"Dataget izleme beklenmeyen hata: {e}")
    finally:
        if 'client' in locals():
            client.close()
            print("MongoDB bağlantısı kapatıldı.")


def watch_batConfigs_collection(pi, gpio_pin, bit_time):
    """MongoDB batconfigs koleksiyonunu dinle ve değişiklikleri seri porttan gönder"""
    try:
        print("\nBatConfigs izleme başlatılıyor...")
        
        # MongoDB bağlantısı
        max_retries = 3
        retry_count = 0
        client = None
        
        while retry_count < max_retries:
            try:
                print(f"MongoDB bağlantısı deneniyor... (Deneme {retry_count + 1}/{max_retries})")
                client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
                # Bağlantıyı test et
                client.admin.command('ping')
                print("MongoDB bağlantısı başarılı!")
                # Başarılı MongoDB bağlantısında zaman damgasını güncelle
                update_last_db_operation()
                break
            except Exception as e:
                retry_count += 1
                print(f"Bağlantı hatası: {e}")
                if retry_count < max_retries:
                    print("5 saniye sonra tekrar deneniyor...")
                    time.sleep(5)
                else:
                    print("Maksimum deneme sayısına ulaşıldı.")
                    return
        
        if client is None:
            print("MongoDB bağlantısı kurulamadı!")
            return
            
        db = client['BatteryManagement']
        collection = db['batconfigs']
        
        # Program başlangıç zamanını kaydet (timestamp olarak)
        program_start_time = int(time.time() * 1000)
        print(f"\nProgram başlangıç zamanı (timestamp): {program_start_time}")
        
        # Son config kaydını bul ve logla
        last_record = collection.find_one(sort=[('time', -1)])
        if last_record:
            print("\nVeritabanındaki son batconfig kaydı:")
            print(f"Timestamp: {last_record['time']}")
            print("-" * 50)
        
        print("\nBatConfigs koleksiyonu dinleniyor...")

        while True:
            try:
                # Program başlangıcından sonraki kayıtları kontrol et
                new_records = collection.find({
                    'time': {
                        '$gt': program_start_time
                    }
                }).sort('time', 1)
                
                for record in new_records:
                    # Yeni kayıt algılandığında log
                    print(f"\nYeni batconfig kaydı algılandı - Timestamp: {record['time']}")
                    
                    try:
                        # Config verilerini hazırla
                        config_packet = bytearray([0x81])  # Header
                        
                        # Arm değerini veritabanından al
                        arm_value = int(record['armValue']) & 0xFF
                        config_packet.append(arm_value)
                        
                        # Dtype ekle
                        config_packet.append(0x7C)
                        
                        # Float değerleri 2 byte olarak hazırla (1 byte tam kısım, 1 byte ondalık kısım)
                        vnom = float(str(record['Vnom']))
                        vmax = float(str(record['Vmax']))
                        vmin = float(str(record['Vmin']))
                        
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
                            int(record['Rintnom']) & 0xFF,
                            int(record['Tempmin_D']) & 0xFF,
                            int(record['Tempmax_D']) & 0xFF,
                            int(record['Tempmin_PN']) & 0xFF,
                            int(record['Tempmaks_PN']) & 0xFF,
                            int(record['Socmin']) & 0xFF,
                            int(record['Sohmin']) & 0xFF
                        ])
                        
                        # CRC hesapla (tüm byte'ların toplamı)
                        crc = sum(config_packet) & 0xFF
                        config_packet.append(crc)
                        
                        # Gönderilen değerleri detaylı logla
                        print("\nGönderilen BatConfig Değerleri:")
                        print(f"Header: 0x81")
                        print(f"Kol Numarası (Arm): {arm_value}")
                        print(f"Dtype: 0x7C")
                        print(f"Vnom: {vnom} (2 byte)")
                        print(f"Vmax: {vmax} (2 byte)")
                        print(f"Vmin: {vmin} (2 byte)")
                        print(f"Rintnom: {record['Rintnom']}")
                        print(f"Tempmin_D: {record['Tempmin_D']}")
                        print(f"Tempmax_D: {record['Tempmax_D']}")
                        print(f"Tempmin_PN: {record['Tempmin_PN']}")
                        print(f"Tempmaks_PN: {record['Tempmaks_PN']}")
                        print(f"Socmin: {record['Socmin']}")
                        print(f"Sohmin: {record['Sohmin']}")
                        print(f"CRC: 0x{crc:02X}")
                        print(f"\nGönderilen veri (HEX): {' '.join([f'{b:02X}' for b in config_packet])}")
                        
                        # Paketi gönder
                        wave_uart_send(pi, gpio_pin, config_packet, bit_time)
                        print("\nBatConfig verileri başarıyla gönderildi")
                        
                        # Başarılı veri gönderiminde zaman damgasını güncelle
                        update_last_db_operation()
                        
                        # Program başlangıç zamanını güncelle
                        program_start_time = int(record['time'])
                        print(f"Program başlangıç zamanı güncellendi: {program_start_time}")
                        
                    except Exception as e:
                        print(f"BatConfig verileri gönderilirken hata oluştu: {e}")
                        print(f"Hatalı veri: {record}")
                    
                    print("-" * 50)
                
                # Kısa bir bekleme
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("\nBatConfig izleme sonlandırılıyor...")
                break
            except Exception as e:
                print(f"BatConfig izleme hatası: {e}")
                time.sleep(1)
                continue
                
    except Exception as e:
        print(f"BatConfig izleme beklenmeyen hata: {e}")
    finally:
        if 'client' in locals() and client is not None:
            client.close()
            print("MongoDB bağlantısı kapatıldı.")

def watch_armConfigs_collection(pi, gpio_pin, bit_time):
    """MongoDB armconfigs koleksiyonunu dinle ve değişiklikleri seri porttan gönder"""
    try:
        print("\nArmConfigs izleme başlatılıyor...")
        
        # MongoDB bağlantısı
        max_retries = 3
        retry_count = 0
        client = None
        
        while retry_count < max_retries:
            try:
                print(f"MongoDB bağlantısı deneniyor... (Deneme {retry_count + 1}/{max_retries})")
                client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
                # Bağlantıyı test et
                client.admin.command('ping')
                print("MongoDB bağlantısı başarılı!")
                # Başarılı MongoDB bağlantısında zaman damgasını güncelle
                update_last_db_operation()
                break
            except Exception as e:
                retry_count += 1
                print(f"Bağlantı hatası: {e}")
                if retry_count < max_retries:
                    print("5 saniye sonra tekrar deneniyor...")
                    time.sleep(5)
                else:
                    print("Maksimum deneme sayısına ulaşıldı.")
                    return
        
        if client is None:
            print("MongoDB bağlantısı kurulamadı!")
            return
            
        db = client['BatteryManagement']
        collection = db['armconfigs']
        
        # Program başlangıç zamanını kaydet (timestamp olarak)
        program_start_time = int(time.time() * 1000)
        print(f"\nProgram başlangıç zamanı (timestamp): {program_start_time}")
        
        # Son config kaydını bul ve logla
        last_record = collection.find_one(sort=[('time', -1)])
        if last_record:
            print("\nVeritabanındaki son armconfig kaydı:")
            print(f"Timestamp: {last_record['time']}")
            print("-" * 50)
        
        print("\nArmConfigs koleksiyonu dinleniyor...")

        while True:
            try:
                # Program başlangıcından sonraki kayıtları kontrol et
                new_records = collection.find({
                    'time': {
                        '$gt': program_start_time
                    }
                }).sort('time', 1)
                
                for record in new_records:
                    # Yeni kayıt algılandığında log
                    print(f"\nYeni armconfig kaydı algılandı - Timestamp: {record['time']}")
                    
                    try:
                        # ArmConfig verilerini hazırla
                        config_packet = bytearray([0x81])  # Header
                        
                        # Arm değerini veritabanından al
                        arm_value = int(record['armValue']) & 0xFF
                        config_packet.append(arm_value)
                        
                        # Dtype ekle (0x7B)
                        config_packet.append(0x7B)
                        
                        # akimMax değerini 3 haneli formata çevir
                        akimMax = int(record['akimMax'])
                        akimMax_str = f"{akimMax:03d}"  # 3 haneli string formatı (örn: 045, 126)
                        
                        # ArmConfig değerlerini ekle
                        config_packet.extend([
                            int(record['akimKats']) & 0xFF,    # akimKats
                            int(akimMax_str[0]) & 0xFF,        # akimMax1 (ilk hane)
                            int(akimMax_str[1]) & 0xFF,        # akimMax2 (ikinci hane)
                            int(akimMax_str[2]) & 0xFF,        # akimMax3 (üçüncü hane)
                            int(record['nemMax']) & 0xFF,       # nemMax
                            int(record['nemMin']) & 0xFF,       # nemMin
                            int(record['tempMax']) & 0xFF,      # tempMax
                            int(record['tempMin']) & 0xFF       # tempMin
                        ])
                        
                        # CRC hesapla (tüm byte'ların toplamı)
                        crc = sum(config_packet) & 0xFF
                        config_packet.append(crc)
                        
                        # Gönderilen değerleri detaylı logla
                        print("\nGönderilen ArmConfig Değerleri:")
                        print(f"Header: 0x81")
                        print(f"Kol Numarası (Arm): {arm_value}")
                        print(f"Dtype: 0x7B")
                        print(f"akimKats: {record['akimKats']}")
                        print(f"akimMax: {akimMax} (3 haneli: {akimMax_str})")
                        print(f"akimMax1: {akimMax_str[0]} (ilk hane)")
                        print(f"akimMax2: {akimMax_str[1]} (ikinci hane)")
                        print(f"akimMax3: {akimMax_str[2]} (üçüncü hane)")
                        print(f"nemMax: {record['nemMax']}")
                        print(f"nemMin: {record['nemMin']}")
                        print(f"tempMax: {record['tempMax']}")
                        print(f"tempMin: {record['tempMin']}")
                        print(f"CRC: 0x{crc:02X}")
                        print(f"\nGönderilen veri (HEX): {' '.join([f'{b:02X}' for b in config_packet])}")
                        
                        # Paketi gönder
                        wave_uart_send(pi, gpio_pin, config_packet, bit_time)
                        print("\nArmConfig verileri başarıyla gönderildi")
                        
                        # Başarılı veri gönderiminde zaman damgasını güncelle
                        update_last_db_operation()
                        
                        # Program başlangıç zamanını güncelle
                        program_start_time = int(record['time'])
                        print(f"Program başlangıç zamanı güncellendi: {program_start_time}")
                        
                    except Exception as e:
                        print(f"ArmConfig verileri gönderilirken hata oluştu: {e}")
                        print(f"Hatalı veri: {record}")
                    
                    print("-" * 50)
                
                # Kısa bir bekleme
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("\nArmConfig izleme sonlandırılıyor...")
                break
            except Exception as e:
                print(f"ArmConfig izleme hatası: {e}")
                time.sleep(1)
                continue
                
    except Exception as e:
        print(f"ArmConfig izleme beklenmeyen hata: {e}")
    finally:
        if 'client' in locals() and client is not None:
            client.close()
            print("MongoDB bağlantısı kapatıldı.")

def watch_commands_collection(pi, gpio_pin, bit_time):
    """MongoDB commands koleksiyonunu dinle ve komutları seri porttan gönder"""
    try:
        print("\nCommands izleme başlatılıyor...")
        
        # MongoDB bağlantısı
        max_retries = 3
        retry_count = 0
        client = None
        
        while retry_count < max_retries:
            try:
                print(f"MongoDB bağlantısı deneniyor... (Deneme {retry_count + 1}/{max_retries})")
                client = MongoClient(uri, server_api=ServerApi('1'), serverSelectionTimeoutMS=10000)
                # Bağlantıyı test et
                client.admin.command('ping')
                print("MongoDB bağlantısı başarılı!")
                # Başarılı MongoDB bağlantısında zaman damgasını güncelle
                update_last_db_operation()
                break
            except Exception as e:
                retry_count += 1
                print(f"Bağlantı hatası: {e}")
                if retry_count < max_retries:
                    print("5 saniye sonra tekrar deneniyor...")
                    time.sleep(5)
                else:
                    print("Maksimum deneme sayısına ulaşıldı.")
                    return
        
        if client is None:
            print("MongoDB bağlantısı kurulamadı!")
            return
            
        db = client['BatteryManagement']
        collection = db['commands']
        
        # Program başlangıç zamanını kaydet (timestamp olarak)
        program_start_time = int(time.time() * 1000)
        print(f"\nProgram başlangıç zamanı (timestamp): {program_start_time}")
        
        print("\nCommands koleksiyonu dinleniyor...")

        while True:
            try:
                # Program başlangıcından sonra güncellenen komutları kontrol et
                new_commands = collection.find({
                    'updatedAt': {
                        '$gt': program_start_time
                    }
                }).sort('updatedAt', 1)
                
                for command in new_commands:
                    try:
                        # Komut paketini hazırla
                        command_packet = bytearray([0x81])  # Header (0x81)
                        
                        # Komut tipini belirle
                        arm_value = None  # Varsayılan değer
                        if command['command'] == 'readAll':
                            # Kol numarasını ekle
                            arm_value = int(command['arm']) & 0xFF
                            command_packet.append(arm_value)
                            command_packet.append(0x7A)  # readAll komutu (0x7A)
                        elif command['command'] == 'resetAll':
                            # Kol numarasını ekle
                            arm_value = int(command['arm']) & 0xFF
                            command_packet.append(arm_value)
                            command_packet.append(0x79)  # resetAll komutu (0x7B)
                        elif command['command'] == 'resetSystem':
                            # resetSystem için arm yerine 0x55 gönder
                            arm_value = 0x55  # resetSystem için sabit değer
                            command_packet.append(0x55)  # Arm yerine sabit 0x55
                            command_packet.append(0x55)  # resetSystem komutu (0x55)
                        elif command['command'] == 'systemTest':
                            # systemTest komutu için test koleksiyonunda kayıt oluştur/güncelle
                            try:
                                test_collection = db['test']
                                current_timestamp = int(time.time() * 1000)
                                
                                # test = 1 kaydını upsert ile oluştur veya güncelle
                                result = test_collection.update_one(
                                    {'test': 1},
                                    {
                                        '$set': {
                                            'test': 1,
                                            'updatedAt': current_timestamp
                                        }
                                    },
                                    upsert=True
                                )
                                
                                if result.upserted_id:
                                    print(f"✓ Test koleksiyonunda yeni kayıt oluşturuldu: test = 1")
                                else:
                                    print(f"✓ Test koleksiyonunda mevcut kayıt güncellendi: test = 1")
                                
                                print(f"✓ updatedAt tarihi güncellendi: {current_timestamp}")
                                
                                # systemTest komutu için sadece veritabanı işlemi yapılıyor, komut gönderilmiyor
                                print(f"✓ systemTest komutu işlendi - veritabanına kayıt atıldı")
                                
                            except Exception as e:
                                print(f"Test koleksiyonu işlemi sırasında hata: {e}")
                            
                            # systemTest komutu için updatedAt alanını güncelle
                            try:
                                current_timestamp = int(time.time() * 1000)
                                collection.update_one(
                                    {'_id': command['_id']},
                                    {'$set': {'updatedAt': current_timestamp}}
                                )
                                print(f"✓ systemTest komutu updatedAt alanı güncellendi: {current_timestamp}")
                                
                                # Program başlangıç zamanını güncelle
                                program_start_time = current_timestamp
                                print(f"Program başlangıç zamanı güncellendi: {program_start_time}")
                            except Exception as e:
                                print(f"systemTest komutu güncellenirken hata: {e}")
                            
                            # systemTest komutu için komut paketi gönderilmiyor, sadece veritabanı işlemi yapılıyor
                            continue
                        else:
                            print(f"Bilinmeyen komut: {command['command']}")
                            continue
                        
                        # Gönderilen komutu logla
                        print(f"\nKomut gönderiliyor: {command['command']}")
                        print(f"Kol Numarası: {arm_value}")
                        print(f"Gönderilen veri (HEX): {' '.join([f'{b:02X}' for b in command_packet])}")
                        
                        # Komutu gönder
                        wave_uart_send(pi, gpio_pin, command_packet, bit_time)
                        print(f"✓ {command['command']} komutu başarıyla gönderildi")
                        
                        # readAll komutu gönderildiğinde periyot sıfırla
                        if command['command'] == 'readAll':
                            reset_period()
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print(f"[{timestamp}] readAll komutu nedeniyle periyot sıfırlandı")
                        
                        # Başarılı veri gönderiminde zaman damgasını güncelle
                        update_last_db_operation()
                        
                        # Komutun tarihini güncelle
                        current_timestamp = int(time.time() * 1000)
                        try:
                            collection.update_one(
                                {'_id': command['_id']},
                                {'$set': {'updatedAt': current_timestamp}}
                            )
                            print("Komut tarihi güncellendi")
                            
                            # Program başlangıç zamanını güncelle
                            program_start_time = current_timestamp
                            print(f"Program başlangıç zamanı güncellendi: {program_start_time}")
                        except Exception as e:
                            print(f"Komut tarihi güncellenirken hata: {e}")
                            # Hata durumunda da program başlangıç zamanını güncelle
                            program_start_time = current_timestamp
                        
                    except Exception as e:
                        print(f"Komut gönderilirken hata oluştu: {e}")
                        print(f"Hatalı komut: {command}")
                    
                    print("-" * 50)
                
                # Kısa bir bekleme
                time.sleep(0.1)
                
            except KeyboardInterrupt:
                print("\nKomut izleme sonlandırılıyor...")
                break
            except Exception as e:
                print(f"Komut izleme hatası: {e}")
                time.sleep(1)
                continue
                
    except Exception as e:
        print(f"Komut izleme beklenmeyen hata: {e}")
    finally:
        if 'client' in locals() and client is not None:
            client.close()
            print("MongoDB bağlantısı kapatıldı.")

def configure_serial_port(port_name):
    try:
        # Port ayarlarını dinamik olarak yapılandır
        ser = serial.Serial()
        ser.port = port_name
        ser.baudrate = 115200
        ser.timeout = 1
        ser.bytesize = serial.EIGHTBITS
        ser.parity = serial.PARITY_NONE
        ser.stopbits = serial.STOPBITS_ONE
        
        # Port açılmadan önce temizle
        if ser.is_open:
            ser.close()
        ser.open()
        
        # Buffer'ı temizle
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        print(f"Port başarıyla yapılandırıldı: {port_name}")
        return ser
    except Exception as e:
        log_error(f"Port yapılandırma hatası: {str(e)}", None, "Port Yapılandırma")
        return None

def validate_data(data):
    try:
        # Minimum uzunluk kontrolü
        if len(data) < 1:
            return False
            
        # Header kontrolü
        if data[0] != 0x80:
            return False
            
        # Dtype kontrolü
        dtype = data[2]
        if dtype == 0x7D and len(data) != 7:
            return False
        elif dtype != 0x7D and len(data) != 11:
            return False
            
        return True
    except Exception as e:
        print(f"Veri doğrulama hatası: {e}")
        return False

def check_connection(ser):
    try:
        # Sadece port açık mı kontrol et
        if not ser.is_open:
            return False
            
        # Buffer'ları temizle
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        
        return True
    except Exception as e:
        log_error(f"Bağlantı kontrolü hatası: {str(e)}", None, "Bağlantı Kontrolü")
        return False

def add_to_pending_data(database, collection, data):
    """Başarısız veri aktarımlarını memory'de tut"""
    global pending_data, pending_data_lock
    
    with pending_data_lock:
        pending_item = {
            "database": database,
            "collection": collection,
            "data": data,
            "timestamp": int(time.time() * 1000),
            "retry_count": 0
        }
        
        pending_data.append(pending_item)
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Veri DB'ye kaydedilemedi, memory'de tutuluyor")

def save_pending_data_to_json():
    """Memory'deki bekleyen verileri JSON dosyasına kaydet"""
    global pending_data, pending_data_lock
    
    with pending_data_lock:
        # DB bekleyen verileri
        if pending_data:
            with open("pending_data.json", 'w', encoding='utf-8') as f:
                json.dump(pending_data, f, indent=2, ensure_ascii=False)
            print(f"DB için {len(pending_data)} adet bekleyen veri JSON'a kaydedildi")

def process_pending_data():
    """Memory'deki bekleyen verileri işle"""
    global pending_data, pending_data_lock
    
    with pending_data_lock:
        # DB bekleyen verileri
        if pending_data:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] {len(pending_data)} adet bekleyen veri DB için işleniyor...")
            
            successful_indices = []
            for i, item in enumerate(pending_data):
                try:
                    if item.get("retry_count", 0) >= 5:
                        print(f"DB veri {i} maksimum retry sayısına ulaştı, atlanıyor")
                        successful_indices.append(i)
                        continue
                    
                    success = insert_to_db(
                        item["database"], 
                        item["collection"], 
                        item["data"], 
                        max_retries=3
                    )
                    
                    if success:
                        successful_indices.append(i)
                        print(f"DB bekleyen veri {i} başarıyla aktarıldı")
                    else:
                        pending_data[i]["retry_count"] = item.get("retry_count", 0) + 1
                        
                except Exception as e:
                    print(f"DB bekleyen veri {i} işlenirken hata: {e}")
                    pending_data[i]["retry_count"] = item.get("retry_count", 0) + 1
            
            # Başarılı aktarılanları listeden çıkar
            for index in reversed(successful_indices):
                pending_data.pop(index)

def load_pending_data_from_json():
    """JSON dosyasından bekleyen verileri memory'ye yükle"""
    global pending_data, pending_data_lock
    
    with pending_data_lock:
        # DB bekleyen verileri
        if os.path.exists("pending_data.json"):
            try:
                with open("pending_data.json", 'r', encoding='utf-8') as f:
                    pending_data = json.load(f)
                print(f"DB için {len(pending_data)} adet bekleyen veri JSON'dan yüklendi")
            except Exception as e:
                print(f"DB bekleyen veriler yüklenirken hata: {e}")

def clear_pending_json_files():
    """JSON dosyasını temizle"""
    filename = "pending_data.json"
    if os.path.exists(filename):
        try:
            os.remove(filename)
            print(f"{filename} dosyası silindi")
        except Exception as e:
            print(f"{filename} silinirken hata: {e}")

def main():
    try:
        # Program başlangıcında JSON'dan bekleyen verileri yükle
        load_pending_data_from_json()

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

        # Bağlantı izleme thread'i
        connection_thread = threading.Thread(target=connection_monitor, daemon=True)
        connection_thread.start()
        print("Bağlantı izleme thread'i başlatıldı.")

        # Diğer watcher thread'leri
        threads = [
            threading.Thread(target=watch_datagets_collection,args=(pi, TX_PIN, BIT_TIME),daemon=True), 
            threading.Thread(target=watch_batConfigs_collection,args=(pi, TX_PIN, BIT_TIME),daemon=True),
            threading.Thread(target=watch_armConfigs_collection,args=(pi, TX_PIN, BIT_TIME),daemon=True),
            threading.Thread(target=watch_commands_collection,args=(pi, TX_PIN, BIT_TIME),daemon=True)
        ]

        for thread in threads:
            thread.start()
            print(f"{thread.name} başlatıldı.")

        print(f"\nSistem başlatıldı. Bağlantı izleme aktif - {CONNECTION_TIMEOUT} saniye timeout")
        print("Program çalışıyor... (Ctrl+C ile durdurun)")

        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\nProgram sonlandırılıyor...")
        connection_monitor_active = False

    finally:
        if 'pi' in locals():
            try:
                pi.bb_serial_read_close(RX_PIN)
                print("Bit-bang UART kapatıldı.")
            except pigpio.error:
                print("Bit-bang UART zaten kapalı.")
            pi.stop()


if __name__ == '__main__':
    print("Program baslatildi ==>")
    main()