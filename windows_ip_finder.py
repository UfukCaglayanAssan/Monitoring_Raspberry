#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TESCOM BMS IP Bulucu - Windows Uygulaması
Raspberry Pi'nin UDP broadcast mesajlarını dinleyerek IP adresini bulur.
"""

import socket
import json
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import webbrowser
from datetime import datetime
import sys

# Broadcast ayarları
BROADCAST_PORT = 9999
DISCOVERY_TIMEOUT = 10  # saniye

class IPFinderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("TESCOM BMS IP Bulucu")
        self.root.geometry("600x500")
        self.root.resizable(False, False)
        
        # Bulunan cihazlar
        self.discovered_devices = {}
        
        # UI oluştur
        self.create_ui()
        
        # Broadcast dinleyicisini başlat
        self.listening = False
        self.socket = None
        
    def create_ui(self):
        """Kullanıcı arayüzünü oluştur"""
        # Başlık
        title_frame = tk.Frame(self.root, bg="#2c3e50", height=60)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        title_label = tk.Label(
            title_frame,
            text="🔍 TESCOM BMS IP Bulucu",
            font=("Arial", 16, "bold"),
            bg="#2c3e50",
            fg="white"
        )
        title_label.pack(pady=15)
        
        # Ana frame
        main_frame = tk.Frame(self.root, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Arama butonu
        search_frame = tk.Frame(main_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.search_button = tk.Button(
            search_frame,
            text="🔍 IP Ara",
            command=self.start_search,
            font=("Arial", 12, "bold"),
            bg="#3498db",
            fg="white",
            relief=tk.FLAT,
            padx=20,
            pady=10,
            cursor="hand2"
        )
        self.search_button.pack(side=tk.LEFT, padx=(0, 10))
        
        self.stop_button = tk.Button(
            search_frame,
            text="⏹️ Durdur",
            command=self.stop_search,
            font=("Arial", 12),
            bg="#e74c3c",
            fg="white",
            relief=tk.FLAT,
            padx=20,
            pady=10,
            state=tk.DISABLED,
            cursor="hand2"
        )
        self.stop_button.pack(side=tk.LEFT)
        
        # Durum etiketi
        self.status_label = tk.Label(
            main_frame,
            text="Hazır - 'IP Ara' butonuna tıklayın",
            font=("Arial", 10),
            fg="#7f8c8d"
        )
        self.status_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Bulunan cihazlar listesi
        devices_label = tk.Label(
            main_frame,
            text="Bulunan Cihazlar:",
            font=("Arial", 11, "bold")
        )
        devices_label.pack(anchor=tk.W, pady=(10, 5))
        
        # Treeview (tablo)
        tree_frame = tk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Treeview
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("IP", "Hostname", "Port", "Zaman"),
            show="headings",
            yscrollcommand=scrollbar.set,
            height=10
        )
        scrollbar.config(command=self.tree.yview)
        
        # Kolon başlıkları
        self.tree.heading("IP", text="IP Adresi")
        self.tree.heading("Hostname", text="Hostname")
        self.tree.heading("Port", text="Port")
        self.tree.heading("Zaman", text="Bulunma Zamanı")
        
        # Kolon genişlikleri
        self.tree.column("IP", width=150)
        self.tree.column("Hostname", width=150)
        self.tree.column("Port", width=80)
        self.tree.column("Zaman", width=150)
        
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Çift tıklama ile tarayıcıda aç
        self.tree.bind("<Double-1>", self.open_in_browser)
        
        # Log alanı
        log_label = tk.Label(
            main_frame,
            text="Log:",
            font=("Arial", 10, "bold")
        )
        log_label.pack(anchor=tk.W, pady=(10, 5))
        
        self.log_text = scrolledtext.ScrolledText(
            main_frame,
            height=6,
            font=("Consolas", 9),
            bg="#ecf0f1"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def log(self, message):
        """Log mesajı ekle"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.log_text.insert(tk.END, log_message)
        self.log_text.see(tk.END)
        self.root.update()
        
    def start_search(self):
        """Aramayı başlat"""
        if self.listening:
            return
            
        self.log("🔍 IP araması başlatılıyor...")
        self.status_label.config(text="Aranıyor...", fg="#f39c12")
        self.search_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Önceki sonuçları temizle
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.discovered_devices.clear()
        
        # Broadcast dinleyicisini başlat
        self.listening = True
        self.listen_thread = threading.Thread(target=self.listen_broadcast, daemon=True)
        self.listen_thread.start()
        
    def stop_search(self):
        """Aramayı durdur"""
        self.listening = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
            
        self.log("⏹️ Arama durduruldu")
        self.status_label.config(text="Durduruldu", fg="#e74c3c")
        self.search_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
    def listen_broadcast(self):
        """UDP broadcast mesajlarını dinle"""
        try:
            # UDP socket oluştur
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            
            # Socket'i bağla (broadcast almak için)
            try:
                self.socket.bind(('0.0.0.0', BROADCAST_PORT))
            except OSError as e:
                # Port zaten kullanılıyorsa, rastgele port kullan
                self.log(f"⚠️ Port {BROADCAST_PORT} kullanılıyor, alternatif port deneniyor...")
                self.socket.bind(('0.0.0.0', 0))
            self.socket.settimeout(1.0)  # 1 saniye timeout
            
            self.log(f"✅ Broadcast dinleyicisi başlatıldı (Port: {BROADCAST_PORT})")
            
            while self.listening:
                try:
                    # Broadcast mesajını al
                    data, addr = self.socket.recvfrom(1024)
                    
                    # JSON mesajını parse et
                    try:
                        message = json.loads(data.decode('utf-8'))
                        
                        # TESCOM BMS mesajı mı kontrol et
                        if message.get('type') == 'tescom_bms_discovery':
                            ip = message.get('ip')
                            hostname = message.get('hostname', 'Bilinmiyor')
                            port = message.get('port', 80)
                            
                            # Yeni cihaz mı kontrol et
                            if ip not in self.discovered_devices:
                                self.discovered_devices[ip] = {
                                    'ip': ip,
                                    'hostname': hostname,
                                    'port': port,
                                    'timestamp': datetime.now()
                                }
                                
                                # Listeye ekle
                                self.root.after(0, self.add_device, ip, hostname, port)
                                self.log(f"✅ Cihaz bulundu: {ip} ({hostname})")
                                
                    except json.JSONDecodeError:
                        pass  # Geçersiz JSON, yok say
                        
                except socket.timeout:
                    continue  # Timeout normal, devam et
                except Exception as e:
                    if self.listening:
                        self.log(f"⚠️ Hata: {e}")
                        
        except Exception as e:
            self.log(f"❌ Broadcast dinleyici hatası: {e}")
            self.root.after(0, self.stop_search)
        finally:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
                
    def add_device(self, ip, hostname, port):
        """Cihazı listeye ekle"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.tree.insert("", tk.END, values=(ip, hostname, port, timestamp))
        
        # Durum güncelle
        count = len(self.discovered_devices)
        self.status_label.config(
            text=f"{count} cihaz bulundu",
            fg="#27ae60"
        )
        
    def open_in_browser(self, event):
        """Seçili cihazı tarayıcıda aç"""
        selection = self.tree.selection()
        if not selection:
            return
            
        item = self.tree.item(selection[0])
        ip = item['values'][0]
        port = item['values'][2]
        
        url = f"http://{ip}:{port}"
        self.log(f"🌐 Tarayıcıda açılıyor: {url}")
        
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Hata", f"Tarayıcı açılamadı: {e}")

def main():
    """Ana fonksiyon"""
    root = tk.Tk()
    app = IPFinderApp(root)
    
    # Pencere kapatıldığında temizlik yap
    def on_closing():
        app.stop_search()
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == '__main__':
    main()

