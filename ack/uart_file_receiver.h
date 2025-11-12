#ifndef UART_FILE_RECEIVER_H
#define UART_FILE_RECEIVER_H

#include <stdint.h>
#include <stdbool.h>

// Protokol Sabitleri
#define UART_HEADER          0x81
#define CMD_FILE_START       0x90
#define CMD_FILE_DATA        0x91
#define CMD_FILE_END         0x92
#define CMD_ACK              0x93
#define CMD_NACK             0x94
#define CMD_READY            0x95

// Paket Ayarları
#define MAX_FILENAME_LEN     64
#define MAX_PACKET_SIZE      256
#define MAX_FILE_SIZE        10240  // 10KB maksimum dosya boyutu
#define PACKET_DATA_SIZE     256    // Her pakette maksimum 256 byte veri (64'ten artırıldı)

// Dosya Transfer Yapısı
typedef struct {
    char filename[MAX_FILENAME_LEN];
    uint32_t file_size;
    uint16_t total_packets;
    uint16_t received_packets;
    uint8_t file_data[MAX_FILE_SIZE];
    bool transfer_active;
} file_transfer_t;

// Fonksiyon Prototipleri
uint8_t calculate_crc(uint8_t* data, uint16_t length);
void uart_send_byte(uint8_t byte);
void uart_send_packet(uint8_t* data, uint16_t length);
void send_ack(void);
void send_nack(void);
void send_ready(void);
bool receive_byte(uint8_t* byte);
void handle_file_start(uint8_t* packet, uint16_t length);
void handle_file_data(uint8_t* packet, uint16_t length);
void handle_file_end(uint8_t* packet, uint16_t length);
void save_file(const char* filename, uint8_t* data, uint32_t size);
void uart_receive_loop(void);
void init_uart_receiver(void);

#endif // UART_FILE_RECEIVER_H



