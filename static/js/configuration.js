// Configuration Sayfası JavaScript
class ConfigurationPage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Configuration sayfası başlatıldı');
        this.bindEvents();
        this.loadActiveArms(); // Önce aktif kolları yükle
        this.loadConfigurations();
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

        // Varsayılana döndür
        document.getElementById('resetConfig').addEventListener('click', () => {
            this.resetToDefaults();
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

    async loadActiveArms() {
        // Aktif kolları yükle ve select'leri güncelle
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
                    this.updateArmSelects(data.activeArms);
                }
            }
        } catch (error) {
            console.error('Aktif kollar yüklenirken hata:', error);
        }
    }

    updateArmSelects(activeArms) {
        // Kol select'lerini güncelle - sadece aktif kolları göster
        const batArmSelect = document.getElementById('batArmSelect');
        const armArmSelect = document.getElementById('armArmSelect');
        
        // Select'leri temizle
        batArmSelect.innerHTML = '<option value="">Kol Seçin</option>';
        armArmSelect.innerHTML = '<option value="">Kol Seçin</option>';
        
        // Aktif kolları ekle
        activeArms.forEach(armData => {
            const option1 = document.createElement('option');
            option1.value = armData.arm;
            option1.textContent = `Kol ${armData.arm} (${armData.batteryCount} Batarya)`;
            batArmSelect.appendChild(option1);
            
            const option2 = document.createElement('option');
            option2.value = armData.arm;
            option2.textContent = `Kol ${armData.arm} (${armData.batteryCount} Batarya)`;
            armArmSelect.appendChild(option2);
        });
    }

    async loadConfigurations() {
        try {
            // DB'den konfigürasyonları yükle
            const [batteryConfigs, armConfigs] = await Promise.all([
                this.loadBatteryConfigsFromDB(),
                this.loadArmConfigsFromDB()
            ]);
            
            // İlk kol için konfigürasyonları yükle
            this.loadBatteryConfigForArm(1, batteryConfigs);
            this.loadArmConfigForArm(1, armConfigs);
            
            // Select'leri ilk kol olarak ayarla
            document.getElementById('batArmSelect').value = '1';
            document.getElementById('armArmSelect').value = '1';
        } catch (error) {
            console.error('Konfigürasyonlar yüklenirken hata:', error);
            // Hata durumunda default değerleri yükle
            this.loadDefaultValues();
        }
    }

    async loadBatteryConfigsFromDB() {
        try {
            const response = await fetch('/api/batconfigs');
            const result = await response.json();
            return result.success ? result.data : [];
        } catch (error) {
            console.error('Batarya konfigürasyonları yüklenirken hata:', error);
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
        // DB'den bu kol için konfigürasyon bul
        const config = configs.find(c => c.arm === armValue);
        
        if (config) {
            // DB'deki değerleri kullan
            document.getElementById('Vmin').value = config.Vmin;
            document.getElementById('Vmax').value = config.Vmax;
            document.getElementById('Vnom').value = config.Vnom;
            document.getElementById('Rintnom').value = config.Rintnom;
            document.getElementById('Tempmin_D').value = config.Tempmin_D;
            document.getElementById('Tempmax_D').value = config.Tempmax_D;
            document.getElementById('Tempmin_PN').value = config.Tempmin_PN;
            document.getElementById('Tempmaks_PN').value = config.Tempmaks_PN;
            document.getElementById('Socmin').value = config.Socmin;
            document.getElementById('Sohmin').value = config.Sohmin;
        } else {
            // DB'de yoksa default değerleri kullan
            this.loadBatteryDefaultsForArm(armValue);
        }
    }

    loadArmConfigForArm(armValue, configs) {
        // DB'den bu kol için konfigürasyon bul
        const config = configs.find(c => c.arm === armValue);
        
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
            const configs = await this.loadBatteryConfigsFromDB();
            this.loadBatteryConfigForArm(armValue, configs);
        } catch (error) {
            console.error('Batarya konfigürasyonu yüklenirken hata:', error);
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
        const defaults = this.getBatteryDefaults(armValue);
        
        document.getElementById('Vmin').value = defaults.Vmin;
        document.getElementById('Vmax').value = defaults.Vmax;
        document.getElementById('Vnom').value = defaults.Vnom;
        document.getElementById('Rintnom').value = defaults.Rintnom;
        document.getElementById('Tempmin_D').value = defaults.Tempmin_D;
        document.getElementById('Tempmax_D').value = defaults.Tempmax_D;
        document.getElementById('Tempmin_PN').value = defaults.Tempmin_PN;
        document.getElementById('Tempmaks_PN').value = defaults.Tempmaks_PN;
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
            Tempmaks_PN: 30,
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
            alert('Lütfen bir kol seçin!');
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
                Tempmaks_PN: parseInt(document.getElementById('Tempmaks_PN').value),
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
                    alert(`Kol ${armValue} batarya konfigürasyonu başarıyla kaydedildi!`);
                } else {
                    alert('Hata: ' + result.message);
                }
            } else {
                alert('Konfigürasyon kaydedilemedi!');
            }
        } catch (error) {
            console.error('Batarya konfigürasyonu kaydedilirken hata:', error);
            alert('Konfigürasyon kaydedilirken hata oluştu!');
        }
    }

    async saveArmConfig() {
        const armValue = document.getElementById('armArmSelect').value;
        
        if (!armValue) {
            alert('Lütfen bir kol seçin!');
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
                    alert(`Kol ${armValue} konfigürasyonu başarıyla kaydedildi!`);
                } else {
                    alert('Hata: ' + result.message);
                }
            } else {
                alert('Konfigürasyon kaydedilemedi!');
            }
        } catch (error) {
            console.error('Kol konfigürasyonu kaydedilirken hata:', error);
            alert('Konfigürasyon kaydedilirken hata oluştu!');
        }
    }

    resetToDefaults() {
        if (confirm('Tüm konfigürasyonları varsayılan değerlere sıfırlamak istediğinizden emin misiniz?')) {
            this.loadDefaultValues();
            alert('Konfigürasyonlar varsayılan değerlere sıfırlandı!');
        }
    }

    async sendConfigToDevice() {
        if (confirm('Konfigürasyonu cihaza göndermek istediğinizden emin misiniz?')) {
            try {
                console.log('Konfigürasyon cihaza gönderiliyor...');
                
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
                        alert('Konfigürasyon başarıyla cihaza gönderildi!');
                    } else {
                        alert('Hata: ' + result.message);
                    }
                } else {
                    alert('Konfigürasyon gönderilemedi!');
                }
            } catch (error) {
                console.error('Konfigürasyon gönderilirken hata:', error);
                alert('Konfigürasyon gönderilirken hata oluştu!');
            }
        }
    }
}

// Sayfa yüklendiğinde başlat
function initConfigurationPage() {
    console.log('🔧 initConfigurationPage() çağrıldı');
    if (!window.configurationPage) {
        window.configurationPage = new ConfigurationPage();
    }
}

// Global olarak erişilebilir yap
window.initConfigurationPage = initConfigurationPage;

// Hem DOMContentLoaded hem de manuel çağrı için
document.addEventListener('DOMContentLoaded', initConfigurationPage);



