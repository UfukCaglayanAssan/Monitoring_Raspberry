class MailServerConfigPage {
    constructor() {
        this.form = document.getElementById('mailConfigForm');
        this.statusIndicator = document.getElementById('configStatus');
        this.testButton = document.getElementById('testConnection');
        
        this.init();
    }

    init() {
        this.loadConfig();
        this.bindEvents();
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
        const saveButton = document.getElementById('saveMailConfig');
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

    bindEvents() {
        // Save mail config button
        const saveButton = document.getElementById('saveMailConfig');
        if (saveButton) {
            saveButton.addEventListener('click', () => {
                this.saveConfig();
            });
        }

        // Test connection
        this.testButton.addEventListener('click', () => {
            this.testConnection();
        });

        // Form validation
        this.form.addEventListener('input', () => {
            this.validateForm();
        });
    }

    async loadConfig() {
        try {
            console.log('Mail sunucu konfigürasyonu yükleniyor...');
            
            const response = await fetch('/api/mail-server-config', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                
                if (data.success && data.config) {
                    this.populateForm(data.config);
                    this.updateStatus('active', 'Konfigürasyon Aktif');
                    console.log('✓ Mail konfigürasyonu yüklendi:', data.config);
                } else {
                    this.updateStatus('inactive', 'Konfigürasyon Yok');
                    console.log('⚠ Mail konfigürasyonu bulunamadı');
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('Mail konfigürasyonu yüklenirken hata:', error);
            this.updateStatus('error', 'Yükleme Hatası');
            this.showToast('Konfigürasyon yüklenirken hata oluştu', 'error');
        }
    }

    populateForm(config) {
        document.getElementById('smtpServer').value = config.smtp_server || '';
        document.getElementById('smtpPort').value = config.smtp_port || '';
        document.getElementById('smtpUsername').value = config.smtp_username || '';
        document.getElementById('smtpPassword').value = config.smtp_password || '';
        document.getElementById('useTls').checked = config.use_tls !== false;
        document.getElementById('isActive').checked = config.is_active !== false;
    }

    async saveConfig() {
        try {
            const formData = new FormData(this.form);
            const config = {
                smtp_server: formData.get('smtp_server'),
                smtp_port: parseInt(formData.get('smtp_port')),
                smtp_username: formData.get('smtp_username'),
                smtp_password: formData.get('smtp_password'),
                use_tls: formData.get('use_tls') === 'on',
                is_active: formData.get('is_active') === 'on'
            };

            // Validation
            if (!config.smtp_server || !config.smtp_port) {
                this.showToast('SMTP sunucu adresi ve port zorunludur', 'error');
                return;
            }

            console.log('Mail konfigürasyonu kaydediliyor...', config);

            const response = await fetch('/api/mail-server-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                const data = await response.json();
                
                if (data.success) {
                    this.showToast('Konfigürasyon başarıyla kaydedildi', 'success');
                    this.updateStatus('active', 'Konfigürasyon Aktif');
                    console.log('✓ Mail konfigürasyonu kaydedildi');
                } else {
                    throw new Error(data.message || 'Kayıt başarısız');
                }
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            console.error('Mail konfigürasyonu kaydedilirken hata:', error);
            this.showToast('Konfigürasyon kaydedilirken hata oluştu: ' + error.message, 'error');
        }
    }

    async testConnection() {
        try {
            this.testButton.disabled = true;
            this.testButton.textContent = '🔄 Test Ediliyor...';

            const formData = new FormData(this.form);
            const config = {
                smtp_server: formData.get('smtp_server'),
                smtp_port: parseInt(formData.get('smtp_port')),
                smtp_username: formData.get('smtp_username'),
                smtp_password: formData.get('smtp_password'),
                use_tls: formData.get('use_tls') === 'on'
            };

            // Validation
            if (!config.smtp_server || !config.smtp_port) {
                this.showToast('SMTP sunucu adresi ve port gerekli', 'error');
                return;
            }

            console.log('Mail bağlantısı test ediliyor...', config);

            // Gerçek SMTP test endpoint'i çağır
            const response = await fetch('/api/test-mail-connection', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(config)
            });

            const result = await response.json();
            
            if (result.success) {
                this.showToast('Bağlantı testi başarılı!', 'success');
                console.log('✓ Mail bağlantı testi başarılı');
            } else {
                this.showToast('Bağlantı testi başarısız: ' + result.message, 'error');
                console.error('❌ Mail bağlantı testi başarısız:', result.message);
            }

        } catch (error) {
            console.error('Mail bağlantı testi hatası:', error);
            this.showToast('Bağlantı testi başarısız: ' + error.message, 'error');
        } finally {
            this.testButton.disabled = false;
            this.testButton.textContent = '🔗 Bağlantıyı Test Et';
        }
    }

    validateForm() {
        const smtpServer = document.getElementById('smtpServer').value;
        const smtpPort = document.getElementById('smtpPort').value;
        const saveButton = document.getElementById('saveMailConfig');
        
        const isValid = smtpServer.trim() !== '' && smtpPort.trim() !== '';
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
        }, 3000);
    }
}

// Sayfa yüklendiğinde başlat
console.log('🔧 MailServerConfigPage.js yüklendi, otomatik init başlatılıyor...');
new MailServerConfigPage();
