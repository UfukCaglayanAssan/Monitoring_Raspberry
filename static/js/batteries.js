// Batteries Page JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.BatteriesPage === 'undefined') {
    window.BatteriesPage = class BatteriesPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 30;
        this.totalPages = 1;
        this.batteriesData = [];
        this.selectedArm = parseInt(localStorage.getItem('selectedArm')) || 3; // localStorage'dan al, yoksa varsayılan: Kol 3
        
        this.init();
    }

    init() {
        const timestamp = new Date().toISOString();
        console.log(`🔧 [${timestamp}] BatteriesPage init() başladı`);
        
        this.bindEvents();
        console.log(`🔗 [${timestamp}] Event listener'lar bağlandı`);
        
        this.loadActiveArms(); // Önce aktif kolları yükle
        console.log(`🔄 [${timestamp}] Aktif kollar yükleniyor`);
        
        this.loadBatteries();
        console.log(`🔋 [${timestamp}] Batarya verileri yükleniyor`);
        
        this.startAutoRefresh();
        console.log(`⏰ [${timestamp}] Auto refresh başlatıldı`);
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

    async loadActiveArms() {
        // Aktif kolları yükle ve butonları güncelle
        console.log('🔍 Aktif kollar yükleniyor...');
        try {
            const response = await fetch('/api/active-arms', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                console.log('📊 API yanıtı:', data);
                
                if (data.success) {
                    console.log('✅ Aktif kollar verisi alındı:', data.activeArms);
                    this.updateArmButtons(data.activeArms);
                } else {
                    console.error('❌ API başarısız:', data.message);
                }
            } else {
                console.error('❌ HTTP hatası:', response.status);
            }
        } catch (error) {
            console.error('❌ Aktif kollar yüklenirken hata:', error);
        }
    }

    updateArmButtons(activeArms) {
        // Kol butonlarını güncelle - tüm kolları göster, sadece aktif olanları enable et
        console.log('🔧 updateArmButtons çağrıldı');
        console.log('📋 Gelen aktif kollar:', activeArms);
        
        const armButtons = document.querySelectorAll('.arm-btn');
        console.log('🔘 Bulunan kol butonları:', armButtons.length);
        
        // Sadece bataryası olan kolları filtrele ve sırala
        const armsWithBatteries = activeArms.filter(arm => arm.slave_count > 0);
        const activeArmNumbers = armsWithBatteries.map(arm => arm.arm).sort((a, b) => a - b);
        
        console.log('📊 Bataryası olan kollar (sıralı):', activeArmNumbers);
        console.log('📊 Tüm kollar:', activeArms.map(arm => `Kol ${arm.arm}: ${arm.slave_count} batarya`));
        
        // Her kol için detaylı bilgi
        activeArms.forEach(arm => {
            console.log(`🔋 Kol ${arm.arm}: ${arm.slave_count} batarya`);
        });
        
        // Tüm butonları göster ve durumlarını güncelle
        console.log('🔄 Butonlar güncelleniyor...');
        armButtons.forEach((button, index) => {
            const armNumber = parseInt(button.getAttribute('data-arm'));
            button.style.display = 'block';
            
            console.log(`🔘 Buton ${index + 1}: Kol ${armNumber} işleniyor...`);
            
            if (activeArmNumbers.includes(armNumber)) {
                // Aktif kol - enable et
                const batteryCount = activeArms.find(arm => arm.arm === armNumber).slave_count;
                button.disabled = false;
                button.classList.remove('disabled');
                
                const batteryCountElement = button.querySelector('.battery-count');
                if (batteryCountElement) {
                    batteryCountElement.textContent = `${batteryCount} Batarya`;
                }
                
                console.log(`✅ Kol ${armNumber}: ${batteryCount} batarya - ENABLED`);
            } else {
                // Pasif kol - disable et
                button.disabled = true;
                button.classList.add('disabled');
                
                const batteryCountElement = button.querySelector('.battery-count');
                if (batteryCountElement) {
                    batteryCountElement.textContent = '0 Batarya';
                }
                
                console.log(`❌ Kol ${armNumber}: 0 batarya - DISABLED`);
            }
        });
        
        // İlk aktif kolu seç (sıralı olarak)
        console.log('🎯 Kol seçimi yapılıyor...');
        if (activeArmNumbers.length > 0) {
            const firstActiveArm = activeArmNumbers[0];
            console.log(`🏆 İlk aktif kol seçiliyor: Kol ${firstActiveArm}`);
            console.log(`📋 Seçim sırası: ${activeArmNumbers.join(', ')}`);
            this.selectArm(firstActiveArm);
        } else {
            console.log('⚠️ Hiç aktif kol bulunamadı!');
        }
    }
    
    selectArm(arm) {
        // Sadece aktif kollar seçilebilir
        const button = document.querySelector(`[data-arm="${arm}"]`);
        if (!button) {
            console.log(`Kol ${arm} butonu bulunamadı`);
            return;
        }
        
        if (button.disabled) {
            console.log(`Kol ${arm} seçilemez - batarya yok`);
            return;
        }
        
        console.log(`Kol ${arm} seçiliyor...`);
        
        // Aktif buton stilini güncelle
        document.querySelectorAll('.arm-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        button.classList.add('active');
        
        // Seçilen kol'u güncelle
        this.selectedArm = arm;
        localStorage.setItem('selectedArm', arm); // localStorage'a kaydet
        
        console.log(`Kol ${arm} seçildi, bataryalar yükleniyor...`);
        
        // Bataryaları yeniden yükle
        this.loadBatteries();
    }
    
    async loadBatteries() {
        const timestamp = new Date().toISOString();
        console.log(`🔋 [${timestamp}] loadBatteries() başladı`);
        
        // Sayfa kontrolü yap
        if (!this.isPageActive()) {
            console.log(`⚠️ [${timestamp}] Sayfa aktif değil, loadBatteries iptal edildi`);
            return;
        }
        
        try {
            console.log(`⏳ [${timestamp}] Loading gösteriliyor`);
            this.showLoading(true);
            
            // Mevcut dili al
            const currentLanguage = localStorage.getItem('language') || 'tr';
            console.log(`🌐 [${timestamp}] Kullanılan dil: ${currentLanguage}`);
            
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
                
                // Kartlar oluşturulduktan sonra çeviri yap
                const currentLanguage = localStorage.getItem('language') || 'tr';
                this.updateCardTexts(currentLanguage);
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
        // Hata mesajını sadece console'da göster
        console.error('❌ Batteries Sayfası Hatası:', message);
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
    };
}

// Sayfa yüklendiğinde başlat
function initBatteriesPage() {
    console.log('🔧 initBatteriesPage() çağrıldı');
    if (!window.batteriesPage) {
        window.batteriesPage = new window.BatteriesPage();
    } else {
        // Mevcut instance'ı yeniden başlat
        console.log('🔄 Mevcut BatteriesPage instance yeniden başlatılıyor');
        window.batteriesPage.init();
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

// Sayfa yüklendiğinde başlat
function initBatteriesPage() {
    console.log('🔧 initBatteriesPage() çağrıldı');
    if (!window.batteriesPage) {
        window.batteriesPage = new BatteriesPage();
    }
}

// Global olarak erişilebilir yap
window.initBatteriesPage = initBatteriesPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Batteries.js yüklendi, otomatik init başlatılıyor...');
initBatteriesPage();

// Unhandled promise rejection handler
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
});



