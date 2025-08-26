import sqlite3
import threading
from datetime import datetime, timedelta
import time

class BatteryDatabase:
    def __init__(self, db_path="battery_data.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.init_database()
    
    def init_database(self):
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Ana veri tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS battery_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        k INTEGER,
                        dtype INTEGER,
                        data REAL,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Veri tipi tanımlama tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_types (
                        dtype INTEGER PRIMARY KEY,
                        name TEXT,
                        unit TEXT,
                        description TEXT
                    )
                ''')
                
                # Alarm tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS alarms (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        error_code_msb INTEGER,
                        error_code_lsb INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Missing data tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS missing_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        slave INTEGER,
                        status INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Balans tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS passive_balances (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        slave INTEGER,
                        arm INTEGER,
                        status INTEGER,
                        updated_at INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Armslave counts tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS arm_slave_counts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm1 INTEGER,
                        arm2 INTEGER,
                        arm3 INTEGER,
                        arm4 INTEGER,
                        updated_at INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Veri tipi tanımlarını ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_types VALUES 
                    (10, 'SOC', '%', 'State of Charge'),
                    (11, 'SOH', '%', 'State of Health'),
                    (13, 'Sıcaklık', '°C', 'Sıcaklık değeri'),
                    (14, 'Sıcaklık', '°C', 'Sıcaklık değeri'),
                    (0x7F, 'Missing Data', '', 'Eksik veri'),
                    (0x7D, 'Alarm', '', 'Alarm verisi'),
                    (0x0F, 'Balans', '', 'Balans durumu'),
                    (0x7E, 'Arm Slave Counts', '', 'Arm slave sayıları')
                ''')
                
                # Performans için index'ler
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_dtype ON battery_data(arm, k, dtype)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON battery_data(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                
                conn.commit()
    
    def insert_battery_data(self, data_list):
        """Battery data ekle - her veri ayrı satır"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Her veriyi ayrı satır olarak ekle
                for item in data_list:
                    cursor.execute('''
                        INSERT INTO battery_data 
                        (arm, k, dtype, data, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        item.get('Arm', 0),
                        item.get('k', 0),
                        item.get('Dtype', 0),
                        item.get('data', 0.0),
                        item.get('timestamp', 0)
                    ))
                
                conn.commit()
    
    def get_recent_data(self, minutes=5, arm=None, dtype=None, limit=50):
        """Son X dakikanın verilerini getir (tarih seçimi yapılmadığında)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Son X dakikanın timestamp'i
                cutoff_time = int((time.time() - minutes * 60) * 1000)
                
                query = '''
                    SELECT 
                        bd.arm as Kol,
                        bd.k as Batarya,
                        dt.name as VeriTipi,
                        dt.unit as Birim,
                        bd.data as Deger,
                        datetime(bd.timestamp/1000, 'unixepoch') as Zaman,
                        bd.timestamp as RawTimestamp
                    FROM battery_data bd
                    JOIN data_types dt ON bd.dtype = dt.dtype
                    WHERE bd.timestamp >= ?
                '''
                
                params = [cutoff_time]
                
                if arm is not None:
                    query += " AND bd.arm = ?"
                    params.append(arm)
                if dtype is not None:
                    query += " AND bd.dtype = ?"
                    params.append(dtype)
                
                query += " ORDER BY bd.timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_data_by_date_range(self, start_date, end_date, arm=None, dtype=None, page=1, page_size=50):
        """Tarih aralığına göre veri getir (sayfalama ile)"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Tarihleri timestamp'e çevir
                start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
                end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                
                # Toplam kayıt sayısını al
                count_query = '''
                    SELECT COUNT(*) FROM battery_data bd
                    WHERE bd.timestamp BETWEEN ? AND ?
                '''
                
                count_params = [start_timestamp, end_timestamp]
                
                if arm is not None:
                    count_query += " AND bd.arm = ?"
                    count_params.append(arm)
                if dtype is not None:
                    count_query += " AND bd.dtype = ?"
                    count_params.append(dtype)
                
                cursor.execute(count_query, count_params)
                total_count = cursor.fetchone()[0]
                
                # Sayfalama hesapla
                offset = (page - 1) * page_size
                total_pages = (total_count + page_size - 1) // page_size
                
                # Veriyi getir
                data_query = '''
                    SELECT 
                        bd.arm as Kol,
                        bd.k as Batarya,
                        dt.name as VeriTipi,
                        dt.unit as Birim,
                        bd.data as Deger,
                        datetime(bd.timestamp/1000, 'unixepoch') as Zaman,
                        bd.timestamp as RawTimestamp
                    FROM battery_data bd
                    JOIN data_types dt ON bd.dtype = dt.dtype
                    WHERE bd.timestamp BETWEEN ? AND ?
                '''
                
                data_params = [start_timestamp, end_timestamp]
                
                if arm is not None:
                    data_query += " AND bd.arm = ?"
                    data_params.append(arm)
                if dtype is not None:
                    data_query += " AND bd.dtype = ?"
                    data_params.append(dtype)
                
                data_query += " ORDER BY bd.timestamp DESC LIMIT ? OFFSET ?"
                data_params.extend([page_size, offset])
                
                cursor.execute(data_query, data_params)
                data = cursor.fetchall()
                
                return {
                    'data': data,
                    'pagination': {
                        'current_page': page,
                        'total_pages': total_pages,
                        'total_count': total_count,
                        'page_size': page_size,
                        'has_next': page < total_pages,
                        'has_prev': page > 1
                    }
                }
    
    def get_latest_data(self, arm=None, dtype=None, limit=100):
        """Son verileri getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = "SELECT * FROM battery_data"
                params = []
                
                if arm is not None:
                    query += " WHERE arm = ?"
                    params.append(arm)
                    if dtype is not None:
                        query += " AND dtype = ?"
                        params.append(dtype)
                elif dtype is not None:
                    query += " WHERE dtype = ?"
                    params.append(dtype)
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_formatted_data(self, arm=None, k=None, limit=100):
        """Formatlanmış veri getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT 
                        bd.arm as Kol,
                        bd.k as Batarya,
                        dt.name as VeriTipi,
                        dt.unit as Birim,
                        bd.data as Deger,
                        datetime(bd.timestamp/1000, 'unixepoch') as Zaman
                    FROM battery_data bd
                    JOIN data_types dt ON bd.dtype = dt.dtype
                '''
                
                params = []
                if arm:
                    query += " WHERE bd.arm = ?"
                    params.append(arm)
                    if k:
                        query += " AND bd.k = ?"
                        params.append(k)
                
                query += " ORDER BY bd.timestamp DESC LIMIT ?"
                params.append(limit)
                
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def get_stats(self):
        """İstatistikleri getir"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Toplam kayıt sayısı
                cursor.execute('SELECT COUNT(*) FROM battery_data')
                total_records = cursor.fetchone()[0]
                
                # Son 24 saatteki kayıt sayısı
                end_time = int(time.time() * 1000)
                start_time = end_time - (24 * 3600 * 1000)
                cursor.execute('SELECT COUNT(*) FROM battery_data WHERE timestamp BETWEEN ? AND ?', (start_time, end_time))
                last_24h = cursor.fetchone()[0]
                
                # Veritabanı boyutu
                db_size = self.get_database_size()
                
                return {
                    'total_records': total_records,
                    'last_24h_records': last_24h,
                    'database_size_mb': round(db_size, 2)
                }
    
    def cleanup_old_data(self, days=30):
        """Eski verileri temizle - disk alanı için"""
        with self.lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cutoff_time = int((time.time() - days * 24 * 3600) * 1000)
                cursor.execute('DELETE FROM battery_data WHERE timestamp < ?', (cutoff_time,))
                conn.commit()
    
    def get_database_size(self):
        """Veritabanı boyutunu kontrol et"""
        import os
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return size_mb
        return 0

    # ... (diğer metodlar aynı kalacak)