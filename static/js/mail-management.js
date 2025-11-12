// Mail Management Sayfası JavaScript
if (typeof window.MailManagementPage === 'undefined') {
    window.MailManagementPage = class MailManagementPage {
        constructor() {
            this.recipients = [];
            this.init();
        }

        async init() {
            this.bindEvents();
            await this.loadRecipients();
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
            const adminButtons = [
                'addRecipientBtn'
            ];
            
            adminButtons.forEach(buttonId => {
                const button = document.getElementById(buttonId);
                if (button) {
                    button.disabled = true;
                    button.textContent = '🔒 Admin Yetkisi Gerekli';
                    button.classList.add('btn-disabled');
                }
            });

            // Tablo içindeki düzenle/sil butonlarını da devre dışı bırak
            document.querySelectorAll('.btn-edit, .btn-delete').forEach(button => {
                button.disabled = true;
                button.textContent = '🔒';
                button.classList.add('btn-disabled');
            });
        }

        bindEvents() {
            // Yeni alıcı ekleme butonu
            document.getElementById('addRecipientBtn')?.addEventListener('click', () => {
                this.showAddModal();
            });

            // Modal kapatma
            document.querySelectorAll('.close').forEach(closeBtn => {
                closeBtn.addEventListener('click', (e) => {
                    this.hideAllModals();
                });
            });

            // Modal dışına tıklama
            window.addEventListener('click', (e) => {
                if (e.target.classList.contains('modal')) {
                    this.hideAllModals();
                }
            });

            // Form gönderimi
            document.getElementById('addRecipientForm')?.addEventListener('submit', (e) => {
                e.preventDefault();
                this.addRecipient();
            });

            document.getElementById('editRecipientForm')?.addEventListener('submit', (e) => {
                e.preventDefault();
                this.updateRecipient();
            });

            // İptal butonları
            document.getElementById('cancelAdd')?.addEventListener('click', () => {
                this.hideAllModals();
            });

            document.getElementById('cancelEdit')?.addEventListener('click', () => {
                this.hideAllModals();
            });

            // Dil değişikliği dinleyicisi
            window.addEventListener('languageChanged', (e) => {
                this.onLanguageChanged(e.detail.language);
            });
        }

        onLanguageChanged(language) {
            // UI metinlerini güncelle
            const elements = document.querySelectorAll('[data-tr], [data-en]');
            elements.forEach(element => {
                if (language === 'en' && element.hasAttribute('data-en')) {
                    element.textContent = element.getAttribute('data-en');
                } else if (language === 'tr' && element.hasAttribute('data-tr')) {
                    element.textContent = element.getAttribute('data-tr');
                }
            });
        }

        async loadRecipients() {
            try {
                this.showLoading();
                
                const response = await fetch('/api/mail-recipients', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const data = await response.json();
                
                if (data.success) {
                    this.recipients = data.recipients || [];
                    this.renderRecipients();
                } else {
                    console.error('Mail alıcıları yüklenirken hata:', data.message);
                    this.showError('Mail alıcıları yüklenirken hata oluştu');
                }
            } catch (error) {
                console.error('Mail alıcıları yüklenirken hata:', error);
                this.showError('Mail alıcıları yüklenirken hata oluştu');
            } finally {
                this.hideLoading();
            }
        }

        renderRecipients() {
            const container = document.getElementById('recipientsList');
            if (!container) return;

            if (this.recipients.length === 0) {
                const t = window.translationManager ? window.translationManager.t.bind(window.translationManager) : (key) => key;
                container.innerHTML = `
                    <div class="no-recipients">
                        <i class="fas fa-envelope"></i>
                        <h3 data-i18n="mailManagement.noRecipients">${t('mailManagement.noRecipients')}</h3>
                        <p data-i18n="mailManagement.noRecipientsMessage">${t('mailManagement.noRecipientsMessage')}</p>
                    </div>
                `;
                // Çevirileri uygula
                if (window.translationManager && window.translationManager.initialized) {
                    window.translationManager.updateAllElements();
                }
                return;
            }

            container.innerHTML = this.recipients.map(recipient => `
                <div class="recipient-card">
                    <div class="recipient-header">
                        <h3 class="recipient-name">${recipient.name}</h3>
                        <div class="recipient-actions">
                            <button class="btn btn-secondary" onclick="mailManagementPage.editRecipient(${recipient.id})">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-danger" onclick="mailManagementPage.deleteRecipient(${recipient.id})">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                    <div class="recipient-email">${recipient.email}</div>
                    <div class="recipient-date">Eklenme: ${this.formatDate(recipient.created_at)}</div>
                </div>
            `).join('');
        }

        showAddModal() {
            document.getElementById('addRecipientModal').style.display = 'block';
            document.getElementById('recipientName').focus();
        }

        showEditModal(recipient) {
            document.getElementById('editRecipientId').value = recipient.id;
            document.getElementById('editRecipientName').value = recipient.name;
            document.getElementById('editRecipientEmail').value = recipient.email;
            document.getElementById('editRecipientModal').style.display = 'block';
            document.getElementById('editRecipientName').focus();
        }

        hideAllModals() {
            document.getElementById('addRecipientModal').style.display = 'none';
            document.getElementById('editRecipientModal').style.display = 'none';
            this.clearForms();
        }

        clearForms() {
            document.getElementById('addRecipientForm').reset();
            document.getElementById('editRecipientForm').reset();
        }

        isEmailExists(email) {
            // Mevcut alıcılar listesinde email kontrolü
            return this.recipients.some(recipient => 
                recipient.email.toLowerCase() === email.toLowerCase()
            );
        }

        isEmailExistsForUpdate(email, currentId) {
            // Mevcut alıcılar listesinde email kontrolü (kendi ID'si hariç)
            return this.recipients.some(recipient => 
                recipient.email.toLowerCase() === email.toLowerCase() && 
                recipient.id !== currentId
            );
        }

        async addRecipient() {
            const formData = new FormData(document.getElementById('addRecipientForm'));
            const data = {
                name: formData.get('name'),
                email: formData.get('email')
            };

            // Email tekrar kontrolü
            if (this.isEmailExists(data.email)) {
                this.showError('Bu email adresi zaten kayıtlı!');
                return;
            }

            try {
                const response = await fetch('/api/mail-recipients', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                const result = await response.json();
                
                if (result.success) {
                    this.hideAllModals();
                    await this.loadRecipients();
                    this.showSuccess(result.message);
                } else {
                    this.showError(result.message);
                }
            } catch (error) {
                console.error('Mail alıcısı eklenirken hata:', error);
                this.showError('Mail alıcısı eklenirken hata oluştu');
            }
        }

        async updateRecipient() {
            const formData = new FormData(document.getElementById('editRecipientForm'));
            const data = {
                id: parseInt(formData.get('id')),
                name: formData.get('name'),
                email: formData.get('email')
            };

            // Email tekrar kontrolü (kendi ID'si hariç)
            if (this.isEmailExistsForUpdate(data.email, data.id)) {
                this.showError('Bu email adresi başka bir alıcı tarafından kullanılıyor!');
                return;
            }

            try {
                const response = await fetch('/api/mail-recipients', {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });

                const result = await response.json();
                
                if (result.success) {
                    this.hideAllModals();
                    await this.loadRecipients();
                    this.showSuccess(result.message);
                } else {
                    this.showError(result.message);
                }
            } catch (error) {
                console.error('Mail alıcısı güncellenirken hata:', error);
                this.showError('Mail alıcısı güncellenirken hata oluştu');
            }
        }

        async deleteRecipient(recipientId) {
            if (!confirm('Bu mail alıcısını silmek istediğinizden emin misiniz?')) {
                return;
            }

            try {
                const response = await fetch(`/api/mail-recipients/${recipientId}`, {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });

                const result = await response.json();
                
                if (result.success) {
                    await this.loadRecipients();
                    this.showSuccess(result.message);
                } else {
                    this.showError(result.message);
                }
            } catch (error) {
                console.error('Mail alıcısı silinirken hata:', error);
                this.showError('Mail alıcısı silinirken hata oluştu');
            }
        }

        editRecipient(recipientId) {
            const recipient = this.recipients.find(r => r.id === recipientId);
            if (recipient) {
                this.showEditModal(recipient);
            }
        }

        showLoading() {
            const container = document.getElementById('recipientsList');
            if (container) {
                container.innerHTML = `
                    <div class="loading-spinner">
                        <div class="spinner"></div>
                    </div>
                `;
            }
        }

        hideLoading() {
            // Loading zaten renderRecipients'da gizleniyor
        }

        showSuccess(message) {
            // Basit toast mesajı
            const toast = document.createElement('div');
            toast.className = 'toast toast-success';
            toast.textContent = message;
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #28a745;
                color: white;
                padding: 15px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                z-index: 10000;
                font-size: 14px;
                font-weight: 500;
                min-width: 200px;
                text-align: center;
                opacity: 0;
                transform: translateX(100%);
                transition: all 0.3s ease;
            `;
            
            document.body.appendChild(toast);
            
            // Animasyon için kısa gecikme
            setTimeout(() => {
                toast.style.opacity = '1';
                toast.style.transform = 'translateX(0)';
            }, 10);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    toast.remove();
                }, 300);
            }, 4000); // 4 saniye göster
        }

        showError(message) {
            // Basit toast mesajı
            const toast = document.createElement('div');
            toast.className = 'toast toast-error';
            toast.textContent = message;
            toast.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                background: #dc3545;
                color: white;
                padding: 15px 20px;
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                z-index: 10000;
                font-size: 14px;
                font-weight: 500;
                min-width: 200px;
                text-align: center;
                opacity: 0;
                transform: translateX(100%);
                transition: all 0.3s ease;
            `;
            
            document.body.appendChild(toast);
            
            // Animasyon için kısa gecikme
            setTimeout(() => {
                toast.style.opacity = '1';
                toast.style.transform = 'translateX(0)';
            }, 10);
            
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateX(100%)';
                setTimeout(() => {
                    toast.remove();
                }, 300);
            }, 4000); // 4 saniye göster
        }

        formatDate(dateString) {
            const date = new Date(dateString);
            return date.toLocaleString('tr-TR', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        }
    };
}

// Sayfa yüklendiğinde başlat
function initMailManagementPage() {
    console.log('🔧 initMailManagementPage() çağrıldı');
    if (!window.mailManagementPage) {
        console.log('🆕 Yeni MailManagementPage instance oluşturuluyor');
        window.mailManagementPage = new window.MailManagementPage();
    } else {
        console.log('🔄 MailManagementPage instance yeniden başlatılıyor');
        window.mailManagementPage.init();
    }
}

// Global olarak erişilebilir yap
window.initMailManagementPage = initMailManagementPage;

// Script yüklendiğinde otomatik init
console.log('🔧 Mail-management.js yüklendi, otomatik init başlatılıyor...');
initMailManagementPage();