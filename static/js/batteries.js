// Batteries Page JavaScript
class BatteriesPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 30;
        this.totalPages = 1;
        this.batteriesData = [];
        this.filters = {
            arm: '',
            battery: '',
            dataType: ''
        };
        
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
        
        // Filter buttons
        document.getElementById('applyFilters').addEventListener('click', () => {
            this.applyFilters();
        });
        
        document.getElementById('clearFilters').addEventListener('click', () => {
            this.clearFilters();
        });
        
        // Pagination
        document.getElementById('prevPage').addEventListener('click', () => {
            this.previousPage();
        });
        
        document.getElementById('nextPage').addEventListener('click', () => {
            this.nextPage();
        });
        
        // Filter inputs
        document.getElementById('armFilter').addEventListener('change', (e) => {
            this.filters.arm = e.target.value;
        });
        
        document.getElementById('batteryFilter').addEventListener('input', (e) => {
            this.filters.battery = e.target.value;
        });
        
        document.getElementById('dataTypeFilter').addEventListener('change', (e) => {
            this.filters.dataType = e.target.value;
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
                    pageSize: this.pageSize,
                    filters: this.filters
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
        const grid = document.getElementById('batteriesGrid');
        grid.innerHTML = '';
        
        if (this.batteriesData.length === 0) {
            this.showNoData();
            return;
        }
        
        // Her batarya için kart oluştur
        this.batteriesData.forEach(battery => {
            const card = this.createBatteryCard(battery);
            grid.appendChild(card);
        });
    }
    
    createBatteryCard(battery) {
        const template = document.getElementById('batteryCardTemplate');
        const card = template.content.cloneNode(true);
        
        // Kart verilerini doldur
        const cardElement = card.querySelector('.battery-card');
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
    
    applyFilters() {
        this.currentPage = 1;
        this.loadBatteries();
    }
    
    clearFilters() {
        document.getElementById('armFilter').value = '';
        document.getElementById('batteryFilter').value = '';
        document.getElementById('dataTypeFilter').value = '';
        
        this.filters = {
            arm: '',
            battery: '',
            dataType: ''
        };
        
        this.currentPage = 1;
        this.loadBatteries();
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
                body: JSON.stringify({
                    filters: this.filters
                })
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
document.addEventListener('DOMContentLoaded', () => {
    new BatteriesPage();
});

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
});

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
});



