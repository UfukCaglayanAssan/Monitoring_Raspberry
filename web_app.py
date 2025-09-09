# interface/web_app.py
from flask import Flask, render_template, jsonify, request
from database import BatteryDatabase
import time
import json
import threading
from datetime import datetime

app = Flask(__name__)

# Thread-safe database erişimi için lock'lar
db_lock = threading.Lock()  # Write işlemleri için
db_read_lock = threading.RLock()  # Read işlemleri için (multiple readers allowed)

# Retry mekanizması için
import time as time_module

# Database instance'ını thread-safe yapmak için lazy loading
# main.py'den farklı bir connection pool kullan
def get_db():
    if not hasattr(get_db, 'instance'):
        get_db.instance = BatteryDatabase()
        # Connection pool zaten WAL mode ve timeout ile yapılandırılmış
        print("✅ Database instance oluşturuldu (WAL mode + timeout enabled)")
    return get_db.instance

# Database işlemleri için retry wrapper
def db_operation_with_retry(operation, max_retries=3, delay=0.1):
    """Database işlemini retry ile çalıştır"""
    for attempt in range(max_retries):
        try:
            return operation()
        except Exception as e:
            if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                print(f"⚠️ Database locked, retry {attempt + 1}/{max_retries} in {delay}s...")
                time_module.sleep(delay)
                delay *= 2  # Exponential backoff
            else:
                raise e

# Global db referansı (backward compatibility için)
db = None

@app.route('/')
def index():
    # Ana sayfa olarak logs sayfasını göster
    return render_template('layout.html')

@app.route('/mail-management')
def mail_management():
    return render_template('pages/mail-management.html')

@app.route('/page/<page_name>')
def get_page(page_name):
    """Sayfa içeriğini döndür"""
    if page_name == 'summary':
        return render_template('pages/summary.html')
    elif page_name == 'alarms':
        return render_template('pages/alarms.html')
    elif page_name == 'batteries':
        return render_template('pages/batteries.html')
    elif page_name == 'battery-logs':
        return render_template('pages/battery-logs.html')
    elif page_name == 'arm-logs':
        return render_template('pages/arm-logs.html')
    elif page_name == 'configuration':
        return render_template('pages/configuration.html')
    elif page_name == 'profile':
        return render_template('pages/profile.html')
    else:
        return render_template('pages/404.html')

@app.route('/pages/<page_name>.html')
def get_page_html(page_name):
    """Sayfa içeriğini HTML olarak döndür (JavaScript için)"""
    if page_name == 'summary':
        return render_template('pages/summary.html')
    elif page_name == 'alarms':
        return render_template('pages/alarms.html')
    elif page_name == 'batteries':
        return render_template('pages/batteries.html')
    elif page_name == 'battery-logs':
        return render_template('pages/battery-logs.html')
    elif page_name == 'arm-logs':
        return render_template('pages/arm-logs.html')
    elif page_name == 'configuration':
        return render_template('pages/configuration.html')
    elif page_name == 'profile':
        return render_template('pages/profile.html')
    else:
        return render_template('pages/404.html')

@app.route('/api/data_types')
def get_data_types():
    language = request.args.get('lang', 'tr')  # Varsayılan Türkçe
    db_instance = get_db()
    with db_read_lock:
        data_types = db_instance.get_data_types_by_language(language)
    return jsonify(data_types)

@app.route('/api/alarm_count')
def get_alarm_count():
    """Aktif alarm sayısını getir"""
    try:
        db_instance = get_db()
        with db_read_lock:
            count = db_instance.get_active_alarm_count()
        return jsonify({
            'success': True,
            'count': count
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/recent_data')
def get_recent_data():
    minutes = int(request.args.get('minutes', 5))
    arm = request.args.get('arm')
    battery = request.args.get('battery')
    dtype = request.args.get('dtype')
    data_type = request.args.get('data_type')
    limit = int(request.args.get('limit', 50))
    language = request.args.get('lang', 'tr')
    
    if arm:
        arm = int(arm)
    if battery:
        battery = int(battery)
    if dtype:
        dtype = int(dtype)
    
    db_instance = get_db()
    with db_read_lock:
        data = db_instance.get_recent_data_with_translations(
        minutes=minutes, 
        arm=arm, 
        battery=battery, 
        dtype=dtype, 
        data_type=data_type, 
        limit=limit,
        language=language
    )
    return jsonify(data)

@app.route('/api/data_by_date')
def get_data_by_date():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    arm = request.args.get('arm')
    dtype = request.args.get('dtype')
    language = request.args.get('lang', 'tr')
    
    if arm:
        arm = int(arm)
    if dtype:
        dtype = int(dtype)
    
    db_instance = get_db()
    with db_read_lock:
        data = db_instance.get_data_by_date_range_with_translations(
        start_date, end_date, arm, dtype, language
    )
    return jsonify(data)



@app.route('/api/battery-logs', methods=['POST'])
def get_battery_logs():
    """Gruplandırılmış batarya log verilerini getir"""
    data = request.get_json()
    page = data.get('page', 1)
    page_size = data.get('pageSize', 50)
    filters = data.get('filters', {})
    
    # Mevcut dili al
    language = request.headers.get('X-Language', 'tr')
    print(f"DEBUG web_app.py battery-logs: Dil parametresi: {language}")
    
    try:
        # Veritabanından gruplandırılmış batarya log verilerini al
        db_instance = get_db()
        with db_read_lock:
            logs_data = db_instance.get_grouped_battery_logs(
            page=page,
            page_size=page_size,
            filters=filters,
            language=language
        )
        
        return jsonify({
            'success': True,
            'logs': logs_data['logs'],
            'totalCount': logs_data['totalCount'],
            'totalPages': logs_data['totalPages'],
            'currentPage': logs_data['currentPage']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/arm-logs', methods=['POST'])
def get_arm_logs():
    """Gruplandırılmış kol log verilerini getir"""
    data = request.get_json()
    page = data.get('page', 1)
    page_size = data.get('pageSize', 50)
    filters = data.get('filters', {})
    
    # Mevcut dili al
    language = request.headers.get('X-Language', 'tr')
    print(f"DEBUG web_app.py arm-logs: Dil parametresi: {language}")
    
    try:
        # Veritabanından gruplandırılmış kol log verilerini al
        db_instance = get_db()
        with db_read_lock:
            logs_data = db_instance.get_grouped_arm_logs(
            page=page,
            page_size=page_size,
            filters=filters,
            language=language
        )
        
        return jsonify({
            'success': True,
            'logs': logs_data['logs'],
            'totalCount': logs_data['totalCount'],
            'totalPages': logs_data['totalPages'],
            'currentPage': logs_data['currentPage']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/logs/export', methods=['POST'])
def export_logs():
    """Log verilerini CSV olarak export et"""
    try:
        data = request.get_json()
        filters = data.get('filters', {})
        
        db_instance = get_db()
        with db_read_lock:
            csv_content = db_instance.export_logs_to_csv(filters)
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=logs_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/batteries', methods=['POST'])
def get_batteries():
    """Batarya verilerini getir"""
    try:
        data = request.get_json()
        page = data.get('page', 1)
        page_size = data.get('pageSize', 30)
        selected_arm = data.get('selectedArm', 3)  # Varsayılan: Kol 3
        
        # Mevcut dili al (localStorage'dan veya varsayılan olarak 'tr')
        language = request.headers.get('X-Language', 'tr')
        print(f"DEBUG web_app.py: Dil parametresi: {language}")
        
        # Read-only işlem için read lock kullan (daha hızlı)
        def get_batteries_data():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_batteries_for_display(page, page_size, selected_arm, language)
        
        batteries_data = db_operation_with_retry(get_batteries_data)
        
        return jsonify({
            'success': True,
            'batteries': batteries_data['batteries'],
            'totalPages': batteries_data['totalPages'],
            'currentPage': batteries_data['currentPage']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/active-arms', methods=['GET'])
def get_active_arms():
    """Aktif kolları getir (armslavecount > 0)"""
    try:
        db_instance = get_db()
        with db_read_lock:
            active_arms = db_instance.get_active_arms()
        return jsonify({
            'success': True,
            'activeArms': active_arms
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/passive-balance', methods=['GET'])
def get_passive_balance():
    """Passive balance verilerini getir"""
    try:
        arm = request.args.get('arm')
        if arm:
            arm = int(arm)
        
        db_instance = get_db()
        with db_read_lock:
            balance_data = db_instance.get_passive_balance(arm)
        return jsonify({
            'success': True,
            'balanceData': balance_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/batteries/export', methods=['POST'])
def export_batteries():
    """Batarya verilerini CSV olarak export et"""
    try:
        db_instance = get_db()
        with db_read_lock:
            csv_content = db_instance.export_batteries_to_csv()
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=batteries_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/arm-logs/export', methods=['POST'])
def export_arm_logs():
    """Kol log verilerini CSV olarak export et"""
    try:
        data = request.get_json()
        filters = data.get('filters', {}) if data else {}
        
        db_instance = get_db()
        with db_read_lock:
            csv_content = db_instance.export_arm_logs_to_csv(filters)
        
        response = app.response_class(
            response=csv_content,
            status=200,
            mimetype='text/csv'
        )
        response.headers['Content-Disposition'] = 'attachment; filename=arm_logs_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    """İstatistik verilerini getir"""
    try:
        # Basit istatistikler
        stats = {
            'database_size': get_db().get_database_size() if hasattr(get_db, 'instance') else 0,
            'timestamp': int(time.time() * 1000)
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/batconfigs', methods=['POST'])
def save_batconfig():
    """Batarya konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        
        # Veri doğrulama
        required_fields = [
            'armValue', 'Vmin', 'Vmax', 'Vnom', 'Rintnom',
            'Tempmin_D', 'Tempmax_D', 'Tempmin_PN', 'Tempmaks_PN',
            'Socmin', 'Sohmin'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({
                    'success': False,
                    'message': f'Eksik alan: {field}'
                }), 400
        
        # Zaman damgası ekle
        data['time'] = int(time.time() * 1000)
        
        # Konfigürasyonu JSON dosyasına kaydet (main.py için)
        config_data = {
            'type': 'batconfig',
            'data': data,
            'timestamp': data['time']
        }
        
        try:
            # Konfigürasyonu dosyaya kaydet (main.py için)
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Batarya konfigürasyonu dosyaya kaydedildi: {data}")
            
            # Konfigürasyonu veritabanına da kaydet
            db_instance = get_db()
            with db_lock:
                db_instance.save_battery_config(
                    arm=data['armValue'],
                    vmin=data['Vmin'],
                    vmax=data['Vmax'],
                    vnom=data['Vnom'],
                    rintnom=data['Rintnom'],
                    tempmin_d=data['Tempmin_D'],
                    tempmax_d=data['Tempmax_D'],
                    tempmin_pn=data['Tempmin_PN'],
                    tempmaks_pn=data['Tempmaks_PN'],
                    socmin=data['Socmin'],
                    sohmin=data['Sohmin']
                )
            print(f"Batarya konfigürasyonu veritabanına kaydedildi: Kol {data['armValue']}")
            
        except Exception as e:
            print(f"Konfigürasyon kaydedilirken hata: {e}")
            return jsonify({
                'success': False,
                'message': 'Konfigürasyon kaydedilemedi'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Batarya konfigürasyonu başarıyla kaydedildi',
            'data': data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/armconfigs', methods=['POST'])
def save_armconfig():
    """Kol konfigürasyonunu kaydet"""
    try:
        data = request.get_json()
        
        # Veri doğrulama
        required_fields = [
            'armValue', 'akimKats', 'akimMax', 'nemMax', 'nemMin',
            'tempMax', 'tempMin'
        ]
        
        for field in required_fields:
            if field not in data or data[field] is None:
                return jsonify({
                    'success': False,
                    'message': f'Eksik alan: {field}'
                }), 400
        
        # Zaman damgası ekle
        data['time'] = int(time.time() * 1000)
        
        # Konfigürasyonu JSON dosyasına kaydet (main.py için)
        config_data = {
            'type': 'armconfig',
            'data': data,
            'timestamp': data['time']
        }
        
        try:
            # Konfigürasyonu dosyaya kaydet (main.py için)
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Kol konfigürasyonu dosyaya kaydedildi: {data}")
            
            # Konfigürasyonu veritabanına da kaydet
            db_instance = get_db()
            with db_lock:
                db_instance.save_arm_config(
                    arm=data['armValue'],
                    akim_kats=data['akimKats'],
                    akim_max=data['akimMax'],
                    nem_max=data['nemMax'],
                    nem_min=data['nemMin'],
                    temp_max=data['tempMax'],
                    temp_min=data['tempMin']
                )
            print(f"Kol konfigürasyonu veritabanına kaydedildi: Kol {data['armValue']}")
            
        except Exception as e:
            print(f"Konfigürasyon kaydedilirken hata: {e}")
            return jsonify({
                'success': False,
                'message': 'Konfigürasyon kaydedilemedi'
            }), 500
        
        return jsonify({
            'success': True,
            'message': 'Kol konfigürasyonu başarıyla kaydedildi',
            'data': data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/batconfigs', methods=['GET'])
def get_batconfigs():
    """Tüm batarya konfigürasyonlarını getir"""
    try:
        # Veritabanından konfigürasyonları oku
        db_instance = get_db()
        with db_read_lock:
            configs = db_instance.get_batconfigs()
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/armconfigs', methods=['GET'])
def get_armconfigs():
    """Tüm kol konfigürasyonlarını getir"""
    try:
        # Veritabanından konfigürasyonları oku
        db_instance = get_db()
        with db_read_lock:
            configs = db_instance.get_armconfigs()
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/alarms', methods=['GET'])
def get_alarms():
    """Sayfalanmış alarmları getir"""
    try:
        # Query parametrelerini al
        show_resolved = request.args.get('show_resolved', 'false').lower() == 'true'
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 50))
        
        # Veritabanından sayfalanmış alarmları oku
        def get_alarms_data():
            db_instance = get_db()
            with db_read_lock:
                return db_instance.get_paginated_alarms(
                    show_resolved=show_resolved,
                    page=page,
                    page_size=page_size
                )
        
        alarms_data = db_operation_with_retry(get_alarms_data)
        
        # Alarm verilerini işle
        processed_alarms = []
        for alarm in alarms_data['alarms']:
            processed_alarm = process_alarm_data(alarm)
            if processed_alarm:  # Sadece geçerli alarmları ekle
                processed_alarms.append(processed_alarm)
        
        return jsonify({
            'success': True,
            'alarms': processed_alarms,
            'totalCount': alarms_data['totalCount'],
            'totalPages': alarms_data['totalPages'],
            'currentPage': alarms_data['currentPage']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/summary', methods=['GET'])
def get_summary():
    """Özet sayfası için veri getir"""
    try:
        print(f"🔄 /api/summary endpoint'i çağrıldı - {datetime.now()}")
        
        # Veritabanından özet verileri oku
        start_time = time.time()
        db_instance = get_db()
        with db_read_lock:
            summary_data = db_instance.get_summary_data()
        end_time = time.time()
        
        print(f"⏱️ Veritabanı sorgu süresi: {end_time - start_time:.3f}s")
        print(f"📊 {len(summary_data)} kol verisi döndürüldü")
        
        return jsonify({
            'success': True,
            'summary': summary_data
        })
    except Exception as e:
        print(f"💥 /api/summary hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

# Mail Yönetimi API'leri
@app.route('/api/mail-recipients', methods=['GET'])
def get_mail_recipients():
    """Mail alıcılarını getir"""
    try:
        db_instance = get_db()
        with db_read_lock:
            recipients = db_instance.get_mail_recipients()
        
        return jsonify({
            'success': True,
            'recipients': recipients
        })
    except Exception as e:
        print(f"💥 /api/mail-recipients GET hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-recipients', methods=['POST'])
def add_mail_recipient():
    """Yeni mail alıcısı ekle"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        
        if not name or not email:
            return jsonify({
                'success': False,
                'message': 'Ad soyad ve email adresi gereklidir'
            }), 400
        
        db_instance = get_db()
        with db_lock:
            result = db_instance.add_mail_recipient(name, email)
        
        return jsonify(result)
    except Exception as e:
        print(f"💥 /api/mail-recipients POST hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-recipients', methods=['PUT'])
def update_mail_recipient():
    """Mail alıcısını güncelle"""
    try:
        data = request.get_json()
        recipient_id = data.get('id')
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        
        if not recipient_id or not name or not email:
            return jsonify({
                'success': False,
                'message': 'ID, ad soyad ve email adresi gereklidir'
            }), 400
        
        db_instance = get_db()
        with db_lock:
            result = db_instance.update_mail_recipient(recipient_id, name, email)
        
        return jsonify(result)
    except Exception as e:
        print(f"💥 /api/mail-recipients PUT hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/api/mail-recipients/<int:recipient_id>', methods=['DELETE'])
def delete_mail_recipient(recipient_id):
    """Mail alıcısını sil"""
    try:
        db_instance = get_db()
        with db_lock:
            result = db_instance.delete_mail_recipient(recipient_id)
        
        return jsonify(result)
    except Exception as e:
        print(f"💥 /api/mail-recipients DELETE hatası: {e}")
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

def process_alarm_data(alarm):
    """Alarm verisini işle ve açıklama oluştur"""
    try:
        arm = alarm[1]  # arm
        battery = alarm[2]  # battery (k değeri)
        error_msb = alarm[3]  # error_code_msb
        error_lsb = alarm[4]  # error_code_lsb
        timestamp = alarm[5]  # timestamp
        status = alarm[6]  # status
        resolved_at = alarm[7] if len(alarm) > 7 else None  # resolved_at
        
        # Batarya alarmı mı kol alarmı mı kontrol et
        if error_lsb == 9:  # Kol alarmı (Hatkon)
            description = get_arm_alarm_description(error_msb)
            if error_msb == 0:  # Düzeldi durumu
                battery_display = "Kol Alarmı"
                status = "Düzeldi"
            else:
                battery_display = "Kol Alarmı"
                status = "Devam Ediyor"
        else:  # Batarya alarmı (Batkon)
            description = get_battery_alarm_description(error_msb, error_lsb)
            if not description:  # Açıklama yoksa alarm yok
                return None
            # Batarya alarmlarında k değeri varsa göster, yoksa boş bırak
            if battery == 0:
                battery_display = ""
            else:
                battery_display = str(battery)
            status = "Devam Ediyor"
        
        return {
            'arm': arm,
            'battery': battery_display,
            'description': description,
            'status': status,
            'timestamp': timestamp,
            'resolved_at': resolved_at
        }
    except Exception as e:
        print(f"Alarm verisi işlenirken hata: {e}")
        return None

def get_battery_alarm_description(error_msb, error_lsb):
    """Batarya alarm açıklaması oluştur"""
    description_parts = []
    
    # MSB kontrolü
    if error_msb >= 1:
        if error_msb == 1:
            description_parts.append("Pozitif kutup başı alarmı")
        elif error_msb == 2:
            description_parts.append("Negatif kutup başı sıcaklık alarmı")
    
    # LSB kontrolü
    if error_lsb == 4:
        description_parts.append("Düşük batarya gerilim uyarısı")
    elif error_lsb == 8:
        description_parts.append("Düşük batarya gerilimi alarmı")
    elif error_lsb == 16:
        description_parts.append("Yüksek batarya gerilimi uyarısı")
    elif error_lsb == 32:
        return "Yüksek batarya gerilimi alarmı"
    elif error_lsb == 64:
        description_parts.append("Modül sıcaklık alarmı")
    
    return " + ".join(description_parts) if description_parts else None

def get_arm_alarm_description(error_msb):
    """Kol alarm açıklaması oluştur"""
    if error_msb == 0:
        return "Alarm Düzeldi"  # Düzeldi durumunda açıklama
    elif error_msb == 2:
        return "Yüksek akım alarmı"
    elif error_msb == 4:
        return "Yüksek nem alarmı"
    elif error_msb == 8:
        return "Yüksek ortam sıcaklığı alarmı"
    elif error_msb == 16:
        return "Yüksek kol sıcaklığı alarmı"
    else:
        return None

@app.route('/api/send-config-to-device', methods=['POST'])
def send_config_to_device():
    """Konfigürasyonu cihaza gönder"""
    try:
        data = request.get_json()
        command = data.get('command', '5 5 0x7A')
        
        # Konfigürasyonu JSON dosyasına kaydet (main.py için)
        config_data = {
            'type': 'send_to_device',
            'command': command,
            'timestamp': int(time.time() * 1000)
        }
        
        try:
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Konfigürasyon cihaza gönderilecek: {command}")
        except Exception as e:
            print(f"Konfigürasyon dosyaya kaydedilirken hata: {e}")
            return jsonify({
                'success': False,
                'message': 'Konfigürasyon kaydedilemedi'
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'Konfigürasyon cihaza gönderildi: {command}',
            'command': command
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    print("Flask web uygulaması başlatılıyor...")
    with db_read_lock:
        print(f"Veritabanı boyutu: {get_db().get_database_size():.2f} MB")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
