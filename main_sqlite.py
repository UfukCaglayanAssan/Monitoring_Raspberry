# -*- coding: utf-8 -*-

import time
import datetime
import threading
import queue
import math
import pigpio
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
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] Yeni periyot başlatıldı: {current_period_timestamp}")
    
    return current_period_timestamp

def reset_period():
    """Periyotu sıfırla"""
    global period_active, current_period_timestamp
    period_active = False
    current_period_timestamp = None
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Periyot sıfırlandı")

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
                alarm_record = {
                    "Arm": int(data[3], 16),
                    "error_code_msb": int(data[4], 16),
                    "error_code_lsb": int(data[5], 16),
                    "timestamp": int(time.time() * 1000)
                }
                
                # SQLite'ye kaydet
                db.insert_alarm(alarm_record)
                print("✓ Batkon alarm SQLite'ye kaydedildi")
                continue

            # 5 byte'lık missing data verisi kontrolü
            if len(data) == 5:
                raw_bytes = [int(b, 16) for b in data]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                
                print(f"\n*** MISSING DATA VERİSİ ALGILANDI - {timestamp} ***")
                
                # Missing data kaydı hazırla
                missing_data_record = {
                    "arm": raw_bytes[3],
                    "slave": raw_bytes[1],
                    "status": raw_bytes[4],
                    "timestamp": int(time.time() * 1000)
                }
                
                # SQLite'ye kaydet
                db.insert_missing_data(missing_data_record)
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
                    
                    # Veri tipine göre log mesajı
                    if k_value == 2:
                        # Kol verisi (k=2)
                        if dtype == 10:
                            print(f"\n*** KOL VERİSİ ALGILANDI - Arm: {arm_value}, Veri Tipi: Akım, Değer: {salt_data} A ***")
                        elif dtype == 11:
                            print(f"\n*** KOL VERİSİ ALGILANDI - Arm: {arm_value}, Veri Tipi: Nem, Değer: {salt_data}% ***")
                        elif dtype == 12:
                            print(f"\n*** KOL VERİSİ ALGILANDI - Arm: {arm_value}, Veri Tipi: Sıcaklık, Değer: {salt_data}°C ***")
                        else:
                            print(f"\n*** KOL VERİSİ ALGILANDI - Arm: {arm_value}, Veri Tipi: {dtype}, Değer: {salt_data} ***")
                    else:
                        # Batarya verisi (k!=2)
                        if dtype == 10:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: Gerilim, Değer: {salt_data} V ***")
                        elif dtype == 11:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: Şarj Durumu, Değer: {salt_data}% ***")
                        elif dtype == 12:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: Modül Sıcaklığı, Değer: {salt_data}°C ***")
                        elif dtype == 13:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: Pozitif Kutup Sıcaklığı, Değer: {salt_data}°C ***")
                        elif dtype == 14:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: Negatif Kutup Sıcaklığı, Değer: {salt_data}°C ***")
                        elif dtype == 126:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: Sağlık Durumu, Değer: {salt_data}% ***")
                        else:
                            print(f"\n*** BATARYA VERİSİ ALGILANDI - Arm: {arm_value}, Batarya: {k_value}, Veri Tipi: {dtype}, Değer: {salt_data} ***")
                    
                    # Veri işleme ve kayıt
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
                    
                else:  # Diğer Dtype değerleri için
                    record = {
                        "Arm": arm_value,
                        "k": k_value,
                        "Dtype": dtype,
                        "data": salt_data,
                        "timestamp": get_period_timestamp()
                    }
                    batch.append(record)

                # Batch kontrolü ve kayıt
                if len(batch) >= 100 or (time.time() - last_insert) > 5:
                    db.insert_battery_data(batch)
                    batch = []
                    last_insert = time.time()

            # 6 byte'lık balans komutu veya armslavecounts kontrolü
            elif len(data) == 6:
                raw_bytes = [int(b, 16) for b in data]
                
                # Slave sayısı verisi: 2. byte (index 1) 0x7E ise
                if raw_bytes[1] == 0x7E:
                    arm1, arm2, arm3, arm4 = raw_bytes[2], raw_bytes[3], raw_bytes[4], raw_bytes[5]
                    print(f"armslavecounts verisi tespit edildi: arm1={arm1}, arm2={arm2}, arm3={arm3}, arm4={arm4}")
                    
                    try:
                        updated_at = int(time.time() * 1000)
                        counts_data = {
                            "arm1": arm1,
                            "arm2": arm2,
                            "arm3": arm3,
                            "arm4": arm4,
                            "updatedAt": updated_at,
                            "timestamp": updated_at
                        }
                        
                        db.insert_arm_slave_counts(counts_data)
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
                            balance_record = {
                                "slave": raw_bytes[1],
                                "arm": raw_bytes[3],
                                "status": raw_bytes[4],
                                "updatedAt": updated_at,
                                "timestamp": updated_at
                            }
                            
                            db.insert_passive_balance(balance_record)
                            print(f"✓ Balans SQLite'ye kaydedildi: Arm={raw_bytes[3]}, Slave={raw_bytes[1]}, Status={raw_bytes[4]}")
                            program_start_time = updated_at
                    except Exception as e:
                        print(f"Balans kayıt hatası: {e}")
                    continue
                
                # Hatkon alarmı: 3. byte (index 2) 0x7D ise
                elif raw_bytes[2] == 0x7D:
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                    print(f"\n*** HATKON ALARM VERİSİ ALGILANDI - {timestamp} ***")

                    alarm_record = {
                        "Arm": raw_bytes[3],
                        "error_code_msb": raw_bytes[4],
                        "error_code_lsb": 9,
                        "timestamp": int(time.time() * 1000)
                    }
                    
                    db.insert_alarm(alarm_record)
                    print("✓ Hatkon alarm SQLite'ye kaydedildi")
                    continue

            data_queue.task_done()
            
        except queue.Empty:
            if batch:
                db.insert_battery_data(batch)
                batch = []
                last_insert = time.time()
        except Exception as e:
            print(f"\ndb_worker'da beklenmeyen hata: {e}")
            continue

def main():
    try:
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