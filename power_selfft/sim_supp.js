// sim_supp.js: supplementary cells for sim_selfft_power.js (same world, same rules): smaller per-round gain g1 and R = 8.
// Reuses the main file's functions by loading it as text with its run block stripped.
const fs = require('fs');
const src = fs.readFileSync(__dirname + '/sim_selfft_power.js', 'utf8').split('const RUNS =')[0];
eval(src);
const RUNS = +(process.env.RUNS || 200), B = +(process.env.BOOT || 200);
const rng = mulberry32(20261105);
const MS = [1.0, 1.1, 1.2, 1.5];
const designs = [];
for (const g1 of [0.10, 0.25]) for (const R of [6, 8, 10]) designs.push({ n: 80, S: 64, R, p0: 0.10, g1, sa: 0.1 });
for (const R of [8, 10]) designs.push({ n: 80, S: 64, R, p0: 0.10, g1: 0.25, sa: 0.25 });
const out = [];
for (const d of designs) {
  const line = [`n=${d.n} S=${d.S} R=${d.R} p0=${d.p0} g1=${d.g1} sa=${d.sa}`];
  for (const m of MS) {
    const hits = { QUAD_TB: 0, QUAD_T: 0, GT_T: 0, ACC_AA: 0 };
    for (let k = 0; k < RUNS; k++) { const frac = simulate(rng, { ...d, m }); const dec = decide(rng, frac, d.n, B, d.R, d.sa); for (const key in hits) hits[key] += dec[key] ? 1 : 0; }
    const rec = { ...d, m, runs: RUNS, ...Object.fromEntries(Object.entries(hits).map(([k, v]) => [k, v / RUNS])) };
    out.push(rec); line.push(`m=${m}: TB ${rec.QUAD_TB.toFixed(3)} T ${rec.QUAD_T.toFixed(3)} GT ${rec.GT_T.toFixed(3)} AA ${rec.ACC_AA.toFixed(3)}`);
  }
  console.log(line.join(' | '));
}
fs.writeFileSync(__dirname + '/power_selfft_supp.json', JSON.stringify(out, null, 1));
