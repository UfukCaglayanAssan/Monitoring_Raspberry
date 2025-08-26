# interface/web_app.py
from flask import Flask, render_template, jsonify, request
from database import BatteryDatabase
import time

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
        
        return jsonify(logs_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/logs/export', methods=['POST'])
def export_logs():
    """Log verilerini CSV olarak dışa aktar"""
    data = request.get_json()
    filters = data.get('filters', {})
    
    try:
        # CSV formatında veri hazırla
        csv_data = db.export_logs_to_csv(filters)
        
        from flask import Response
        response = Response(csv_data, mimetype='text/csv')
        response.headers['Content-Disposition'] = f'attachment; filename=logs_{time.strftime("%Y%m%d")}.csv'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats')
def get_stats():
    stats = db.get_stats()
    return jsonify(stats)

if __name__ == '__main__':
    print("Flask web uygulaması başlatılıyor...")
    print(f"Veritabanı boyutu: {db.get_database_size():.2f} MB")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)