class InterfaceIPSettingsPage {
    constructor() {
        this.form = document.getElementById('ipConfigForm');
        this.statusIndicator = document.getElementById('ipStatus');
        this.currentIpElement = document.getElementById('currentIp');
        this.refreshButton = document.getElementById('refreshIp');
        this.testButton = document.getElementById('testConnection');
        this.staticIpFields = document.querySelectorAll('#staticIpFields');
        this.ipMethodStatic = document.getElementById('ipMethodStatic');
        this.ipMethodDhcp = document.getElementById('ipMethodDhcp');
        
        this.init();
    }

    init() {
        this.loadCurrentIP();
        this.loadConfig();
        this.bindEvents();
        this.initializeForm();
        this.checkUserPermissions();
    }

    checkUserPermissions() {
        // Kullanıcı rolünü kontrol et
        fetch('/api/user-info')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.user) {
                    const userRole = data.user.role;
                    if (userRole !== 'admin') {
                        // Guest kullanıcısı için butonları devre dışı bırak
                        this.disableAdminButtons();
                    }
                }
            })
            .catch(error => {
                console.error('Kullanıcı bilgisi alınırken hata:', error);
            });
    }

    disableAdminButtons() {
        // Admin yetkisi gerektiren butonları devre dışı bırak
        const saveButton = document.getElementById('saveIpConfig');
        const testButton = document.getElementById('testConnection');
        
        if (saveButton) {
            saveButton.disabled = true;
            saveButton.textContent = '🔒 Admin Yetkisi Gerekli';
            saveButton.classList.add('btn-disabled');
        }
        
        if (testButton) {
            testButton.disabled = true;
            testButton.textContent = '🔒 Admin Yetkisi Gerekli';
            testButton.classList.add('btn-disabled');
        }
    }

    initializeForm() {
        // Form alanlarını temizle ve varsayılan değerleri ayarla
        document.getElementById('ipAddress').value = '';
        document.getElementById('subnetMask').value = '255.255.255.0';
        document.getElementById('gateway').value = '';
        document.getElementById('dnsServers').value = '';
        
        // Varsayılan olarak Statik IP seçili olsun (loadConfig'de override edilecek)
        this.ipMethodStatic.checked = true;
        this.toggleStaticIpFields();
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

        // IP method radio button changes
        this.ipMethodStatic.addEventListener('change', () => {
            this.toggleStaticIpFields();
        });

        this.ipMethodDhcp.addEventListener('change', () => {
            this.toggleStaticIpFields();
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
                    if (data.config.use_dhcp) {
                        this.updateStatus('active', 'DHCP Aktif');
                        this.ipMethodDhcp.checked = true; // DHCP radyo butonunu seç
                    } else if (data.config.is_assigned) {
                        this.updateStatus('active', 'Statik IP Aktif');
                        this.ipMethodStatic.checked = true; // Statik IP radyo butonunu seç
                    } else {
                        this.updateStatus('inactive', 'IP Ataması Yok');
                        this.ipMethodStatic.checked = true; // Varsayılan olarak Statik IP
                    }
                    this.toggleStaticIpFields(); // Alanları doğru şekilde göster/gizle
                    console.log('✓ IP konfigürasyonu yüklendi:', data.config);
                } else {
                    this.updateStatus('inactive', 'IP Ataması Yok');
                    this.ipMethodStatic.checked = true; // Varsayılan olarak Statik IP
                    this.toggleStaticIpFields();
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


    toggleStaticIpFields() {
        const isStatic = this.ipMethodStatic.checked;
        
        this.staticIpFields.forEach(field => {
            if (isStatic) {
                field.classList.remove('hidden');
                // Required attribute'ları ekle
                const inputs = field.querySelectorAll('input, select');
                inputs.forEach(input => {
                    if (input.id === 'ipAddress' || input.id === 'subnetMask') {
                        input.required = true;
                    }
                });
            } else {
                field.classList.add('hidden');
                // Required attribute'ları kaldır
                const inputs = field.querySelectorAll('input, select');
                inputs.forEach(input => {
                    input.required = false;
                });
            }
        });
        
        // Form validasyonunu yeniden çalıştır
        this.validateForm();
    }

    async saveConfig() {
        try {
            const formData = new FormData(this.form);
            const ipMethod = formData.get('ip_method');
            const isDhcp = ipMethod === 'dhcp';
            
            const config = {
                ip_method: ipMethod,
                use_dhcp: isDhcp
            };

            // DHCP seçilmediyse statik IP alanlarını ekle
            if (!isDhcp) {
                config.ip_address = formData.get('ip_address');
                config.subnet_mask = formData.get('subnet_mask');
                config.gateway = formData.get('gateway');
                config.dns_servers = formData.get('dns_servers');

                // Statik IP validasyonu
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
            const ipMethod = formData.get('ip_method');
            const isDhcp = ipMethod === 'dhcp';
            
            if (isDhcp) {
                this.showToast('DHCP seçildi - test gerekmez', 'info');
                return;
            }

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
        const saveButton = document.getElementById('saveIpConfig');
        const isDhcp = this.ipMethodDhcp.checked;
        
        let isValid = true;
        
        if (!isDhcp) {
            // Statik IP validasyonu
            const ipAddress = document.getElementById('ipAddress').value;
            isValid = ipAddress.trim() !== '' && this.isValidIP(ipAddress);
        }
        
        if (saveButton) {
            saveButton.disabled = !isValid;
        }
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
console.log('🔧 InterfaceIPSettingsPage.js yüklendi, otomatik init başlatılıyor...');
new InterfaceIPSettingsPage();
