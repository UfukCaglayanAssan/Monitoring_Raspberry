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
        this.hideOperationsList();
        this.loadArmOptions();
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

        // Kol seçimi değiştiğinde batarya adresi sınırlaması
        document.getElementById('dataArmSelect').addEventListener('change', (e) => {
            this.updateAddressInput(e.target.value);
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
                // Tümünü oku işlemi için veri alma modu başlat
                if (selectedArm !== '5') {
                    // Belirli bir kol seçildiyse, o kol için veri alma modu başlat
                    await this.startDataRetrievalMode({
                        arm: parseInt(selectedArm),
                        address: 0, // Tümünü Oku işlemi için adres 0
                        value: 0, // Tümünü Oku işlemi için değer 0
                        valueText: 'Tüm Veriler'
                    });
                } else {
                    // Tüm kollar seçildiyse, genel veri alma modu başlat
                    await this.startDataRetrievalMode({
                        arm: 5,
                        address: 0,
                        value: 0,
                        valueText: 'Tüm Veriler'
                    });
                }
                
                // Veri tablosunu göster
                this.showDataTable();
                
                // Tablo kısmına kaydır
                this.scrollToDataTable();
                
                // Periyot durumunu kontrol etmeye başla
                this.checkPeriodStatus();
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
                // Toast bildirimi kaldırıldı
                
                // Komut gönderildiği zamanı kaydet
                const commandTimestamp = Date.now();
                console.log(`🕐 Komut gönderildi: ${new Date(commandTimestamp).toLocaleString()}`);
                
                // Tekil veri alma - sadece 3 saniye bekle
                this.showLoading('Veri bekleniyor...');
                await this.waitForSingleData(parseInt(arm), parseInt(address), parseInt(value), valueText, commandTimestamp);
                
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

    async waitForSingleData(arm, address, value, valueText, commandTimestamp) {
        const maxAttempts = 2; // 2 deneme (3 saniye + 3 saniye)
        let attempt = 0;
        
        while (attempt < maxAttempts) {
            attempt++;
            console.log(`🔍 Tekil veri bekleme - Deneme ${attempt}/${maxAttempts}`);
            
            // 3 saniye bekle
            await new Promise(resolve => setTimeout(resolve, 3000));
            
            // Veri gelip gelmediğini kontrol et
            const data = await this.checkForSingleData(arm, address, value, commandTimestamp);
            
            if (data) {
                console.log('✅ Tekil veri alındı:', data);
                this.showToast(`${valueText} verisi alındı: ${data}`, 'success');
                return data;
            }
            
            if (attempt < maxAttempts) {
                console.log('⏳ Veri gelmedi, tekrar denenecek...');
                // Deneme sayısı gösterilmiyor, sadece başlangıç mesajı
                this.showLoading('Veri bekleniyor...');
            }
        }
        
        console.log('❌ Tekil veri alınamadı');
        this.showToast('Veri alınamadı, lütfen tekrar deneyin', 'error');
        return null;
    }

    async checkForSingleData(arm, address, value, commandTimestamp) {
        try {
            // Tekil veri alma için doğrudan batarya verilerini kontrol et
            const response = await fetch('/api/batteries', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            
            if (response.ok) {
                const result = await response.json();
                if (result.success && result.data) {
                    // Gönderilen adresin 1 fazlasına bak (k-2 mantığı nedeniyle)
                    const targetAddress = parseInt(address) + 1;
                    
                    console.log(`🔍 Tekil veri arama: Kol ${arm}, Gönderilen adres ${address}, Aranan adres ${targetAddress}, Tip ${value}`);
                    console.log(`🕐 Komut zamanı: ${new Date(commandTimestamp).toLocaleString()}`);
                    console.log(`🔍 Mevcut bataryalar:`, result.data.map(b => ({arm: b.arm, address: b.address})));
                    
                    // İlgili kol ve adrese sahip bataryayı ara
                    const targetBattery = result.data.find(battery => 
                        battery.arm == arm && 
                        battery.address == targetAddress
                    );
                    
                    if (targetBattery && targetBattery.entries) {
                        // Komut gönderildikten sonraki verileri kontrol et
                        const recentEntry = targetBattery.entries.find(entry => {
                            const entryTime = new Date(entry.timestamp).getTime();
                            return entryTime >= commandTimestamp; // Komut gönderildikten sonraki veriler
                        });
                        
                        if (recentEntry) {
                            // Değer tipine göre veriyi al
                            const dataValue = this.getDataValueFromEntry(recentEntry, value);
                            if (dataValue !== null) {
                                console.log(`✅ Tekil veri bulundu: Kol ${arm}, Adres ${targetAddress}, Tip ${value}, Değer ${dataValue}`);
                                console.log(`🕐 Veri zamanı: ${new Date(recentEntry.timestamp).toLocaleString()}`);
                                return dataValue;
                            }
                        }
                        
                        console.log(`❌ Tekil veri bulunamadı: Kol ${arm}, Adres ${targetAddress}, Tip ${value} - Komut gönderildikten sonra veri yok`);
                    } else {
                        console.log(`❌ Batarya bulunamadı: Kol ${arm}, Adres ${targetAddress}`);
                    }
                }
            }
        } catch (error) {
            console.error('Tekil veri kontrol hatası:', error);
        }
        
        return null;
    }

    getDataValueFromEntry(entry, value) {
        // entry.entries array'inden ilgili dtype'ı bul
        const targetEntry = entry.entries.find(e => e.dtype == value);
        return targetEntry ? targetEntry.data : null;
    }

    getDataValueByType(data, value) {
        const valueMap = {
            '10': data.voltage,
            '11': data.health_status,
            '12': data.temperature,
            '13': data.positive_pole_temp,
            '14': data.negative_pole_temp,
            '15': data.ntc3_temp,
            '126': data.charge_status
        };
        
        return valueMap[value] || null;
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
    }

    hideOperationsList() {
        // "Son İşlemler" bölümünü gizle
        const operationsList = document.getElementById('operationsList');
        if (operationsList) {
            operationsList.innerHTML = `
                <div class="data-table-container">
                    <div class="no-data-message">
                        <i class="fas fa-database"></i>
                        <h4>Veri Alma Sistemi</h4>
                        <p>Yukarıdaki butonları kullanarak veri alma işlemi başlatın</p>
                    </div>
                </div>
            `;
        }
    }

    async loadArmOptions() {
        try {
            const response = await fetch('/api/active-arms', {
                method: 'GET',
                headers: { 'Content-Type': 'application/json' }
            });
            
            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    this.updateArmSelectOptions(data.activeArms);
                }
            }
        } catch (error) {
            console.error('Kol seçenekleri yükleme hatası:', error);
        }
    }

    updateArmSelectOptions(activeArms) {
        // arm_slave_counts verilerini map'e çevir
        const armSlaveCountsMap = new Map();
        activeArms.forEach(arm => {
            armSlaveCountsMap.set(arm.arm, arm.slave_count || 0);
        });
        
        // Toplu işlemler kol seçimi
        const batchArmSelect = document.getElementById('batchArmSelect');
        if (batchArmSelect) {
            batchArmSelect.innerHTML = '<option value="">Kol Seçiniz</option>';
            
            // Sadece batarya olan kolları ekle
            for (let arm = 1; arm <= 4; arm++) {
                if (armSlaveCountsMap.has(arm) && armSlaveCountsMap.get(arm) > 0) {
                    const option = document.createElement('option');
                    option.value = arm;
                    option.textContent = `Kol ${arm}`;
                    batchArmSelect.appendChild(option);
                }
            }
            
            // Tüm kollar seçeneği (eğer en az 2 kol varsa)
            if (armSlaveCountsMap.size > 1) {
                const option = document.createElement('option');
                option.value = '5';
                option.textContent = 'Tüm Kollar';
                batchArmSelect.appendChild(option);
            }
        }
        
        // Veri alma formu kol seçimi
        const dataArmSelect = document.getElementById('dataArmSelect');
        if (dataArmSelect) {
            dataArmSelect.innerHTML = '<option value="">Seçiniz</option>';
            
            // Sadece batarya olan kolları ekle
            for (let arm = 1; arm <= 4; arm++) {
                if (armSlaveCountsMap.has(arm) && armSlaveCountsMap.get(arm) > 0) {
                    const option = document.createElement('option');
                    option.value = arm;
                    option.textContent = `Kol ${arm}`;
                    dataArmSelect.appendChild(option);
                }
            }
        }
    }

    async updateAddressInput(selectedArm) {
        const addressInput = document.getElementById('dataAddressInput');
        
        if (!selectedArm) {
            addressInput.placeholder = 'Önce kol seçiniz';
            addressInput.min = 0;
            addressInput.max = 0;
            addressInput.disabled = true;
            addressInput.value = '';
            return;
        }
        
        try {
            // active-arms'tan batarya sayısını al
            const response = await fetch('/api/active-arms');
            const data = await response.json();
            
            if (data.success && data.activeArms) {
                const selectedArmData = data.activeArms.find(arm => arm.arm == selectedArm);
                const batteryCount = selectedArmData ? selectedArmData.slave_count : 0;
                
                if (batteryCount > 0) {
                    addressInput.placeholder = `0-${batteryCount} arası giriniz`;
                    addressInput.min = 0;
                    addressInput.max = batteryCount;
                    addressInput.disabled = false;
                } else {
                    addressInput.placeholder = 'Bu kolda batarya yok';
                    addressInput.min = 0;
                    addressInput.max = 0;
                    addressInput.disabled = true;
                }
            }
        } catch (error) {
            console.error('Batarya sayısı alma hatası:', error);
            addressInput.placeholder = 'Hata oluştu';
            addressInput.disabled = true;
        }
    }

    scrollToDataTable() {
        // Tablo kısmına yumuşak kaydırma
        const dataTable = document.getElementById('retrievedDataTable');
        if (dataTable) {
            dataTable.scrollIntoView({ 
                behavior: 'smooth', 
                block: 'start' 
            });
        } else {
            // Eğer tablo henüz oluşmamışsa, operationsList'e kaydır
            const operationsList = document.getElementById('operationsList');
            if (operationsList) {
                operationsList.scrollIntoView({ 
                    behavior: 'smooth', 
                    block: 'start' 
                });
            }
        }
    }

    saveOperations() {
        localStorage.setItem('dataRetrievalOperations', JSON.stringify(this.operations));
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
            console.log('🔍 fetchRetrievedData çağrıldı');
            // Yakalanan verileri al
            const response = await fetch('/api/get-retrieved-data');
            console.log('📡 API yanıtı:', response.status);
            
            if (response.ok) {
                const result = await response.json();
                console.log('📊 API sonucu:', result);
                
                if (result.success && result.data) {
                    // Verileri temizle ve yeni verileri ekle
                    this.retrievedData = [];
                    result.data.forEach(data => {
                        this.retrievedData.push({
                            timestamp: data.timestamp,
                            arm: data.arm,
                            address: data.address,
                            voltage: data.voltage,
                            health_status: data.health_status,
                            temperature: data.temperature,
                            positive_pole_temp: data.positive_pole_temp,
                            negative_pole_temp: data.negative_pole_temp,
                            ntc3_temp: data.ntc3_temp,
                            charge_status: data.charge_status
                        });
                    });
                    console.log(`📊 ${this.retrievedData.length} adet veri alındı ve this.retrievedData'ya eklendi`);
                } else {
                    console.log('⚠️ API başarılı ama veri yok');
                }
            } else {
                console.log('❌ API hatası:', response.status);
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
                    <table>
                        <thead>
                            <tr>
                                    <th>ZAMAN</th>
                                    <th>KOL</th>
                                    <th>BATARYA ADRESİ</th>
                                    <th>GERİLİM</th>
                                    <th>ŞARJ DURUMU</th>
                                    <th>MODÜL SICAKLIĞI</th>
                                    <th>POZİTİF KUTUP SICAKLIĞI</th>
                                    <th>NEGATİF KUTUP SICAKLIĞI</th>
                                    <th>SAĞLIK DURUMU</th>
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
        if (!tbody) {
            console.log('❌ dataTableBody bulunamadı');
            return;
        }
        
        console.log(`🔍 updateDataTable çağrıldı - Veri sayısı: ${this.retrievedData.length}`);
        
        if (this.retrievedData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="no-data">Veri bekleniyor...</td></tr>';
            console.log('⚠️ Veri yok, "Veri bekleniyor..." gösteriliyor');
            return;
        }
        
        tbody.innerHTML = this.retrievedData.map(data => `
            <tr>
                <td>${data.timestamp}</td>
                <td>${data.arm}</td>
                <td>${data.address}</td>
                <td>${data.voltage || '-'}</td>
                <td>${data.charge_status || '-'}</td>
                <td>${data.temperature || '-'}</td>
                <td>${data.positive_pole_temp || '-'}</td>
                <td>${data.negative_pole_temp || '-'}</td>
                <td>${data.health_status || '-'}</td>
            </tr>
        `).join('');
        
        console.log('✅ Veriler tabloya yazıldı');
    }
    
    showRetrievedData() {
        // Loading'i gizle, tabloyu göster
        const loadingContainer = document.querySelector('.loading-container');
        const dataTable = document.getElementById('retrievedDataTable');
        
        if (loadingContainer) loadingContainer.style.display = 'none';
        if (dataTable) {
            dataTable.style.display = 'block';
            // Verileri tabloya yaz
            this.updateDataTable();
        }
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
                
                // Ana sayfaya dön
                this.hideOperationsList();
                
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