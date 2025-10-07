// Veri Alma Sayfası JavaScript
// Class'ın zaten tanımlanıp tanımlanmadığını kontrol et
if (typeof window.DataRetrieval === 'undefined') {
    window.DataRetrieval = class DataRetrieval {
    constructor() {
        this.operations = [];
        this.isDataRetrievalMode = false;
        this.retrievalConfig = null;
        this.retrievedData = [];
        this.init();
    }

    init() {
        this.bindEvents();
        this.loadOperations();
    }

    bindEvents() {
        // Toplu işlem butonları
        document.getElementById('readAllBtn').addEventListener('click', () => {
            this.handleReadAll();
        });

        document.getElementById('resetAllBtn').addEventListener('click', () => {
            this.handleResetAll();
        });

        // Veri alma butonu
        document.getElementById('getDataBtn').addEventListener('click', () => {
            this.handleGetData();
        });

        // Form validasyonu
        document.getElementById('dataArmSelect').addEventListener('change', () => {
            this.validateForm();
        });

        document.getElementById('dataAddressInput').addEventListener('input', () => {
            this.updateDataTypeOptions();
            this.validateForm();
        });

        document.getElementById('dataValueSelect').addEventListener('change', () => {
            this.validateForm();
        });
    }

    updateDataTypeOptions() {
        const address = document.getElementById('dataAddressInput').value;
        const valueSelect = document.getElementById('dataValueSelect');
        
        // Mevcut seçimi temizle
        valueSelect.innerHTML = '<option value="">Seçiniz</option>';
        
        if (address === '0') {
            // Kol verileri (adres 0)
            const kolOptions = [
                { value: '10', text: 'Akım' },
                { value: '11', text: 'Nem' },
                { value: '12', text: 'Modül Sıcaklığı' },
                { value: '13', text: 'Ortam Sıcaklığı' }
            ];
            
            kolOptions.forEach(option => {
                const optionElement = document.createElement('option');
                optionElement.value = option.value;
                optionElement.textContent = option.text;
                valueSelect.appendChild(optionElement);
            });
        } else {
            // Batarya verileri (adres 1-255)
            const bataryaOptions = [
                { value: '10', text: 'Gerilim (V)' },
                { value: '11', text: 'SOH (%)' },
                { value: '12', text: 'Sıcaklık (°C)' },
                { value: '13', text: 'NTC2 (°C)' },
                { value: '14', text: 'NTC3 (°C)' },
                { value: '126', text: 'SOC (%)' }
            ];
            
            bataryaOptions.forEach(option => {
                const optionElement = document.createElement('option');
                optionElement.value = option.value;
                optionElement.textContent = option.text;
                valueSelect.appendChild(optionElement);
            });
        }
    }

    validateForm() {
        const arm = document.getElementById('dataArmSelect').value;
        const address = document.getElementById('dataAddressInput').value;
        const value = document.getElementById('dataValueSelect').value;
        
        const isValid = arm && address && value;
        document.getElementById('getDataBtn').disabled = !isValid;
        
        return isValid;
    }

    async handleReadAll() {
        const armSelect = document.getElementById('batchArmSelect');
        const selectedArm = armSelect.value;
        
        if (!selectedArm) {
            this.showToast('Lütfen bir kol seçiniz', 'error');
            return;
        }

        this.showLoading('Tümünü oku komutu gönderiliyor...');

        try {
            const response = await fetch('/api/commands', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    command: 'readAll',
                    arm: selectedArm === '5' ? 5 : parseInt(selectedArm)
                })
            });

            if (response.ok) {
                this.showToast('Tümünü oku komutu başarıyla gönderildi', 'success');
                
                // Tümünü oku işlemi için veri alma modu başlat
                if (selectedArm !== '5') {
                    // Belirli bir kol seçildiyse, o kol için veri alma modu başlat
                    await this.startDataRetrievalMode({
                        arm: parseInt(selectedArm),
                        address: 0, // Tümünü Oku işlemi için adres 0
                        value: 0, // Tümünü Oku işlemi için değer 0
                        valueText: 'Tüm Veriler'
                    });
                }
    } else {
                throw new Error('Komut gönderilemedi');
            }
        } catch (error) {
            console.error('ReadAll hatası:', error);
            this.showToast('Komut gönderilirken hata oluştu', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async handleResetAll() {
        const armSelect = document.getElementById('batchArmSelect');
        const selectedArm = armSelect.value;
        
        if (!selectedArm) {
            this.showToast('Lütfen bir kol seçiniz', 'error');
            return;
        }

        this.showLoading('Tümünü sıfırla komutu gönderiliyor...');

        try {
            const response = await fetch('/api/commands', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    command: 'resetAll',
                    arm: selectedArm === '5' ? 5 : parseInt(selectedArm)
                })
            });

            if (response.ok) {
                this.addOperation('reset', `Tümünü Sıfırla - ${selectedArm === '5' ? 'Tüm Kollar' : `Kol ${selectedArm}`}`);
                this.showToast('Tümünü sıfırla komutu başarıyla gönderildi', 'success');
            } else {
                throw new Error('Komut gönderilemedi');
            }
        } catch (error) {
            console.error('ResetAll hatası:', error);
            this.showToast('Komut gönderilirken hata oluştu', 'error');
        } finally {
            this.hideLoading();
        }
    }

    async handleGetData() {
        if (!this.validateForm()) {
            this.showToast('Lütfen tüm alanları doldurunuz', 'error');
            return;
        }

        const arm = document.getElementById('dataArmSelect').value;
        const address = document.getElementById('dataAddressInput').value;
        const value = document.getElementById('dataValueSelect').value;

        this.showLoading('Veri alma komutu gönderiliyor...');

        try {
            const response = await fetch('/api/datagets', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    armValue: parseInt(arm),
                    slaveAddress: parseInt(address),
                    slaveCommand: parseInt(value)
                })
            });

            if (response.ok) {
                const valueText = this.getDataTypeText(value);
                this.showToast('Veri alma komutu başarıyla gönderildi', 'success');
                
                // Veri alma modunu aktif et
                await this.startDataRetrievalMode({
                    arm: parseInt(arm),
                    address: parseInt(address),
                    value: parseInt(value),
                    valueText: valueText
                });
                
                // Formu temizle
                this.clearForm();
            } else {
                throw new Error('Komut gönderilemedi');
            }
        } catch (error) {
            console.error('GetData hatası:', error);
            this.showToast('Komut gönderilirken hata oluştu', 'error');
        } finally {
            this.hideLoading();
        }
    }

    getDataTypeText(value) {
        const address = document.getElementById('dataAddressInput').value;
        
        if (address === '0') {
            // Kol verileri
            const kolDataTypes = {
                '10': 'Akım',
                '11': 'Nem',
                '12': 'Modül Sıcaklığı',
                '13': 'Ortam Sıcaklığı'
            };
            return kolDataTypes[value] || `Tip ${value}`;
        } else {
            // Batarya verileri
            const bataryaDataTypes = {
                '10': 'Gerilim (V)',
                '11': 'SOH (%)',
                '12': 'Sıcaklık (°C)',
                '13': 'NTC2 (°C)',
                '14': 'NTC3 (°C)',
                '126': 'SOC (%)'
            };
            return bataryaDataTypes[value] || `Tip ${value}`;
        }
    }

    addOperation(type, description, retrievedData = null) {
        const operation = {
            id: Date.now(),
            type: type,
            description: description,
            timestamp: new Date().toLocaleString('tr-TR'),
            retrievedData: retrievedData || []
        };

        this.operations.unshift(operation);
        
        // Son 10 işlemi tut
        if (this.operations.length > 10) {
            this.operations = this.operations.slice(0, 10);
        }

        this.saveOperations();
        this.renderOperations();
    }

    loadOperations() {
        const saved = localStorage.getItem('dataRetrievalOperations');
        if (saved) {
            this.operations = JSON.parse(saved);
            this.renderOperations();
        }
    }

    saveOperations() {
        localStorage.setItem('dataRetrievalOperations', JSON.stringify(this.operations));
    }

    renderOperations() {
        const container = document.getElementById('operationsList');
        
        if (this.operations.length === 0) {
            container.innerHTML = `
                <div class="no-operations">
                    <i class="fas fa-inbox"></i>
                    <h4>Henüz işlem yapılmadı</h4>
                    <p>Veri alma işlemleri burada görüntülenecek</p>
                </div>
            `;
            return;
        }

        container.innerHTML = this.operations.map(op => {
            let operationHtml = `
                <div class="operation-item">
                    <div class="operation-info">
                        <div class="operation-icon ${op.type}">
                            <i class="fas ${this.getOperationIcon(op.type)}"></i>
                        </div>
                        <div class="operation-details">
                            <h4>${op.description}</h4>
                            <p>İşlem tamamlandı</p>
                        </div>
                    </div>
                    <div class="operation-time">${op.timestamp}</div>
                </div>
            `;

            // Eğer alınan veri varsa, tablo halinde göster
            if (op.retrievedData && op.retrievedData.length > 0) {
                operationHtml += `
                    <div class="operation-data-table">
                        <div class="data-table-header">
                            <h5>Alınan Veriler (${op.retrievedData.length} adet)</h5>
                        </div>
                        <div class="data-table-container">
                            <table class="data-table">
                                <thead>
                                    <tr>
                                        <th>Saat</th>
                                        <th>Kol</th>
                                        <th>Adres</th>
                                        <th>Tip</th>
                                        <th>Değer</th>
                                        <th>İstenen</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${op.retrievedData.map(data => `
                                        <tr>
                                            <td>${data.timestamp}</td>
                                            <td>${data.arm}</td>
                                            <td>${data.k}</td>
                                            <td>${data.dtype}</td>
                                            <td>${data.value}</td>
                                            <td>${data.requested_value}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }

            return operationHtml;
        }).join('');
    }

    getOperationIcon(type) {
        const icons = {
            'read': 'fa-download',
            'reset': 'fa-refresh',
            'data': 'fa-database'
        };
        return icons[type] || 'fa-cog';
    }

    async startDataRetrievalMode(config) {
        try {
            // Backend'e veri alma modunu başlat
            const response = await fetch('/api/start-data-retrieval', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(config)
            });

            if (response.ok) {
                this.isDataRetrievalMode = true;
                this.retrievalConfig = config;
                this.retrievedData = [];
                
                // Veri tablosunu göster
                this.showDataTable();
                
                // Periyot başlangıcını bekle
                this.waitForPeriodStart();
                
                console.log('🔍 Veri alma modu başlatıldı:', config);
            } else {
                throw new Error('Veri alma modu başlatılamadı');
            }
        } catch (error) {
            console.error('Veri alma modu başlatma hatası:', error);
            this.showToast('Veri alma modu başlatılamadı', 'error');
        }
    }
    
    waitForPeriodStart() {
        // Periyot başlangıcını kontrol et
        this.checkPeriodStatus();
    }
    
    async checkPeriodStatus() {
        if (!this.isDataRetrievalMode) return;
        
        try {
            // Veri alma modu durdu mu kontrol et
            const statusResponse = await fetch('/api/data-retrieval-status');
            if (statusResponse.ok) {
                const statusResult = await statusResponse.json();
                console.log('🔍 VERİ ALMA MODU DURUMU:', statusResult);
                if (statusResult.success && !statusResult.is_active) {
                    // Mod durdu - periyot bitti, verileri çek
                    await this.fetchRetrievedData();
                    
                    // Alınan verileri işleme ekle
                    if (this.retrievedData.length > 0) {
                        let operationDescription;
                        let operationType = 'data';
                        
                        if (this.retrievalConfig) {
                            if (this.retrievalConfig.address === 0) {
                                // Tümünü Oku işlemi
                                operationDescription = `Tümünü Oku - Kol ${this.retrievalConfig.arm}`;
                                operationType = 'read';
                            } else {
                                // Veri Al işlemi
                                operationDescription = `Veri Al - Kol ${this.retrievalConfig.arm}, Adres ${this.retrievalConfig.address}, ${this.retrievalConfig.valueText}`;
                                operationType = 'data';
                            }
                        } else {
                            operationDescription = 'Veri Alma İşlemi';
                        }
                        
                        this.addOperation(operationType, operationDescription, this.retrievedData);
                        this.showToast(`${this.retrievedData.length} adet veri alındı`, 'success');
                    }
                    
                    // Mod durdu, frontend'i güncelle
                    this.isDataRetrievalMode = false;
                    this.retrievalConfig = null;
                    
                    // Verileri göster
                    this.showRetrievedData();
                    console.log('🛑 Veri alma modu otomatik olarak durduruldu');
                    return;
                }
            }
        } catch (error) {
            console.error('Veri alma hatası:', error);
        }
        
        // 3 saniye sonra tekrar kontrol et (daha az sıklıkta)
        setTimeout(() => {
            if (this.isDataRetrievalMode) {
                this.checkPeriodStatus();
            }
        }, 3000);
    }
    
    async fetchRetrievedData() {
        try {
            // Yakalanan verileri al
            const response = await fetch('/api/get-retrieved-data');
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    // Yeni verileri ekle
                    result.data.forEach(data => {
                        this.addRetrievedData({
                            timestamp: data.timestamp,
                            requestedValue: data.requested_value,
                            receivedValue: data.value,
                            arm: data.arm,
                            address: data.address
                        });
                    });
                }
            }
        } catch (error) {
            console.error('Veri çekme hatası:', error);
        }
    }
    
    showDataTable() {
        // Veri tablosunu göster
        const operationsList = document.getElementById('operationsList');
        operationsList.innerHTML = `
            <div class="data-table-container">
                <div class="loading-container">
                    <div class="loading">
                        <i class="fas fa-spinner fa-spin"></i>
                        <h4>Veriler alınıyor...</h4>
                    </div>
                </div>
                <div class="data-table" style="display: none;" id="retrievedDataTable">
                    <h4>📊 Alınan Veriler</h4>
                    <table>
                        <thead>
                            <tr>
                                <th>Saat</th>
                                <th>İstenilen Değer</th>
                                <th>Gelen Veri</th>
                                <th>Kol</th>
                                <th>Adres</th>
                            </tr>
                        </thead>
                        <tbody id="dataTableBody">
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }
    
    addRetrievedData(data) {
        if (!this.isDataRetrievalMode) return;
        
        this.retrievedData.push(data);
        this.updateDataTable();
    }
    
    updateDataTable() {
        const tbody = document.getElementById('dataTableBody');
        if (!tbody) return;
        
        if (this.retrievedData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="no-data">Veri bekleniyor...</td></tr>';
            return;
        }
        
        tbody.innerHTML = this.retrievedData.map(data => `
            <tr>
                <td>${data.timestamp}</td>
                <td>${data.requestedValue}</td>
                <td>${data.receivedValue}</td>
                <td>${data.arm}</td>
                <td>${data.address}</td>
            </tr>
        `).join('');
    }
    
    showRetrievedData() {
        // Loading'i gizle, tabloyu göster
        const loadingContainer = document.querySelector('.loading-container');
        const dataTable = document.getElementById('retrievedDataTable');
        
        if (loadingContainer) loadingContainer.style.display = 'none';
        if (dataTable) dataTable.style.display = 'block';
        
        // Verileri tabloya yaz
        this.updateDataTable();
    }
    
    async stopDataRetrieval() {
        try {
            // Backend'e veri alma modunu durdur
            const response = await fetch('/api/stop-data-retrieval', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (response.ok) {
                this.isDataRetrievalMode = false;
                this.retrievalConfig = null;
                this.retrievedData = [];
                
                // Normal işlemler listesine dön
                this.renderOperations();
                
                console.log('🛑 Veri alma modu durduruldu');
            } else {
                throw new Error('Veri alma modu durdurulamadı');
            }
        } catch (error) {
            console.error('Veri alma modu durdurma hatası:', error);
            this.showToast('Veri alma modu durdurulamadı', 'error');
        }
    }

    clearForm() {
        document.getElementById('dataArmSelect').value = '';
        document.getElementById('dataAddressInput').value = '';
        document.getElementById('dataValueSelect').value = '';
        document.getElementById('getDataBtn').disabled = true;
    }

    showLoading(text) {
        document.getElementById('loadingText').textContent = text;
        document.getElementById('loadingOverlay').style.display = 'flex';
    }

    hideLoading() {
        document.getElementById('loadingOverlay').style.display = 'none';
    }

    showToast(message, type = 'success') {
        const toast = document.getElementById('toast');
        const toastMessage = document.getElementById('toastMessage');
        const toastIcon = toast.querySelector('.toast-icon i');
        
        toastMessage.textContent = message;
        
        if (type === 'error') {
            toastIcon.className = 'fas fa-exclamation-triangle';
            toast.querySelector('.toast-icon').style.background = '#ef4444';
        } else {
            toastIcon.className = 'fas fa-check';
            toast.querySelector('.toast-icon').style.background = '#10b981';
        }
        
        toast.style.display = 'block';
        
        setTimeout(() => {
            toast.style.display = 'none';
        }, 3000);
    }
    };
}

// Sayfa yüklendiğinde başlat
function initDataRetrievalPage() {
    console.log('🔧 initDataRetrievalPage() çağrıldı');
    if (!window.dataRetrievalPage) {
        window.dataRetrievalPage = new window.DataRetrieval();
    } else {
        // Mevcut instance'ı yeniden başlat
        console.log('🔄 Mevcut DataRetrieval instance yeniden başlatılıyor');
        window.dataRetrievalPage.init();
    }
}

// Global olarak erişilebilir yap
window.initDataRetrievalPage = initDataRetrievalPage;

// Script yüklendiğinde otomatik init
console.log('🔧 DataRetrieval.js yüklendi, otomatik init başlatılıyor...');
initDataRetrievalPage();