// Batteries Page JavaScript
class BatteriesPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 30;
        this.totalPages = 1;
        this.batteriesData = [];
        this.selectedArm = 3; // 1-4 = Belirli kol (varsayılan: Kol 3)
        
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadBatteries();
        this.startAutoRefresh();
    }

    bindEvents() {
        // Kol seçimi event listener'ları
        const armButtons = document.querySelectorAll('.arm-btn');
        armButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                const arm = parseInt(e.target.closest('.arm-btn').dataset.arm);
                this.selectArm(arm);
            });
        });
        
        // Dil değişikliği dinleyicisi - global olarak ekle
        window.addEventListener('languageChanged', (e) => {
            console.log('=== DIL DEGISIKLIGI EVENT\'I ALINDI (GLOBAL) ===');
            console.log('Event detail:', e.detail);
            console.log('Dil:', e.detail.language);
            console.log('BatteriesPage instance:', this);
            
            if (this && typeof this.onLanguageChanged === 'function') {
                console.log('onLanguageChanged cagriliyor...');
                this.onLanguageChanged(e.detail.language);
                console.log('onLanguageChanged cagrildi');
            } else {
                console.log('BatteriesPage instance bulunamadı veya onLanguageChanged fonksiyonu yok!');
            }
        });
        console.log('Global language listener eklendi');


    }
    
    selectArm(arm) {
        // Aktif buton stilini güncelle
        document.querySelectorAll('.arm-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-arm="${arm}"]`).classList.add('active');
        
        // Seçilen kol'u güncelle
        this.selectedArm = arm;
        
        // Bataryaları yeniden yükle
        this.loadBatteries();
    }
    
    async loadBatteries() {
        // Sayfa kontrolü yap
        if (!this.isPageActive()) {
            return;
        }
        
        try {
            this.showLoading(true);
            
            // Mevcut dili al
            const currentLanguage = localStorage.getItem('language') || 'tr';
            console.log('loadBatteries - Kullanılan dil:', currentLanguage);
            
            // API endpoint'den batarya verilerini çek
            const response = await fetch('/api/batteries', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Language': currentLanguage
                },
                body: JSON.stringify({
                    page: this.currentPage,
                    pageSize: this.pageSize,
                    selectedArm: this.selectedArm
                })
            })
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.batteriesData = data.batteries;
                this.totalPages = data.totalPages;
                this.currentPage = data.currentPage;
                this.renderBatteries();
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
        // Sayfa kontrolü yap
        if (!this.isPageActive()) {
            return;
        }
        
        const grid = document.getElementById('batteriesGrid');
        if (!grid) {
            console.error('batteriesGrid bulunamadı!');
            return;
        }
        
        grid.innerHTML = '';
        
        if (this.batteriesData.length === 0) {
            this.showNoData();
            return;
        }
        
        // Her batarya için kart oluştur
        this.batteriesData.forEach((battery, index) => {
            const card = this.createBatteryCard(battery);
            if (card) {
                grid.appendChild(card);
            }
        });
    }
    
    createBatteryCard(battery) {
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
        
        // Batarya adresi (2 eksiği olarak göster)
        const batteryValue = cardElement.querySelector('.battery-value');
        if (batteryValue) batteryValue.textContent = battery.batteryAddress - 2;
        
        // Timestamp
        const timestampValue = cardElement.querySelector('.timestamp-value');
        if (timestampValue) {
            const timestamp = new Date(battery.timestamp);
            timestampValue.textContent = timestamp.toLocaleString('tr-TR');
        }
        
        // Veri değerleri (arka yüzde)
        const voltageValue = cardElement.querySelector('.voltage-value');
        const temperatureValue = cardElement.querySelector('.temperature-value');
        const healthValue = cardElement.querySelector('.health-value');
        const chargeValue = cardElement.querySelector('.charge-value');
        
        if (voltageValue) voltageValue.textContent = this.formatValue(battery.voltage, '');
        if (temperatureValue) temperatureValue.textContent = this.formatValue(battery.temperature, '');
        if (healthValue) healthValue.textContent = this.formatValue(battery.health, '');
        if (chargeValue) chargeValue.textContent = this.formatValue(battery.charge, '');
        
        // Debug: Çeviri verilerini yazdır
        console.log('Battery data:', battery);
        console.log('Voltage name:', battery.voltage_name);
        console.log('Temperature name:', battery.temperature_name);
        console.log('Health name:', battery.health_name);
        console.log('Charge name:', battery.charge_name);
        
        // Çeviri attribute'larını ekle
        this.addTranslationAttributes(cardElement);
        
        return cardElement;
    }
    
    onLanguageChanged(language) {
        // Dil değiştiğinde bataryaları yeniden yükle
        console.log('onLanguageChanged çağrıldı, dil:', language);
        console.log('updateCardTexts çağrılıyor...');
        this.updateCardTexts(language);
        console.log('loadBatteries çağrılıyor...');
      
    }
    
    updateCardTexts(language) {
        // Debug: Fonksiyon çağrıldı mı?
        console.log('updateCardTexts çağrıldı, dil:', language);
        
        // Mevcut kartlardaki metinleri güncelle
        const cards = document.querySelectorAll('.battery-card');
        console.log('Bulunan kart sayısı:', cards.length);
        
        cards.forEach((card, index) => {
            console.log(`Kart ${index + 1} güncelleniyor...`);
            
            // Başlık
            const title = card.querySelector('.card-title');
            if (title) {
                const oldText = title.textContent;
                const newText = title.getAttribute(`data-${language}`) || title.textContent;
                console.log(`Kart ${index + 1} başlık güncelleniyor: "${oldText}" -> "${newText}"`);
                
                // DOM'u güncelle
                title.textContent = newText;
                
                // Güncelleme sonrası kontrol
                const updatedText = title.textContent;
                console.log(`Kart ${index + 1} başlık güncellendi: "${updatedText}"`);
                
                // DOM'da gerçekten güncellendi mi kontrol et
                if (updatedText === newText) {
                    console.log(`Kart ${index + 1} başlık DOM'da başarıyla güncellendi`);
                } else {
                    console.log(`Kart ${index + 1} başlık DOM'da güncellenemedi!`);
                }
            } else {
                console.log(`Kart ${index + 1} başlık bulunamadı!`);
            }
            
            // Adres etiketi
            const addressLabel = card.querySelector('.battery-address span');
            if (addressLabel) {
                const labelText = addressLabel.getAttribute(`data-${language}`) || addressLabel.textContent;
                const batteryValue = addressLabel.querySelector('.battery-value');
                if (batteryValue) {
                    addressLabel.innerHTML = labelText + batteryValue.outerHTML;
                } else {
                    addressLabel.textContent = labelText;
                }
            }
            
            // Son güncelleme etiketi
            const updateLabel = card.querySelector('.last-update span');
            if (updateLabel) {
                updateLabel.textContent = updateLabel.getAttribute(`data-${language}`) || updateLabel.textContent;
            }
            
            // Arka yüz başlığı
            const backTitle = card.querySelector('.back-title');
            if (backTitle) {
                backTitle.textContent = backTitle.getAttribute(`data-${language}`) || backTitle.textContent;
            }
            
            // Veri etiketleri
            const voltageLabel = card.querySelector('.voltage-label');
            if (voltageLabel) {
                voltageLabel.textContent = voltageLabel.getAttribute(`data-${language}`) || voltageLabel.textContent;
            }
            
            const temperatureLabel = card.querySelector('.temperature-label');
            if (temperatureLabel) {
                temperatureLabel.textContent = temperatureLabel.getAttribute(`data-${language}`) || temperatureLabel.textContent;
            }
            
            const healthLabel = card.querySelector('.health-label');
            if (healthLabel) {
                healthLabel.textContent = healthLabel.getAttribute(`data-${language}`) || healthLabel.textContent;
            }
            
            const chargeLabel = card.querySelector('.charge-label');
            if (chargeLabel) {
                chargeLabel.textContent = chargeLabel.getAttribute(`data-${language}`) || chargeLabel.textContent;
            }
        });
    }
    
    addTranslationAttributes(cardElement) {
        // Template'den oluşturulan kartlara çeviri attribute'larını ekle
        const title = cardElement.querySelector('.card-title');
        if (title) {
            title.setAttribute('data-tr', 'Batarya Ünitesi');
            title.setAttribute('data-en', 'Battery Unit');
        }
        
        const addressLabel = cardElement.querySelector('.battery-address span');
        if (addressLabel) {
            addressLabel.setAttribute('data-tr', 'Adres: ');
            addressLabel.setAttribute('data-en', 'Address: ');
        }
        
        const updateLabel = cardElement.querySelector('.last-update span');
        if (updateLabel) {
            updateLabel.setAttribute('data-tr', 'Son güncelleme:');
            updateLabel.setAttribute('data-en', 'Last update:');
        }
        
        const backTitle = cardElement.querySelector('.back-title');
        if (backTitle) {
            backTitle.setAttribute('data-tr', 'Batarya Detayları');
            backTitle.setAttribute('data-en', 'Battery Details');
        }
        
        const voltageLabel = cardElement.querySelector('.voltage-label');
        if (voltageLabel) {
            voltageLabel.setAttribute('data-tr', 'Gerilim:');
            voltageLabel.setAttribute('data-en', 'Voltage:');
        }
        
        const temperatureLabel = cardElement.querySelector('.temperature-label');
        if (temperatureLabel) {
            temperatureLabel.setAttribute('data-tr', 'Sıcaklık:');
            temperatureLabel.setAttribute('data-en', 'Temperature:');
        }
        
        const healthLabel = cardElement.querySelector('.health-label');
        if (healthLabel) {
            healthLabel.setAttribute('data-tr', 'Sağlık:');
            healthLabel.setAttribute('data-en', 'Health:');
        }
        
        const chargeLabel = cardElement.querySelector('.charge-label');
        if (chargeLabel) {
            chargeLabel.setAttribute('data-tr', 'Şarj:');
            chargeLabel.setAttribute('data-en', 'Charge:');
        }
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
    

    

    

    
    showLoading(show) {
        // Sayfa kontrolü yap
        if (!this.isPageActive()) {
            return;
        }
        
        const spinner = document.getElementById('loadingSpinner');
        const grid = document.getElementById('batteriesGrid');
        const noData = document.getElementById('noDataMessage');
        
        if (!spinner || !grid || !noData) {
            return;
        }
        
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
        // Sayfa kontrolü yap
        if (!this.isPageActive()) {
            return;
        }
        
        const noData = document.getElementById('noDataMessage');
        const grid = document.getElementById('batteriesGrid');
        
        if (!noData || !grid) {
            return;
        }
        
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
    

    
    isPageActive() {
        // Batteries sayfasında olup olmadığımızı kontrol et
        const batteriesPage = document.querySelector('.batteries-page');
        return batteriesPage && batteriesPage.style.display !== 'none';
    }
    
    startAutoRefresh() {
        // Her 30 saniyede bir otomatik yenile
        setInterval(() => {
            // Sadece sayfa aktifse yenile
            if (this.isPageActive()) {
                console.log('Otomatik yenileme çalışıyor...');
                // Mevcut dili al ve otomatik güncellemede de kullan
                const currentLanguage = localStorage.getItem('language') || 'tr';
                console.log('Otomatik güncelleme dili:', currentLanguage);
                this.loadBatteries();
                
            }
        }, 30000);
    }
}

// Sayfa yüklendiğinde başlat
function initBatteriesPage() {
    console.log('Batteries sayfası başlatılıyor...');
    try {
window.batteriesPage = new BatteriesPage();
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



