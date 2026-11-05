// A1 UNDERPOWERED check for silicyte-0128 (PREREG sec. 5 label 2): re-simulated power at m = 1.2 at the MEASURED noise and gain.
// Noise model (PREREG sec. 4 / VERDICT_SIM): y_t = x_t + e_t, x_t = x_{t-1} + g m^(t-1) + w_t; w ~ N(0, tau), e ~ N(0, s_e).
// Moments of within-seed gains D_t: var(D) = tau^2 + 2 s_e^2, lag-1 autocov = -s_e^2. Seeds differ in g by sd sg.
const Y = {s1: [2.863, 3.101, 3.168, 3.738, 3.532, 3.723, 3.781, 4.08, 4.398, 4.428, 4.682],
  s2: [2.86, 2.956, 3.292, 3.984, 4.234, 4.033, 4.386, 4.511, 4.617, 4.437, 4.9],
  s3: [2.778, 3.231, 3.148, 3.381, 3.551, 4.058, 3.905, 4.204, 4.201, 4.091, 4.305],
  s4: [2.635, 2.96, 3.22, 3.502, 3.659, 3.803, 3.814, 4.001, 4.447, 4.844, 4.473]};
const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
let v = 0, c1 = 0, nv = 0, nc = 0; const gs = [];
for (const k in Y) { const y = Y[k], d = y.slice(1).map((x, i) => x - y[i]), m = mean(d); gs.push(m);
  d.forEach(x => { v += (x - m) ** 2; nv++; }); for (let i = 1; i < d.length; i++) { c1 += (d[i] - m) * (d[i - 1] - m); nc++; } }
const varD = v / (nv - 4), ac1 = c1 / nc, se2 = Math.max(0, -ac1), tau2 = Math.max(0, varD - 2 * se2);
const g = mean(gs), sg = Math.sqrt(mean(gs.map(x => (x - g) ** 2)) * 4 / 3);
// xorshift128+ RNG
let s0 = 0x9E3779B97F4A7C15n, s1 = 0x0123456789ABCDEFn; const M64 = (1n << 64n) - 1n;
function rnd() { let x = s0, y = s1; s0 = y; x ^= (x << 23n) & M64; s1 = x ^ y ^ (x >> 17n) ^ (y >> 26n); return Number(((s1 + y) & M64) >> 11n) / 2 ** 53; }
function N() { let u = 0; while (u === 0) u = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * rnd()); }
function quadc(ts, ys) { // OLS y = a + b t + c t^2, return c
  const n = ts.length; const X = ts.map(t => [1, t, t * t]); const XtX = [[0,0,0],[0,0,0],[0,0,0]], Xty = [0,0,0];
  for (let i = 0; i < n; i++) for (let a = 0; a < 3; a++) { Xty[a] += X[i][a] * ys[i]; for (let b = 0; b < 3; b++) XtX[a][b] += X[i][a] * X[i][b]; }
  const A = XtX.map((r, i) => [...r, Xty[i]]); for (let i = 0; i < 3; i++) { let p = i; for (let r = i + 1; r < 3; r++) if (Math.abs(A[r][i]) > Math.abs(A[p][i])) p = r; [A[i], A[p]] = [A[p], A[i]];
    for (let r = 0; r < 3; r++) if (r !== i) { const f = A[r][i] / A[i][i]; for (let cc = i; cc < 4; cc++) A[r][cc] -= f * A[i][cc]; } } return A[2][3] / A[2][2]; }
const T96 = 2.605, T95 = 2.353; // one-sided alpha 0.04 and 0.05 at df 3
function run(m, K = 4, R = 10) { const cs = [], gm = [];
  for (let k = 0; k < K; k++) { const gk = g + sg * N(); let x = 2.8; const ys = [];
    for (let t = 0; t <= R; t++) { if (t > 0) x += gk * Math.pow(m, t - 1) + Math.sqrt(tau2) * N(); ys.push(x + Math.sqrt(se2) * N()); }
    cs.push(quadc([...Array(R + 1).keys()], ys)); gm.push((ys[R] - ys[0]) / R); }
  const mc = mean(cs), sc = Math.sqrt(cs.reduce((a, c) => a + (c - mc) ** 2, 0) / (K - 1)), t = mc / (sc / Math.sqrt(K));
  const mg = mean(gm), sdg = Math.sqrt(gm.reduce((a, c) => a + (c - mg) ** 2, 0) / (K - 1)), lb = mg - T95 * sdg / Math.sqrt(K);
  return {shape: t > T96, level: lb > 0}; }
const NR = 4000; const out = {measured: {g, sg, tau: Math.sqrt(tau2), s_e: Math.sqrt(se2), varD, ac1}};
for (const m of [1.0, 1.1, 1.2]) { let sh = 0, both = 0, lv = 0; for (let i = 0; i < NR; i++) { const r = run(m); sh += r.shape; lv += r.level; both += r.shape && r.level; }
  out['m' + m] = {shape: sh / NR, compounds: both / NR, level: lv / NR}; }
console.log(JSON.stringify(out, null, 1)); require('fs').writeFileSync('resim_a1.json', JSON.stringify(out, null, 1));
