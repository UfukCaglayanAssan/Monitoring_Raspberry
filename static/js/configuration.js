// Configuration Sayfası JavaScript
class ConfigurationPage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Configuration sayfası başlatıldı');
        this.bindEvents();
        this.loadDefaultValues();
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

        // Kol seçimi değiştiğinde varsayılan değerleri yükle
        document.getElementById('batArmSelect').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadBatteryDefaultsForArm(parseInt(e.target.value));
            }
        });

        document.getElementById('armArmSelect').addEventListener('change', (e) => {
            if (e.target.value) {
                this.loadArmDefaultsForArm(parseInt(e.target.value));
            }
        });
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
            Rintnom: 150,
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
}

// Global instance oluştur
window.configurationPage = new ConfigurationPage();



