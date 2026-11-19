#pragma once
#define AP_SSID   "NightPulse"
#define AP_PASS   "nightpulse"        // 8+ characters. Join this WiFi, then open http://192.168.4.1
#define ECG_PIN   1                   // ADC pin for an AD8232 style ECG output (untested hardware path)
// Waveshare ESP32-S3-LCD-1.47 (ST7789 172x320), pins from the Waveshare wiki
#define LCD_MOSI 45
#define LCD_SCLK 40
#define LCD_CS   42
#define LCD_DC   41
#define LCD_RST  39
#define LCD_BL   48
