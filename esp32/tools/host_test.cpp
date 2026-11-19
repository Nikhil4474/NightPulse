// g++ -O2 -I../src host_test.cpp -o host_test && ./host_test beats_ms.txt
#include <stdio.h>
#include "nightpulse_core.h"
int main(int argc, char** argv) {
  static NightPulse np; FILE* f = fopen(argv[1], "r"); unsigned long v; uint32_t last = 0; NPResult r;
  while (fscanf(f, "%lu", &v) == 1) { np.addBeat(v); last = v; while (np.poll(v, r)) printf("%d %d %.5f %.2f %s\n", r.minute, r.status, r.score, r.hr, r.why); }
  return 0;
}
