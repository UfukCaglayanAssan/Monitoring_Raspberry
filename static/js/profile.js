// Profile Sayfası JavaScript
class ProfilePage {
    constructor() {
        this.init();
    }

    init() {
        console.log('Profile sayfası başlatıldı');
        this.bindEvents();
        this.loadProfileData();
        this.checkUserPermissions();
    }

    bindEvents() {
        // Şifre değiştirme formu
        const passwordForm = document.getElementById('passwordForm');
        if (passwordForm) {
            passwordForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.changePassword();
            });
        }
        console.log('Profile sayfası event listener\'ları bağlandı');
    }

    loadProfileData() {
        console.log('Profil verileri yükleniyor...');
        // Gerçek uygulamada API'den profil verileri gelecek
    }

    checkUserPermissions() {
        // Kullanıcı rolünü kontrol et
        fetch('/api/user-info')
            .then(response => response.json())
            .then(data => {
                if (data.success && data.user) {
                    const userRole = data.user.role;
                    if (userRole !== 'admin') {
                        // Guest kullanıcısı için şifre değiştirme butonunu devre dışı bırak
                        this.disablePasswordChange();
                    }
                }
            })
            .catch(error => {
                console.error('Kullanıcı bilgisi alınırken hata:', error);
            });
    }

    disablePasswordChange() {
        // Şifre değiştirme butonunu devre dışı bırak
        const changePasswordBtn = document.getElementById('changePasswordBtn');
        if (changePasswordBtn) {
            changePasswordBtn.disabled = true;
            changePasswordBtn.textContent = '🔒 Admin Yetkisi Gerekli';
            changePasswordBtn.classList.add('btn-disabled');
        }

        // Şifre alanlarını da devre dışı bırak
        const passwordInputs = document.querySelectorAll('#passwordForm input');
        passwordInputs.forEach(input => {
            input.disabled = true;
            input.placeholder = 'Admin yetkisi gerekli';
        });
    }

    async changePassword() {
        const currentPassword = document.getElementById('currentPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;

        // Validasyon
        if (newPassword !== confirmPassword) {
            this.showMessage('Yeni şifreler eşleşmiyor!', 'error');
            return;
        }

        if (newPassword.length < 6) {
            this.showMessage('Yeni şifre en az 6 karakter olmalı!', 'error');
            return;
        }

        try {
            const response = await fetch('/api/change-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    currentPassword: currentPassword,
                    newPassword: newPassword,
                    confirmPassword: confirmPassword
                })
            });

            const data = await response.json();

            if (data.success) {
                this.showMessage('Şifre başarıyla değiştirildi!', 'success');
                document.getElementById('passwordForm').reset();
            } else {
                this.showMessage(data.message || 'Şifre değiştirilemedi!', 'error');
            }
        } catch (error) {
            console.error('Şifre değiştirme hatası:', error);
            this.showMessage('Bir hata oluştu!', 'error');
        }
    }

    showMessage(message, type) {
        // Toast mesajı göster
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

// Global instance oluştur
window.profilePage = new ProfilePage();



