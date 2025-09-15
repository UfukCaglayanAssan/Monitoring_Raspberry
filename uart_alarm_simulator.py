#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pigpio
import time
import threading
from datetime import datetime

class UARTAlarmSimulator:
    def __init__(self):
        self.pi = pigpio.pi()
        self.RX_PIN = 16  # GPIO 16 (main.py'deki gibi)
        self.TX_PIN = 26  # GPIO 26 (opsiyonel)
        self.BAUD_RATE = 9600
        self.BIT_TIME = int(1e6 / self.BAUD_RATE)  # Mikrosaniye
        
        # GPIO pinlerini hazırla
        self.pi.set_mode(self.RX_PIN, pigpio.INPUT)
        self.pi.set_mode(self.TX_PIN, pigpio.OUTPUT)
        self.pi.write(self.TX_PIN, 1)  # Idle state (high)
        
        print(f"🔧 UART Simülatörü başlatıldı")
        print(f"📡 RX Pin: GPIO {self.RX_PIN}")
        print(f"📡 TX Pin: GPIO {self.TX_PIN}")
        print(f"⚡ Baud Rate: {self.BAUD_RATE}")
    
    def send_uart_byte(self, byte_value):
        """Tek byte'ı UART formatında gönder"""
        # Start bit (0)
        self.pi.write(self.TX_PIN, 0)
        time.sleep(self.BIT_TIME / 1e6)
        
        # 8 data bits (LSB first)
        for i in range(8):
            bit = (byte_value >> i) & 1
            self.pi.write(self.TX_PIN, bit)
            time.sleep(self.BIT_TIME / 1e6)
        
        # Stop bit (1)
        self.pi.write(self.TX_PIN, 1)
        time.sleep(self.BIT_TIME / 1e6)
    
    def send_uart_frame(self, data_bytes):
        """7 byte UART frame gönder"""
        print(f"📤 UART Frame gönderiliyor: {[hex(x) for x in data_bytes]}")
        
        for byte_val in data_bytes:
            self.send_uart_byte(byte_val)
        
        # Frame arası bekleme
        time.sleep(0.1)
    
    def create_batkon_alarm(self, arm, battery, error_msb, error_lsb):
        """Batkon (batarya) alarm verisi oluştur - 7 byte"""
        # Format: [0x80, battery, 0x00, arm, error_msb, error_lsb, checksum]
        frame = [
            0x80,      # Start byte
            battery,   # Batarya numarası (k değeri)
            0x00,      # Reserved
            arm,       # Kol numarası
            error_msb, # Error MSB
            error_lsb, # Error LSB
            0x00       # Checksum (basit)
        ]
        
        # Checksum hesapla (basit XOR)
        checksum = 0
        for i in range(6):
            checksum ^= frame[i]
        frame[6] = checksum
        
        return frame
    
    def create_hatkon_alarm(self, arm, error_msb, error_lsb, status):
        """Hatkon (kol) alarm verisi oluştur - 7 byte"""
        # Format: [0x80, 0x8E, arm, error_msb, error_lsb, status, checksum]
        frame = [
            0x80,      # Start byte
            0x8E,      # Hatkon identifier
            arm,       # Kol numarası
            error_msb, # Error MSB
            error_lsb, # Error LSB
            status,    # Status
            0x00       # Checksum
        ]
        
        # Checksum hesapla
        checksum = 0
        for i in range(6):
            checksum ^= frame[i]
        frame[6] = checksum
        
        return frame
    
    def simulate_battery_alarms(self):
        """Batarya alarmlarını simüle et"""
        print("\n🔋 BATKON (Batarya) Alarm Simülasyonu Başlıyor...")
        
        # Farklı alarm türleri
        alarm_scenarios = [
            # (arm, battery, error_msb, error_lsb, açıklama)
            (1, 3, 0, 4, "Düşük batarya gerilim uyarısı (LVoltageWarn)"),
            (1, 3, 0, 8, "Düşük batarya gerilimi alarmı (LVoltageAlarm)"),
            (1, 4, 0, 16, "Yüksek batarya gerilimi uyarısı (OVoltageWarn)"),
            (1, 4, 0, 32, "Yüksek batarya gerilimi alarmı (OVoltageAlarm)"),
            (2, 5, 0, 64, "Modül sıcaklık alarmı (OvertempD)"),
            (2, 5, 1, 0, "Pozitif kutup başı sıcaklık alarmı (OvertempP)"),
            (2, 6, 2, 0, "Negatif kutup başı sıcaklık alarmı (OvertempN)"),
            (3, 7, 3, 4, "Çoklu alarm (LVoltageWarn + OvertempP + OvertempN)"),
        ]
        
        for i, (arm, battery, error_msb, error_lsb, description) in enumerate(alarm_scenarios):
            print(f"\n--- Senaryo {i+1}: {description} ---")
            print(f"Kol: {arm}, Batarya: {battery}, MSB: {error_msb}, LSB: {error_lsb}")
            
            # Alarm verisi oluştur ve gönder
            frame = self.create_batkon_alarm(arm, battery, error_msb, error_lsb)
            self.send_uart_frame(frame)
            
            # 3 saniye bekle
            time.sleep(3)
    
    def simulate_arm_alarms(self):
        """Kol alarmlarını simüle et"""
        print("\n🦾 HATKON (Kol) Alarm Simülasyonu Başlıyor...")
        
        # Kol alarm senaryoları
        arm_scenarios = [
            # (arm, error_msb, error_lsb, status, açıklama)
            (1, 1, 9, 1, "Kol 1 alarmı (devam ediyor)"),
            (2, 0, 9, 0, "Kol 2 alarmı düzeldi"),
            (3, 1, 9, 1, "Kol 3 alarmı (devam ediyor)"),
            (4, 0, 9, 0, "Kol 4 alarmı düzeldi"),
        ]
        
        for i, (arm, error_msb, error_lsb, status, description) in enumerate(arm_scenarios):
            print(f"\n--- Senaryo {i+1}: {description} ---")
            print(f"Kol: {arm}, MSB: {error_msb}, LSB: {error_lsb}, Status: {status}")
            
            # Kol alarm verisi oluştur ve gönder
            frame = self.create_hatkon_alarm(arm, error_msb, error_lsb, status)
            self.send_uart_frame(frame)
            
            # 3 saniye bekle
            time.sleep(3)
    
    def simulate_mixed_alarms(self):
        """Karışık alarm senaryoları"""
        print("\n🔄 Karışık Alarm Simülasyonu Başlıyor...")
        
        scenarios = [
            # Batkon alarmları
            (1, 3, 0, 4, "batkon"),
            (1, 3, 0, 8, "batkon"),
            (2, 4, 0, 16, "batkon"),
            (2, 4, 0, 32, "batkon"),
            # Hatkon alarmları
            (1, 1, 9, 1, "hatkon"),
            (2, 0, 9, 0, "hatkon"),
            # Tekrar batkon
            (3, 5, 0, 64, "batkon"),
            (3, 5, 1, 0, "batkon"),
        ]
        
        for i, (arm, battery_or_error_msb, error_lsb, status_or_error_msb, alarm_type) in enumerate(scenarios):
            print(f"\n--- Senaryo {i+1}: {alarm_type.upper()} ---")
            
            if alarm_type == "batkon":
                battery = battery_or_error_msb
                error_msb = status_or_error_msb
                print(f"Kol: {arm}, Batarya: {battery}, MSB: {error_msb}, LSB: {error_lsb}")
                frame = self.create_batkon_alarm(arm, battery, error_msb, error_lsb)
            else:  # hatkon
                error_msb = battery_or_error_msb
                status = status_or_error_msb
                print(f"Kol: {arm}, MSB: {error_msb}, LSB: {error_lsb}, Status: {status}")
                frame = self.create_hatkon_alarm(arm, error_msb, error_lsb, status)
            
            self.send_uart_frame(frame)
            time.sleep(2)
    
    def run_continuous_simulation(self):
        """Sürekli alarm simülasyonu"""
        print("\n🔄 Sürekli Alarm Simülasyonu Başlıyor...")
        print("Ctrl+C ile durdurun")
        
        try:
            while True:
                # Rastgele alarm oluştur
                import random
                
                alarm_type = random.choice(["batkon", "hatkon"])
                
                if alarm_type == "batkon":
                    arm = random.randint(1, 4)
                    battery = random.randint(3, 9)
                    error_msb = random.choice([0, 1, 2, 3])
                    error_lsb = random.choice([4, 8, 16, 32, 64])
                    
                    frame = self.create_batkon_alarm(arm, battery, error_msb, error_lsb)
                    print(f"🔄 Rastgele Batkon: Kol {arm}, Batarya {battery}, MSB {error_msb}, LSB {error_lsb}")
                else:
                    arm = random.randint(1, 4)
                    error_msb = random.choice([0, 1])
                    error_lsb = 9
                    status = random.choice([0, 1])
                    
                    frame = self.create_hatkon_alarm(arm, error_msb, error_lsb, status)
                    print(f"🔄 Rastgele Hatkon: Kol {arm}, MSB {error_msb}, LSB {error_lsb}, Status {status}")
                
                self.send_uart_frame(frame)
                time.sleep(5)  # 5 saniyede bir alarm
                
        except KeyboardInterrupt:
            print("\n⏹️ Simülasyon durduruldu")
    
    def cleanup(self):
        """Temizlik"""
        self.pi.write(self.TX_PIN, 1)  # Idle state
        self.pi.stop()
        print("🧹 UART Simülatörü temizlendi")

def main():
    print("🚀 UART Alarm Simülatörü")
    print("=" * 50)
    
    simulator = UARTAlarmSimulator()
    
    try:
        while True:
            print("\n📋 Simülasyon Seçenekleri:")
            print("1. Batarya Alarmları (Batkon)")
            print("2. Kol Alarmları (Hatkon)")
            print("3. Karışık Alarmlar")
            print("4. Sürekli Simülasyon")
            print("5. Çıkış")
            
            choice = input("\nSeçiminiz (1-5): ").strip()
            
            if choice == "1":
                simulator.simulate_battery_alarms()
            elif choice == "2":
                simulator.simulate_arm_alarms()
            elif choice == "3":
                simulator.simulate_mixed_alarms()
            elif choice == "4":
                simulator.run_continuous_simulation()
            elif choice == "5":
                break
            else:
                print("❌ Geçersiz seçim!")
    
    except KeyboardInterrupt:
        print("\n⏹️ Program durduruldu")
    
    finally:
        simulator.cleanup()

if __name__ == "__main__":
    main()
