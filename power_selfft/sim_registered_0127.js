// sim_registered_0127.js: the rule exactly as registered for silicyte-0127 (A1), against the validated variant in
// testpower/sim_verify_rasch.js (copied functions, same world). Differences tested:
//   ALPHA: registered one-sided 0.04 (critical t at df 3 = 2.605) vs the verifier's 0.05 (2.353).
//   R0:    registered scores round 0 ONCE and shares it across the K seeds (c_k correlated through y_0) vs an own round 0 per seed.
//   FIT:   registered read_selfft.py fits task difficulties jointly over ALL seeds and rounds vs per seed.
// World as VERDICT_SIM: random-walk training noise tau per round per seed, logistic difficulty spread s, S samples per task.
// Usage: DESIGN='{"n":80,"R":8,"K":4,"S":64,"p0":0.2,"g1":0.25,"tau":0.1}' MS=1,1.2 RUNS=1000 node sim_registered_0127.js
function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const sig = x => 1 / (1 + Math.exp(-x));
function gauss(rng) { let u = 0, v = 0; while (u === 0) u = rng(); while (v === 0) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
function quadC(xs, ys) { const n = xs.length; let S = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], T = [0, 0, 0];
  for (let i = 0; i < n; i++) { const v = [1, xs[i], xs[i] ** 2]; for (let a = 0; a < 3; a++) { T[a] += v[a] * ys[i]; for (let b = 0; b < 3; b++) S[a][b] += v[a] * v[b]; } }
  const det = M => M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0]) + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]);
  return det(S.map((row, i) => [row[0], row[1], T[i]])) / det(S); }
// units: array of count rows (Int32Array n); returns theta per unit; difficulties shared across all given units
function rasch(units, S) {
  const U = units.length, n = units[0].length, keep = [];
  for (let i = 0; i < n; i++) { let t = 0; for (let u = 0; u < U; u++) t += units[u][i]; if (t > 0 && t < S * U) keep.push(i); }
  if (keep.length < 2) return null; const th = new Array(U).fill(0), b = {}; for (const i of keep) b[i] = 0;
  for (let it = 0; it < 60; it++) {
    for (let u = 0; u < U; u++) { let g = 0, h = 0; for (const i of keep) { const p = sig(th[u] - b[i]); g += units[u][i] - S * p; h += S * p * (1 - p); } th[u] += Math.max(-2, Math.min(2, g / h)); }
    for (const i of keep) { let g = 0, h = 0; for (let u = 0; u < U; u++) { const p = sig(th[u] - b[i]); g += S * p - units[u][i]; h += S * p * (1 - p); } b[i] += Math.max(-2, Math.min(2, g / h)); }
  }
  return th; }
const T04 = { 2: 3.320, 3: 2.605, 4: 2.333, 5: 2.191 }, T05 = { 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015 };
function sample(rng, z, th, s, S) { const row = new Int32Array(z.length); for (let i = 0; i < z.length; i++) { const p = sig(th - s * z[i]); let c = 0; for (let j = 0; j < S; j++) if (rng() < p) c++; row[i] = c; } return row; }
function run(rng, { n, R, p0, g1, m, S = 64, s = 1.5, tau = 0, K = 4 }) {
  const z = Array.from({ length: n }, () => gauss(rng));
  const pm = th => z.reduce((a, zi) => a + sig(th - s * zi), 0) / n;
  let lo = -12, hi = 12; for (let it = 0; it < 50; it++) { const mid = (lo + hi) / 2; if (pm(mid) < p0) lo = mid; else hi = mid; }
  const th0 = (lo + hi) / 2, rr = Array.from({ length: R + 1 }, (_, r) => r);
  const shared0 = sample(rng, z, th0, s, S);
  const seeds = [];
  for (let k = 0; k < K; k++) { let th = th0; const rows = [sample(rng, z, th0, s, S)];
    for (let r = 1; r <= R; r++) { th += g1 * m ** (r - 1) + tau * gauss(rng); rows.push(sample(rng, z, th, s, S)); }
    seeds.push(rows); }
  // OWN: own round 0 per seed, per-seed Rasch (the validated variant)
  const cOwn = seeds.map(rows => { const t = rasch(rows, S); return t ? quadC(rr, t) : 0; });
  // REG: shared round 0, joint Rasch over all seeds and rounds (read_selfft.py as registered)
  const units = [shared0]; for (const rows of seeds) for (let r = 1; r <= R; r++) units.push(rows[r]);
  const tj = rasch(units, S); const cReg = [];
  for (let k = 0; k < K; k++) { const th = [tj[0]]; for (let r = 1; r <= R; r++) th.push(tj[1 + k * R + (r - 1)]); cReg.push(quadC(rr, th)); }
  // OWN round 0 + joint fit over all seeds (the amended rule)
  const unitsO = []; for (const rows of seeds) for (let r = 0; r <= R; r++) unitsO.push(rows[r]);
  const tjo = rasch(unitsO, S); const cOJ = []; for (let k = 0; k < K; k++) cOJ.push(quadC(rr, tjo.slice(k * (R + 1), (k + 1) * (R + 1))));
  // SHARED0 + per-seed fit (isolates the shared-round-0 effect)
  const cSh = seeds.map(rows => { const t = rasch([shared0, ...rows.slice(1)], S); return t ? quadC(rr, t) : 0; });
  const tstat = a => { const mu = a.reduce((x, y) => x + y) / K, sd = Math.sqrt(a.reduce((x, c) => x + (c - mu) ** 2, 0) / (K - 1)); return mu / (sd / Math.sqrt(K)); };
  return { own05: tstat(cOwn) > T05[K - 1], own04: tstat(cOwn) > T04[K - 1], sh04: tstat(cSh) > T04[K - 1], reg04: tstat(cReg) > T04[K - 1], ownjoint04: tstat(cOJ) > T04[K - 1] };
}
const d = JSON.parse(process.env.DESIGN), MS = (process.env.MS || '1,1.2').split(',').map(Number), RUNS = +(process.env.RUNS || 1000);
const rng = mulberry32(+(process.env.SEED || 20261104));
const out = [];
for (const m of MS) { const h = { own05: 0, own04: 0, sh04: 0, reg04: 0, ownjoint04: 0 }; for (let t = 0; t < RUNS; t++) { const r = run(rng, { ...d, m }); for (const k in h) h[k] += r[k] ? 1 : 0; }
  const rec = { ...d, m, runs: RUNS, ...Object.fromEntries(Object.entries(h).map(([k, v]) => [k, v / RUNS])) }; out.push(rec);
  console.log(`${JSON.stringify(d)} m=${m} OWN_a05=${rec.own05.toFixed(3)} OWN_a04=${rec.own04.toFixed(3)} SHARED0_a04=${rec.sh04.toFixed(3)} REGISTERED(shared0+joint)_a04=${rec.reg04.toFixed(3)} OWN0+JOINT_a04=${rec.ownjoint04.toFixed(3)}`); }
require('fs').appendFileSync(__dirname + '/sim_registered_0127.jsonl', out.map(x => JSON.stringify(x)).join('\n') + '\n');
