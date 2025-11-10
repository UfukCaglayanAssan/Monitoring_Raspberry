#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SISCON Klasöründeki Dosyaları UART Üzerinden Gönderme Scripti
siscon/ klasöründeki tüm dosyaları MCU'ya gönderir
"""

import os
import sys
import time
import struct
import pigpio
from pathlib import Path

# UART Ayarları
TX_PIN = 26
RX_PIN = 16
BAUD_RATE = 9600
BIT_TIME = int(1e6 / BAUD_RATE)

# Paket Ayarları
PACKET_SIZE = 64  # Her pakette maksimum 64 byte veri
MAX_RETRY = 3     # Maksimum retry sayısı
ACK_TIMEOUT = 2.0  # ACK bekleme süresi (saniye)

# Komut Kodları
CMD_FILE_START = 0x90  # Dosya gönderimi başlıyor
CMD_FILE_DATA = 0x91    # Dosya verisi
CMD_FILE_END = 0x92     # Dosya gönderimi bitti
CMD_ACK = 0x93          # Paket alındı
CMD_NACK = 0x94         # Paket hatalı
CMD_READY = 0x95        # Hazır

# SISCON klasör yolu
SISCON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "siscon")

def calculate_crc(data):
    """CRC hesapla (basit checksum: tüm byte'ların toplamı)"""
    return sum(data) & 0xFF

def wave_uart_send(pi, gpio_pin, data_bytes, bit_time):
    """Bit-banging UART ile veri gönder"""
    try:
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
        
        return True
    except Exception as e:
        print(f"❌ UART gönderim hatası: {e}")
        return False

def wait_for_ack(pi, expected_cmd=CMD_ACK, timeout=ACK_TIMEOUT):
    """ACK/NACK bekle"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            (count, data) = pi.bb_serial_read(RX_PIN)
            if count > 0:
                for byte in data:
                    if byte == expected_cmd:
                        return True
                    elif byte == CMD_NACK:
                        print("⚠️ NACK alındı - Paket hatalı")
                        return False
        except:
            pass
        time.sleep(0.01)
    
    return False

def send_file_start(pi, filename, file_size, wait_ack=True):
    """FILE_START paketi gönder"""
    # Paket: Header(0x81) + CMD + FilenameLength + Filename + FileSize(4 byte) + CRC
    filename_bytes = filename.encode('utf-8')
    filename_len = len(filename_bytes)
    
    packet = bytearray([0x81])  # Header
    packet.append(CMD_FILE_START)
    packet.append(filename_len & 0xFF)
    packet.extend(filename_bytes)
    
    # File size (4 byte, big-endian)
    packet.extend(struct.pack('>I', file_size))
    
    # CRC
    crc = calculate_crc(packet)
    packet.append(crc)
    
    print(f"📤 FILE_START gönderiliyor: {filename} ({file_size} byte)")
    print(f"   Paket: {[f'0x{b:02X}' for b in packet]}")
    
    if wave_uart_send(pi, TX_PIN, packet, BIT_TIME):
        if wait_ack:
            # READY bekle
            if wait_for_ack(pi, CMD_READY, timeout=5.0):
                print("✅ MCU hazır, dosya gönderimi başlıyor...")
                return True
            else:
                print("⚠️ MCU hazır değil veya timeout (ACK beklemeden devam ediliyor)")
                time.sleep(0.5)  # Kısa bekleme
                return True  # ACK beklemeden devam et
        else:
            print("✅ FILE_START gönderildi (ACK beklemeden)")
            time.sleep(0.5)  # Kısa bekleme
            return True
    return False

def send_file_data(pi, packet_num, data_chunk, wait_ack=True):
    """FILE_DATA paketi gönder"""
    # Paket: Header(0x81) + CMD + PacketNum(2 byte) + DataLength + Data + CRC
    packet = bytearray([0x81])  # Header
    packet.append(CMD_FILE_DATA)
    
    # Packet number (2 byte, big-endian)
    packet.extend(struct.pack('>H', packet_num))
    
    # Data length
    data_len = len(data_chunk)
    packet.append(data_len & 0xFF)
    
    # Data
    packet.extend(data_chunk)
    
    # CRC
    crc = calculate_crc(packet)
    packet.append(crc)
    
    if wait_ack:
        # Retry mekanizması
        for retry in range(MAX_RETRY):
            if wave_uart_send(pi, TX_PIN, packet, BIT_TIME):
                if wait_for_ack(pi, CMD_ACK):
                    print(f"✅ Paket {packet_num} gönderildi ({data_len} byte)")
                    return True
                else:
                    print(f"⚠️ Paket {packet_num} ACK alınamadı (Retry {retry + 1}/{MAX_RETRY})")
                    if retry < MAX_RETRY - 1:
                        time.sleep(0.1)
            else:
                print(f"❌ Paket {packet_num} gönderilemedi (Retry {retry + 1}/{MAX_RETRY})")
                if retry < MAX_RETRY - 1:
                    time.sleep(0.1)
        
        print(f"❌ Paket {packet_num} gönderilemedi (Max retry aşıldı)")
        return False
    else:
        # ACK beklemeden gönder
        if wave_uart_send(pi, TX_PIN, packet, BIT_TIME):
            print(f"✅ Paket {packet_num} gönderildi ({data_len} byte) - ACK beklemeden")
            time.sleep(0.1)  # Paketler arası kısa bekleme
            return True
        else:
            print(f"❌ Paket {packet_num} gönderilemedi")
            return False

def send_file_end(pi, filename, total_packets, wait_ack=True):
    """FILE_END paketi gönder"""
    # Paket: Header(0x81) + CMD + TotalPackets(2 byte) + CRC
    packet = bytearray([0x81])  # Header
    packet.append(CMD_FILE_END)
    
    # Total packets (2 byte, big-endian)
    packet.extend(struct.pack('>H', total_packets))
    
    # CRC
    crc = calculate_crc(packet)
    packet.append(crc)
    
    print(f"📤 FILE_END gönderiliyor: {filename} (Toplam {total_packets} paket)")
    
    if wave_uart_send(pi, TX_PIN, packet, BIT_TIME):
        if wait_ack:
            if wait_for_ack(pi, CMD_ACK, timeout=5.0):
                print(f"✅ Dosya gönderimi tamamlandı: {filename}")
                return True
            else:
                print(f"⚠️ FILE_END ACK alınamadı (ACK beklemeden tamamlandı): {filename}")
                return True
        else:
            print(f"✅ FILE_END gönderildi (ACK beklemeden): {filename}")
            time.sleep(0.5)
            return True
    return False

def send_file(pi, file_path, wait_ack=False):
    """Tek bir dosyayı gönder"""
    filename = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    print(f"\n{'='*60}")
    print(f"📁 Dosya gönderiliyor: {filename}")
    print(f"   Boyut: {file_size} byte")
    if not wait_ack:
        print(f"   ⚠️ TEST MODU: ACK beklemeden gönderiliyor")
    print(f"{'='*60}")
    
    # FILE_START gönder
    if not send_file_start(pi, filename, file_size, wait_ack=wait_ack):
        print(f"❌ Dosya gönderimi başlatılamadı: {filename}")
        return False
    
    # Dosyayı oku ve parçalara böl
    try:
        with open(file_path, 'rb') as f:
            packet_num = 0
            total_packets = (file_size + PACKET_SIZE - 1) // PACKET_SIZE
            
            while True:
                chunk = f.read(PACKET_SIZE)
                if not chunk:
                    break
                
                packet_num += 1
                print(f"📦 Paket {packet_num}/{total_packets} gönderiliyor... ({len(chunk)} byte)")
                
                if not send_file_data(pi, packet_num, chunk, wait_ack=wait_ack):
                    print(f"❌ Dosya gönderimi başarısız: {filename}")
                    return False
                
                # Paketler arası kısa bekleme
                if not wait_ack:
                    time.sleep(0.1)  # Test modunda biraz daha bekle
                else:
                    time.sleep(0.05)
            
            # FILE_END gönder
            if send_file_end(pi, filename, total_packets, wait_ack=wait_ack):
                print(f"✅ Dosya başarıyla gönderildi: {filename}")
                return True
            else:
                print(f"⚠️ Dosya gönderildi ama FILE_END onaylanmadı: {filename}")
                return True  # Dosya gönderildi, sadece END onaylanmadı
    
    except Exception as e:
        print(f"❌ Dosya okuma hatası: {e}")
        return False

def send_all_siscon_files():
    """siscon/ klasöründeki tüm dosyaları gönder"""
    # Pigpio bağlantısı
    try:
        pi = pigpio.pi()
        if not pi.connected:
            print("❌ Pigpio bağlantısı kurulamadı!")
            return False
    except Exception as e:
        print(f"❌ Pigpio başlatma hatası: {e}")
        return False
    
    # GPIO pinlerini ayarla
    try:
        pi.set_mode(TX_PIN, pigpio.OUTPUT)
        pi.bb_serial_read_open(RX_PIN, BAUD_RATE)
        print(f"✅ UART hazır: TX=GPIO{TX_PIN}, RX=GPIO{RX_PIN}, Baud={BAUD_RATE}")
    except Exception as e:
        print(f"❌ UART ayarlama hatası: {e}")
        pi.stop()
        return False
    
    # SISCON klasörünü kontrol et
    if not os.path.exists(SISCON_DIR):
        print(f"❌ SISCON klasörü bulunamadı: {SISCON_DIR}")
        pi.stop()
        return False
    
    # Tüm dosyaları bul
    files = []
    for item in os.listdir(SISCON_DIR):
        file_path = os.path.join(SISCON_DIR, item)
        if os.path.isfile(file_path):
            files.append(file_path)
    
    if not files:
        print(f"⚠️ SISCON klasöründe dosya bulunamadı: {SISCON_DIR}")
        pi.stop()
        return False
    
    files.sort()  # Alfabetik sırala
    
    print(f"\n{'='*60}")
    print(f"📂 SISCON Klasöründeki Dosyalar ({len(files)} dosya)")
    print(f"{'='*60}")
    for i, file_path in enumerate(files, 1):
        filename = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        print(f"{i}. {filename} ({file_size} byte)")
    print(f"{'='*60}\n")
    
    # Her dosyayı gönder (TEST MODU: ACK beklemeden)
    success_count = 0
    failed_files = []
    wait_ack = False  # TEST MODU: ACK beklemeden gönder
    
    for file_path in files:
        filename = os.path.basename(file_path)
        
        if send_file(pi, file_path, wait_ack=wait_ack):
            success_count += 1
        else:
            failed_files.append(filename)
        
        # Dosyalar arası bekleme
        if file_path != files[-1]:  # Son dosya değilse
            print("\n⏳ Sonraki dosya için bekleniyor...\n")
            time.sleep(1)
    
    # Özet
    print(f"\n{'='*60}")
    print(f"📊 GÖNDERİM ÖZETİ")
    print(f"{'='*60}")
    print(f"✅ Başarılı: {success_count}/{len(files)}")
    if failed_files:
        print(f"❌ Başarısız: {len(failed_files)}")
        for filename in failed_files:
            print(f"   - {filename}")
    print(f"{'='*60}\n")
    
    # Temizlik
    try:
        pi.bb_serial_read_close(RX_PIN)
        pi.stop()
    except:
        pass
    
    return success_count == len(files)

if __name__ == "__main__":
    print("="*60)
    print("SISCON Dosya Gönderimi")
    print("="*60)
    print(f"SISCON klasörü: {SISCON_DIR}")
    print(f"Paket boyutu: {PACKET_SIZE} byte")
    print(f"Max retry: {MAX_RETRY}")
    print("="*60)
    
    try:
        success = send_all_siscon_files()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ Kullanıcı tarafından durduruldu")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Beklenmeyen hata: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

