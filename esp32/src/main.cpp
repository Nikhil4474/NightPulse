// NightPulse on ESP32-S3: beat times -> on-chip apnea-like risk per minute.
// LCD shows only the risk graph. WiFi access point serves the full dashboard and accepts a beat-log upload.
// Serial (115200): d demo | r record from ADC ECG | s stop | c clear | b benchmark
#include <Arduino.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WebServer.h>
#include <SD_MMC.h>
#include "config.h"
#include "nightpulse_core.h"
#include "demo_rr.h"
#include "web_page.h"
#if USE_LCD
#include <Arduino_GFX_Library.h>
static Arduino_DataBus* bus = new Arduino_ESP32SPI(LCD_DC, LCD_CS, LCD_SCLK, LCD_MOSI, GFX_NOT_DEFINED);
static Arduino_GFX* panel = new Arduino_ST7789(bus, LCD_RST, 1, true, 172, 320, 34, 0, 34, 0);
static Arduino_GFX* gfx = panel;   // draw straight to the panel (no framebuffer)
#endif

#define MAXMIN 720
struct Hist { float score; uint8_t hr; uint8_t st; };
static Hist H[MAXMIN]; static int nh = 0;
static NightPulse np; static WebServer web(80);
enum Job { IDLE, DEMO, FILEJOB, REC } job = IDLE;
static const char* UP = "/up.csv"; static bool sdok = false; static File lg;
static File jf; static size_t demo_i = 0; static uint32_t vnow = 0, t0 = 0; static int pct = 0;
static uint32_t us_sum = 0, us_max = 0; static int nscored = 0; static bool dirty = true;

static void resetAll() { np.reset(); nh = 0; nscored = 0; us_sum = us_max = 0; pct = 0; dirty = true; }

static void pollScores(uint32_t now) {
  NPResult r;
  for (;;) {
    uint32_t a = micros(); if (!np.poll(now, r)) break; uint32_t us = micros() - a;
    nscored++; us_sum += us; if (us > us_max) us_max = us;
    int i = r.minute - 2; if (i >= 0 && i < MAXMIN) { H[i] = {r.score, (uint8_t)(r.status == NP_STATUS_OK ? r.hr : 0), (uint8_t)r.status}; if (i + 1 > nh) nh = i + 1; }
    dirty = true;
    if (r.status == NP_STATUS_OK) Serial.printf("minute %3d  risk %.2f  %s  hr %.0f  (%u us)\n", r.minute, r.score, r.score > 0.5f ? "APNEA-LIKE" : "normal", r.hr, us);
    else Serial.printf("minute %3d  UNKNOWN (%s)\n", r.minute, r.why);
  }
}

#if USE_LCD
#include <Preferences.h>
static Preferences prefs; static int rot = 1;
static uint16_t C(uint8_t r, uint8_t g, uint8_t b) { return gfx->color565(r, g, b); }
static void ctext(const char* t, int cx, int y, int size, uint16_t col) { gfx->setTextSize(size); gfx->setTextColor(col); gfx->setCursor(cx - (int)strlen(t) * 3 * size, y); gfx->print(t); }
static void arc(int cx, int cy, int r0, int r1, float v0, float v1, uint16_t col) {      // value 0..1 maps to 180..0 degrees (left to right)
  for (float v = v0; v < v1; v += 0.004f) {
    float a = M_PI * (1 - v), b = M_PI * (1 - min(v + 0.0045f, v1));
    int x0 = cx + r0 * cosf(a), y0 = cy - r0 * sinf(a), x1 = cx + r1 * cosf(a), y1 = cy - r1 * sinf(a), x2 = cx + r1 * cosf(b), y2 = cy - r1 * sinf(b), x3 = cx + r0 * cosf(b), y3 = cy - r0 * sinf(b);
    gfx->fillTriangle(x0, y0, x1, y1, x2, y2, col); gfx->fillTriangle(x0, y0, x2, y2, x3, y3, col);
  }
}
static void drawLcd(const char* msg = nullptr) {
  const int cx = 160, cy = 112, ro = 92, ri = 66;
  uint16_t bg = C(16, 35, 49), mute = C(140, 166, 183), white = C(240, 246, 250);
  gfx->fillScreen(bg);
  if (msg) { ctext(msg, 160, 70, 2, white); return; }
  arc(cx, cy, ri, ro, 0.0f, 0.4f, C(67, 205, 120)); arc(cx, cy, ri, ro, 0.4f, 0.5f, C(222, 164, 58)); arc(cx, cy, ri, ro, 0.5f, 1.0f, C(235, 90, 106));
  gfx->setTextSize(1); gfx->setTextColor(mute); gfx->setCursor(cx - ro + 8, cy + 6); gfx->print("0"); gfx->setCursor(cx + ro - 14, cy + 6); gfx->print("1");
  int i = nh - 1; char buf[40];
  if (i < 0) { ctext("--", cx, cy - 34, 3, mute); ctext("WAITING FOR DATA", cx, 132, 2, mute); ctext("open 192.168.4.1", cx, 158, 1, mute); }
  else if (H[i].st != NP_STATUS_OK) { ctext("--", cx, cy - 34, 3, mute); ctext("LOW QUALITY", cx, 132, 2, C(222, 164, 58)); snprintf(buf, sizeof buf, "minute %d. signal not usable", i + 2); ctext(buf, cx, 158, 1, mute); }
  else {
    float sc = H[i].score; uint16_t col = sc > 0.5f ? C(255, 93, 108) : sc >= 0.4f ? C(245, 177, 61) : C(74, 222, 128);
    snprintf(buf, sizeof buf, "%.2f", sc); ctext(buf, cx, cy - 36, 4, col);
    float a = M_PI * (1 - sc); for (int d = -1; d <= 1; d++) gfx->drawLine(cx + 28 * cosf(a) + d, cy - 28 * sinf(a), cx + (ri - 6) * cosf(a) + d, cy - (ri - 6) * sinf(a), white);
    ctext(sc > 0.5f ? "APNEA-LIKE PATTERN" : sc >= 0.4f ? "BORDERLINE" : "NORMAL PATTERN", cx, 132, 2, col);
    snprintf(buf, sizeof buf, "minute %d. research cue, not a diagnosis", i + 2); ctext(buf, cx, 158, 1, mute);
  }
  gfx->fillCircle(cx, cy - 2, 5, white);
}
static void flipCheck() {     // double tap BOOT (GPIO0) to flip the screen
  static bool last = true; static uint32_t t1 = 0; bool now = digitalRead(0); uint32_t ms = millis();
  if (last && !now) { if (ms - t1 < 700 && t1) { rot = rot == 1 ? 3 : 1; panel->setRotation(rot); prefs.putInt("rot", rot); dirty = true; t1 = 0; } else t1 = ms; }
  last = now;
}
#endif

static void startDemo() { resetAll(); demo_i = 0; vnow = 0; job = DEMO; }
static void startFile() { resetAll(); jf = LittleFS.open(UP); if (!jf) { job = IDLE; return; } job = FILEJOB; }
static void startRec() {
  resetAll(); t0 = millis(); job = REC; if (lg) lg.close();
  if (sdok) { lg = SD_MMC.open("/latest.csv", FILE_WRITE); Serial.println("logging beats to SD /latest.csv"); }
  else lg = LittleFS.open("/rec.csv", FILE_WRITE);
}

static void stepJob() {
  if (job == DEMO) {
    for (int k = 0; k < 40 && demo_i < sizeof(DEMO_RR) / 2; k++) { vnow += DEMO_RR[demo_i++]; np.addBeat(vnow); pollScores(vnow); }
    pct = demo_i * 100 / (sizeof(DEMO_RR) / 2); if (demo_i >= sizeof(DEMO_RR) / 2) { job = IDLE; pct = 100; dirty = true; }
  } else if (job == FILEJOB) {
    for (int k = 0; k < 40 && jf.available(); k++) {
      String l = jf.readStringUntil('\n'); l.trim(); int c = l.indexOf(','); if (c > 0) l = l.substring(0, c); if (!l.length() || !isDigit(l[0])) continue;
      uint32_t ms = l.indexOf('.') >= 0 ? (uint32_t)(l.toFloat() * 1000.0f + 0.5f) : (uint32_t)l.toInt(); np.addBeat(ms); pollScores(ms);
    }
    pct = jf.size() ? jf.position() * 100 / jf.size() : 100; if (!jf.available()) { jf.close(); job = IDLE; pct = 100; dirty = true; }
  } else if (job == REC) {
    static uint32_t next = 0, lastbeat = 0; static float prev = 0, pk = 0; uint32_t us = micros(); if ((int32_t)(us - next) < 0) return; next = us + 4000;   // 250 Hz
    float v = analogRead(ECG_PIN), d = v - prev, e; prev = v; e = d * d; pk = e > pk ? e : pk * 0.9995f; uint32_t now = millis() - t0;
    if (e > 0.35f * pk && e > 4.0f && now - lastbeat > 300) { lastbeat = now; np.addBeat(now); if (lg) { lg.println(now); lg.flush(); } pollScores(now); }
  }
}

static const char* jobName() { return job == DEMO ? "demo" : job == FILEJOB ? "scoring file" : job == REC ? "recording" : "idle"; }
static void handleState() {
  String s; s.reserve(nh * 14 + 80); s += "{\"status\":\""; s += jobName(); s += "\",\"pct\":"; s += pct; s += ",\"h\":[";
  for (int i = 0; i < nh; i++) { if (i) s += ','; s += '['; s += H[i].st == NP_STATUS_OK ? (int)(H[i].score * 100 + 0.5f) : -1; s += ','; s += H[i].hr; s += ']'; }
  s += "]}"; web.send(200, "application/json", s);
}
static void handleUploadData() {
  HTTPUpload& u = web.upload();
  if (u.status == UPLOAD_FILE_START) { job = IDLE; if (jf) jf.close(); jf = LittleFS.open(UP, FILE_WRITE); }
  else if (u.status == UPLOAD_FILE_WRITE) { if (jf) jf.write(u.buf, u.currentSize); }
  else if (u.status == UPLOAD_FILE_END || u.status == UPLOAD_FILE_ABORTED) { if (jf) jf.close(); }
}

void setup() {
  Serial.begin(115200); LittleFS.begin(true); analogReadResolution(12);
#if USE_LCD
  pinMode(LCD_BL, OUTPUT); digitalWrite(LCD_BL, HIGH); gfx->begin(); pinMode(0, INPUT_PULLUP); prefs.begin("np"); rot = prefs.getInt("rot", 1); panel->setRotation(rot);
#endif
  WiFi.mode(WIFI_AP); WiFi.softAP(AP_SSID, AP_PASS); IPAddress ip = WiFi.softAPIP();
  web.on("/", HTTP_GET, [] { web.send_P(200, "text/html", PAGE); });
  web.on("/api/state", HTTP_GET, handleState);
  web.on("/api/demo", HTTP_GET, [] { startDemo(); web.send(200, "application/json", "{}"); });
  web.on("/api/clear", HTTP_GET, [] { job = IDLE; resetAll(); web.send(200, "application/json", "{}"); });
  web.on("/api/upload", HTTP_POST, [] { web.send(200, "application/json", "{}"); startFile(); }, handleUploadData);
  SD_MMC.setPins(14, 15, 16); sdok = SD_MMC.begin("/sdcard", true); Serial.println(sdok ? "SD card ready" : "no SD card (logging to flash)");
  web.on("/api/log", HTTP_GET, [] { File f = sdok ? SD_MMC.open("/latest.csv") : LittleFS.open("/rec.csv"); if (!f) { web.send(404, "text/plain", "no log"); return; } web.streamFile(f, "text/csv"); f.close(); });
  web.begin();
  Serial.printf("NightPulse %s. WiFi '%s' / '%s', open http://%s\n", NP_VERSION, AP_SSID, AP_PASS, ip.toString().c_str());
#if USE_LCD
  char m[40]; snprintf(m, sizeof m, "WiFi %s", AP_SSID); drawLcd(m); gfx->setTextSize(1); gfx->setTextColor(C(140, 166, 183)); gfx->setCursor(30, 110); gfx->printf("password %s   http://%s", AP_PASS, ip.toString().c_str()); delay(6000); dirty = true;
#endif
}

void loop() {
  web.handleClient();
  if (Serial.available()) switch (Serial.read()) {
    case 'd': startDemo(); break; case 'r': startRec(); break; case 's': job = IDLE; if (lg) lg.close(); break; case 'c': job = IDLE; resetAll(); break;
    case 'b': Serial.printf("heap %u psram %u cpu %u MHz; scoring %d min, mean %u us, max %u us\n", ESP.getFreeHeap(), ESP.getFreePsram(), getCpuFrequencyMhz(), nscored, nscored ? us_sum / nscored : 0, us_max); break;
  }
  stepJob();
#if USE_LCD
  flipCheck(); static uint32_t lastdraw = 0; if (dirty && millis() - lastdraw > 300) { dirty = false; lastdraw = millis(); drawLcd(); }
#endif
}
