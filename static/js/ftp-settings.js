// SFTP Settings Page JavaScript
console.log('🎯 [SFTP Settings] Script yüklendi');

class FTPSettings {
    constructor() {
        this.init();
    }

    init() {
        console.log('🔧 [SFTP Settings] Başlatılıyor...');
        this.bindEvents();
        this.loadFTPConfig();
    }

    bindEvents() {
        // Şifre göster/gizle
        document.getElementById('togglePassword')?.addEventListener('click', () => {
            this.togglePasswordVisibility();
        });

        // Ayarları kaydet
        document.getElementById('saveFtpConfig')?.addEventListener('click', () => {
            this.saveFTPConfig();
        });

        // Bağlantıyı test et
        document.getElementById('testFtp')?.addEventListener('click', () => {
            this.testFTPConnection();
        });

        // Şimdi gönder
        document.getElementById('sendNow')?.addEventListener('click', () => {
            this.sendDatabaseNow();
        });

        console.log('✅ [SFTP Settings] Event listenerlar bağlandı');
    }

    togglePasswordVisibility() {
        const passwordInput = document.getElementById('ftpPassword');
        const toggleBtn = document.getElementById('togglePassword');
        const icon = toggleBtn.querySelector('i');

        if (passwordInput.type === 'password') {
            passwordInput.type = 'text';
            icon.classList.remove('fa-eye');
            icon.classList.add('fa-eye-slash');
        } else {
            passwordInput.type = 'password';
            icon.classList.remove('fa-eye-slash');
            icon.classList.add('fa-eye');
        }
    }

    async loadFTPConfig() {
        try {
            console.log('📥 [SFTP Settings] Konfigürasyon yükleniyor...');
            const response = await fetch('/api/ftp-config', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                const data = await response.json();
                console.log('✅ [SFTP Settings] Konfigürasyon yüklendi:', data);

                if (data.success && data.config) {
                    this.populateForm(data.config);
                }
            } else {
                console.error('❌ [SFTP Settings] Konfigürasyon yüklenemedi:', response.status);
            }
        } catch (error) {
            console.error('❌ [SFTP Settings] Hata:', error);
        }
    }

    populateForm(config) {
        // Form alanlarını doldur
        document.getElementById('ftpHost').value = config.ftp_host || '';
        document.getElementById('ftpUsername').value = config.ftp_username || '';
        
        // Şifre varsa placeholder göster
        if (config.ftp_password) {
            document.getElementById('ftpPassword').placeholder = '••••••••';
        }

        // Status güncelle (otomatik gönderim yok artık)
        const statusElement = document.getElementById('ftpStatus');
        statusElement.textContent = 'Manuel';
        statusElement.classList.remove('status-active');
        statusElement.classList.add('status-inactive');

        // Son gönderim zamanı
        if (config.last_sent_at) {
            const lastSent = new Date(config.last_sent_at);
            document.getElementById('lastSentAt').textContent = lastSent.toLocaleString('tr-TR');
        }
    }

    showToast(message, type = 'success') {
        // Toast container oluştur (yoksa)
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container';
            document.body.appendChild(toastContainer);
        }

        // Toast elementi oluştur
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
        toast.innerHTML = `
            <span class="toast-icon">${icon}</span>
            <span class="toast-message">${message}</span>
        `;

        toastContainer.appendChild(toast);

        // Animasyon için timeout
        setTimeout(() => toast.classList.add('show'), 10);

        // 3 saniye sonra kaldır
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    async saveFTPConfig() {
        try {
            // Form verilerini al
            const ftpHost = document.getElementById('ftpHost').value.trim();
            const ftpUsername = document.getElementById('ftpUsername').value.trim();
            const ftpPassword = document.getElementById('ftpPassword').value;

            // Validasyon
            if (!ftpHost || !ftpUsername) {
                this.showToast('Lütfen tüm zorunlu alanları doldurun', 'error');
                return;
            }

            // Şifre boşsa ve placeholder varsa, mevcut şifreyi koru
            const configData = {
                ftp_host: ftpHost,
                ftp_port: 22,  // SFTP sabit port
                ftp_username: ftpUsername,
                is_active: false  // Otomatik gönderim yok
            };

            // Şifre girilmişse ekle
            if (ftpPassword && ftpPassword !== '') {
                configData.ftp_password = ftpPassword;
            }

            console.log('💾 [SFTP Settings] Kaydediliyor...', configData);

            const response = await fetch('/api/ftp-config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(configData)
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('SFTP ayarları başarıyla kaydedildi', 'success');
                this.loadFTPConfig(); // Formu yeniden yükle
            } else {
                this.showToast(`Hata: ${result.message}`, 'error');
            }
        } catch (error) {
            console.error('❌ [SFTP Settings] Kaydetme hatası:', error);
            this.showToast('SFTP ayarları kaydedilemedi', 'error');
        }
    }

    async testFTPConnection() {
        try {
            const ftpHost = document.getElementById('ftpHost').value.trim();
            const ftpUsername = document.getElementById('ftpUsername').value.trim();
            const ftpPassword = document.getElementById('ftpPassword').value;

            if (!ftpHost || !ftpUsername || !ftpPassword) {
                this.showToast('Lütfen tüm alanları doldurun', 'error');
                return;
            }

            console.log('🔌 [SFTP Settings] Bağlantı test ediliyor...');
            
            const testBtn = document.getElementById('testFtp');
            testBtn.disabled = true;
            testBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Test Ediliyor...';

            const response = await fetch('/api/ftp-test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    ftp_host: ftpHost,
                    ftp_port: 22,  // SFTP sabit port
                    ftp_username: ftpUsername,
                    ftp_password: ftpPassword
                })
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('SFTP bağlantısı başarılı', 'success');
            } else {
                this.showToast(`SFTP bağlantısı başarısız: ${result.message}`, 'error');
            }

            testBtn.disabled = false;
            testBtn.innerHTML = '<i class="fas fa-plug"></i> Bağlantıyı Test Et';
        } catch (error) {
            console.error('❌ [SFTP Settings] Test hatası:', error);
            this.showToast('SFTP bağlantısı test edilemedi', 'error');
            
            const testBtn = document.getElementById('testFtp');
            testBtn.disabled = false;
            testBtn.innerHTML = '<i class="fas fa-plug"></i> Bağlantıyı Test Et';
        }
    }

    async sendDatabaseNow() {
        // Onay modalı göster
        if (!await this.showConfirmDialog('Veritabanı şimdi SFTP sunucusuna gönderilecek. Devam etmek istiyor musunuz?')) {
            return;
        }

        try {
            console.log('📤 [SFTP Settings] Veritabanı gönderiliyor...');
            
            const sendBtn = document.getElementById('sendNow');
            sendBtn.disabled = true;
            sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Gönderiliyor...';

            const response = await fetch('/api/ftp-send-now', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const result = await response.json();

            if (result.success) {
                this.showToast('Veritabanı başarıyla gönderildi', 'success');
                this.loadFTPConfig(); // Son gönderim zamanını güncelle
            } else {
                this.showToast(`Gönderim başarısız: ${result.message}`, 'error');
            }

            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Şimdi Gönder';
        } catch (error) {
            console.error('❌ [SFTP Settings] Gönderim hatası:', error);
            this.showToast('Veritabanı gönderilemedi', 'error');
            
            const sendBtn = document.getElementById('sendNow');
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Şimdi Gönder';
        }
    }

    showConfirmDialog(message) {
        return new Promise((resolve) => {
            // Modal oluştur
            const modal = document.createElement('div');
            modal.className = 'confirm-modal';
            modal.innerHTML = `
                <div class="confirm-modal-overlay"></div>
                <div class="confirm-modal-content">
                    <div class="confirm-modal-icon">
                        <i class="fas fa-question-circle"></i>
                    </div>
                    <div class="confirm-modal-message">${message}</div>
                    <div class="confirm-modal-buttons">
                        <button class="btn btn-secondary confirm-cancel">İptal</button>
                        <button class="btn btn-warning confirm-ok">Gönder</button>
                    </div>
                </div>
            `;

            document.body.appendChild(modal);

            // Animasyon için timeout
            setTimeout(() => modal.classList.add('show'), 10);

            // Buton event'leri
            const cancelBtn = modal.querySelector('.confirm-cancel');
            const okBtn = modal.querySelector('.confirm-ok');

            const closeModal = (result) => {
                modal.classList.remove('show');
                setTimeout(() => {
                    modal.remove();
                    resolve(result);
                }, 300);
            };

            cancelBtn.addEventListener('click', () => closeModal(false));
            okBtn.addEventListener('click', () => closeModal(true));
            modal.querySelector('.confirm-modal-overlay').addEventListener('click', () => closeModal(false));
        });
    }
}

// Sayfa yüklendiğinde başlat
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        new FTPSettings();
    });
} else {
    new FTPSettings();
}

