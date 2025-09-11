// Configuration Sayfası JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.ConfigurationPage === 'undefined') {
    window.ConfigurationPage = class ConfigurationPage {
    constructor() {
        this.init().catch(error => {
            console.error('Configuration sayfası başlatılırken hata:', error);
        });
    }

    async init() {
        console.log('Configuration sayfası başlatıldı');
        this.bindEvents();
        this.loadArmOptions(); // Sabit 4 kol seçeneği yükle
        await this.loadConfigurations();
    }

    bindEvents() {
        // Batarya konfigürasyonu kaydet
        document.getElementById('saveBatConfig').addEventListener('click', () => {
            this.saveBatteryConfig();
        });

        // Kol konfigürasyonu kaydet
        document.getElementById('saveArmConfig').addEventListener('click', () => {
            this.saveArmConfig();
        });

        // Manuel kol set
        document.getElementById('manualSetArm').addEventListener('click', () => {
            this.manualSetArm();
        });

        // Konfigürasyonu cihaza gönder
        document.getElementById('sendConfigToDevice').addEventListener('click', () => {
            this.sendConfigToDevice();
        });

        // Kol seçimi değiştiğinde konfigürasyonları yükle
        document.getElementById('batArmSelect').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadBatteryConfigForSelectedArm(parseInt(e.target.value));
            }
        });

        document.getElementById('armArmSelect').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadArmConfigForSelectedArm(parseInt(e.target.value));
            }
        });
    }

    async loadArmOptions() {
        // Sabit 4 kol seçeneği yükle ve batarya durumunu kontrol et
        try {
            const response = await fetch('/api/active-arms', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.updateArmSelectsWithBatteryStatus(data.activeArms);
                }
            }
        } catch (error) {
            console.error('Kol seçenekleri yüklenirken hata:', error);
            // Hata durumunda sadece sabit kolları göster
            this.updateArmSelectsWithBatteryStatus([]);
        }
    }

    updateArmSelectsWithBatteryStatus(activeArms) {
        // Sayfa kontrolü yap - sadece configuration sayfasında çalış
        if (!this.isConfigurationPageActive()) {
            return;
        }
        
        // Sabit 4 kol seçeneği yükle - sadece arm_slave_counts kullan
        const batArmSelect = document.getElementById('batArmSelect');
        const armArmSelect = document.getElementById('armArmSelect');
        
        // Element kontrolü yap
        if (!batArmSelect || !armArmSelect) {
            console.warn('Configuration sayfası elementleri bulunamadı');
            return;
        }
        
        // Select'leri temizle
        batArmSelect.innerHTML = '<option value="">Kol Seçin</option>';
        armArmSelect.innerHTML = '<option value="">Kol Seçin</option>';
        
        // arm_slave_counts verilerini map'e çevir
        const armSlaveCountsMap = new Map();
        activeArms.forEach(arm => {
            armSlaveCountsMap.set(arm.arm, arm.slave_count || 0);
        });
        
        // Sabit 4 kol seçeneği
        for (let arm = 1; arm <= 4; arm++) {
            const slaveCount = armSlaveCountsMap.get(arm) || 0;
            const hasBattery = slaveCount > 0;
            
            // Batarya konfigürasyonu select'i
            const option1 = document.createElement('option');
            option1.value = arm;
            option1.textContent = `Kol ${arm}`;
            option1.disabled = !hasBattery; // Batarya yoksa tıklanamaz
            if (!hasBattery) {
                option1.style.color = '#999';
                option1.style.fontStyle = 'italic';
            }
            batArmSelect.appendChild(option1);
            
            // Kol konfigürasyonu select'i
            const option2 = document.createElement('option');
            option2.value = arm;
            option2.textContent = `Kol ${arm}`;
            option2.disabled = !hasBattery; // Batarya yoksa tıklanamaz
            if (!hasBattery) {
                option2.style.color = '#999';
                option2.style.fontStyle = 'italic';
            }
            armArmSelect.appendChild(option2);
        }
    }

    async getFirstArmWithBattery() {
        try {
            // Aktif kolları API'den yükle
            const response = await fetch('/api/active-arms', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success && data.activeArms) {
                    const armsWithBatteries = data.activeArms.filter(arm => arm.slave_count > 0);
                    if (armsWithBatteries.length > 0) {
                        return armsWithBatteries.sort((a, b) => a.arm - b.arm)[0].arm;
                    }
                }
            }
        } catch (error) {
            console.error('Aktif kollar yüklenirken hata:', error);
        }
        return null;
    }

    async loadConfigurations() {
        try {
            // DB'den konfigürasyonları yükle
            const [batteryConfigs, armConfigs] = await Promise.all([
                this.loadBatteryConfigsFromDB(),
                this.loadArmConfigsFromDB()
            ]);
            
            // İlk bataryası olan kol için konfigürasyonları yükle
            const firstArmWithBattery = await this.getFirstArmWithBattery();
            if (firstArmWithBattery) {
                this.loadBatteryConfigForArm(firstArmWithBattery, batteryConfigs);
                this.loadArmConfigForArm(firstArmWithBattery, armConfigs);
                
                // Select'leri ilk bataryası olan kol olarak ayarla
                document.getElementById('batArmSelect').value = firstArmWithBattery.toString();
                document.getElementById('armArmSelect').value = firstArmWithBattery.toString();
            } else {
                console.warn('Hiç bataryası olan kol bulunamadı!');
            }
        } catch (error) {
            console.error('Konfigürasyonlar yüklenirken hata:', error);
            // Hata durumunda default değerleri yükle
            this.loadDefaultValues();
        }
    }

    async loadBatteryConfigsFromDB() {
        try {
            console.log('🔄 DB\'den batarya konfigürasyonları yükleniyor...');
            const response = await fetch('/api/batconfigs');
            const result = await response.json();
            console.log('📡 API Response:', result);
            
            if (result.success) {
                console.log(`✅ ${result.data.length} adet batarya konfigürasyonu yüklendi:`, result.data);
                return result.data;
            } else {
                console.error('❌ API hatası:', result.message);
                return [];
            }
        } catch (error) {
            console.error('❌ Batarya konfigürasyonları yüklenirken hata:', error);
            return [];
        }
    }

    async loadArmConfigsFromDB() {
        try {
            const response = await fetch('/api/armconfigs');
            const result = await response.json();
            return result.success ? result.data : [];
        } catch (error) {
            console.error('Kol konfigürasyonları yüklenirken hata:', error);
            return [];
        }
    }

    loadBatteryConfigForArm(armValue, configs) {
        console.log(`🔍 Kol ${armValue} için konfigürasyon aranıyor...`);
        console.log(`📋 Mevcut konfigürasyonlar:`, configs);
        
        // DB'den bu kol için konfigürasyon bul
        const config = configs.find(c => c.armValue === armValue);
        console.log(`🔍 Bulunan konfigürasyon:`, config);
        
        if (config) {
            console.log(`✅ Kol ${armValue} konfigürasyonu bulundu, DB değerleri yükleniyor`);
            console.log(`📊 DB Değerleri:`, {
                Vmin: config.Vmin,
                Vmax: config.Vmax,
                Vnom: config.Vnom,
                Rintnom: config.Rintnom,
                Tempmin_D: config.Tempmin_D,
                Tempmax_D: config.Tempmax_D,
                Tempmin_PN: config.Tempmin_PN,
                Tempmax_PN: config.Tempmax_PN,
                Socmin: config.Socmin,
                Sohmin: config.Sohmin
            });
            
            // DB'deki değerleri kullan
            document.getElementById('Vmin').value = config.Vmin;
            document.getElementById('Vmax').value = config.Vmax;
            document.getElementById('Vnom').value = config.Vnom;
            document.getElementById('Rintnom').value = config.Rintnom;
            document.getElementById('Tempmin_D').value = config.Tempmin_D;
            document.getElementById('Tempmax_D').value = config.Tempmax_D;
            document.getElementById('Tempmin_PN').value = config.Tempmin_PN;
            document.getElementById('Tempmax_PN').value = config.Tempmax_PN;
            document.getElementById('Socmin').value = config.Socmin;
            document.getElementById('Sohmin').value = config.Sohmin;
            
            console.log(`✅ Form alanları DB değerleri ile dolduruldu`);
        } else {
            console.log(`❌ Kol ${armValue} konfigürasyonu bulunamadı, default değerler yükleniyor`);
            // DB'de yoksa default değerleri kullan
            this.loadBatteryDefaultsForArm(armValue);
        }
    }

    loadArmConfigForArm(armValue, configs) {
        // DB'den bu kol için konfigürasyon bul
        const config = configs.find(c => c.armValue === armValue);
        
        if (config) {
            // DB'deki değerleri kullan
            document.getElementById('akimKats').value = config.akimKats;
            document.getElementById('akimMax').value = config.akimMax;
            document.getElementById('nemMin').value = config.nemMin;
            document.getElementById('nemMax').value = config.nemMax;
            document.getElementById('tempMin').value = config.tempMin;
            document.getElementById('tempMax').value = config.tempMax;
        } else {
            // DB'de yoksa default değerleri kullan
            this.loadArmDefaultsForArm(armValue);
        }
    }

    async loadBatteryConfigForSelectedArm(armValue) {
        try {
            console.log(`🔄 Kol ${armValue} için batarya konfigürasyonu yükleniyor...`);
            const configs = await this.loadBatteryConfigsFromDB();
            console.log(`📋 Yüklenen konfigürasyonlar:`, configs);
            this.loadBatteryConfigForArm(armValue, configs);
        } catch (error) {
            console.error('❌ Batarya konfigürasyonu yüklenirken hata:', error);
            this.loadBatteryDefaultsForArm(armValue);
        }
    }

    async loadArmConfigForSelectedArm(armValue) {
        try {
            const configs = await this.loadArmConfigsFromDB();
            this.loadArmConfigForArm(armValue, configs);
        } catch (error) {
            console.error('Kol konfigürasyonu yüklenirken hata:', error);
            this.loadArmDefaultsForArm(armValue);
        }
    }

    loadDefaultValues() {
        // İlk kol için varsayılan değerleri yükle
        this.loadBatteryDefaultsForArm(1);
        this.loadArmDefaultsForArm(1);
        
        // Select'leri ilk kol olarak ayarla
        document.getElementById('batArmSelect').value = '1';
        document.getElementById('armArmSelect').value = '1';
    }

    loadBatteryDefaultsForArm(armValue) {
        // Sayfa kontrolü yap
        if (!this.isConfigurationPageActive()) {
            return;
        }
        
        const defaults = this.getBatteryDefaults(armValue);
        
        // Element kontrolü yap
        const vminElement = document.getElementById('Vmin');
        if (!vminElement) {
            console.warn('Vmin elementi bulunamadı');
            return;
        }
        
        vminElement.value = defaults.Vmin;
        document.getElementById('Vmax').value = defaults.Vmax;
        document.getElementById('Vnom').value = defaults.Vnom;
        document.getElementById('Rintnom').value = defaults.Rintnom;
        document.getElementById('Tempmin_D').value = defaults.Tempmin_D;
        document.getElementById('Tempmax_D').value = defaults.Tempmax_D;
        document.getElementById('Tempmin_PN').value = defaults.Tempmin_PN;
        document.getElementById('Tempmax_PN').value = defaults.Tempmax_PN;
        document.getElementById('Socmin').value = defaults.Socmin;
        document.getElementById('Sohmin').value = defaults.Sohmin;
    }

    loadArmDefaultsForArm(armValue) {
        const defaults = this.getArmDefaults(armValue);
        
        document.getElementById('akimKats').value = defaults.akimKats;
        document.getElementById('akimMax').value = defaults.akimMax;
        document.getElementById('nemMin').value = defaults.nemMin;
        document.getElementById('nemMax').value = defaults.nemMax;
        document.getElementById('tempMin').value = defaults.tempMin;
        document.getElementById('tempMax').value = defaults.tempMax;
    }

    getBatteryDefaults(armValue) {
        return {
            Vmin: 10.12,
            Vmax: 13.95,
            Vnom: 11.00,
            Rintnom: 20,
            Tempmin_D: 15,
            Tempmax_D: 55,
            Tempmin_PN: 15,
            Tempmax_PN: 30,
            Socmin: 30,
            Sohmin: 30
        };
    }

    getArmDefaults(armValue) {
        return {
            akimKats: 150,
            akimMax: 1000,
            nemMin: 0,
            nemMax: 100,
            tempMin: 15,
            tempMax: 65
        };
    }

    async saveBatteryConfig() {
        const armValue = document.getElementById('batArmSelect').value;
        
        if (!armValue) {
            this.showToast('Lütfen bir kol seçin!', 'warning');
            return;
        }

        try {
            const configData = {
                armValue: parseInt(armValue),
                Vmin: parseFloat(document.getElementById('Vmin').value),
                Vmax: parseFloat(document.getElementById('Vmax').value),
                Vnom: parseFloat(document.getElementById('Vnom').value),
                Rintnom: parseInt(document.getElementById('Rintnom').value),
                Tempmin_D: parseInt(document.getElementById('Tempmin_D').value),
                Tempmax_D: parseInt(document.getElementById('Tempmax_D').value),
                Tempmin_PN: parseInt(document.getElementById('Tempmin_PN').value),
                Tempmax_PN: parseInt(document.getElementById('Tempmax_PN').value),
                Socmin: parseInt(document.getElementById('Socmin').value),
                Sohmin: parseInt(document.getElementById('Sohmin').value)
            };

            console.log('Batarya konfigürasyonu kaydediliyor:', configData);

            const response = await fetch('/api/batconfigs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData)
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast(`Kol ${armValue} batarya konfigürasyonu başarıyla kaydedildi!`, 'success');
                } else {
                    this.showToast('Hata: ' + result.message, 'error');
                }
            } else {
                this.showToast('Konfigürasyon kaydedilemedi!', 'error');
            }
        } catch (error) {
            console.error('Batarya konfigürasyonu kaydedilirken hata:', error);
            this.showToast('Konfigürasyon kaydedilirken hata oluştu!', 'error');
        }
    }

    async saveArmConfig() {
        const armValue = document.getElementById('armArmSelect').value;
        
        if (!armValue) {
            this.showToast('Lütfen bir kol seçin!', 'warning');
            return;
        }

        try {
            const configData = {
                armValue: parseInt(armValue),
                akimKats: parseInt(document.getElementById('akimKats').value),
                akimMax: parseInt(document.getElementById('akimMax').value),
                nemMin: parseInt(document.getElementById('nemMin').value),
                nemMax: parseInt(document.getElementById('nemMax').value),
                tempMin: parseInt(document.getElementById('tempMin').value),
                tempMax: parseInt(document.getElementById('tempMax').value)
            };

            console.log('Kol konfigürasyonu kaydediliyor:', configData);

            const response = await fetch('/api/armconfigs', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(configData)
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast(`Kol ${armValue} konfigürasyonu başarıyla kaydedildi!`, 'success');
                } else {
                    this.showToast('Hata: ' + result.message, 'error');
                }
            } else {
                this.showToast('Konfigürasyon kaydedilemedi!', 'error');
            }
        } catch (error) {
            console.error('Kol konfigürasyonu kaydedilirken hata:', error);
            this.showToast('Konfigürasyon kaydedilirken hata oluştu!', 'error');
        }
    }


    async sendConfigToDevice() {
        try {
            console.log('Tümünü oku komutu gönderiliyor...');
                
                const response = await fetch('/api/send-config-to-device', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        command: '5 5 0x7A'
                    })
                });

                if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        console.log('Tümünü oku komutu başarıyla gönderildi');
                    } else {
                        console.error('Hata: ' + result.message);
                    }
                } else {
                    console.error('Tümünü oku komutu gönderilemedi');
                }
        } catch (error) {
            console.error('Tümünü oku komutu gönderilirken hata:', error);
        }
    }
    
    async manualSetArm() {
        try {
            const armSelect = document.getElementById('manualArmSelect');
            const selectedArm = armSelect.value;
            
            if (!selectedArm) {
                this.showToast('Lütfen bir kol seçin!', 'warning');
                return;
            }
            
            this.showToast(`Kol ${selectedArm} manuel set komutu gönderiliyor...`, 'info');
            
            // Manuel set komutu gönder (0x81 0xkol_no 0x78)
            const response = await fetch('/api/send-manual-set-command', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    arm: parseInt(selectedArm)
                })
            });

            if (response.ok) {
                const result = await response.json();
                if (result.success) {
                    this.showToast(`Kol ${selectedArm} manuel set komutu başarıyla gönderildi`, 'success');
                } else {
                    this.showToast('Manuel set komutu gönderilemedi: ' + result.message, 'error');
                }
            } else {
                this.showToast('Manuel set komutu gönderilemedi', 'error');
            }
        } catch (error) {
            console.error('Manuel set komutu gönderilirken hata:', error);
            this.showToast('Manuel set komutu gönderilirken hata oluştu', 'error');
        }
    }

    showToast(message, type = 'info') {
        // Toast notification göster
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        
        document.body.appendChild(toast);
        
        // Animasyon
        setTimeout(() => toast.classList.add('show'), 100);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => document.body.removeChild(toast), 300);
        }, 3000);
    }

    isConfigurationPageActive() {
        // Configuration sayfasında olup olmadığımızı kontrol et
        const configPage = document.querySelector('.configuration-page');
        return configPage && configPage.style.display !== 'none';
    }
    };
}

// Sayfa yüklendiğinde başlat
function initConfigurationPage() {
    console.log('🔧 initConfigurationPage() çağrıldı');
    if (!window.configurationPage) {
        window.configurationPage = new window.ConfigurationPage();
    } else {
        // Mevcut instance'ı yeniden başlat
        console.log('🔄 Mevcut ConfigurationPage instance yeniden başlatılıyor');
        window.configurationPage.init();
    }
}

// Global olarak erişilebilir yap
window.initConfigurationPage = initConfigurationPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Configuration.js yüklendi, otomatik init başlatılıyor...');
initConfigurationPage();



