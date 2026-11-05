// sim_selfft_power.js: power and false-positive rate of compounding rules for the SELF-FT HELD design (Silicyte, 2026-11-04).
//
// Extends testpower/sim_compounding_power.js in two ways the SELF-FT design needs:
//   1. Outcome per task per round is a pass FRACTION over S samples (SELF-FT samples S = 64 per HELD task per round),
//      not one Bernoulli solve. This is the continuous measure the approach verdict asked for.
//   2. Training-seed noise: every round retrains from base, so each adapter A_r carries its own random offset eps_r ~ N(0, sa)
//      on the logit scale, shared by ALL tasks in that round. A bootstrap over tasks cannot see it; it is what makes
//      round-to-round curves wiggle. sa = 0 reproduces a world with no training noise.
//
// World: n HELD tasks, z_i ~ N(0, 1), per-sample pass prob sigmoid(theta_r + eps_r - 1.5 z_i); theta_0 set so the mean
// per-sample pass rate is p0; theta_r = theta_{r-1} + g1 * m^(r-1). Rounds r = 1..R are the adapters A_1..A_R (h_0 = base,
// excluded from the shape tests as the approach verdict requires).
//
// Rules (one-sided alpha 0.05), statistic on y_r = logit(mean over tasks of pass fraction at round r), r = 1..R:
//   QUAD_TB : quadratic coefficient c of y_r on r, lower bound by task bootstrap (blind to eps_r)
//   QUAD_T  : same c, classical OLS t-test with R - 3 df (residuals carry eps_r and sampling noise)
//   GT_T    : OLS slope of gains D_r = y_r - y_{r-1}, r = 2..R, t-test with R - 3 df
//   ACC_AA  : c from QUAD, z-test with Var(c) from a known per-round noise sd measured by an A/A (two seeds per round
//             at rounds 1 and R, i.e. sa_hat from 2 pairs; modelled here as sa known up to a chi-square(2) draw)
// Usage: node sim_selfft_power.js  (RUNS, BOOT env vars)

function mulberry32(a) { return function () { a |= 0; a = a + 0x6D2B79F5 | 0; let t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
const sig = x => 1 / (1 + Math.exp(-x));
const logit = p => Math.log(p / (1 - p));
function gauss(rng) { let u = 0, v = 0; while (u === 0) u = rng(); while (v === 0) v = rng(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); }
function binom(rng, S, p) { let k = 0; for (let s = 0; s < S; s++) if (rng() < p) k++; return k; }

// least squares y = a + b x + c x^2: returns {c, se_c, df}
function quadFit(xs, ys) {
  const n = xs.length; const X = xs.map(x => [1, x, x * x]);
  const XtX = [[0, 0, 0], [0, 0, 0], [0, 0, 0]], Xty = [0, 0, 0];
  for (let i = 0; i < n; i++) for (let a = 0; a < 3; a++) { Xty[a] += X[i][a] * ys[i]; for (let b = 0; b < 3; b++) XtX[a][b] += X[i][a] * X[i][b]; }
  const inv = inv3(XtX); const beta = [0, 1, 2].map(a => inv[a][0] * Xty[0] + inv[a][1] * Xty[1] + inv[a][2] * Xty[2]);
  let rss = 0; for (let i = 0; i < n; i++) { const f = beta[0] + beta[1] * xs[i] + beta[2] * xs[i] * xs[i]; rss += (ys[i] - f) ** 2; }
  const df = n - 3; const s2 = df > 0 ? rss / df : NaN; return { c: beta[2], se_c: Math.sqrt(s2 * inv[2][2]), df, invcc: inv[2][2] };
}
function inv3(M) {
  const [a, b, c] = M[0], [d, e, f] = M[1], [g, h, i] = M[2];
  const A = e * i - f * h, B = -(d * i - f * g), C = d * h - e * g, D = -(b * i - c * h), E = a * i - c * g, F = -(a * h - b * g), G = b * f - c * e, H = -(a * f - c * d), I = a * e - b * d;
  const det = a * A + b * B + c * C; return [[A / det, D / det, G / det], [B / det, E / det, H / det], [C / det, F / det, I / det]];
}
function linFit(xs, ys) {
  const n = xs.length, mx = xs.reduce((s, x) => s + x, 0) / n, my = ys.reduce((s, y) => s + y, 0) / n;
  let sxy = 0, sxx = 0; for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; }
  const b = sxy / sxx; let rss = 0; for (let i = 0; i < n; i++) rss += (ys[i] - my - b * (xs[i] - mx)) ** 2;
  const df = n - 2; return { b, se: Math.sqrt(rss / df / sxx), df };
}
// one-sided 95% t critical values by df
const TCRIT = { 1: 6.314, 2: 2.920, 3: 2.353, 4: 2.132, 5: 2.015, 6: 1.943, 7: 1.895, 8: 1.860, 9: 1.833, 10: 1.812, 13: 1.771, 17: 1.740 };

function simulate(rng, { n, S, R, p0, g1, m, sa }) {
  const z = Array.from({ length: n }, () => gauss(rng));
  let lo = -12, hi = 8; for (let it = 0; it < 50; it++) { const mid = (lo + hi) / 2; const p = z.reduce((s, zi) => s + sig(mid - 1.5 * zi), 0) / n; if (p < p0) lo = mid; else hi = mid; }
  let theta = (lo + hi) / 2; const frac = [];
  for (let r = 0; r <= R; r++) {
    if (r > 0) theta += g1 * m ** (r - 1);
    const eps = r > 0 ? sa * gauss(rng) : 0;
    frac.push(z.map(zi => binom(rng, S, sig(theta + eps - 1.5 * zi)) / S));
  }
  return frac;
}
function yOf(frac, idx) { return frac.map(row => { const p = idx.reduce((s, i) => s + row[i], 0) / idx.length; return logit(Math.min(Math.max(p, 1e-4), 1 - 1e-4)); }); }

function decide(rng, frac, n, B, R, sa) {
  const all = Array.from({ length: n }, (_, i) => i); const y = yOf(frac, all);
  const rs = [], ys = []; for (let r = 1; r <= R; r++) { rs.push(r); ys.push(y[r]); }
  const q = quadFit(rs, ys);
  const boots = []; for (let b = 0; b < B; b++) { const idx = Array.from({ length: n }, () => Math.floor(rng() * n)); const yb = yOf(frac, idx); boots.push(quadFit(rs, rs.map(r => yb[r])).c); }
  boots.sort((a, b) => a - b); const QUAD_TB = boots[Math.floor(0.05 * B)] > 0;
  const QUAD_T = q.c / q.se_c > TCRIT[q.df];
  const dr = [], dv = []; for (let r = 2; r <= R; r++) { dr.push(r); dv.push(y[r] - y[r - 1]); }
  const l = linFit(dr, dv); const GT_T = l.b / l.se > (TCRIT[l.df] || 1.645);
  // ACC_AA: per-round noise variance = sa^2 (training) + task-sampling variance of y_r (from the bootstrap of c we only have c;
  // approximate task part by the bootstrap variance of c). sa estimated from 2 A/A pairs: sa_hat^2 = sa^2 * chi2(2)/2.
  const chi2 = (gauss(rng) ** 2 + gauss(rng) ** 2) / 2; const saHat2 = sa * sa * chi2;
  const mb = boots.reduce((s, x) => s + x, 0) / B, vb = boots.reduce((s, x) => s + (x - mb) ** 2, 0) / (B - 1);
  const varC = vb + saHat2 * q.invcc; const ACC_AA = q.c / Math.sqrt(varC) > 2.920; // df 2 for the A/A variance estimate
  return { QUAD_TB, QUAD_T, GT_T, ACC_AA };
}

const RUNS = +(process.env.RUNS || 200), B = +(process.env.BOOT || 200);
const rng = mulberry32(20261104);
const MS = [1.0, 1.1, 1.2, 1.5];
const designs = [];
for (const p0 of [0.05, 0.15]) for (const sa of [0, 0.1, 0.25]) for (const R of [6, 10]) designs.push({ n: 80, S: 64, R, p0, g1: 0.25, sa });
designs.push({ n: 80, S: 64, R: 6, p0: 0.05, g1: 0.10, sa: 0.1 });
const out = [];
for (const d of designs) {
  const name = `n=${d.n} S=${d.S} R=${d.R} p0=${d.p0} g1=${d.g1} sa=${d.sa}`;
  const line = [name];
  for (const m of MS) {
    const hits = { QUAD_TB: 0, QUAD_T: 0, GT_T: 0, ACC_AA: 0 };
    for (let k = 0; k < RUNS; k++) { const frac = simulate(rng, { ...d, m }); const dec = decide(rng, frac, d.n, B, d.R, d.sa); for (const key in hits) hits[key] += dec[key] ? 1 : 0; }
    const rec = { ...d, m, runs: RUNS, ...Object.fromEntries(Object.entries(hits).map(([k, v]) => [k, v / RUNS])) };
    out.push(rec); line.push(`m=${m}: TB ${rec.QUAD_TB.toFixed(3)} T ${rec.QUAD_T.toFixed(3)} GT ${rec.GT_T.toFixed(3)} AA ${rec.ACC_AA.toFixed(3)}`);
  }
  console.log(line.join(' | '));
}
require('fs').writeFileSync(__dirname + '/power_selfft.json', JSON.stringify(out, null, 1));
