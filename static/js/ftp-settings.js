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

        document.getElementById('ftpActive').checked = config.is_active || false;

        // Status güncelle
        const statusElement = document.getElementById('ftpStatus');
        if (config.is_active) {
            statusElement.textContent = 'Aktif';
            statusElement.classList.remove('status-inactive');
            statusElement.classList.add('status-active');
        } else {
            statusElement.textContent = 'Pasif';
            statusElement.classList.remove('status-active');
            statusElement.classList.add('status-inactive');
        }

        // Son gönderim zamanı
        if (config.last_sent_at) {
            const lastSent = new Date(config.last_sent_at);
            document.getElementById('lastSentAt').textContent = lastSent.toLocaleString('tr-TR');
        }
    }

    async saveFTPConfig() {
        try {
            // Form verilerini al
            const ftpHost = document.getElementById('ftpHost').value.trim();
            const ftpUsername = document.getElementById('ftpUsername').value.trim();
            const ftpPassword = document.getElementById('ftpPassword').value;

            // Validasyon
            if (!ftpHost || !ftpUsername) {
                alert('⚠️ Lütfen tüm zorunlu alanları doldurun!');
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
                alert('✅ SFTP ayarları başarıyla kaydedildi!');
                this.loadFTPConfig(); // Formu yeniden yükle
            } else {
                alert(`❌ Hata: ${result.message}`);
            }
        } catch (error) {
            console.error('❌ [SFTP Settings] Kaydetme hatası:', error);
            alert('❌ SFTP ayarları kaydedilemedi!');
        }
    }

    async testFTPConnection() {
        try {
            const ftpHost = document.getElementById('ftpHost').value.trim();
            const ftpUsername = document.getElementById('ftpUsername').value.trim();
            const ftpPassword = document.getElementById('ftpPassword').value;

            if (!ftpHost || !ftpUsername || !ftpPassword) {
                alert('⚠️ Lütfen tüm alanları doldurun!');
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
                alert('✅ SFTP bağlantısı başarılı!');
            } else {
                alert(`❌ SFTP bağlantısı başarısız: ${result.message}`);
            }

            testBtn.disabled = false;
            testBtn.innerHTML = '<i class="fas fa-plug"></i> Bağlantıyı Test Et';
        } catch (error) {
            console.error('❌ [SFTP Settings] Test hatası:', error);
            alert('❌ SFTP bağlantısı test edilemedi!');
            
            const testBtn = document.getElementById('testFtp');
            testBtn.disabled = false;
            testBtn.innerHTML = '<i class="fas fa-plug"></i> Bağlantıyı Test Et';
        }
    }

    async sendDatabaseNow() {
        if (!confirm('🚀 Veritabanı şimdi SFTP sunucusuna gönderilecek. Devam etmek istiyor musunuz?')) {
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
                alert('✅ Veritabanı başarıyla gönderildi!');
                this.loadFTPConfig(); // Son gönderim zamanını güncelle
            } else {
                alert(`❌ Gönderim başarısız: ${result.message}`);
            }

            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Şimdi Gönder';
        } catch (error) {
            console.error('❌ [SFTP Settings] Gönderim hatası:', error);
            alert('❌ Veritabanı gönderilemedi!');
            
            const sendBtn = document.getElementById('sendNow');
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Şimdi Gönder';
        }
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

