/*
 * Nuvoton MCU için UART File Receiver
 * NuMicro SDK kullanarak dosya alma ve birleştirme
 */

#include "uart_file_receiver.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

// Nuvoton SDK includes (projenize göre düzenleyin)
// #include "NuMicro.h"  // veya projenizin header dosyası
// #include "uart.h"      // UART driver

// UART Port tanımı (projenize göre değiştirin)
// #define UART_PORT      UART0    // veya UART1, UART2, vb.
// #define UART_BAUD      9600

// Global dosya transfer durumu
file_transfer_t file_info;

// UART buffer
uint8_t uart_buffer[MAX_PACKET_SIZE];
uint16_t buffer_index = 0;
bool header_found = false;

// UART interrupt flag
volatile bool uart_rx_ready = false;
volatile uint8_t uart_rx_byte = 0;

// ============================================
// CRC Hesaplama
// ============================================
uint8_t calculate_crc(uint8_t* data, uint16_t length) {
    uint8_t crc = 0;
    for (uint16_t i = 0; i < length; i++) {
        crc += data[i];
    }
    return crc;
}

// ============================================
// Nuvoton UART Gönderme Fonksiyonları
// ============================================
void uart_send_byte(uint8_t byte) {
    // Nuvoton UART gönderme
    // Yöntem 1: Polling (basit)
    // while(UART_IS_TX_FULL(UART_PORT));  // TX buffer boşalana kadar bekle
    // UART_WRITE(UART_PORT, byte);
    
    // Yöntem 2: SDK fonksiyonu (NuMicro SDK)
    // UART_Write(UART_PORT, &byte, 1);
    
    // Yöntem 3: HAL benzeri (bazı Nuvoton SDK'larında)
    // UART_SendByte(UART_PORT, byte);
    
    // ÖRNEK (projenize göre düzenleyin):
    // UART0->DAT = byte;  // Direkt register yazma (dikkatli kullanın)
    
    // Şimdilik placeholder - projenize göre düzenleyin
    // printf("[UART TX] 0x%02X\n", byte);
}

void uart_send_packet(uint8_t* data, uint16_t length) {
    for (uint16_t i = 0; i < length; i++) {
        uart_send_byte(data[i]);
        // Küçük delay (UART buffer için)
        // CLK_SysTickDelay(100);  // 1us @ 100MHz (projenize göre)
    }
}

void send_ack(void) {
    uint8_t ack_packet[3] = {UART_HEADER, CMD_ACK, 0};
    ack_packet[2] = calculate_crc(ack_packet, 2);
    uart_send_packet(ack_packet, 3);
    // printf("[MCU] ACK gönderildi\n");
}

void send_nack(void) {
    uint8_t nack_packet[3] = {UART_HEADER, CMD_NACK, 0};
    nack_packet[2] = calculate_crc(nack_packet, 2);
    uart_send_packet(nack_packet, 3);
    // printf("[MCU] NACK gönderildi\n");
}

void send_ready(void) {
    uint8_t ready_packet[3] = {UART_HEADER, CMD_READY, 0};
    ready_packet[2] = calculate_crc(ready_packet, 2);
    uart_send_packet(ready_packet, 3);
    // printf("[MCU] READY gönderildi\n");
}

// ============================================
// Nuvoton UART Alma Fonksiyonları
// ============================================

// UART Interrupt Handler (IRQ Handler)
// Bu fonksiyonu UART interrupt'ına bağlayın
void UART_IRQHandler(void) {
    uint32_t u32IntSts = UART_GET_INT_FLAG(UART_PORT);
    
    if (u32IntSts & UART_INTSTS_RDAINT_Msk) {
        // RX data available
        uart_rx_byte = UART_READ(UART_PORT);
        uart_rx_ready = true;
        
        // RX FIFO temizle (gerekirse)
        UART_CLR_INT_FLAG(UART_PORT, UART_INTSTS_RDAINT_Msk);
    }
    
    if (u32IntSts & UART_INTSTS_THREINT_Msk) {
        // TX buffer empty (gerekirse)
        UART_CLR_INT_FLAG(UART_PORT, UART_INTSTS_THREINT_Msk);
    }
}

// Polling yöntemi (interrupt kullanmıyorsanız)
bool receive_byte(uint8_t* byte) {
    // Yöntem 1: Interrupt kullanıyorsanız
    if (uart_rx_ready) {
        *byte = uart_rx_byte;
        uart_rx_ready = false;
        return true;
    }
    
    // Yöntem 2: Polling (interrupt yoksa)
    // if (UART_IS_RX_READY(UART_PORT)) {
    //     *byte = UART_READ(UART_PORT);
    //     return true;
    // }
    
    // Yöntem 3: SDK fonksiyonu
    // if (UART_Read(UART_PORT, byte, 1) > 0) {
    //     return true;
    // }
    
    return false;
}

// ============================================
// Dosya Kaydetme Fonksiyonu
// ============================================
void save_file(const char* filename, uint8_t* data, uint32_t size) {
    // Nuvoton MCU'da dosya kaydetme seçenekleri:
    
    // 1. SPI Flash (SPIFFS benzeri)
    // SPI_Flash_Write(filename, data, size);
    
    // 2. SD Kart (SPI veya SDIO)
    // SD_WriteFile(filename, data, size);
    
    // 3. EEPROM (küçük dosyalar için)
    // EEPROM_Write(filename, data, size);
    
    // 4. Internal Flash (küçük dosyalar için)
    // Flash_Write(filename, data, size);
    
    // 5. RAM'de tutma (geçici)
    // memcpy(file_storage, data, size);
    
    // ÖRNEK: SPI Flash'a kaydetme (projenize göre düzenleyin)
    // FILE* file = fopen(filename, "wb");
    // if (file) {
    //     fwrite(data, 1, size, file);
    //     fclose(file);
    // }
    
    // Şimdilik sadece log (gerçek implementasyonda dosyaya yazın)
    // printf("Dosya kaydediliyor: %s (%lu byte)\n", filename, (unsigned long)size);
}

// ============================================
// FILE_START Komutu İşleme (0x90)
// ============================================
void handle_file_start(uint8_t* packet, uint16_t length) {
    if (length < 8) {
        send_nack();
        return;
    }
    
    uint8_t filename_len = packet[2];
    
    if (filename_len > MAX_FILENAME_LEN - 1 || length < 7 + filename_len) {
        send_nack();
        return;
    }
    
    memcpy(file_info.filename, &packet[3], filename_len);
    file_info.filename[filename_len] = '\0';
    
    uint32_t file_size = ((uint32_t)packet[3 + filename_len] << 24) |
                         ((uint32_t)packet[4 + filename_len] << 16) |
                         ((uint32_t)packet[5 + filename_len] << 8) |
                         ((uint32_t)packet[6 + filename_len]);
    
    if (file_size > MAX_FILE_SIZE) {
        send_nack();
        return;
    }
    
    file_info.file_size = file_size;
    file_info.total_packets = (file_size + PACKET_DATA_SIZE - 1) / PACKET_DATA_SIZE;
    file_info.received_packets = 0;
    file_info.transfer_active = true;
    
    memset(file_info.file_data, 0, sizeof(file_info.file_data));
    
    uint8_t received_crc = packet[7 + filename_len];
    uint8_t calculated_crc = calculate_crc(packet, 7 + filename_len);
    
    if (received_crc == calculated_crc) {
        send_ready();
    } else {
        send_nack();
        file_info.transfer_active = false;
    }
}

// ============================================
// FILE_DATA Komutu İşleme (0x91)
// ============================================
void handle_file_data(uint8_t* packet, uint16_t length) {
    if (!file_info.transfer_active) {
        send_nack();
        return;
    }
    
    if (length < 6) {
        send_nack();
        return;
    }
    
    uint16_t packet_num = ((uint16_t)packet[2] << 8) | packet[3];
    uint8_t data_len = packet[4];
    
    if (data_len > PACKET_DATA_SIZE || length < 5 + data_len + 1) {
        send_nack();
        return;
    }
    
    uint32_t offset = ((uint32_t)(packet_num - 1)) * PACKET_DATA_SIZE;
    if (offset + data_len > MAX_FILE_SIZE) {
        send_nack();
        return;
    }
    
    memcpy(&file_info.file_data[offset], &packet[5], data_len);
    
    uint8_t received_crc = packet[5 + data_len];
    uint8_t calculated_crc = calculate_crc(packet, 5 + data_len);
    
    if (received_crc == calculated_crc) {
        file_info.received_packets++;
        send_ack();
    } else {
        send_nack();
    }
}

// ============================================
// FILE_END Komutu İşleme (0x92)
// ============================================
void handle_file_end(uint8_t* packet, uint16_t length) {
    if (!file_info.transfer_active) {
        send_nack();
        return;
    }
    
    if (length < 5) {
        send_nack();
        return;
    }
    
    uint16_t total_packets = ((uint16_t)packet[2] << 8) | packet[3];
    
    uint8_t received_crc = packet[4];
    uint8_t calculated_crc = calculate_crc(packet, 4);
    
    if (received_crc != calculated_crc) {
        send_nack();
        file_info.transfer_active = false;
        return;
    }
    
    // Dosyayı kaydet
    save_file(file_info.filename, file_info.file_data, file_info.file_size);
    
    send_ack();
    
    // Transfer durumunu sıfırla
    file_info.transfer_active = false;
    memset(&file_info, 0, sizeof(file_info));
}

// ============================================
// Ana UART Okuma Döngüsü
// ============================================
void uart_receive_loop(void) {
    uint8_t byte;
    
    while (1) {
        if (receive_byte(&byte)) {
            if (byte == UART_HEADER) {
                buffer_index = 0;
                header_found = true;
                uart_buffer[buffer_index++] = byte;
                continue;
            }
            
            if (header_found && buffer_index < MAX_PACKET_SIZE) {
                uart_buffer[buffer_index++] = byte;
                
                if (buffer_index == 2) {
                    uint8_t command = uart_buffer[1];
                    uint16_t expected_length = 0;
                    
                    if (command == CMD_FILE_START) {
                        if (buffer_index >= 3) {
                            uint8_t filename_len = uart_buffer[2];
                            expected_length = 3 + filename_len + 4 + 1;
                        }
                    }
                    else if (command == CMD_FILE_DATA) {
                        if (buffer_index >= 5) {
                            uint8_t data_len = uart_buffer[4];
                            expected_length = 5 + data_len + 1;
                        }
                    }
                    else if (command == CMD_FILE_END) {
                        expected_length = 5;
                    }
                    
                    if (expected_length > 0 && buffer_index >= expected_length) {
                        if (command == CMD_FILE_START) {
                            handle_file_start(uart_buffer, buffer_index);
                        }
                        else if (command == CMD_FILE_DATA) {
                            handle_file_data(uart_buffer, buffer_index);
                        }
                        else if (command == CMD_FILE_END) {
                            handle_file_end(uart_buffer, buffer_index);
                        }
                        
                        buffer_index = 0;
                        header_found = false;
                    }
                }
            } else if (buffer_index >= MAX_PACKET_SIZE) {
                buffer_index = 0;
                header_found = false;
            }
        }
        
        // MCU'da task delay veya idle
        // CLK_SysTickDelay(1000);  // 10us @ 100MHz
    }
}

// ============================================
// İlk Kurulum
// ============================================
void init_uart_receiver(void) {
    // UART başlatma (projenize göre)
    // UART_Open(UART_PORT, UART_BAUD);
    // UART_EnableInt(UART_PORT, UART_INTEN_RDAIEN_Msk);
    // NVIC_EnableIRQ(UART0_IRQn);  // veya UART1_IRQn, vb.
    
    memset(&file_info, 0, sizeof(file_info));
    memset(uart_buffer, 0, sizeof(uart_buffer));
    buffer_index = 0;
    header_found = false;
    uart_rx_ready = false;
}

// ============================================
// Ana Fonksiyon (Örnek)
// ============================================
int main(void) {
    // Nuvoton MCU ilk kurulumu
    // SYS_Init();
    // CLK_EnableXtalRC(CLK_PWRCTL_HIRCEN_Msk);
    // UART_Open(UART_PORT, UART_BAUD);
    
    init_uart_receiver();
    
    // Ana döngü
    uart_receive_loop();
    
    return 0;
}




