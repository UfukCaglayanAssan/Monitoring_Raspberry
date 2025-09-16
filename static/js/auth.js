// Authentication JavaScript
class AuthManager {
    constructor() {
        this.currentUser = null;
        this.init();
    }

    init() {
        // Sayfa yüklendiğinde kullanıcı bilgilerini kontrol et
        this.checkAuthStatus();
        
        // Global event listener'lar
        this.bindEvents();
    }

    bindEvents() {
        // Login form
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => this.handleLogin(e));
        }

        // Logout button
        const logoutBtn = document.getElementById('logoutBtn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', () => this.handleLogout());
        }

        // Password change form
        const passwordForm = document.getElementById('passwordForm');
        if (passwordForm) {
            passwordForm.addEventListener('submit', (e) => this.handlePasswordChange(e));
        }
    }

    async checkAuthStatus() {
        // Login sayfasındaysa auth check yapma
        if (window.location.pathname === '/login') {
            return;
        }
        
        try {
            const response = await fetch('/api/user-info');
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.currentUser = data.user;
                    this.updateUI();
                } else {
                    this.redirectToLogin();
                }
            } else {
                this.redirectToLogin();
            }
        } catch (error) {
            console.log('Auth check failed:', error);
            this.redirectToLogin();
        }
    }

    async handleLogin(e) {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        if (!email || !password) {
            this.showToast('E-posta ve şifre gerekli', 'error');
            return;
        }

        try {
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();
            
            if (data.success) {
                this.currentUser = data.user;
                window.location.href = '/';
            } else {
                this.showToast(data.message || 'Giriş başarısız', 'error');
            }
        } catch (error) {
            this.showToast('Giriş hatası: ' + error.message, 'error');
        }
    }

    async handleLogout() {
        try {
            const response = await fetch('/api/logout', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            const data = await response.json();
            
            if (data.success) {
                this.currentUser = null;
                window.location.href = '/login';
            } else {
                this.showToast('Çıkış hatası', 'error');
            }
        } catch (error) {
            this.showToast('Çıkış hatası: ' + error.message, 'error');
        }
    }

    async handlePasswordChange(e) {
        e.preventDefault();
        
        const currentPassword = document.getElementById('currentPassword').value;
        const newPassword = document.getElementById('newPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        
        if (!currentPassword || !newPassword || !confirmPassword) {
            this.showToast('Tüm alanlar gerekli', 'error');
            return;
        }

        if (newPassword !== confirmPassword) {
            this.showToast('Yeni şifreler eşleşmiyor', 'error');
            return;
        }

        if (newPassword.length < 6) {
            this.showToast('Şifre en az 6 karakter olmalı', 'error');
            return;
        }

        try {
            const response = await fetch('/api/change-password', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    currentPassword,
                    newPassword,
                    confirmPassword
                })
            });

            const data = await response.json();
            
            if (data.success) {
                this.showToast('Şifre başarıyla değiştirildi', 'success');
                document.getElementById('passwordForm').reset();
            } else {
                this.showToast(data.message || 'Şifre değiştirilemedi', 'error');
            }
        } catch (error) {
            this.showToast('Şifre değiştirme hatası: ' + error.message, 'error');
        }
    }

    updateUI() {
        // Navbar kullanıcı bilgilerini güncelle
        const userNameElement = document.querySelector('.user-name');
        const userEmailElement = document.querySelector('.user-email');
        
        if (userNameElement && this.currentUser) {
            userNameElement.textContent = this.currentUser.username;
        }
        
        if (userEmailElement && this.currentUser) {
            userEmailElement.textContent = this.currentUser.email;
        }

        // Profil sayfası bilgilerini güncelle
        const profileUsername = document.getElementById('profileUsername');
        const profileEmail = document.getElementById('profileEmail');
        const profileRole = document.getElementById('profileRole');
        
        if (profileUsername && this.currentUser) {
            profileUsername.textContent = this.currentUser.username;
        }
        
        if (profileEmail && this.currentUser) {
            profileEmail.textContent = this.currentUser.email;
        }
        
        if (profileRole && this.currentUser) {
            profileRole.textContent = this.currentUser.role;
            profileRole.className = `role-badge ${this.currentUser.role}`;
        }

        // Admin/Guest yetki kontrolü
        this.updatePermissions();
    }

    updatePermissions() {
        if (!this.currentUser) return;

        const isAdmin = this.currentUser.role === 'admin';
        
        // Admin-only elementleri bul ve kontrol et
        const adminElements = document.querySelectorAll('[data-requires-admin]');
        adminElements.forEach(element => {
            if (isAdmin) {
                element.style.display = '';
                element.disabled = false;
            } else {
                element.style.display = 'none';
                element.disabled = true;
            }
        });

        // Admin-only butonları devre dışı bırak
        const adminButtons = document.querySelectorAll('.btn[data-requires-admin]');
        adminButtons.forEach(button => {
            if (isAdmin) {
                button.disabled = false;
                button.style.opacity = '1';
            } else {
                button.disabled = true;
                button.style.opacity = '0.5';
            }
        });
    }

    updateAdminControls() {
        const isAdmin = this.currentUser && this.currentUser.role === 'admin';
        
        // Konfigürasyon butonlarını kontrol et
        const configButtons = document.querySelectorAll('[data-requires-admin]');
        configButtons.forEach(button => {
            if (isAdmin) {
                button.disabled = false;
                button.style.opacity = '1';
                button.style.cursor = 'pointer';
            } else {
                button.disabled = true;
                button.style.opacity = '0.5';
                button.style.cursor = 'not-allowed';
            }
        });

        // Şifre değiştirme butonunu kontrol et
        const changePasswordBtn = document.getElementById('changePasswordBtn');
        if (changePasswordBtn) {
            if (isAdmin) {
                changePasswordBtn.disabled = false;
                changePasswordBtn.style.opacity = '1';
            } else {
                changePasswordBtn.disabled = true;
                changePasswordBtn.style.opacity = '0.5';
                changePasswordBtn.textContent = 'Şifre Değiştirilemez (Guest)';
            }
        }
    }

    redirectToLogin() {
        if (window.location.pathname !== '/login') {
            window.location.href = '/login';
        }
    }

    showToast(message, type = 'info') {
        // Toast mesajı göster (mevcut toast sistemini kullan)
        if (window.showToast) {
            window.showToast(message, type);
        } else {
            // Basit toast mesajı oluştur
            const toast = document.createElement('div');
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: ${type === 'error' ? '#e74c3c' : type === 'success' ? '#27ae60' : '#3498db'};
                color: white;
                padding: 12px 20px;
                border-radius: 4px;
                z-index: 10000;
                font-weight: 500;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            `;
            toast.textContent = message;
            document.body.appendChild(toast);
            
            setTimeout(() => {
                document.body.removeChild(toast);
            }, 3000);
        }
    }

    isAdmin() {
        return this.currentUser && this.currentUser.role === 'admin';
    }

    isLoggedIn() {
        return this.currentUser !== null;
    }
}

// Global auth manager instance
window.authManager = new AuthManager();

// Global fonksiyonlar
window.isAdmin = () => window.authManager.isAdmin();
window.isLoggedIn = () => window.authManager.isLoggedIn();
