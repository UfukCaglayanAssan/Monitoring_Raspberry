// Batteries Page JavaScript
class BatteriesPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 30;
        this.totalPages = 1;
        this.batteriesData = [];
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadBatteries();
        this.startAutoRefresh();
    }
    
    bindEvents() {
        // Refresh button
        document.getElementById('refreshBatteries').addEventListener('click', () => {
            this.loadBatteries();
        });
        
        // Export button
        document.getElementById('exportBatteries').addEventListener('click', () => {
            this.exportBatteries();
        });
        
        // Pagination
        document.getElementById('prevPage').addEventListener('click', () => {
            this.previousPage();
        });
        
        document.getElementById('nextPage').addEventListener('click', () => {
            this.nextPage();
        });
    }
    
    async loadBatteries() {
        try {
            this.showLoading(true);
            
            // API endpoint'den batarya verilerini çek
            const response = await fetch('/api/batteries', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    page: this.currentPage,
                    pageSize: this.pageSize
                })
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.batteriesData = data.batteries;
                this.totalPages = data.totalPages;
                this.currentPage = data.currentPage;
                this.renderBatteries();
                this.updatePagination();
            } else {
                throw new Error(data.message || 'Veri yüklenemedi');
            }
            
        } catch (error) {
            console.error('Batarya verileri yüklenirken hata:', error);
            this.showError('Batarya verileri yüklenirken hata oluştu: ' + error.message);
        } finally {
            this.showLoading(false);
        }
    }
    
    renderBatteries() {
        console.log('renderBatteries çağrıldı, veri sayısı:', this.batteriesData.length);
        
        const grid = document.getElementById('batteriesGrid');
        if (!grid) {
            console.error('batteriesGrid bulunamadı!');
            return;
        }
        
        grid.innerHTML = '';
        
        if (this.batteriesData.length === 0) {
            console.log('Veri yok, showNoData çağrılıyor');
            this.showNoData();
            return;
        }
        
        console.log('Kartlar oluşturuluyor...');
        // Her batarya için kart oluştur
        this.batteriesData.forEach((battery, index) => {
            console.log(`Kart ${index + 1} oluşturuluyor:`, battery);
            const card = this.createBatteryCard(battery);
            grid.appendChild(card);
        });
        
        console.log('Tüm kartlar eklendi');
    }
    
    createBatteryCard(battery) {
        console.log('createBatteryCard çağrıldı:', battery);
        
        const template = document.getElementById('batteryCardTemplate');
        if (!template) {
            console.error('batteryCardTemplate bulunamadı!');
            return null;
        }
        
        const card = template.content.cloneNode(true);
        
        // Kart verilerini doldur
        const cardElement = card.querySelector('.battery-card');
        if (!cardElement) {
            console.error('battery-card elementi bulunamadı!');
            return null;
        }
        
        cardElement.dataset.arm = battery.arm;
        cardElement.dataset.battery = battery.batteryAddress;
        cardElement.dataset.timestamp = battery.timestamp;
        
        // Header bilgileri
        cardElement.querySelector('.arm-value').textContent = battery.arm;
        cardElement.querySelector('.battery-value').textContent = battery.batteryAddress;
        
        // Veri değerleri
        cardElement.querySelector('.voltage-value').textContent = this.formatValue(battery.voltage, 'V');
        cardElement.querySelector('.temperature-value').textContent = this.formatValue(battery.temperature, '°C');
        cardElement.querySelector('.health-value').textContent = this.formatValue(battery.health, '%');
        cardElement.querySelector('.charge-value').textContent = this.formatValue(battery.charge, '%');
        
        // Timestamp
        const timestamp = new Date(battery.timestamp);
        cardElement.querySelector('.timestamp-value').textContent = timestamp.toLocaleString('tr-TR');
        
        // Status indicator
        const statusDot = cardElement.querySelector('.status-dot');
        const statusText = cardElement.querySelector('.status-text');
        
        if (battery.isActive) {
            statusDot.style.background = '#4CAF50';
            statusText.textContent = 'Aktif';
            statusText.style.color = '#4CAF50';
        } else {
            statusDot.style.background = '#FF6B6B';
            statusText.textContent = 'Pasif';
            statusText.style.color = '#FF6B6B';
        }
        
        return cardElement;
    }
    
    formatValue(value, unit) {
        if (value === null || value === undefined) {
            return '--';
        }
        
        if (typeof value === 'number') {
            return value.toFixed(3) + unit;
        }
        
        return value + unit;
    }
    

    
    previousPage() {
        if (this.currentPage > 1) {
            this.currentPage--;
            this.loadBatteries();
        }
    }
    
    nextPage() {
        if (this.currentPage < this.totalPages) {
            this.currentPage++;
            this.loadBatteries();
        }
    }
    
    updatePagination() {
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const currentPageSpan = document.getElementById('currentPage');
        const totalPagesSpan = document.getElementById('totalPages');
        
        prevBtn.disabled = this.currentPage <= 1;
        nextBtn.disabled = this.currentPage >= this.totalPages;
        
        currentPageSpan.textContent = this.currentPage;
        totalPagesSpan.textContent = this.totalPages;
    }
    
    showLoading(show) {
        const spinner = document.getElementById('loadingSpinner');
        const grid = document.getElementById('batteriesGrid');
        const noData = document.getElementById('noDataMessage');
        
        if (show) {
            spinner.style.display = 'flex';
            grid.style.display = 'none';
            noData.style.display = 'none';
        } else {
            spinner.style.display = 'none';
            grid.style.display = 'grid';
        }
    }
    
    showNoData() {
        const noData = document.getElementById('noDataMessage');
        const grid = document.getElementById('batteriesGrid');
        
        noData.style.display = 'block';
        grid.style.display = 'none';
    }
    
    showError(message) {
        // Hata mesajını göster
        const errorDiv = document.createElement('div');
        errorDiv.className = 'error-message';
        errorDiv.innerHTML = `
            <div class="error-content">
                <i class="fas fa-exclamation-triangle"></i>
                <h3>Hata</h3>
                <p>${message}</p>
                <button onclick="this.parentElement.parentElement.remove()">Kapat</button>
            </div>
        `;
        
        document.body.appendChild(errorDiv);
        
        // 5 saniye sonra otomatik kaldır
        setTimeout(() => {
            if (errorDiv.parentElement) {
                errorDiv.remove();
            }
        }, 5000);
    }
    
    async exportBatteries() {
        try {
            const response = await fetch('/api/batteries/export', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({})
            });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `batteries_export_${new Date().toISOString().split('T')[0]}.csv`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
            
        } catch (error) {
            console.error('Export hatası:', error);
            this.showError('Export sırasında hata oluştu: ' + error.message);
        }
    }
    
    startAutoRefresh() {
        // Her 30 saniyede bir otomatik yenile
        setInterval(() => {
            this.loadBatteries();
        }, 30000);
    }
}

// Sayfa yüklendiğinde başlat
function initBatteriesPage() {
    console.log('Batteries sayfası başlatılıyor...');
    try {
        new BatteriesPage();
        console.log('Batteries sayfası başarıyla başlatıldı');
    } catch (error) {
        console.error('Batteries sayfası başlatılırken hata:', error);
    }
}

// DOMContentLoaded event'i için
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initBatteriesPage);
} else {
    // DOM zaten yüklenmiş
    initBatteriesPage();
}

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
});



