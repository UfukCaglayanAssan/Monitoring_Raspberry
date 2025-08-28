# interface/web_app.py
from flask import Flask, render_template, jsonify, request
from database import BatteryDatabase
import time
import json

app = Flask(__name__)
db = BatteryDatabase()

@app.route('/')
def index():
    # Ana sayfa olarak logs sayfasını göster
    return render_template('layout.html')

@app.route('/page/<page_name>')
def get_page(page_name):
    """Sayfa içeriğini döndür"""
    if page_name == 'logs':
        return render_template('pages/logs.html')
    elif page_name == 'summary':
        return render_template('pages/summary.html')
    elif page_name == 'alarms':
        return render_template('pages/alarms.html')
    elif page_name == 'batteries':
        return render_template('pages/batteries.html')
    elif page_name == 'configuration':
        return render_template('pages/configuration.html')
    elif page_name == 'data-retrieval':
        return render_template('pages/data-retrieval.html')
    elif page_name == 'profile':
        return render_template('pages/profile.html')
    else:
        return render_template('pages/404.html')

@app.route('/api/data_types')
def get_data_types():
    language = request.args.get('lang', 'tr')  # Varsayılan Türkçe
    data_types = db.get_data_types_by_language(language)
    return jsonify(data_types)

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
    
    data = db.get_recent_data_with_translations(
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
    
    data = db.get_data_by_date_range_with_translations(
        start_date, end_date, arm, dtype, language
    )
    return jsonify(data)

@app.route('/api/logs', methods=['POST'])
def get_logs():
    """Log verilerini getir"""
    data = request.get_json()
    page = data.get('page', 1)
    page_size = data.get('pageSize', 50)
    filters = data.get('filters', {})
    
    try:
        # Veritabanından log verilerini al
        logs_data = db.get_logs_with_filters(
            page=page,
            page_size=page_size,
            filters=filters
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
        
        csv_content = db.export_logs_to_csv(filters)
        
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
        
        batteries_data = db.get_batteries_for_display(page, page_size)
        
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

@app.route('/api/batteries/export', methods=['POST'])
def export_batteries():
    """Batarya verilerini CSV olarak export et"""
    try:
        csv_content = db.export_batteries_to_csv()
        
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

@app.route('/api/stats')
def get_stats():
    """İstatistik verilerini getir"""
    try:
        # Basit istatistikler
        stats = {
            'database_size': db.get_database_size(),
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
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Batarya konfigürasyonu dosyaya kaydedildi: {data}")
        except Exception as e:
            print(f"Konfigürasyon dosyaya kaydedilirken hata: {e}")
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
            with open('pending_config.json', 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            print(f"Kol konfigürasyonu dosyaya kaydedildi: {data}")
        except Exception as e:
            print(f"Konfigürasyon dosyaya kaydedilirken hata: {e}")
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
        configs = db.get_batconfigs()
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
        configs = db.get_armconfigs()
        return jsonify({
            'success': True,
            'data': configs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    print("Flask web uygulaması başlatılıyor...")
    print(f"Veritabanı boyutu: {db.get_database_size():.2f} MB")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
