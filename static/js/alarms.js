// Alarms Sayfası JavaScript
class AlarmsPage {
    constructor() {
        this.alarms = [];
        this.showResolved = false; // Varsayılan olarak sadece aktif alarmları göster
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadAlarms();
        this.startAutoRefresh();
    }

    bindEvents() {
        // Alarm geçmişi toggle butonu
        const toggleBtn = document.getElementById('toggleAlarmHistory');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => {
                this.toggleAlarmHistory();
            });
        }
    }

    async loadAlarms() {
        try {
            this.showLoading();
            
            const response = await fetch(`/api/alarms?show_resolved=${this.showResolved}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            
            if (data.success) {
                this.alarms = data.alarms || [];
                this.renderAlarms();
            } else {
                console.error('Alarm verileri yüklenirken hata:', data.message);
                this.showNoData();
            }
        } catch (error) {
            console.error('Alarm verileri yüklenirken hata:', error);
            this.showNoData();
        } finally {
            this.hideLoading();
        }
    }

    renderAlarms() {
        const tbody = document.getElementById('alarmsTableBody');
        if (!tbody) return;

        if (this.alarms.length === 0) {
            this.showNoData();
            return;
        }

        tbody.innerHTML = '';
        
        this.alarms.forEach(alarm => {
            const row = this.createAlarmRow(alarm);
            tbody.appendChild(row);
        });

        // Tabloyu göster
        const table = document.getElementById('alarmsTable');
        if (table) table.style.display = 'table';
    }

    createAlarmRow(alarm) {
        const row = document.createElement('tr');
        
        // Zaman
        const timeCell = document.createElement('td');
        timeCell.textContent = this.formatTimestamp(alarm.timestamp);
        row.appendChild(timeCell);
        
        // Kol
        const armCell = document.createElement('td');
        armCell.textContent = alarm.arm;
        row.appendChild(armCell);
        
        // Batarya
        const batteryCell = document.createElement('td');
        batteryCell.textContent = alarm.battery || 'Kol Alarmı';
        row.appendChild(batteryCell);
        
        // Açıklama
        const descriptionCell = document.createElement('td');
        descriptionCell.textContent = alarm.description;
        row.appendChild(descriptionCell);
        
        // Durum
        const statusCell = document.createElement('td');
        const statusBadge = document.createElement('span');
        let statusText;
        if (alarm.status === 'resolved') {
            statusText = 'Düzeldi';
        } else if (alarm.status === 'Düzeldi') {
            statusText = 'Düzeldi';
        } else {
            statusText = 'Aktif';
        }
        statusBadge.className = `status-badge ${this.getStatusClass(alarm.status)}`;
        statusBadge.textContent = statusText;
        statusCell.appendChild(statusBadge);
        row.appendChild(statusCell);
        
        // Çözüm Zamanı
        const resolvedCell = document.createElement('td');
        if (alarm.status === 'resolved' && alarm.resolved_at) {
            resolvedCell.textContent = this.formatTimestamp(alarm.resolved_at);
        } else {
            resolvedCell.textContent = '-';
        }
        row.appendChild(resolvedCell);
        
        return row;
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        return date.toLocaleString('tr-TR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
    }

    getStatusClass(status) {
        switch (status) {
            case 'resolved':
            case 'Düzeldi':
                return 'status-success';
            case 'active':
            case 'Devam Ediyor':
                return 'status-error';
            default:
                return 'status-default';
        }
    }

    showLoading() {
        const loading = document.getElementById('loadingSpinner');
        const table = document.getElementById('alarmsTable');
        const noData = document.getElementById('noDataMessage');
        
        if (loading) loading.style.display = 'flex';
        if (table) table.style.display = 'none';
        if (noData) noData.style.display = 'none';
    }

    hideLoading() {
        const loading = document.getElementById('loadingSpinner');
        if (loading) loading.style.display = 'none';
    }

    showNoData() {
        const noData = document.getElementById('noDataMessage');
        const table = document.getElementById('alarmsTable');
        const loading = document.getElementById('loadingSpinner');
        
        if (noData) noData.style.display = 'block';
        if (table) table.style.display = 'none';
        if (loading) loading.style.display = 'none';
    }

    startAutoRefresh() {
        setInterval(() => {
            if (this.isPageActive()) {
                this.loadAlarms();
            }
        }, 30000); // 30 saniyede bir yenile
    }

    isPageActive() {
        return document.querySelector('.alarms-page') !== null;
    }
}

// Sayfa yüklendiğinde başlat
function initAlarmsPage() {
    if (document.querySelector('.alarms-page')) {
        new AlarmsPage();
    }
}

// DOMContentLoaded event listener
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAlarmsPage);
} else {
    initAlarmsPage();
}



