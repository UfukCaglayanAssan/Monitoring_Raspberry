// Batteries Page JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.BatteriesPage === 'undefined') {
    window.BatteriesPage = class BatteriesPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 30;
        this.totalPages = 1;
        this.batteriesData = [];
        this.selectedArm = parseInt(localStorage.getItem('selectedArm')) || 1; // localStorage'dan al, yoksa varsayılan: Kol 1
        this.isLoading = false; // Yükleme durumu flag'i
        this.autoRefreshInterval = null; // Interval referansı
        this.eventsBound = false; // Event listener flag'i
        this.activeAlarms = new Set(); // Aktif alarmlar (arm-battery formatında)
        
        this.init();
    }

    init() {
        const timestamp = new Date().toISOString();
        console.log(`🔧 [${timestamp}] BatteriesPage init() başladı`);
        
        // Önce tüm butonları disabled yap
        this.disableAllArmButtons();
        
        this.bindEvents();
        console.log(`🔗 [${timestamp}] Event listener'lar bağlandı`);
        
        // Önce aktif kolları yükle, sonra alarmları yükle, sonra bataryaları yükle
        this.loadActiveArms().then(() => {
            console.log(`🔄 [${timestamp}] Aktif kollar yüklendi, alarmlar yükleniyor`);
            return this.loadActiveAlarms();
        }).then(() => {
            console.log(`🔄 [${timestamp}] Alarmlar yüklendi, bataryalar yükleniyor`);
            this.loadBatteries();
        });
        
        this.startAutoRefresh();
        console.log(`⏰ [${timestamp}] Auto refresh başlatıldı`);
    }

    disableAllArmButtons() {
        const armButtons = document.querySelectorAll('.arm-btn');
        armButtons.forEach(button => {
            button.disabled = true;
            button.classList.add('disabled');
        });
        console.log('🔒 Tüm kol butonları disabled yapıldı');
    }

    bindEvents() {
        // Event delegation kullan - tek bir listener ile tüm butonları dinle
        if (!this.eventsBound) {
            document.addEventListener('click', (e) => {
                // Sadece .arm-btn sınıfına sahip elementlere tıklanırsa
                const armButton = e.target.closest('.arm-btn');
                if (armButton) {
                    const arm = parseInt(armButton.dataset.arm);
                    console.log(`🔘 Kol butonu tıklandı: Kol ${arm}`);
                    this.selectArm(arm);
                }
            });
            this.eventsBound = true;
            console.log('🔗 Event delegation bağlandı');
        }
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
        
        // Promise döndür (her durumda)
        return Promise.resolve();
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

    async loadActiveAlarms() {
        // Aktif alarmları yükle
        console.log('🔔 Aktif alarmlar yükleniyor...');
        try {
            const response = await fetch('/api/alarms?show_resolved=false&page=1&pageSize=100', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                console.log('📊 Alarm API yanıtı:', data);
                
                if (data.success) {
                    // Aktif alarmları Set'e ekle
                    this.activeAlarms.clear();
                    data.alarms.forEach(alarm => {
                        if (alarm.battery === "Kol Alarmı") {
                            // Kol alarmı
                            this.activeAlarms.add(`arm-${alarm.arm}`);
                        } else if (alarm.battery && alarm.battery !== "") {
                            // Batarya alarmı
                            this.activeAlarms.add(`arm-${alarm.arm}-battery-${alarm.battery}`);
                        }
                    });
                    console.log('🚨 Aktif alarmlar yüklendi:', Array.from(this.activeAlarms));
                } else {
                    console.error('Alarm verileri yüklenirken hata:', data.message);
                }
            } else {
                console.error('Alarm API yanıt hatası:', response.status);
            }
        } catch (error) {
            console.error('Alarm verileri yüklenirken hata:', error);
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
        
        // Kol butonlarının alarm durumunu güncelle
        this.updateArmButtonAlarmStatus();
        
        // Seçilen kol'u güncelle
        this.selectedArm = arm;
        localStorage.setItem('selectedArm', arm); // localStorage'a kaydet
        
        console.log(`Kol ${arm} seçildi, bataryalar yükleniyor...`);
        
        // Bataryaları yeniden yükle
        this.loadBatteries();
    }

    updateArmButtonAlarmStatus() {
        // Tüm kol butonlarının alarm durumunu güncelle
        document.querySelectorAll('.arm-btn').forEach(button => {
            const arm = parseInt(button.dataset.arm);
            
            // Alarm sınıflarını temizle
            button.classList.remove('arm-alarm', 'battery-alarm');
            
            // Kol alarmı var mı kontrol et
            if (this.activeAlarms.has(`arm-${arm}`)) {
                button.classList.add('arm-alarm');
                console.log(`🚨 Kol ${arm} alarm durumu: KOL ALARMI`);
            } else {
                // Bu kolda batarya alarmı var mı kontrol et
                const hasBatteryAlarm = Array.from(this.activeAlarms).some(alarm => 
                    alarm.startsWith(`arm-${arm}-battery-`)
                );
                if (hasBatteryAlarm) {
                    button.classList.add('battery-alarm');
                    console.log(`🚨 Kol ${arm} alarm durumu: BATARYA ALARMI`);
                }
            }
        });
    }

    async loadBatteries() {
        const timestamp = new Date().toISOString();
        console.log(`🔋 [${timestamp}] loadBatteries() başladı`);
        
        // Sayfa kontrolü yap
        if (!this.isPageActive()) {
            console.log(`⚠️ [${timestamp}] Sayfa aktif değil, loadBatteries iptal edildi`);
            return;
        }
        
        // Yükleme durumu kontrolü
        if (this.isLoading) {
            console.log(`⏳ [${timestamp}] Zaten yükleme devam ediyor, iptal edildi`);
            return;
        }
        
        this.isLoading = true;
        console.log(`⏳ [${timestamp}] Loading gösteriliyor`);
        
        try {
            this.showLoading(true);
            
            // API endpoint'den batarya verilerini çek
            const response = await fetch('/api/batteries', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Language': 'tr'
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
                this.updateCardTexts('tr');
                
                // Batarya kartlarının alarm durumunu güncelle
                this.updateBatteryCardAlarmStatus();
            } else {
                throw new Error(data.message || 'Veri yüklenemedi');
            }
            
        } catch (error) {
            console.error('Batarya verileri yüklenirken hata:', error);
            this.showError('Batarya verileri yüklenirken hata oluştu: ' + error.message);
        } finally {
            this.isLoading = false;
            this.showLoading(false);
        }
    }

    updateBatteryCardAlarmStatus() {
        // Batarya kartlarının alarm durumunu güncelle
        document.querySelectorAll('.battery-card').forEach(card => {
            const arm = this.selectedArm;
            const batteryAddress = card.dataset.batteryAddress;
            
            if (!batteryAddress) return;
            
            // Alarm sınıflarını temizle
            card.classList.remove('battery-alarm');
            
            // Bu bataryada alarm var mı kontrol et
            const alarmKey = `arm-${arm}-battery-${batteryAddress}`;
            if (this.activeAlarms.has(alarmKey)) {
                card.classList.add('battery-alarm');
                console.log(`🚨 Batarya ${batteryAddress} alarm durumu: ALARM VAR`);
            }
        });
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
        cardElement.dataset.batteryAddress = battery.batteryAddress; // Alarm kontrolü için
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
        // Önceki interval'ı temizle
        if (this.autoRefreshInterval) {
            clearInterval(this.autoRefreshInterval);
            console.log('🧹 Önceki auto refresh interval temizlendi');
        }
        
        // Her 30 saniyede bir otomatik yenile
        this.autoRefreshInterval = setInterval(() => {
            // Sadece sayfa aktifse ve manuel işlem yoksa yenile
            if (this.isPageActive() && !this.isLoading) {
                console.log('🔄 Otomatik yenileme çalışıyor...');
                // Önce alarmları güncelle, sonra bataryaları yükle
                this.loadActiveAlarms().then(() => {
                    this.loadBatteries();
                });
            } else if (this.isLoading) {
                console.log('⏳ Manuel yükleme devam ediyor, otomatik yenileme atlanıyor...');
            }
        }, 30000);
        
        console.log('⏰ Yeni auto refresh interval başlatıldı (30s)');
    }
    };
}

// Eski initBatteriesPage fonksiyonu kaldırıldı - çift init sorunu

// Global error handler
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
});

// Sayfa yüklendiğinde başlat
function initBatteriesPage() {
    console.log('🔧 initBatteriesPage() çağrıldı');
    if (!window.batteriesPage) {
        window.batteriesPage = new BatteriesPage();
        console.log('✅ Yeni BatteriesPage instance oluşturuldu');
    } else {
        // Mevcut instance varsa sadece veri yükle, init() çağırma
        console.log('🔄 Mevcut BatteriesPage instance kullanılıyor, sadece veri yükleniyor');
        if (window.batteriesPage.isPageActive() && !window.batteriesPage.isLoading) {
            window.batteriesPage.loadBatteries();
        }
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


