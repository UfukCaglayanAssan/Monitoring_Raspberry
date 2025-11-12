// Kullanıcı Yönetimi Sayfası JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.UserManagementPage === 'undefined') {
    window.UserManagementPage = class UserManagementPage {
        constructor() {
            this.init().catch(error => {
                console.error('Kullanıcı yönetimi sayfası başlatılırken hata:', error);
            });
        }

        async init() {
            console.log('Kullanıcı yönetimi sayfası başlatıldı');
            this.checkUserPermissions();
            this.bindEvents();
            await this.loadUsers();
        }

        checkUserPermissions() {
            // Kullanıcı rolünü kontrol et
            fetch('/api/user-info')
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.user) {
                        const userRole = data.user.role;
                        if (userRole !== 'admin') {
                            // Admin değilse sayfayı kapat
                            this.showToast('Bu sayfaya erişim için admin yetkisi gereklidir!', 'error');
                            // Ana sayfaya yönlendir
                            setTimeout(() => {
                                window.location.href = '/';
                            }, 2000);
                        }
                    }
                })
                .catch(error => {
                    console.error('Kullanıcı bilgisi alınırken hata:', error);
                });
        }

        bindEvents() {
            // Kullanıcı oluştur butonu
            const createUserBtn = document.getElementById('createUserBtn');
            if (createUserBtn) {
                createUserBtn.addEventListener('click', () => {
                    this.createUser();
                });
            }
        }

        async loadUsers() {
            try {
                const response = await fetch('/api/users', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    const result = await response.json();
                    if (result.success) {
                        this.displayUsers(result.users);
                    } else {
                        this.showToast('Kullanıcılar yüklenemedi: ' + result.message, 'error');
                        this.showErrorInTable(result.message);
                    }
                } else {
                    if (response.status === 403) {
                        this.showToast('Bu işlem için admin yetkisi gereklidir!', 'error');
                        this.showErrorInTable('Admin yetkisi gereklidir');
                    } else {
                        this.showToast('Kullanıcılar yüklenemedi!', 'error');
                        this.showErrorInTable('Kullanıcılar yüklenemedi');
                    }
                }
            } catch (error) {
                console.error('Kullanıcılar yüklenirken hata:', error);
                this.showToast('Kullanıcılar yüklenirken hata oluştu!', 'error');
                this.showErrorInTable('Hata: ' + error.message);
            }
        }

        displayUsers(users) {
            const tableBody = document.getElementById('usersTableBody');
            if (!tableBody) return;

            if (users.length === 0) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7" class="text-center">
                            <div class="no-data-message">
                                <i class="fas fa-users"></i>
                                <p>Henüz kullanıcı bulunmuyor</p>
                            </div>
                        </td>
                    </tr>
                `;
                return;
            }

            tableBody.innerHTML = users.map(user => {
                const roleBadge = user.role === 'admin' 
                    ? '<span class="badge badge-danger">Admin</span>' 
                    : '<span class="badge badge-secondary">Guest</span>';
                
                const statusBadge = user.is_active 
                    ? '<span class="badge badge-success">Aktif</span>' 
                    : '<span class="badge badge-warning">Pasif</span>';
                
                const createdDate = user.created_at 
                    ? new Date(user.created_at).toLocaleString('tr-TR') 
                    : '-';
                
                return `
                    <tr>
                        <td>${user.id}</td>
                        <td>${user.username}</td>
                        <td>${user.email}</td>
                        <td>${roleBadge}</td>
                        <td>${statusBadge}</td>
                        <td>${createdDate}</td>
                        <td>
                            <button class="btn btn-sm btn-warning reset-password-btn" data-user-id="${user.id}" data-user-email="${user.email}">
                                <i class="fas fa-key"></i>
                                Şifre Sıfırla
                            </button>
                        </td>
                    </tr>
                `;
            }).join('');

            // Şifre sıfırlama butonlarına event listener ekle
            document.querySelectorAll('.reset-password-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const userId = parseInt(e.target.closest('.reset-password-btn').getAttribute('data-user-id'));
                    const userEmail = e.target.closest('.reset-password-btn').getAttribute('data-user-email');
                    this.resetUserPassword(userId, userEmail);
                });
            });
        }

        showErrorInTable(message) {
            const tableBody = document.getElementById('usersTableBody');
            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7" class="text-center">
                            <div class="no-data-message">
                                <i class="fas fa-exclamation-triangle"></i>
                                <p>${message}</p>
                            </div>
                        </td>
                    </tr>
                `;
            }
        }

        async createUser() {
            const email = document.getElementById('newUserEmail').value.trim();
            const password = document.getElementById('newUserPassword').value;
            const role = document.getElementById('newUserRole').value;

            if (!email || !password) {
                this.showToast('E-posta ve şifre gerekli!', 'warning');
                return;
            }

            if (password.length < 6) {
                this.showToast('Şifre en az 6 karakter olmalı!', 'warning');
                return;
            }

            // Email format kontrolü
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(email)) {
                this.showToast('Geçerli bir e-posta adresi girin!', 'warning');
                return;
            }

            try {
                const createBtn = document.getElementById('createUserBtn');
                createBtn.disabled = true;
                createBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Oluşturuluyor...';

                const response = await fetch('/api/users', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        email: email,
                        password: password,
                        role: role
                    })
                });

                const result = await response.json();

                if (result.success) {
                    this.showToast('Kullanıcı başarıyla oluşturuldu!', 'success');
                    // Formu temizle
                    document.getElementById('newUserEmail').value = '';
                    document.getElementById('newUserPassword').value = '';
                    document.getElementById('newUserRole').value = 'guest';
                    // Kullanıcı listesini yenile
                    await this.loadUsers();
                } else {
                    this.showToast('Hata: ' + result.message, 'error');
                }

                createBtn.disabled = false;
                createBtn.innerHTML = '<i class="fas fa-user-plus"></i> Kullanıcı Oluştur';
            } catch (error) {
                console.error('Kullanıcı oluşturulurken hata:', error);
                this.showToast('Kullanıcı oluşturulurken hata oluştu!', 'error');
                const createBtn = document.getElementById('createUserBtn');
                createBtn.disabled = false;
                createBtn.innerHTML = '<i class="fas fa-user-plus"></i> Kullanıcı Oluştur';
            }
        }

        async resetUserPassword(userId, userEmail) {
            if (!confirm(`${userEmail} kullanıcısının şifresini sıfırlamak istediğinize emin misiniz?`)) {
                return;
            }

            try {
                const response = await fetch(`/api/users/${userId}/reset-password`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();

                if (result.success) {
                    this.showResetPasswordModal(result.new_password);
                    this.showToast('Şifre başarıyla sıfırlandı!', 'success');
                } else {
                    this.showToast('Hata: ' + result.message, 'error');
                }
            } catch (error) {
                console.error('Şifre sıfırlanırken hata:', error);
                this.showToast('Şifre sıfırlanırken hata oluştu!', 'error');
            }
        }

        showResetPasswordModal(newPassword) {
            const modal = document.getElementById('resetPasswordModal');
            const passwordDisplay = document.getElementById('resetPasswordDisplay');
            
            if (modal && passwordDisplay) {
                passwordDisplay.textContent = newPassword;
                modal.style.display = 'flex';
            }
        }

        showToast(message, type = 'info') {
            // Toast notification göster
            const toast = document.createElement('div');
            toast.className = 'toast';
            
            // Toast content div'i oluştur
            const toastContent = document.createElement('div');
            toastContent.className = 'toast-content';
            
            // İkon ekle
            const toastIcon = document.createElement('div');
            toastIcon.className = 'toast-icon';
            
            // Tip'e göre ikon ve renk ayarla
            if (type === 'error') {
                toastIcon.innerHTML = '<i class="fas fa-exclamation-triangle"></i>';
                toastIcon.style.background = '#ef4444';
                toastContent.style.background = '#dc3545';
            } else if (type === 'success') {
                toastIcon.innerHTML = '<i class="fas fa-check"></i>';
                toastIcon.style.background = '#10b981';
                toastContent.style.background = '#28a745';
            } else if (type === 'warning') {
                toastIcon.innerHTML = '<i class="fas fa-exclamation-circle"></i>';
                toastIcon.style.background = '#f59e0b';
                toastContent.style.background = '#ffc107';
            } else { // info
                toastIcon.innerHTML = '<i class="fas fa-info-circle"></i>';
                toastIcon.style.background = '#3b82f6';
                toastContent.style.background = '#17a2b8';
            }
            
            // Mesaj ekle
            const toastMessage = document.createElement('span');
            toastMessage.className = 'toast-message';
            toastMessage.textContent = message;
            toastMessage.style.color = 'white';
            
            // Yapıyı oluştur
            toastContent.appendChild(toastIcon);
            toastContent.appendChild(toastMessage);
            toast.appendChild(toastContent);
            
            // Toast'un kendisine background verme
            toast.style.background = 'transparent';
            toast.style.border = 'none';
            
            document.body.appendChild(toast);
            
            // Animasyon
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => {
                    if (toast.parentNode) {
                        document.body.removeChild(toast);
                    }
                }, 300);
            }, 3000);
        }

        isUserManagementPageActive() {
            // Kullanıcı yönetimi sayfasında olup olmadığımızı kontrol et
            const userManagementPage = document.querySelector('.user-management-page');
            return userManagementPage && userManagementPage.style.display !== 'none';
        }
    };
}

// Global fonksiyonlar (modal için)
function closeResetPasswordModal() {
    const modal = document.getElementById('resetPasswordModal');
    if (modal) {
        modal.style.display = 'none';
    }
}

function copyPassword() {
    const passwordDisplay = document.getElementById('resetPasswordDisplay');
    if (passwordDisplay) {
        const password = passwordDisplay.textContent;
        navigator.clipboard.writeText(password).then(() => {
            // Kopyalama başarılı mesajı göster
            const toast = document.createElement('div');
            toast.className = 'toast';
            toast.innerHTML = `
                <div class="toast-content" style="background: #28a745;">
                    <div class="toast-icon" style="background: #10b981;">
                        <i class="fas fa-check"></i>
                    </div>
                    <span class="toast-message" style="color: white;">Şifre kopyalandı!</span>
                </div>
            `;
            document.body.appendChild(toast);
            setTimeout(() => toast.classList.add('show'), 10);
            setTimeout(() => {
                toast.classList.remove('show');
                setTimeout(() => {
                    if (toast.parentNode) {
                        document.body.removeChild(toast);
                    }
                }, 300);
            }, 2000);
        }).catch(err => {
            console.error('Kopyalama hatası:', err);
        });
    }
}

// Sayfa yüklendiğinde başlat
function initUserManagementPage() {
    console.log('🔧 initUserManagementPage() çağrıldı');
    if (!window.userManagementPage) {
        window.userManagementPage = new window.UserManagementPage();
    } else {
        // Mevcut instance'ı yeniden başlat
        console.log('🔄 Mevcut UserManagementPage instance yeniden başlatılıyor');
        window.userManagementPage.init();
    }
}

// Global olarak erişilebilir yap
window.initUserManagementPage = initUserManagementPage;

// Script yüklendiğinde otomatik init
console.log('🔧 User-management.js yüklendi, otomatik init başlatılıyor...');
initUserManagementPage();

