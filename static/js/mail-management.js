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
                container.innerHTML = `
                    <div class="no-recipients">
                        <i class="fas fa-envelope"></i>
                        <h3>Henüz mail alıcısı yok</h3>
                        <p>Yeni mail alıcısı eklemek için yukarıdaki butona tıklayın.</p>
                    </div>
                `;
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
                    <div class="recipient-alarm-levels">
                        <div class="alarm-level-badge ${recipient.receive_critical_alarms ? 'active' : 'inactive'}">
                            <i class="fas fa-exclamation-triangle"></i>
                            <span>Kritik Alarmlar</span>
                        </div>
                        <div class="alarm-level-badge ${recipient.receive_normal_alarms ? 'active' : 'inactive'}">
                            <i class="fas fa-info-circle"></i>
                            <span>Normal Alarmlar</span>
                        </div>
                    </div>
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
            document.getElementById('editReceiveCriticalAlarms').checked = recipient.receive_critical_alarms;
            document.getElementById('editReceiveNormalAlarms').checked = recipient.receive_normal_alarms;
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
                email: formData.get('email'),
                receive_critical_alarms: document.getElementById('receiveCriticalAlarms').checked,
                receive_normal_alarms: document.getElementById('receiveNormalAlarms').checked
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
                email: formData.get('email'),
                receive_critical_alarms: document.getElementById('editReceiveCriticalAlarms').checked,
                receive_normal_alarms: document.getElementById('editReceiveNormalAlarms').checked
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
                animation: slideIn 0.3s ease;
            `;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.remove();
            }, 3000);
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
                animation: slideIn 0.3s ease;
            `;
            
            document.body.appendChild(toast);
            
            setTimeout(() => {
                toast.remove();
            }, 3000);
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
