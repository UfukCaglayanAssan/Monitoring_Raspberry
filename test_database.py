#!/usr/bin/env python3
"""
Database Test Scripti
"""

from database import BatteryDatabase
import time
from datetime import datetime, timedelta

def test_database():
    """Veritabanını test et"""
    print("=== DATABASE TEST ===")
    
    db = BatteryDatabase()
    
    # Test verisi ekle
    print("1. Test verisi ekleniyor...")
    test_data = [
        {'Arm': 1, 'k': 1, 'Dtype': 13, 'data': 25.5, 'timestamp': int(time.time() * 1000)},
        {'Arm': 1, 'k': 1, 'Dtype': 10, 'data': 85.2, 'timestamp': int(time.time() * 1000)},
        {'Arm': 1, 'k': 2, 'Dtype': 13, 'data': 24.8, 'timestamp': int(time.time() * 1000)},
        {'Arm': 2, 'k': 1, 'Dtype': 13, 'data': 26.1, 'timestamp': int(time.time() * 1000)},
    ]
    
    db.insert_battery_data(test_data)
    print(f"✓ {len(test_data)} test verisi eklendi")
    
    # Son 5 dakika verisi
    print("\n2. Son 5 dakika verisi:")
    recent_data = db.get_recent_data(minutes=5)
    print(f"Son 5 dakikada {len(recent_data)} kayıt bulundu")
    
    for row in recent_data:
        print(f"  Kol{row[0]}, Batarya{row[1]}, {row[2]}: {row[4]} {row[3]}")
    
    # Tarih aralığı verisi
    print("\n3. Bugünün verisi:")
    today = datetime.now().strftime('%Y-%m-%d')
    date_result = db.get_data_by_date_range(today, today)
    
    print(f"Bugün {date_result['pagination']['total_count']} kayıt bulundu")
    print(f"Sayfa bilgisi: {date_result['pagination']}")
    
    for row in date_result['data']:
        print(f"  Kol{row[0]}, Batarya{row[1]}, {row[2]}: {row[4]} {row[3]}")
    
    # İstatistikler
    print("\n4. İstatistikler:")
    stats = db.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print("\n✓ Database test tamamlandı!")

if __name__ == "__main__":
    test_database()