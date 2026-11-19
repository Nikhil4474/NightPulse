"""Writes src/model_data.h from ../model.json (same weights the board uses)."""
import json, os
d = os.path.dirname(os.path.abspath(__file__)); M = json.load(open(os.path.join(d, '..', '..', 'model.json')))
arr = lambda n, v: f"static const float {n}[{len(v)}] = {{{', '.join(f'{float(x)!r}f' for x in v)}}};\n"
s = f"// generated from model.json ({M['version']}); do not edit\n#pragma once\n#define NP_VERSION \"{M['version']}\"\n#define NP_NF {len(M['coef'])}\n#define NP_OOD_MAX {M['ood_max_features']}\n"
for n in ('mean', 'scale', 'coef', 'clip_lo', 'clip_hi', 'ood_lo', 'ood_hi'): s += arr('NP_' + n.upper(), M[n])
s += f"static const float NP_INTERCEPT = {float(M['intercept'])!r}f;\n"
open(os.path.join(d, '..', 'src', 'model_data.h'), 'w').write(s); print('wrote model_data.h', len(M['coef']), 'weights')
