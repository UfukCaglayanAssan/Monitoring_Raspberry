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
                        battery INTEGER,
                        error_code_msb INTEGER,
                        error_code_lsb INTEGER,
                        timestamp INTEGER,
                        status TEXT DEFAULT 'active',
                        resolved_at DATETIME,
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
                        (10, 'Gerilim', 'V', 'Batarya gerilim değeri'),
                        (11, 'Şarj Durumu', '%', 'Batarya şarj yüzdesi'),
                        (12, 'Sıcaklık', '°C', 'Batarya sıcaklık değeri'),
                        (13, 'Nem', '%', 'Ortam nem değeri'),
                        (14, 'Akım', 'A', 'Akım değeri'),
                        (126, 'Sağlık Durumu', '%', 'Batarya sağlık yüzdesi')
                ''')
                print("✓ Veri tipleri eklendi")
                
                # Türkçe çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'tr', 'Gerilim', 'Batarya gerilim değeri'),
                        (11, 'tr', 'Şarj Durumu', 'Batarya şarj yüzdesi'),
                        (12, 'tr', 'Sıcaklık', 'Batarya sıcaklık değeri'),
                        (13, 'tr', 'Nem', 'Ortam nem değeri'),
                        (14, 'tr', 'Akım', 'Akım değeri'),
                        (126, 'tr', 'Sağlık Durumu', 'Batarya sağlık yüzdesi')
                ''')
                print("✓ Türkçe çeviriler eklendi")
                
                # İngilizce çevirileri ekle
                cursor.execute('''
                    INSERT OR IGNORE INTO data_type_translations (dtype, language_code, name, description)
                    VALUES 
                        (10, 'en', 'Voltage', 'Battery voltage value'),
                        (11, 'en', 'Charge Status', '%', 'Battery charge percentage'),
                        (12, 'en', 'Temperature', '°C', 'Battery temperature value'),
                        (13, 'en', 'Humidity', '%', 'Ambient humidity value'),
                        (14, 'en', 'Current', 'A', 'Current value'),
                        (126, 'en', 'Health Status', '%', 'Battery health percentage')
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
    
    def execute_query(self, query, params=None):
        """Özel SQL sorgusu çalıştır"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                conn.commit()
                return cursor
        except Exception as e:
            print(f"execute_query hatası: {e}")
            raise e
    
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
    
    def insert_alarm(self, arm, battery, error_code_msb, error_code_lsb, timestamp):
        """Alarm verisi ekle"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO alarms (arm, battery, error_code_msb, error_code_lsb, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (arm, battery, error_code_msb, error_code_lsb, timestamp))
            conn.commit()
    
    def resolve_alarm(self, arm, battery):
        """Belirli bir batarya için aktif alarmı düzelt"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE alarms 
                SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP
                WHERE arm = ? AND battery = ? AND status = 'active'
            ''', (arm, battery))
            conn.commit()
            return cursor.rowcount > 0

    def get_all_alarms(self, show_resolved=True):
        """Tüm alarmları getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if show_resolved:
                    # Tüm alarmları getir (aktif + düzelen)
                    cursor.execute('''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        ORDER BY timestamp DESC
                    ''')
                else:
                    # Sadece aktif alarmları getir
                    cursor.execute('''
                        SELECT id, arm, battery, error_code_msb, error_code_lsb, timestamp, status, resolved_at, created_at
                        FROM alarms 
                        WHERE status = 'active'
                        ORDER BY timestamp DESC
                    ''')
                
                rows = cursor.fetchall()
                return rows
        except Exception as e:
            print(f"get_all_alarms hatası: {e}")
            return []
    
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
    
    def get_logs_with_filters(self, page=1, page_size=50, filters=None, language='tr'):
        """Filtrelenmiş log verilerini getir"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Temel sorgu - JOIN'de k koşulunu kaldırdık ve çeviri ekle
            query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    bd.dtype,
                    bd.data,
                    bd.timestamp,
                    COALESCE(dtt.name, dt.name) as name,
                    dt.unit
                FROM battery_data bd
                LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype AND dtt.language_code = ?
                WHERE 1=1
            '''
            
            params = [language]  # Dil parametresi ilk sırada
            
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

    def get_batteries_for_display(self, page=1, page_size=30, selected_arm=0, language='tr'):
        """Batteries sayfası için batarya verilerini getir"""
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Arm filtresi ekle (her zaman bir kol seçilmeli)
                arm_filter = f"AND bd.arm = {selected_arm}"
                
                # Her batarya için en son veri zamanını bul ve sadece en güncel olanları getir
                cursor.execute(f'''
                    SELECT 
                        bd.arm,
                        bd.k as batteryAddress,
                        MAX(bd.timestamp) as latest_timestamp
                    FROM battery_data bd
                    WHERE bd.k != 2 {arm_filter}
                    GROUP BY bd.arm, bd.k
                    ORDER BY bd.arm, bd.k
                ''')
                
                all_batteries = cursor.fetchall()
                print(f"Bulunan batarya sayısı: {len(all_batteries)}")
                print(f"Batarya listesi: {all_batteries}")
                
                if not all_batteries:
                    print("Hiç batarya bulunamadı!")
                    return {
                        'batteries': [],
                        'totalPages': 1,
                        'currentPage': 1
                    }
                
                # Sayfalama
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                page_batteries = all_batteries[start_idx:end_idx]
                
                batteries = []
                
                for arm, battery_address, latest_timestamp in page_batteries:
                    # Her batarya için sadece en son verileri getir
                    battery_data = self.get_latest_battery_data(arm, battery_address, language)
                    
                    if battery_data:
                        batteries.append(battery_data)
                
                return {
                    'batteries': batteries,
                    'totalPages': (len(all_batteries) + page_size - 1) // page_size,
                    'currentPage': 1
                }
        except Exception as e:
            print(f"get_batteries_for_display hatası: {e}")
            raise e
    
    def get_latest_battery_data(self, arm, battery_address, language='tr'):
        """Belirli bir batarya için son verileri getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # En son veri zamanını bul
                cursor.execute('''
                    SELECT MAX(timestamp) FROM battery_data 
                    WHERE arm = ? AND k = ?
                ''', (arm, battery_address))
                
                latest_timestamp = cursor.fetchone()[0]
                
                if not latest_timestamp:
                    return None
                
                # Debug: Dil parametresini yazdır
                print(f"DEBUG: Dil parametresi: {language}")
                
                # Sadece en son verileri getir (en son timestamp'teki tüm dtype'lar)
                cursor.execute('''
                    SELECT bd.dtype, bd.data, dt.name, dt.unit,
                           COALESCE(dtt.name, dt.name) as translated_name
                    FROM battery_data bd
                    LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                    LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype 
                        AND dtt.language_code = ?
                    WHERE bd.arm = ? AND bd.k = ? AND bd.timestamp = ?
                    ORDER BY bd.dtype
                ''', (language, arm, battery_address, latest_timestamp))
                
                data_rows = cursor.fetchall()
                
                # Debug: Veri satırlarını yazdır
                print(f"DEBUG: Veri satırları: {data_rows}")
                
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
                
                # Sadece en son verileri kullan
                for dtype, data, name, unit, translated_name in data_rows:
                    print(f"DEBUG: dtype={dtype}, name={name}, translated_name={translated_name}")
                    if dtype == 10:  # Gerilim
                        battery_data['voltage'] = data
                        battery_data['voltage_name'] = translated_name or name
                    elif dtype == 11:  # Şarj durumu
                        battery_data['charge'] = data
                        battery_data['charge_name'] = translated_name or name
                    elif dtype == 12:  # Sıcaklık
                        battery_data['temperature'] = data
                        battery_data['temperature_name'] = translated_name or name
                    elif dtype == 126:  # Sağlık durumu
                        battery_data['health'] = data
                        battery_data['health_name'] = translated_name or name
                
                return battery_data
        except Exception as e:
            print(f"get_latest_battery_data hatası (arm: {arm}, battery: {battery_address}): {e}")
            return None
    
    def export_batteries_to_csv(self):
        """Batarya verilerini CSV formatında export et"""
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Her batarya için en son veri zamanını bul
            base_query = '''
                SELECT 
                    bd.arm,
                    bd.k as batteryAddress,
                    MAX(bd.timestamp) as latest_timestamp
                FROM battery_data bd
                WHERE bd.k != 2
                GROUP BY bd.arm, bd.k 
                ORDER BY bd.arm, bd.k
            '''
            
            cursor.execute(base_query)
            battery_groups = cursor.fetchall()
            
            # CSV formatı
            csv_content = "KOL,BATARYA ADRESİ,SON GÜNCELLEME,GERİLİM (V),SICAKLIK (°C),SAĞLIK DURUMU (%),ŞARJ DURUMU (%)\n"
            
            for group in battery_groups:
                arm, battery_address, latest_timestamp = group
                
                # Her batarya için sadece en son verileri getir
                battery_data = self.get_latest_battery_data(arm, battery_address)
                
                if battery_data:
                    timestamp = datetime.fromtimestamp(latest_timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    
                    csv_content += f"{arm},{battery_address},{timestamp},"
                    csv_content += f"{battery_data['voltage'] or '--'},"
                    csv_content += f"{battery_data['temperature'] or '--'},"
                    csv_content += f"{battery_data['charge'] or '--'},"
                    csv_content += f"{battery_data['health'] or '--'}\n"
            
            return csv_content
    
    def get_database_size(self):
        """Veritabanı boyutunu MB cinsinden döndür"""
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
            return size_mb
        return 0
    
    def get_summary_data(self):
        """Özet sayfası için veri getir - son 10 dakikada verisi gelen kollar"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Son 10 dakikada verisi gelen kolları bul
                ten_minutes_ago = int((datetime.now() - timedelta(minutes=10)).timestamp() * 1000)
                
                # Her kol için son veri zamanını bul
                cursor.execute('''
                    SELECT arm, MAX(timestamp) as latest_timestamp
                    FROM battery_data 
                    WHERE timestamp >= ?
                    GROUP BY arm
                    ORDER BY arm
                ''', (ten_minutes_ago,))
                
                active_arms = cursor.fetchall()
                summary_data = []
                
                for arm, latest_timestamp in active_arms:
                    if not latest_timestamp:
                        continue
                    
                    # Bu kol için nem ve sıcaklık bilgisini al (k=2)
                    cursor.execute('''
                        SELECT bd.dtype, bd.data, dt.name, dt.unit
                        FROM battery_data bd
                        LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                        WHERE bd.arm = ? AND bd.k = 2 AND bd.timestamp = ?
                        ORDER BY bd.dtype
                    ''', (arm, latest_timestamp))
                    
                    arm_data = cursor.fetchall()
                    
                    print(f"Kol {arm} için k=2 verileri: {arm_data}")
                    
                    # Nem ve sıcaklık değerlerini al
                    humidity = None
                    temperature = None
                    
                    for dtype, data, name, unit in arm_data:
                        print(f"  dtype={dtype}, data={data}, name={name}, unit={unit}")
                        if dtype == 13:  # Nem
                            humidity = data
                            print(f"    Nem bulundu: {humidity}")
                        elif dtype == 12:  # Sıcaklık
                            temperature = data
                            print(f"    Sıcaklık bulundu: {temperature}")
                    
                    # Bu kol için batarya sayısını ve ortalama değerleri hesapla
                    cursor.execute('''
                        SELECT 
                            COUNT(DISTINCT bd.k) as battery_count,
                            AVG(CASE WHEN bd.dtype = 10 THEN bd.data END) as avg_voltage,
                            AVG(CASE WHEN bd.dtype = 11 THEN bd.data END) as avg_charge,
                            AVG(CASE WHEN bd.dtype = 126 THEN bd.data END) as avg_health
                        FROM battery_data bd
                        WHERE bd.arm = ? AND bd.k != 2 AND bd.timestamp = ?
                    ''', (arm, latest_timestamp))
                    
                    battery_stats = cursor.fetchone()
                    
                    if battery_stats:
                        battery_count, avg_voltage, avg_charge, avg_health = battery_stats
                        
                        summary_data.append({
                            'arm': arm,
                            'timestamp': latest_timestamp,
                            'humidity': humidity,
                            'temperature': temperature,
                            'battery_count': battery_count or 0,
                            'avg_voltage': round(avg_voltage, 3) if avg_voltage else None,
                            'avg_charge': round(avg_charge, 3) if avg_charge else None,
                            'avg_health': round(avg_health, 3) if avg_health else None
                        })
                
                return summary_data
                
        except Exception as e:
            print(f"get_summary_data hatası: {e}")
            return []
    
    def get_batconfigs(self):
        """Tüm batarya konfigürasyonlarını getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT armValue, Vmin, Vmax, Vnom, Rintnom, Tempmin_D, Tempmax_D, 
                           Tempmin_PN, Tempmaks_PN, Socmin, Sohmin, time, created_at
                    FROM batconfigs 
                    ORDER BY armValue
                ''')
                
                rows = cursor.fetchall()
                configs = []
                
                for row in rows:
                    config = {
                        'armValue': row[0],
                        'Vmin': row[1],
                        'Vmax': row[2],
                        'Vnom': row[3],
                        'Rintnom': row[4],
                        'Tempmin_D': row[5],
                        'Tempmax_D': row[6],
                        'Tempmin_PN': row[7],
                        'Tempmaks_PN': row[8],
                        'Socmin': row[9],
                        'Sohmin': row[10],
                        'time': row[11],
                        'created_at': row[12]
                    }
                    configs.append(config)
                
                return configs
        except Exception as e:
            print(f"get_batconfigs hatası: {e}")
            return []
    
    def get_armconfigs(self):
        """Tüm kol konfigürasyonlarını getir"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT armValue, akimKats, akimMax, nemMax, nemMin, tempMax, tempMin, time, created_at
                    FROM armconfigs 
                    ORDER BY armValue
                ''')
                
                rows = cursor.fetchall()
                configs = []
                
                for row in rows:
                    config = {
                        'armValue': row[0],
                        'akimKats': row[1],
                        'akimMax': row[2],
                        'nemMax': row[3],
                        'nemMin': row[4],
                        'tempMax': row[5],
                        'tempMin': row[6],
                        'time': row[7],
                        'created_at': row[8]
                    }
                    configs.append(config)
                
                return configs
        except Exception as e:
            print(f"get_armconfigs hatası: {e}")
            return []
    
    def get_grouped_battery_logs(self, page=1, page_size=50, filters=None, language='tr'):
        """Gruplandırılmış batarya log verilerini getir"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Önce benzersiz timestamp'leri bul
            timestamp_query = '''
                SELECT DISTINCT timestamp
                FROM battery_data
                WHERE 1=1
            '''
            
            timestamp_params = []
            
            if filters.get('arm'):
                timestamp_query += ' AND arm = ?'
                timestamp_params.append(filters['arm'])
            
            if filters.get('battery'):
                timestamp_query += ' AND k = ?'
                timestamp_params.append(filters['battery'])
            
            if filters.get('startDate'):
                start_timestamp = int(datetime.strptime(filters['startDate'], '%Y-%m-%d').timestamp() * 1000)
                timestamp_query += ' AND timestamp >= ?'
                timestamp_params.append(start_timestamp)
            
            if filters.get('endDate'):
                end_timestamp = int(datetime.strptime(filters['endDate'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                timestamp_query += ' AND timestamp <= ?'
                timestamp_params.append(end_timestamp)
            
            timestamp_query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
            timestamp_params.extend([page_size, (page - 1) * page_size])
            
            cursor.execute(timestamp_query, timestamp_params)
            timestamps = [row[0] for row in cursor.fetchall()]
            
            if not timestamps:
                return {'logs': [], 'totalCount': 0, 'totalPages': 1, 'currentPage': page}
            
            # Her timestamp için tüm veri tiplerini getir
            logs = []
            for timestamp in timestamps:
                data_query = '''
                    SELECT 
                        bd.arm,
                        bd.k as batteryAddress,
                        bd.dtype,
                        bd.data,
                        bd.timestamp,
                        COALESCE(dtt.name, dt.name) as name,
                        dt.unit
                    FROM battery_data bd
                    LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                    LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype AND dtt.language_code = ?
                    WHERE bd.timestamp = ?
                '''
                
                data_params = [language, timestamp]
                
                if filters.get('arm'):
                    data_query += ' AND bd.arm = ?'
                    data_params.append(filters['arm'])
                
                if filters.get('battery'):
                    data_query += ' AND bd.k = ?'
                    data_params.append(filters['battery'])
                
                cursor.execute(data_query, data_params)
                rows = cursor.fetchall()
                
                if rows:
                    # Verileri grupla
                    grouped_data = {
                        'timestamp': timestamp,
                        'arm': rows[0][0],
                        'batteryAddress': rows[0][1],
                        'voltage': None,
                        'charge_status': None,
                        'temperature': None,
                        'positive_pole_temp': None,
                        'negative_pole_temp': None,
                        'health_status': None
                    }
                    
                    for row in rows:
                        dtype = row[2]
                        data = row[3]
                        
                        if dtype == 10:  # Gerilim
                            grouped_data['voltage'] = data
                        elif dtype == 11:  # Şarj Durumu
                            grouped_data['charge_status'] = data
                        elif dtype == 12:  # Sıcaklık
                            grouped_data['temperature'] = data
                        elif dtype == 13:  # Pozitif Kutup Sıcaklığı
                            grouped_data['positive_pole_temp'] = data
                        elif dtype == 14:  # Negatif Kutup Sıcaklığı
                            grouped_data['negative_pole_temp'] = data
                        elif dtype == 126:  # Sağlık Durumu
                            grouped_data['health_status'] = data
                    
                    logs.append(grouped_data)
            
            # Toplam sayfa sayısını hesapla
            count_query = '''
                SELECT COUNT(DISTINCT timestamp)
                FROM battery_data
                WHERE 1=1
            '''
            
            count_params = []
            
            if filters.get('arm'):
                count_query += ' AND arm = ?'
                count_params.append(filters['arm'])
            
            if filters.get('battery'):
                count_query += ' AND k = ?'
                count_params.append(filters['battery'])
            
            if filters.get('startDate'):
                start_timestamp = int(datetime.strptime(filters['startDate'], '%Y-%m-%d').timestamp() * 1000)
                count_query += ' AND timestamp >= ?'
                count_params.append(start_timestamp)
            
            if filters.get('endDate'):
                end_timestamp = int(datetime.strptime(filters['endDate'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                count_query += ' AND timestamp <= ?'
                count_params.append(end_timestamp)
            
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]
            total_pages = (total_count + page_size - 1) // page_size
            
            return {
                'logs': logs,
                'totalCount': total_count,
                'totalPages': total_pages,
                'currentPage': page
            }
    
    def get_grouped_arm_logs(self, page=1, page_size=50, filters=None, language='tr'):
        """Gruplandırılmış kol log verilerini getir"""
        if filters is None:
            filters = {}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Önce benzersiz timestamp'leri bul
            timestamp_query = '''
                SELECT DISTINCT timestamp
                FROM battery_data
                WHERE k = 2  # Kol verileri için k=2
                AND 1=1
            '''
            
            timestamp_params = []
            
            if filters.get('arm'):
                timestamp_query += ' AND arm = ?'
                timestamp_params.append(filters['arm'])
            
            if filters.get('startDate'):
                start_timestamp = int(datetime.strptime(filters['startDate'], '%Y-%m-%d').timestamp() * 1000)
                timestamp_query += ' AND timestamp >= ?'
                timestamp_params.append(start_timestamp)
            
            if filters.get('endDate'):
                end_timestamp = int(datetime.strptime(filters['endDate'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                timestamp_query += ' AND timestamp <= ?'
                timestamp_params.append(end_timestamp)
            
            timestamp_query += ' ORDER BY timestamp DESC LIMIT ? OFFSET ?'
            timestamp_params.extend([page_size, (page - 1) * page_size])
            
            cursor.execute(timestamp_query, timestamp_params)
            timestamps = [row[0] for row in cursor.fetchall()]
            
            if not timestamps:
                return {'logs': [], 'totalCount': 0, 'totalPages': 1, 'currentPage': page}
            
            # Her timestamp için tüm veri tiplerini getir
            logs = []
            for timestamp in timestamps:
                data_query = '''
                    SELECT 
                        bd.arm,
                        bd.k as batteryAddress,
                        bd.dtype,
                        bd.data,
                        bd.timestamp,
                        COALESCE(dtt.name, dt.name) as name,
                        dt.unit
                    FROM battery_data bd
                    LEFT JOIN data_types dt ON bd.dtype = dt.dtype
                    LEFT JOIN data_type_translations dtt ON dt.dtype = dtt.dtype AND dtt.language_code = ?
                    WHERE bd.timestamp = ? AND bd.k = 2
                '''
                
                data_params = [language, timestamp]
                
                if filters.get('arm'):
                    data_query += ' AND bd.arm = ?'
                    data_params.append(filters['arm'])
                
                cursor.execute(data_query, data_params)
                rows = cursor.fetchall()
                
                if rows:
                    # Verileri grupla
                    grouped_data = {
                        'timestamp': timestamp,
                        'arm': rows[0][0],
                        'current': None,
                        'voltage': None,
                        'humidity': None,
                        'ambient_temperature': None,
                        'arm_temperature': None
                    }
                    
                    for row in rows:
                        dtype = row[2]
                        data = row[3]
                        
                        if dtype == 10:  # Akım/Gerilim (akım olarak kullan)
                            grouped_data['current'] = data
                        elif dtype == 11:  # Nem
                            grouped_data['humidity'] = data
                        elif dtype == 12:  # Ortam Sıcaklığı
                            grouped_data['ambient_temperature'] = data
                        elif dtype == 13:  # Kol Sıcaklığı
                            grouped_data['arm_temperature'] = data
                        elif dtype == 14:  # Gerilim (ayrı kolon)
                            grouped_data['voltage'] = data
                    
                    logs.append(grouped_data)
            
            # Toplam sayfa sayısını hesapla
            count_query = '''
                SELECT COUNT(DISTINCT timestamp)
                FROM battery_data
                WHERE k = 2
                AND 1=1
            '''
            
            count_params = []
            
            if filters.get('arm'):
                count_query += ' AND arm = ?'
                count_params.append(filters['arm'])
            
            if filters.get('startDate'):
                start_timestamp = int(datetime.strptime(filters['startDate'], '%Y-%m-%d').timestamp() * 1000)
                count_query += ' AND timestamp >= ?'
                count_params.append(start_timestamp)
            
            if filters.get('endDate'):
                end_timestamp = int(datetime.strptime(filters['endDate'], '%Y-%m-%d').timestamp() * 1000) + (24 * 60 * 60 * 1000) - 1
                count_query += ' AND timestamp <= ?'
                count_params.append(end_timestamp)
            
            cursor.execute(count_query, count_params)
            total_count = cursor.fetchone()[0]
            total_pages = (total_count + page_size - 1) // page_size
            
            return {
                'logs': logs,
                'totalCount': total_count,
                'totalPages': total_pages,
                'currentPage': page
            }