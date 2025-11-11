#include "uart_file_receiver.h"
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

// Global dosya transfer durumu
file_transfer_t file_info;

// UART buffer
uint8_t uart_buffer[MAX_PACKET_SIZE];
uint16_t buffer_index = 0;
bool header_found = false;

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
// UART Gönderme Fonksiyonları
// ============================================
// NOT: Bu fonksiyonlar MCU'nuzun UART API'sine göre düzenlenmelidir
// Örnek: STM32 için HAL_UART_Transmit, ESP32 için uart_write_bytes, vb.

void uart_send_byte(uint8_t byte) {
    // MCU'nuzun UART gönderme fonksiyonunu buraya yazın
    // Örnek: HAL_UART_Transmit(&huart1, &byte, 1, 100);
    // Örnek: uart_write_bytes(UART_NUM_1, &byte, 1);
    printf("[UART TX] 0x%02X\n", byte);
}

void uart_send_packet(uint8_t* data, uint16_t length) {
    for (uint16_t i = 0; i < length; i++) {
        uart_send_byte(data[i]);
    }
}

void send_ack(void) {
    uint8_t ack_packet[3] = {UART_HEADER, CMD_ACK, 0};
    ack_packet[2] = calculate_crc(ack_packet, 2);
    uart_send_packet(ack_packet, 3);
    printf("[MCU] ACK gönderildi\n");
}

void send_nack(void) {
    uint8_t nack_packet[3] = {UART_HEADER, CMD_NACK, 0};
    nack_packet[2] = calculate_crc(nack_packet, 2);
    uart_send_packet(nack_packet, 3);
    printf("[MCU] NACK gönderildi\n");
}

void send_ready(void) {
    uint8_t ready_packet[3] = {UART_HEADER, CMD_READY, 0};
    ready_packet[2] = calculate_crc(ready_packet, 2);
    uart_send_packet(ready_packet, 3);
    printf("[MCU] READY gönderildi\n");
}

// ============================================
// UART Alma Fonksiyonu
// ============================================
// NOT: Bu fonksiyon MCU'nuzun UART API'sine göre düzenlenmelidir
bool receive_byte(uint8_t* byte) {
    // MCU'nuzun UART alma fonksiyonunu buraya yazın
    // Örnek: HAL_UART_Receive(&huart1, byte, 1, 10) == HAL_OK
    // Örnek: uart_read_bytes(UART_NUM_1, byte, 1, 0) > 0
    
    // Simülasyon için: Gerçek implementasyonda UART interrupt veya polling kullanın
    static uint8_t test_byte = 0;
    *byte = test_byte++;
    return true;  // Gerçek implementasyonda UART'tan veri gelip gelmediğini kontrol edin
}

// ============================================
// Dosya Kaydetme Fonksiyonu
// ============================================
void save_file(const char* filename, uint8_t* data, uint32_t size) {
    // MCU'nuzun dosya sistemi API'sine göre düzenleyin
    // Örnek: SPIFFS, LittleFS, SD kart, vb.
    
    printf("\n========================================\n");
    printf("Dosya Kaydediliyor: %s\n", filename);
    printf("Boyut: %lu byte\n", (unsigned long)size);
    printf("========================================\n");
    
    // Örnek: SPIFFS ile kaydetme
    // FILE* file = fopen(filename, "wb");
    // if (file) {
    //     fwrite(data, 1, size, file);
    //     fclose(file);
    //     printf("Dosya başarıyla kaydedildi\n");
    // } else {
    //     printf("Dosya açılamadı\n");
    // }
    
    // Örnek: SD kart ile kaydetme
    // SD.open(filename, FILE_WRITE).write(data, size);
    
    // Şimdilik sadece log
    printf("İlk 100 byte:\n");
    for (uint32_t i = 0; i < size && i < 100; i++) {
        printf("%02X ", data[i]);
        if ((i + 1) % 16 == 0) printf("\n");
    }
    printf("\n");
}

// ============================================
// FILE_START Komutu İşleme (0x90)
// ============================================
// Paket yapısı: [0x81] [0x90] [filename_len] [filename...] [file_size_4byte] [CRC]
void handle_file_start(uint8_t* packet, uint16_t length) {
    if (length < 8) {  // Minimum paket boyutu kontrolü
        printf("[ERROR] FILE_START paketi çok kısa\n");
        send_nack();
        return;
    }
    
    uint8_t filename_len = packet[2];
    
    if (filename_len > MAX_FILENAME_LEN - 1 || length < 7 + filename_len) {
        printf("[ERROR] Geçersiz filename uzunluğu\n");
        send_nack();
        return;
    }
    
    // Filename'i kopyala
    memcpy(file_info.filename, &packet[3], filename_len);
    file_info.filename[filename_len] = '\0';
    
    // File size (4 byte, big-endian)
    uint32_t file_size = ((uint32_t)packet[3 + filename_len] << 24) |
                         ((uint32_t)packet[4 + filename_len] << 16) |
                         ((uint32_t)packet[5 + filename_len] << 8) |
                         ((uint32_t)packet[6 + filename_len]);
    
    if (file_size > MAX_FILE_SIZE) {
        printf("[ERROR] Dosya boyutu çok büyük: %lu byte\n", (unsigned long)file_size);
        send_nack();
        return;
    }
    
    file_info.file_size = file_size;
    file_info.total_packets = (file_size + PACKET_DATA_SIZE - 1) / PACKET_DATA_SIZE;
    file_info.received_packets = 0;
    file_info.transfer_active = true;
    
    // Dosya buffer'ını temizle
    memset(file_info.file_data, 0, sizeof(file_info.file_data));
    
    // CRC kontrolü
    uint8_t received_crc = packet[7 + filename_len];
    uint8_t calculated_crc = calculate_crc(packet, 7 + filename_len);
    
    if (received_crc == calculated_crc) {
        send_ready();
        printf("\n[FILE_START] Dosya: %s\n", file_info.filename);
        printf("  Boyut: %lu byte\n", (unsigned long)file_info.file_size);
        printf("  Toplam paket: %d\n", file_info.total_packets);
    } else {
        printf("[ERROR] FILE_START CRC hatası (Alınan: 0x%02X, Hesaplanan: 0x%02X)\n", 
               received_crc, calculated_crc);
        send_nack();
        file_info.transfer_active = false;
    }
}

// ============================================
// FILE_DATA Komutu İşleme (0x91)
// ============================================
// Paket yapısı: [0x81] [0x91] [packet_num_2byte] [data_len] [data...] [CRC]
void handle_file_data(uint8_t* packet, uint16_t length) {
    if (!file_info.transfer_active) {
        printf("[ERROR] Aktif dosya transferi yok\n");
        send_nack();
        return;
    }
    
    if (length < 6) {  // Minimum paket boyutu kontrolü
        printf("[ERROR] FILE_DATA paketi çok kısa\n");
        send_nack();
        return;
    }
    
    // Packet number (2 byte, big-endian)
    uint16_t packet_num = ((uint16_t)packet[2] << 8) | packet[3];
    uint8_t data_len = packet[4];
    
    if (data_len > PACKET_DATA_SIZE || length < 5 + data_len + 1) {
        printf("[ERROR] Geçersiz data uzunluğu: %d\n", data_len);
        send_nack();
        return;
    }
    
    // Veriyi al
    uint32_t offset = ((uint32_t)(packet_num - 1)) * PACKET_DATA_SIZE;
    if (offset + data_len > MAX_FILE_SIZE) {
        printf("[ERROR] Dosya boyutu limiti aşıldı\n");
        send_nack();
        return;
    }
    
    memcpy(&file_info.file_data[offset], &packet[5], data_len);
    
    // CRC kontrolü
    uint8_t received_crc = packet[5 + data_len];
    uint8_t calculated_crc = calculate_crc(packet, 5 + data_len);
    
    if (received_crc == calculated_crc) {
        file_info.received_packets++;
        send_ack();
        printf("[FILE_DATA] Paket %d/%d alındı (%d byte)\n", 
               packet_num, file_info.total_packets, data_len);
    } else {
        printf("[ERROR] FILE_DATA CRC hatası - Paket %d (Alınan: 0x%02X, Hesaplanan: 0x%02X)\n", 
               packet_num, received_crc, calculated_crc);
        send_nack();
    }
}

// ============================================
// FILE_END Komutu İşleme (0x92)
// ============================================
// Paket yapısı: [0x81] [0x92] [total_packets_2byte] [CRC]
void handle_file_end(uint8_t* packet, uint16_t length) {
    if (!file_info.transfer_active) {
        printf("[ERROR] Aktif dosya transferi yok\n");
        send_nack();
        return;
    }
    
    if (length < 5) {  // Minimum paket boyutu kontrolü
        printf("[ERROR] FILE_END paketi çok kısa\n");
        send_nack();
        return;
    }
    
    uint16_t total_packets = ((uint16_t)packet[2] << 8) | packet[3];
    
    // CRC kontrolü
    uint8_t received_crc = packet[4];
    uint8_t calculated_crc = calculate_crc(packet, 4);
    
    if (received_crc != calculated_crc) {
        printf("[ERROR] FILE_END CRC hatası\n");
        send_nack();
        file_info.transfer_active = false;
        return;
    }
    
    // Paket sayısı kontrolü
    if (file_info.received_packets != total_packets) {
        printf("[WARNING] Paket sayısı uyuşmuyor (Alınan: %d, Beklenen: %d)\n", 
               file_info.received_packets, total_packets);
    }
    
    // Dosyayı kaydet
    save_file(file_info.filename, file_info.file_data, file_info.file_size);
    
    // ACK gönder
    send_ack();
    
    printf("\n[FILE_END] Dosya transferi tamamlandı: %s\n", file_info.filename);
    printf("  Toplam paket: %d\n", total_packets);
    printf("  Alınan paket: %d\n", file_info.received_packets);
    
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
            // Header (0x81) bul
            if (byte == UART_HEADER) {
                buffer_index = 0;
                header_found = true;
                uart_buffer[buffer_index++] = byte;
                continue;
            }
            
            // Header bulunduysa paketi topla
            if (header_found && buffer_index < MAX_PACKET_SIZE) {
                uart_buffer[buffer_index++] = byte;
                
                // Komut byte'ını kontrol et
                if (buffer_index == 2) {
                    uint8_t command = uart_buffer[1];
                    
                    // Paket boyutunu belirle ve tamamlanana kadar bekle
                    uint16_t expected_length = 0;
                    
                    if (command == CMD_FILE_START) {
                        // FILE_START: [0x81] [0x90] [filename_len] [filename...] [file_size_4byte] [CRC]
                        if (buffer_index >= 3) {
                            uint8_t filename_len = uart_buffer[2];
                            expected_length = 3 + filename_len + 4 + 1;  // header + cmd + filename_len + filename + file_size + CRC
                        }
                    }
                    else if (command == CMD_FILE_DATA) {
                        // FILE_DATA: [0x81] [0x91] [packet_num_2byte] [data_len] [data...] [CRC]
                        if (buffer_index >= 5) {
                            uint8_t data_len = uart_buffer[4];
                            expected_length = 5 + data_len + 1;  // header + cmd + packet_num + data_len + data + CRC
                        }
                    }
                    else if (command == CMD_FILE_END) {
                        // FILE_END: [0x81] [0x92] [total_packets_2byte] [CRC]
                        expected_length = 5;  // header + cmd + total_packets + CRC
                    }
                    
                    // Paket tamamlandı mı kontrol et
                    if (expected_length > 0 && buffer_index >= expected_length) {
                        // Paketi işle
                        if (command == CMD_FILE_START) {
                            handle_file_start(uart_buffer, buffer_index);
                        }
                        else if (command == CMD_FILE_DATA) {
                            handle_file_data(uart_buffer, buffer_index);
                        }
                        else if (command == CMD_FILE_END) {
                            handle_file_end(uart_buffer, buffer_index);
                        }
                        
                        // Buffer'ı temizle
                        buffer_index = 0;
                        header_found = false;
                    }
                }
            } else if (buffer_index >= MAX_PACKET_SIZE) {
                // Buffer taşması
                printf("[ERROR] UART buffer taştı, temizleniyor\n");
                buffer_index = 0;
                header_found = false;
            }
        }
        
        // MCU'nuzda delay veya task delay kullanın
        // Örnek: HAL_Delay(1); veya vTaskDelay(1);
    }
}

// ============================================
// İlk Kurulum
// ============================================
void init_uart_receiver(void) {
    memset(&file_info, 0, sizeof(file_info));
    memset(uart_buffer, 0, sizeof(uart_buffer));
    buffer_index = 0;
    header_found = false;
    
    printf("UART File Receiver başlatıldı\n");
    printf("Baud Rate: 9600\n");
    printf("Protokol: Header=0x81, FILE_START=0x90, FILE_DATA=0x91, FILE_END=0x92\n");
}

// ============================================
// Ana Fonksiyon (Örnek)
// ============================================
int main(void) {
    // MCU ilk kurulumu (UART, GPIO, vb.)
    // init_uart();
    // init_gpio();
    
    init_uart_receiver();
    
    // Ana döngü
    uart_receive_loop();
    
    return 0;
}



