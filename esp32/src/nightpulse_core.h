// NightPulse core for microcontrollers: beat times (ms) -> per-minute apnea-like risk.
// Same maths as nightpulse.py (model v4). Input is R-peak times only; the ECG/PPG front end must find the beats.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
#include "model_data.h"

#define NP_MAXB 1400            // beats kept (about 7 min at 200 bpm)
#define NP_MAXX 1500            // 4 Hz resampled samples (5 min = 1200)
#define NP_STATUS_OK 0
#define NP_UNKNOWN 1

struct NPResult { int minute; int status; float score; float hr; const char* why; };

class NightPulse {
 public:
  uint32_t b[NP_MAXB]; int n = 0; int next_minute = 2;
  void reset() { n = 0; next_minute = 2; }
  void addBeat(uint32_t ms) {
    if (n == NP_MAXB) { memmove(b, b + 1, (NP_MAXB - 1) * sizeof(uint32_t)); n--; }   // drop oldest
    b[n++] = ms;
  }
  // Call often. Returns true when a new minute result is ready (needs 2 minutes of look-ahead after the minute).
  bool poll(uint32_t now_ms, NPResult& r) {
    if ((uint32_t)(next_minute + 3) * 60000u > now_ms) return false;
    r = scoreMinute(next_minute); next_minute++; return true;
  }
  NPResult scoreMinute(int m) {
    NPResult r{m, NP_UNKNOWN, 0, 0, "ok"};
    double f0[9], nb[16], w[4];
    if (!gate(m)) { r.why = "irregular or missing beats"; return r; }
    minuteFeats(m, f0); r.hr = (float)(60.0 / f0[0]);
    if (!winFeats(m, w)) { r.why = "short window"; return r; }
    int k = 0; const int ks[4] = {-1, 1, -2, 2};
    for (int i = 0; i < 4; i++) {
      int mm = m + ks[i];
      if (mm >= 0 && gate(mm)) { double g[9]; minuteFeats(mm, g); for (int j = 0; j < 4; j++) nb[k++] = g[j]; }
      else for (int j = 0; j < 4; j++) nb[k++] = 0;
    }
    float f[NP_NF]; for (int i = 0; i < 9; i++) f[i] = (float)f0[i]; for (int i = 0; i < 4; i++) f[9 + i] = (float)w[i]; for (int i = 0; i < 16; i++) f[13 + i] = (float)nb[i];
    int out = 0; for (int i = 0; i < NP_NF; i++) if (f[i] < NP_OOD_LO[i] || f[i] > NP_OOD_HI[i]) out++;
    if (out >= NP_OOD_MAX) { r.why = "outside trained range"; return r; }
    double z = NP_INTERCEPT;
    for (int i = 0; i < NP_NF; i++) { double v = f[i] < NP_CLIP_LO[i] ? NP_CLIP_LO[i] : (f[i] > NP_CLIP_HI[i] ? NP_CLIP_HI[i] : f[i]); z += (v - NP_MEAN[i]) / NP_SCALE[i] * NP_COEF[i]; }
    r.score = (float)(1.0 / (1.0 + exp(-z))); r.status = NP_STATUS_OK; return r;
  }

 private:
  // beats with start <= t < end (seconds*1000)
  int range(int64_t s_ms, int64_t e_ms, int& lo) const {
    int i = 0; while (i < n && (int64_t)b[i] < s_ms) i++; lo = i; while (i < n && (int64_t)b[i] < e_ms) i++; return i - lo;
  }
  bool gate(int m) const {
    int lo; int c = range((int64_t)m * 60000, (int64_t)(m + 1) * 60000, lo);
    if (c < 30 || c > 200) return false;
    int ok = 0; for (int i = lo + 1; i < lo + c; i++) { double rr = (b[i] / 1000.0 - b[i - 1] / 1000.0); if (rr > 0.3 && rr < 2.0) ok++; }
    return (double)ok / (c - 1) >= 0.9;
  }
  static double pct(double* a, int len, double q) {   // numpy linear percentile on a sorted copy
    for (int i = 1; i < len; i++) { double v = a[i]; int j = i - 1; while (j >= 0 && a[j] > v) { a[j + 1] = a[j]; j--; } a[j + 1] = v; }
    double pos = (len - 1) * q / 100.0; int lo = (int)pos; double fr = pos - lo; return lo + 1 < len ? a[lo] + (a[lo + 1] - a[lo]) * fr : a[lo];
  }
  void minuteFeats(int m, double* f) const {
    int lo; int c = range((int64_t)m * 60000, (int64_t)(m + 1) * 60000, lo);
    double rr[260]; int k = 0;
    for (int i = lo + 1; i < lo + c; i++) { double v = (b[i] / 1000.0 - b[i - 1] / 1000.0); if (v > 0.3 && v < 2.0) rr[k++] = v; }
    double s = 0; for (int i = 0; i < k; i++) s += rr[i]; double mean = s / k;
    double v2 = 0, mn = rr[0], mx = rr[0]; for (int i = 0; i < k; i++) { v2 += (rr[i] - mean) * (rr[i] - mean); if (rr[i] < mn) mn = rr[i]; if (rr[i] > mx) mx = rr[i]; }
    double sd = sqrt(v2 / k), ss = 0; int big = 0;
    for (int i = 1; i < k; i++) { double d = rr[i] - rr[i - 1]; ss += d * d; if (fabs(d) > 0.05) big++; }
    double p90 = pct(rr, k, 90), p10 = pct(rr, k, 10);
    f[0] = mean; f[1] = sd; f[2] = sqrt(ss / (k - 1)); f[3] = (double)big / (k - 1); f[4] = sd / mean; f[5] = mn; f[6] = mx; f[7] = p90 - p10; f[8] = k;
  }
  bool winFeats(int m, double* out) const {
    int lo; int c = range((int64_t)(m - 2) * 60000, (int64_t)(m + 3) * 60000, lo);
    static double tt[NP_MAXB], rr[NP_MAXB]; int k = 0;
    for (int i = lo + 1; i < lo + c; i++) { double v = (b[i] / 1000.0 - b[i - 1] / 1000.0); if (v > 0.3 && v < 2.0) { tt[k] = b[i] / 1000.0; rr[k++] = v; } }
    if (k < 100) return false;
    static double x[NP_MAXX]; int nx = 0; int j = 0;
    for (int i = 0;; i++) {                      // np.arange(tt[0], tt[-1], 0.25) with linear interpolation
      double t = tt[0] + i * 0.25; if (t >= tt[k - 1] || nx >= NP_MAXX) break;
      while (j + 2 < k && tt[j + 1] < t) j++;
      double fr = (t - tt[j]) / (tt[j + 1] - tt[j]); x[nx++] = rr[j] + (rr[j + 1] - rr[j]) * fr;
    }
    double mu = 0; for (int i = 0; i < nx; i++) mu += x[i]; mu /= nx; for (int i = 0; i < nx; i++) x[i] -= mu;
    int N = nx < 512 ? nx : 512, step = N - N / 2, nseg = (nx - N / 2) / step;
    static float ct[512], st[512], hw[512]; double w2 = 0;
    for (int i = 0; i < N; i++) { ct[i] = (float)cos(2 * M_PI * i / N); st[i] = (float)sin(2 * M_PI * i / N); hw[i] = (float)(0.5 - 0.5 * cos(2 * M_PI * i / N)); w2 += (double)hw[i] * hw[i]; }
    double val = 1.0 / (N * 0.25); int kmax = 0; while (kmax * val < 0.4) kmax++;
    static double P[260]; for (int i = 0; i <= kmax; i++) P[i] = 0;
    static float seg[512];
    for (int sgm = 0; sgm < nseg; sgm++) {
      const double* xs = x + sgm * step; double sm = 0; for (int i = 0; i < N; i++) sm += xs[i]; sm /= N;
      for (int i = 0; i < N; i++) seg[i] = (float)((xs[i] - sm) * hw[i]);
      for (int q = 0; q <= kmax; q++) {
        double re = 0, im = 0; for (int i = 0; i < N; i++) { int idx = (int)(((int64_t)q * i) % N); re += seg[i] * ct[idx]; im -= seg[i] * st[idx]; }
        double p = (re * re + im * im) / (4.0 * w2); if (q != 0 && !(N % 2 == 0 && q == N / 2)) p *= 2; P[q] += p / nseg;
      }
    }
    auto bd = [&](double a, double bb) { double s = 0; for (int q = 0; q <= kmax; q++) { double f = q * val; if (f >= a && f < bb) s += P[q]; } return s; };
    double tot = bd(0.0033, 0.4) + 1e-9;
    out[0] = bd(0.01, 0.04) / tot; out[1] = bd(0.04, 0.15) / tot; out[2] = bd(0.15, 0.4) / tot; out[3] = log(bd(0.01, 0.04) + 1e-9);
    return true;
  }
};
