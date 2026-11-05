// Power of a pre-registered late-takeoff test for silicyte-0128 extended to R rounds (node, seed 20261105).
// World per seed k: true reach x_t = x0 + g_k * t for t <= T0, then gains grow by m per round: dx_t = g_k * m^(t - T0).
// g_k ~ N(g, sg) across seeds (measured: g 0.26, sd across seeds 0.107 at 08:25 ET).
// Training random walk: x_t += N(0, sw) per round. Measurement: y_t = x_t + N(0, sm), sm from the lag-1 structure of seed 1.
// Ceiling: an unbounded ruler (deeper pool) vs the depth-10 pool (y capped near CAP).
// Test L: per seed, OLS slope of y on rounds [11, R] minus OLS slope on rounds [0, 10]; one-sided t across K seeds, df K-1,
// at alpha 0.04 (critical 2.605 for K = 4), the same alpha and seed-level unit as the registered curvature test.
let s = 20261105; const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
const N = () => { let u = 0, v = 0; while (u === 0) u = rnd(); v = rnd(); return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v); };
const slope = (xs, ys) => { const n = xs.length, mx = xs.reduce((a, b) => a + b) / n, my = ys.reduce((a, b) => a + b) / n;
  let sxy = 0, sxx = 0; for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; } return sxy / sxx; };
function run({ K = 4, R = 30, g = 0.26, sg = 0.107, sw = 0.08, sm = 0.17, m = 1.0, T0 = 10, cap = Infinity, crit = 2.605 }) {
  const d = [];
  for (let k = 0; k < K; k++) {
    const gk = g + sg * N(); let x = 2.8; const ys = [];
    for (let t = 0; t <= R; t++) {
      if (t > 0) x += (t <= T0 ? gk : gk * Math.pow(m, t - T0)) + sw * N();
      ys.push(Math.min(x, cap) + sm * N());
    }
    const early = [...Array(11).keys()], late = []; for (let t = 11; t <= R; t++) late.push(t);
    d.push(slope(late, late.map(t => ys[t])) - slope(early, early.map(t => ys[t])));
  }
  const mean = d.reduce((a, b) => a + b) / K, sd = Math.sqrt(d.reduce((a, b) => a + (b - mean) ** 2, 0) / (K - 1));
  return mean / (sd / Math.sqrt(K)) > crit;
}
const rate = (o, n = 2000) => { let c = 0; for (let i = 0; i < n; i++) c += run(o) ? 1 : 0; return c / n; };
const rows = [];
for (const R of [20, 30, 40]) for (const cap of [Infinity, 9.5]) for (const [m, T0] of [[1.0, 10], [1.05, 10], [1.1, 10], [1.2, 10], [1.1, 15], [1.2, 15], [1.2, 20]]) {
  if (T0 >= R) continue;
  rows.push({ R, ruler: cap === Infinity ? 'deep' : 'depth10', m, T0, declare_rate: rate({ R, m, T0, cap }) });
}
for (const sm of [0.12, 0.25]) rows.push({ R: 30, ruler: 'deep', m: 1.0, T0: 10, sm, declare_rate: rate({ R: 30, m: 1.0, T0: 10, sm }) });
for (const sw of [0.0, 0.15]) rows.push({ R: 30, ruler: 'deep', m: 1.0, T0: 10, sw, declare_rate: rate({ R: 30, m: 1.0, T0: 10, sw }) });
console.log(JSON.stringify(rows));
require('fs').writeFileSync('sim_late_takeoff.json', JSON.stringify(rows, null, 1));
