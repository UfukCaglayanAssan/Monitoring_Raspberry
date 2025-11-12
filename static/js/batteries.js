// Batteries Page JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.BatteriesPage === 'undefined') {
    window.BatteriesPage = class BatteriesPage {
    constructor() {
        this.currentPage = 1;
        this.pageSize = 120; // Tüm bataryaları göster (maksimum)
        this.totalPages = 1;
        this.batteriesData = [];
        this.selectedArm = parseInt(localStorage.getItem('selectedArm')) || 3; // localStorage'dan al, yoksa varsayılan: Kol 3
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
        
        // Her zaman aktif kolları yükle ve butonları güncelle
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
            
            // Dil değişikliği dinleyicisi
            window.addEventListener('languageChanged', (e) => {
                console.log('🌐 Bataryalar sayfası - Dil değişti:', e.detail.language);
                this.onLanguageChanged(e.detail.language);
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
                    await this.updateArmButtons(data.activeArms);
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

    async updateArmButtons(activeArms) {
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
        
        // localStorage'dan veya ilk aktif kolu seç
        console.log('🎯 Kol seçimi yapılıyor...');
        if (activeArmNumbers.length > 0) {
            // localStorage'dan seçili kolu al
            const savedArm = parseInt(localStorage.getItem('selectedArm'));
            
            // Eğer kaydedilmiş kol aktifse onu seç, değilse ilk aktif kolu seç
            const armToSelect = (savedArm && activeArmNumbers.includes(savedArm)) 
                ? savedArm 
                : activeArmNumbers[0];
            
            console.log(`🏆 Kol seçiliyor: Kol ${armToSelect} (Kaydedilmiş: ${savedArm || 'yok'}, Aktif kollar: ${activeArmNumbers.join(', ')})`);
            await this.selectArm(armToSelect);
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
                        if (!alarm.battery || alarm.battery === 0) {
                            // Kol alarmı (battery yok veya 0)
                            this.activeAlarms.add(`arm-${alarm.arm}`);
                        } else {
                            // Batarya alarmı (battery > 0)
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
    
    async selectArm(arm) {
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
        
        // Alarm verilerini yeniden yükle ve kol butonlarının alarm durumunu güncelle
        await this.loadActiveAlarms();
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
            
            // SADECE kol alarmı var mı kontrol et
            if (this.activeAlarms.has(`arm-${arm}`)) {
                button.classList.add('arm-alarm');
                console.log(`🚨 Kol ${arm} alarm durumu: KOL ALARMI`);
            }
            // Batarya alarmları kol kartını kırmızı yapmaz - sadece batarya kartları kırmızı olur
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
            
            // Tüm durum sınıflarını temizle
            card.classList.remove('battery-alarm', 'passive-balance');
            
            // Bu bataryada alarm var mı kontrol et
            const alarmKey = `arm-${arm}-battery-${batteryAddress}`;
            if (this.activeAlarms.has(alarmKey)) {
                card.classList.add('battery-alarm');
                console.log(`🚨 Batarya ${batteryAddress} alarm durumu: ALARM VAR`);
            } else {
                // Alarm yoksa, pasif balans durumunu kontrol et
                const batteryData = this.batteriesData.find(b => 
                    b.arm === arm && b.batteryAddress == batteryAddress
                );
                console.log(`🔍 Batarya ${batteryAddress} verisi:`, batteryData);
                console.log(`🔍 passiveBalance değeri:`, batteryData?.passiveBalance);
                if (batteryData && batteryData.passiveBalance) {
                    card.classList.add('passive-balance');
                    console.log(`⚡ Batarya ${batteryAddress} pasif balans durumu: AKTIF - Class eklendi`);
                    console.log(`🔍 Kart class'ları:`, card.className);
                    
                    // Pasif balans yazısını ekle - "Son güncelleme" yerine
                    const lastUpdateDiv = card.querySelector('.battery-last-update');
                    if (lastUpdateDiv) {
                        // "Son güncelleme" yazısını kaldır
                        lastUpdateDiv.style.display = 'none';
                        
                        // Önceki pasif balans yazısını kontrol et
                        const existingPassiveText = card.querySelector('.passive-balance-text');
                        if (!existingPassiveText) {
                            // "Pasif Balans Aktif" yazısını ekle
                            const passiveBalanceText = document.createElement('div');
                            passiveBalanceText.className = 'passive-balance-text';
                            passiveBalanceText.style.cssText = 'color: #2563eb; font-weight: 500; font-size: 0.9rem; margin-top: 0.5rem; text-align: center;';
                            passiveBalanceText.textContent = 'Pasif Balans Aktif';
                            lastUpdateDiv.parentNode.insertBefore(passiveBalanceText, lastUpdateDiv.nextSibling);
                        }
                    }
                }
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
        
        // Kartlar oluşturulduktan sonra durumlarını güncelle
        this.updateBatteryCardAlarmStatus();
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
        
        // Modal açma event listener'ı ekle
        cardElement.addEventListener('click', () => {
            this.openBatteryModal(battery);
        });
        
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
        
        // Pasif balans durumunu kontrol et ve şimşek ikonunu ekle
        if (battery.passiveBalance) {
            const batteryValue = cardElement.querySelector('.battery-value');
            if (batteryValue) {
                batteryValue.innerHTML = `${battery.batteryAddress - 2} <span class="passive-balance-indicator">⚡</span>`;
            }
        }
        
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
        
        // Tüm data-tr ve data-en attribute'larına sahip elementleri güncelle
        const elements = document.querySelectorAll('[data-tr], [data-en]');
        elements.forEach(element => {
            if (language === 'en' && element.hasAttribute('data-en')) {
                element.textContent = element.getAttribute('data-en');
            } else if (language === 'tr' && element.hasAttribute('data-tr')) {
                element.textContent = element.getAttribute('data-tr');
            }
        });
        
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
        // Mevcut instance varsa aktif kolları yükle ve butonları güncelle
        console.log('🔄 Mevcut BatteriesPage instance kullanılıyor, aktif kollar yükleniyor');
        // Önce aktif kolları yükle ve butonları güncelle (isPageActive kontrolü kaldırıldı)
        window.batteriesPage.loadActiveArms().then(() => {
            console.log('🔄 Aktif kollar yüklendi, alarmlar yükleniyor');
            return window.batteriesPage.loadActiveAlarms();
        }).then(() => {
            console.log('🔄 Alarmlar yüklendi, bataryalar yükleniyor');
            window.batteriesPage.loadBatteries();
        });
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

// Modal fonksiyonları
function openBatteryModal(battery) {
    console.log('🔋 Modal açılıyor:', battery);
    
    const modal = document.getElementById('batteryModal');
    if (!modal) {
        console.error('batteryModal bulunamadı!');
        return;
    }
    
    // Modal verilerini doldur
    document.getElementById('modalArm').textContent = battery.arm;
    document.getElementById('modalBatteryAddress').textContent = battery.batteryAddress - 2;
    document.getElementById('modalTimestamp').textContent = new Date(battery.timestamp).toLocaleString('tr-TR');
    
    // Ölçüm verilerini doldur
    document.getElementById('modalVoltage').textContent = formatValue(battery.voltage, 'V');
    document.getElementById('modalTemperature').textContent = formatValue(battery.temperature, '°C');
    document.getElementById('modalHealth').textContent = formatValue(battery.health, '%');
    document.getElementById('modalCharge').textContent = formatValue(battery.charge, '%');
    
    // Modal'ı göster
    modal.style.display = 'flex';
    
    // Event listener'ları ekle
    bindModalEvents();
}

function bindModalEvents() {
    const modal = document.getElementById('batteryModal');
    const closeBtn = document.getElementById('modalClose');
    
    if (!modal || !closeBtn) return;
    
    // Kapatma butonuna tıklama
    closeBtn.addEventListener('click', () => {
        closeBatteryModal();
    });
    
    // Modal dışına tıklama
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeBatteryModal();
        }
    });
    
    // ESC tuşu
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && modal.style.display === 'flex') {
            closeBatteryModal();
        }
    });
}

function closeBatteryModal() {
    const modal = document.getElementById('batteryModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function formatValue(value, unit) {
    if (value === null || value === undefined || value === '') {
        return 'N/A';
    }
    
    if (typeof value === 'number') {
        return value.toFixed(3) + (unit ? ' ' + unit : '');
    }
    
    return value + (unit ? ' ' + unit : '');
}


