# NightPulse on ESP32-S3 (Waveshare ESP32-S3-LCD-1.47)
Plug in USB-C. Flash from a laptop: `pio run -e s3_lcd147 -t upload`, monitor: `pio device monitor` (hold BOOT while plugging in if no port appears).
The chip makes its own WiFi "NightPulse" (password "nightpulse"). Join it, open http://192.168.4.1 for the full dashboard (risk graph, heart rate, upload beat log, run demo).
The LCD shows only the risk graph. Serial: d demo, r record from ADC ECG (untested hardware), s stop, c clear, b benchmark.
Beat log format: one beat time in ms per line. SD card (optional, 1 bit mode, pins 14/15/16) holds /latest.csv while recording; /api/log downloads it.
Limits: needs a real ECG/PPG front end to find beats; board timings not measured; LCD offsets and the SD wiring come from the Waveshare wiki and are untested here.
`tools/gen_model.py` regenerates the weights; `tools/host_test.cpp` checks the core against Python.
