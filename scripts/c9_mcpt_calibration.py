"""ADR 002 Appendix A: calibration of sequential (Besag-Clifford h/m) vs fixed-count MCPT p-values.

Pure simulation of exceedance counts; reads no market data. Seed 20261117.
"""
import numpy as np
rng = np.random.default_rng(20261117)
H, NMAX, A = 50, 100_000, 0.05
def bc_p(q):
    # trials until H-th exceedance ~ H + NegBin(H, q) failures
    m = H + rng.negative_binomial(H, q) if q > 0 else 10**12
    if m <= NMAX: return H / m
    e = rng.binomial(NMAX, q); return (e + 1) / (NMAX + 1)
def fixed_p(q): return (rng.binomial(NMAX, q) + 1) / (NMAX + 1)
R = 200_000
U = rng.random(R)            # under H0 the observed stat's exceedance prob q ~ Uniform(0,1)
bc = np.array([bc_p(q) for q in U]); fx = np.array([fixed_p(q) for q in U])
for a in (0.05, 0.01, 0.05/132):
    print(f"H0 type-I @alpha={a:.6f}: BC={np.mean(bc<=a):.5f}  fixed={np.mean(fx<=a):.5f}  (nominal {a:.5f})")
q = 0.05
bcb = np.array([bc_p(q) for _ in range(20_000)]); fxb = np.array([fixed_p(q) for _ in range(20_000)])
print(f"Boundary q=0.05 (conditional, NOT type-I): P(p<=0.05) BC={np.mean(bcb<=A):.3f} fixed={np.mean(fxb<=A):.3f}")
