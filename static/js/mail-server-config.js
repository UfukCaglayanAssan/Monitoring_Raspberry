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

            // Test endpoint'i yoksa simüle et
            await new Promise(resolve => setTimeout(resolve, 2000));
            
            this.showToast('Bağlantı testi tamamlandı (simüle edildi)', 'info');
            console.log('✓ Mail bağlantı testi tamamlandı');

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
        const submitButton = this.form.querySelector('button[type="submit"]');
        
        const isValid = smtpServer.trim() !== '' && smtpPort.trim() !== '';
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
        }, 3000);
    }
}

// Sayfa yüklendiğinde başlat
document.addEventListener('DOMContentLoaded', () => {
    new MailServerConfigPage();
});
