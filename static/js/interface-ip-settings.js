class InterfaceIPSettingsPage {
    constructor() {
        this.form = document.getElementById('ipConfigForm');
        this.statusIndicator = document.getElementById('ipStatus');
        this.currentIpElement = document.getElementById('currentIp');
        this.refreshButton = document.getElementById('refreshIp');
        this.testButton = document.getElementById('testConnection');
        
        this.init();
    }

    init() {
        this.loadCurrentIP();
        this.loadConfig();
        this.bindEvents();
    }

    bindEvents() {
        // Save IP config button
        const saveButton = document.getElementById('saveIpConfig');
        if (saveButton) {
            saveButton.addEventListener('click', () => {
                this.saveConfig();
            });
        }

        // Test connection
        this.testButton.addEventListener('click', () => {
            this.testConnection();
        });

        // Refresh current IP
        this.refreshButton.addEventListener('click', () => {
            this.loadCurrentIP();
        });

        // Form validation
        this.form.addEventListener('input', () => {
            this.validateForm();
        });
    }

    async loadCurrentIP() {
        try {
            this.currentIpElement.textContent = 'Yükleniyor...';
            this.refreshButton.disabled = true;
            
            // Mevcut IP'yi al (basit bir yöntem)
            const response = await fetch('/api/current-ip');
            if (response.ok) {
                const data = await response.json();
                this.currentIpElement.textContent = data.ip || 'Bilinmiyor';
            } else {
                this.currentIpElement.textContent = 'Alınamadı';
            }
        } catch (error) {
            console.error('Mevcut IP alınırken hata:', error);
            this.currentIpElement.textContent = 'Hata';
        } finally {
            this.refreshButton.disabled = false;
        }
    }

    async loadConfig() {
        try {
            console.log('IP konfigürasyonu yükleniyor...');
            
            const response = await fetch('/api/ip-config', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                
                if (data.success && data.config) {
                    this.populateForm(data.config);
                    this.updateStatus('active', 'IP Ataması Yapılmış');
                    console.log('✓ IP konfigürasyonu yüklendi:', data.config);
                } else {
                    this.updateStatus('inactive', 'IP Ataması Yok');
                    console.log('⚠ IP konfigürasyonu bulunamadı');
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('IP konfigürasyonu yüklenirken hata:', error);
            this.updateStatus('error', 'Yükleme Hatası');
            this.showToast('Konfigürasyon yüklenirken hata oluştu', 'error');
        }
    }

    populateForm(config) {
        document.getElementById('ipAddress').value = config.ip_address || '';
        document.getElementById('subnetMask').value = config.subnet_mask || '255.255.255.0';
        document.getElementById('gateway').value = config.gateway || '';
        document.getElementById('dnsServers').value = config.dns_servers || '';
    }

    async saveConfig() {
        try {
            const formData = new FormData(this.form);
            const config = {
                ip_address: formData.get('ip_address'),
                subnet_mask: formData.get('subnet_mask'),
                gateway: formData.get('gateway'),
                dns_servers: formData.get('dns_servers')
            };

            // Validation
            if (!config.ip_address) {
                this.showToast('IP adresi zorunludur', 'error');
                return;
            }

            if (!this.isValidIP(config.ip_address)) {
                this.showToast('Geçersiz IP adresi formatı', 'error');
                return;
            }

            if (config.gateway && !this.isValidIP(config.gateway)) {
                this.showToast('Geçersiz Gateway IP adresi formatı', 'error');
                return;
            }

            console.log('IP konfigürasyonu kaydediliyor...', config);

            const response = await fetch('/api/ip-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                const data = await response.json();
                
                if (data.success) {
                    this.showToast('IP konfigürasyonu kaydedildi. Sistem yeniden başlatılacak...', 'success');
                    this.updateStatus('active', 'IP Ataması Yapılmış');
                    console.log('✓ IP konfigürasyonu kaydedildi');
                    
                    // 3 saniye sonra sayfayı yenile
                    setTimeout(() => {
                        window.location.reload();
                    }, 3000);
                } else {
                    throw new Error(data.message || 'Kayıt başarısız');
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('IP konfigürasyonu kaydedilirken hata:', error);
            this.showToast('Konfigürasyon kaydedilirken hata oluştu: ' + error.message, 'error');
        }
    }

    async testConnection() {
        try {
            this.testButton.disabled = true;
            this.testButton.textContent = '🔄 Test Ediliyor...';

            const formData = new FormData(this.form);
            const config = {
                ip_address: formData.get('ip_address'),
                subnet_mask: formData.get('subnet_mask'),
                gateway: formData.get('gateway')
            };

            // Validation
            if (!config.ip_address) {
                this.showToast('IP adresi gerekli', 'error');
                return;
            }

            if (!this.isValidIP(config.ip_address)) {
                this.showToast('Geçersiz IP adresi formatı', 'error');
                return;
            }

            console.log('IP bağlantısı test ediliyor...', config);

            // Test endpoint'i yoksa simüle et
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            this.showToast('IP konfigürasyonu geçerli görünüyor (simüle edildi)', 'info');
            console.log('✓ IP bağlantı testi tamamlandı');

        } catch (error) {
            console.error('IP bağlantı testi hatası:', error);
            this.showToast('Bağlantı testi başarısız: ' + error.message, 'error');
        } finally {
            this.testButton.disabled = false;
            this.testButton.textContent = '🔗 Bağlantıyı Test Et';
        }
    }

    isValidIP(ip) {
        const ipRegex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
        return ipRegex.test(ip);
    }

    validateForm() {
        const ipAddress = document.getElementById('ipAddress').value;
        const submitButton = this.form.querySelector('button[type="submit"]');
        
        const isValid = ipAddress.trim() !== '' && this.isValidIP(ipAddress);
        submitButton.disabled = !isValid;
    }

    updateStatus(type, text) {
        this.statusIndicator.className = `status-${type}`;
        this.statusIndicator.textContent = text;
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
        }, 5000);
    }
}

// Sayfa yüklendiğinde başlat
document.addEventListener('DOMContentLoaded', () => {
    new InterfaceIPSettingsPage();
});
