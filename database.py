# interface/database.py
import sqlite3
import threading
import os
from datetime import datetime, timedelta
import time

class BatteryDatabase:
    def __init__(self, db_path="battery_data.db"):
        self.db_path = db_path
        self.lock = threading.Lock()
        self.conn = None
        # Veritabanı yoksa oluştur, varsa sadece bağlan
        if not os.path.exists(self.db_path):
            self.init_database()
        else:
            print(f"Veritabanı zaten mevcut: {self.db_path}")
    
    def init_database(self):
        with self.lock:
            print(f"Yeni veritabanı oluşturuluyor: {self.db_path}")
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                print("Yeni veritabanı oluşturuluyor...")
                
                # Tek veri tablosu (tüm veriler için)
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
                print("✓ battery_data tablosu oluşturuldu")
                
                # Dil tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS languages (
                        language_code TEXT PRIMARY KEY,
                        language_name TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_default BOOLEAN DEFAULT FALSE
                    )
                ''')
                print("✓ languages tablosu oluşturuldu")
                
                # Veri tipi tablosu (sadece dtype ile)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_types (
                        dtype INTEGER PRIMARY KEY,
                        name TEXT,
                        unit TEXT,
                        description TEXT
                    )
                ''')
                print("✓ data_types tablosu oluşturuldu")
                
                # Veri tipi çevirileri
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS data_type_translations (
                        dtype INTEGER,
                        language_code TEXT,
                        name TEXT,
                        description TEXT,
                        PRIMARY KEY (dtype, language_code),
                        FOREIGN KEY (language_code) REFERENCES languages(language_code)
                    )
                ''')
                print("✓ data_type_translations tablosu oluşturuldu")
                
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
                print("✓ alarms tablosu oluşturuldu")
                
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
                print("✓ missing_data tablosu oluşturuldu")
                
                # Balans tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS passive_balance (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        slave INTEGER,
                        status INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ passive_balance tablosu oluşturuldu")
                
                # Arm slave counts tablosu
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS arm_slave_counts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        arm INTEGER,
                        slave_count INTEGER,
                        timestamp INTEGER,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                print("✓ arm_slave_counts tablosu oluşturuldu")
                
                # Dilleri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO languages (language_code, language_name, is_active, is_default)
                    VALUES 
                        ('tr', 'Türkçe', TRUE, TRUE),
                        ('en', 'English', TRUE, FALSE),
                        ('de', 'Deutsch', TRUE, FALSE)
                ''')
                print("✓ Diller eklendi")
                
                # Veri tiplerini ekle (sadece dtype ile)
                cursor.execute('''
                    INSERT OR IGNORE INTO data_types (dtype, name, unit, description)
                    VALUES 
                        (10, 'Veri Tipi 10', '', 'Genel veri tipi 10'),
                        (11, 'Veri Tipi 11', '', 'Genel veri tipi 11'),
                        (12, 'Veri Tipi 12', '', 'Genel veri tipi 12'),
                        (13, 'Veri Tipi 13', '', 'Genel veri tipi 13'),
                        (14, 'Veri Tipi 14', '', 'Genel veri tipi 14'),
                        (126, 'Veri Tipi 126', '', 'Genel veri tipi 126')
                ''')
                print("✓ Veri tipleri eklendi")
                
                # Türkçe çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'tr', 'Veri Tipi 10', 'Genel veri tipi 10'),
                        (11, 'tr', 'Veri Tipi 11', 'Genel veri tipi 11'),
                        (12, 'tr', 'Veri Tipi 12', 'Genel veri tipi 12'),
                        (13, 'tr', 'Veri Tipi 13', 'Genel veri tipi 13'),
                        (14, 'tr', 'Veri Tipi 14', 'Genel veri tipi 14'),
                        (126, 'tr', 'Veri Tipi 126', 'Genel veri tipi 126')
                ''')
                print("✓ Türkçe çeviriler eklendi")
                
                # İngilizce çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'en', 'Data Type 10', 'General data type 10'),
                        (11, 'en', 'Data Type 11', 'General data type 11'),
                        (12, 'en', 'Data Type 12', 'General data type 12'),
                        (13, 'en', 'Data Type 13', 'General data type 13'),
                        (14, 'en', 'Data Type 14', 'General data type 14'),
                        (126, 'en', 'Data Type 126', 'General data type 126')
                ''')
                print("✓ İngilizce çeviriler eklendi")
                
                # Almanca çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'de', 'Datentyp 10', 'Allgemeiner Datentyp 10'),
                        (11, 'de', 'Datentyp 11', 'Allgemeiner Datentyp 11'),
                        (12, 'de', 'Datentyp 12', 'Allgemeiner Datentyp 12'),
                        (13, 'de', 'Datentyp 13', 'Allgemeiner Datentyp 13'),
                        (14, 'de', 'Datentyp 14', 'Allgemeiner Datentyp 14'),
                        (126, 'de', 'Datentyp 126', 'Allgemeiner Datentyp 126')
                ''')
                print("✓ Almanca çeviriler eklendi")
                
                # Index'ler oluştur
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_k_timestamp ON battery_data(k, timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm_k_dtype ON battery_data(arm, k, dtype)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_alarm_timestamp ON alarms(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON battery_data(timestamp)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_arm ON battery_data(arm)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_dtype ON battery_data(dtype)')
                print("✓ Index'ler oluşturuldu")
                
                conn.commit()
                print("✓ Veritabanı başarıyla oluşturuldu!")
                
                # Veritabanı boyutunu göster
                db_size = os.path.getsize(self.db_path) / (1024 * 1024)  # MB
                print(f"Veritabanı boyutu: {db_size:.2f} MB")
    
    def get_connection(self):
        """Thread-safe bağlantı döndür"""
        return sqlite3.connect(self.db_path)
    
    def insert_battery_data(self, arm, k, dtype, data, timestamp):
        """Veri ekle (arm ve battery için tek tablo)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO battery_data (arm, k, dtype, data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (arm, k, dtype, data, timestamp))
            conn.commit()

    def insert_battery_data_batch(self, batch):
        """Batch olarak veri ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany('''
                INSERT INTO battery_data (arm, k, dtype, data, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', [(record['Arm'], record['k'], record['Dtype'], record['data'], record['timestamp']) for record in batch])
            conn.commit()
    
    def insert_alarm(self, arm, error_code_msb, error_code_lsb, timestamp):
        """Alarm verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alarms (arm, error_code_msb, error_code_lsb, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (arm, error_code_msb, error_code_lsb, timestamp))
            conn.commit()
    
    def insert_missing_data(self, arm, slave, status, timestamp):
        """Missing data verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO missing_data (arm, slave, status, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (arm, slave, status, timestamp))
            conn.commit()
    
    def insert_passive_balance(self, arm, slave, status, timestamp):
        """Passive balance verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO passive_balance (arm, slave, status, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (arm, slave, status, timestamp))
            conn.commit()
    
    def insert_arm_slave_counts(self, arm, slave_count, timestamp):
        """Arm slave count verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO arm_slave_counts (arm, slave_count, timestamp)
                VALUES (?, ?, ?)
            ''', (arm, slave_count, timestamp))
            conn.commit()
    
    def get_recent_data_with_translations(self, minutes=5, arm=None, battery=None, dtype=None, data_type=None, limit=100, language='tr'):
        """Son verileri çevirilerle birlikte getir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Temel sorgu
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit,
                    COALESCE(dtt.name, dt.name) as translated_name,
                    COALESCE(dtt.description, dt.description) as translated_description
                FROM battery_data bd
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dtt.language_code = ?
                WHERE bd.timestamp >= ?
            '''
            
            params = [language, int((datetime.now() - timedelta(minutes=minutes)).timestamp() * 1000)]
            
            # Filtreler
            if arm:
                query += ' AND bd.arm = ?'
                params.append(arm)
            
            if battery:
                query += ' AND bd.k = ?'
                params.append(battery)
            
            if dtype:
                query += ' AND bd.dtype = ?'
                params.append(dtype)
            
            if data_type and data_type != 'all':
                if data_type == 'arm':
                    query += ' AND bd.k = 2'
                elif data_type == 'battery':
                    query += ' AND bd.k != 2'
            
            query += ' ORDER BY bd.timestamp DESC LIMIT ?'
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'arm': row[0],
                'batteryAddress': row[1],
                'dtype': row[2],
                'data': row[3],
                'timestamp': row[4],
                'name': row[5],
                'unit': row[6],
                'translated_name': row[7],
                'translated_description': row[8]
            } for row in rows]
    
    def get_data_types_by_language(self, language='tr'):
        """Dile göre veri tiplerini getir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    dt.dtype,
                    COALESCE(dtt.name, dt.name) as name,
                    dt.unit,
                    COALESCE(dtt.description, dt.description) as description
                FROM data_types dt
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dtt.language_code = ?
                ORDER BY dt.dtype
            ''', (language,))
            
            rows = cursor.fetchall()
            return [{
                'dtype': row[0],
                'name': row[1],
                'unit': row[2],
                'description': row[3]
            } for row in rows]
    
    def get_data_by_date_range_with_translations(self, start_date, end_date, arm=None, battery=None, dtype=None, language='tr'):
        """Tarih aralığında veri getir (çevirilerle)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Tarihleri timestamp'e çevir
            start_timestamp = int(datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
            end_timestamp = int(datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
            
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit,
                    COALESCE(dtt.name, dt.name) as translated_name,
                    COALESCE(dtt.description, dt.description) as translated_description
                FROM battery_data bd
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                    AND dtt.language_code = ?
                WHERE bd.timestamp >= ? AND bd.timestamp <= ?
            '''
            
            params = [language, start_timestamp, end_timestamp]
            
            if arm:
                query += ' AND bd.arm = ?'
                params.append(arm)
            
            if battery:
                query += ' AND bd.k = ?'
                params.append(battery)
            
            if dtype:
                query += ' AND bd.dtype = ?'
                params.append(dtype)
            
            query += ' ORDER BY bd.timestamp DESC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'arm': row[0],
                'batteryAddress': row[1],
                'dtype': row[2],
                'data': row[3],
                'timestamp': row[4],
                'name': row[5],
                'unit': row[6],
                'translated_name': row[7],
                'translated_description': row[8]
            } for row in rows]
    
    def get_logs_with_filters(self, page=1, page_size=50, filters=None):
        """Filtrelenmiş log verilerini getir"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Temel sorgu - JOIN'de k koşulunu kaldırdık
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit
                FROM battery_data bd
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                WHERE 1=1
            '''
            
            params = []
            
            # Filtreler
            if filters.get('arm'):
                query += ' AND bd.arm = ?'
                params.append(filters['arm'])
            
            if filters.get('battery'):
                query += ' AND bd.k = ?'
                params.append(filters['battery'])
            
            if filters.get('dtype'):
                query += ' AND bd.dtype = ?'
                params.append(filters['dtype'])
            
            if filters.get('status'):
                if filters['status'] == 'success':
                    query += ' AND bd.data > 0'
                elif filters['status'] == 'error':
                    query += ' AND bd.data <= 0'
                elif filters['status'] == 'warning':
                    query += ' AND bd.data BETWEEN 0 AND 50'
            
            if filters.get('start_date'):
                start_timestamp = int(datetime.strptime(filters['start_date'], '%Y-%m-%d').timestamp() * 1000)
                query += ' AND bd.timestamp >= ?'
                params.append(start_timestamp)
            
            if filters.get('end_date'):
                end_timestamp = int(datetime.strptime(filters['end_date'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                query += ' AND bd.timestamp <= ?'
                params.append(end_timestamp)
            
            # Toplam sayı
            count_query = f"SELECT COUNT(*) FROM ({query})"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Sayfalama
            query += ' ORDER BY bd.timestamp DESC LIMIT ? OFFSET ?'
            params.extend([page_size, (page - 1) * page_size])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                logs.append({
                    'arm': row[0],
                    'batteryAddress': row[1],
                    'dtype': row[2],
                    'data': row[3],
                    'timestamp': row[4],
                    'name': row[5],
                    'unit': row[6],
                    'status': 'success'  # Tüm veriler başarılı
                })
            
            return {
                'logs': logs,
                'totalCount': total_count,
                'totalPages': (total_count + page_size - 1) // page_size,
                'currentPage': page
            }
    
    def export_logs_to_csv(self, filters=None):
        """Log verilerini CSV formatında export et"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    dt.name,
                    dt.unit
                FROM battery_data bd
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                WHERE 1=1
            '''
            
            params = []
            
            # Filtreler
            if filters.get('arm'):
                query += ' AND bd.arm = ?'
                params.append(filters['arm'])
            
            if filters.get('battery'):
                query += ' AND bd.k = ?'
                params.append(filters['battery'])
            
            if filters.get('dtype'):
                query += ' AND bd.dtype = ?'
                params.append(filters['dtype'])
            
            if filters.get('status'):
                if filters['status'] == 'success':
                    query += ' AND bd.data > 0'
                elif filters['status'] == 'error':
                    query += ' AND bd.data <= 0'
                elif filters['status'] == 'warning':
                    query += ' AND bd.data BETWEEN 0 AND 50'
            
            if filters.get('start_date'):
                start_timestamp = int(datetime.strptime(filters['start_date'], '%Y-%m-%d').timestamp() * 1000)
                query += ' AND bd.timestamp >= ?'
                params.append(start_timestamp)
            
            if filters.get('end_date'):
                end_timestamp = int(datetime.strptime(filters['end_date'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                query += ' AND bd.timestamp <= ?'
                params.append(end_timestamp)
            
            query += ' ORDER BY bd.timestamp DESC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # CSV formatı - Türkçe karakterler için
            csv_content = "ZAMAN,KOL,BATARYA ADRESİ,VERİ TÜRÜ,VERİ,DURUM\n"
            
            for row in rows:
                timestamp = datetime.fromtimestamp(row[4] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                
                csv_content += f"{timestamp},{row[0]},{row[1]},{row[5]},{row[3]},Başarılı\n"
            
            return csv_content

    def get_batteries_for_display(self, page=1, page_size=30):
        """Batteries sayfası için batarya verilerini getir"""
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Son batarya verilerini getir (k!=2 olanlar, yani batarya verileri)
            base_query = '''
                SELECT DISTINCT
                    bd.arm,
                    bd.k as batteryAddress,
                    MAX(bd.timestamp) as latest_timestamp
                FROM battery_data bd
                WHERE bd.k != 2
            '''
            
            params = []
            
            base_query += ' GROUP BY bd.arm, bd.k'
            
            # Toplam sayı
            count_query = f"SELECT COUNT(*) FROM ({base_query})"
            cursor.execute(count_query, params)
            total_count = cursor.fetchone()[0]
            
            # Sayfalama
            base_query += ' ORDER BY bd.arm, bd.k LIMIT ? OFFSET ?'
            params.extend([page_size, (page - 1) * page_size])
            
            cursor.execute(base_query, params)
            battery_groups = cursor.fetchall()
            
            batteries = []
            
            for group in battery_groups:
                arm, battery_address, latest_timestamp = group
                
                # Her batarya için son verileri getir
                battery_data = self.get_latest_battery_data(arm, battery_address)
                
                if battery_data:
                    batteries.append(battery_data)
            
            return {
                'batteries': batteries,
                'totalPages': (total_count + page_size - 1) // page_size,
                'currentPage': page
            }
    
    def get_latest_battery_data(self, arm, battery_address):
        """Belirli bir batarya için son verileri getir"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Son veri zamanını bul
            cursor.execute('''
                SELECT MAX(timestamp) FROM battery_data 
                WHERE arm = ? AND k = ? AND k != 2
            ''', (arm, battery_address))
            
            latest_timestamp = cursor.fetchone()[0]
            
            if not latest_timestamp:
                return None
            
            # Son verileri getir
            cursor.execute('''
                SELECT dtype, data FROM battery_data 
                WHERE arm = ? AND k = ? AND timestamp = ? AND k != 2
            ''', (arm, battery_address, latest_timestamp))
            
            data_rows = cursor.fetchall()
            
            # Veri tiplerine göre organize et
            battery_data = {
                'arm': arm,
                'batteryAddress': battery_address,
                'timestamp': latest_timestamp,
                'voltage': None,
                'temperature': None,
                'health': None,
                'charge': None,
                'isActive': True
            }
            
            for dtype, data in data_rows:
                if dtype == 10:  # Gerilim
                    battery_data['voltage'] = data
                elif dtype == 11:  # Şarj durumu
                    battery_data['charge'] = data
                elif dtype == 12:  # Sıcaklık
                    battery_data['temperature'] = data
                elif dtype == 126:  # Sağlık durumu
                    battery_data['health'] = data
            
            return battery_data
    
    def export_batteries_to_csv(self):
        """Batarya verilerini CSV formatında export et"""
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Son batarya verilerini getir
            base_query = '''
                SELECT DISTINCT
                    bd.arm,
                    bd.k as batteryAddress,
                MAX(bd.timestamp) as latest_timestamp
                FROM battery_data bd
                WHERE bd.k != 2
            '''
            
            params = []
            
            base_query += ' GROUP BY bd.arm, bd.k ORDER BY bd.arm, bd.k'
            
            cursor.execute(base_query, params)
            battery_groups = cursor.fetchall()
            
            # CSV formatı
            csv_content = "KOL,BATARYA ADRESİ,SON GÜNCELLEME,GERİLİM (V),SICAKLIK (°C),SAĞLIK DURUMU (%),ŞARJ DURUMU (%)\n"
            
            for group in battery_groups:
                arm, battery_address, latest_timestamp = group
                
                # Her batarya için son verileri getir
                battery_data = self.get_latest_battery_data(arm, battery_address)
                
                if battery_data:
                    timestamp = datetime.fromtimestamp(latest_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    
                    csv_content += f"{arm},{battery_address},{timestamp},"
                    csv_content += f"{battery_data['voltage'] or '--'},"
                    csv_content += f"{battery_data['temperature'] or '--'},"
                    csv_content += f"{battery_data['health'] or '--'},"
                    csv_content += f"{battery_data['charge'] or '--'}\n"
            
            return csv_content
    
    def get_database_size(self):
        """Veritabanı boyutunu MB cinsinden döndür"""
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return size_mb
        return 0