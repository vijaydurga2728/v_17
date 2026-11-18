# Cycle 21 reproducibility report

- Git HEAD: `ab6a1ce651ef8b844264c0eae28bf19f6f8f26e7` on branch `cycle21-sb-smc-spec`
- Uncommitted changes in cycle 21 paths: `none`
- Spec: `docs/superpowers/specs/2026-11-18-cycle21-sb-smc-spec-v1.md` (frozen in commit `ab6a1ce`)
- Python 3.14.3 (Windows 11)
- Packages: numpy 2.3.4, pandas 2.3.3, pyarrow 25.0.1, pandas_market_calendars 5.6.1
- Tests: `python -m pytest tests/unit/smc_sb -q` -> **39 passed in 5.04s** (exit 0)
- Determinism: no randomness in signal/execution code; the luck test uses `numpy.random.default_rng(seed)` with a fixed per-instrument seed (to be set in the execution pre-registration).

## Configuration (CONFIG_VERSION 21.1.0)

| variant | fingerprint | entry_model | smt_enabled |
|---|---|---|---|
| BASELINE | `92fc41cf3ff3f461` | A | False |
| EXPERIMENT_OTE | `7c64be2196c5a2c7` | B | False |
| EXPERIMENT_SMT | `7c7059f1788054a2` | A | True |

All parameters (baseline):

```
entry_model = 'A'
smt_enabled = False
daily_rollover_hour = 17
window_start = '10:00'
window_end = '11:00'
order_expiry = '11:05'
force_close = '16:00'
asia_start_hour = 20
sweep_refs = ('PD', 'ASIA')
daily_pivot_left = 2
daily_pivot_right = 2
mss_pivot_left = 2
mss_pivot_right = 2
fvg_tf_min = 5
mss_tf_min = 15
ote_low = 0.62
ote_high = 0.79
min_rr = 2.0
slippage_pts = 0.5
commission_pts = 0.0
cost_multiplier = 1.0
data_check_start = '09:30'
null_perms = 5000
```

Instruments: `{'NAS100': 'USATECHIDXUSD', 'SPX': 'USA500IDXUSD', 'US30': 'USA30IDXUSD'}`  SMT partners (experiment only): `{'NAS100': 'SPX', 'SPX': 'NAS100', 'US30': 'SPX'}`

## Data files (SHA-256)

- **NAS100**: 120 files, combined hash `0567d8c91d170700`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=01/data.parquet` `4b1a5b6779511ca5`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=02/data.parquet` `b0901d4fdc293a5c`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=03/data.parquet` `29aecbf36e55f7f9`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=04/data.parquet` `5fd1b4fb246d2168`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=05/data.parquet` `4c0c965e211a94fe`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=06/data.parquet` `01209150d193a0be`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=07/data.parquet` `4a401744eac0eb8a`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=08/data.parquet` `2319cd4663ab3cb1`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=09/data.parquet` `b09fc53a45cc0285`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=10/data.parquet` `1c1444716b66a2e8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=11/data.parquet` `a4b76c01986dd43e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2015/month=12/data.parquet` `65ecdca4eec1a7ad`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=01/data.parquet` `6fe3291c023c2b11`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=02/data.parquet` `c3c9ba54080a6389`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=03/data.parquet` `7608597c1b5bc3b8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=04/data.parquet` `9e7888e38f7f0ea3`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=05/data.parquet` `c4f043babb98d725`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=06/data.parquet` `065594d44fff9c16`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=07/data.parquet` `041ed331a5486484`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=08/data.parquet` `b3add38ca1812a10`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=09/data.parquet` `e11dbd4aef1308ce`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=10/data.parquet` `a8282f9a1230253b`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=11/data.parquet` `1b6a2eeff5b738dc`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2016/month=12/data.parquet` `580c63e03a4bd732`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=01/data.parquet` `eae452812bdb646a`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=02/data.parquet` `713d61c027cecfa3`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=03/data.parquet` `b461ada9d4d4225a`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=04/data.parquet` `805a7d3dc23c7ab2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=05/data.parquet` `efab18e85d189722`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=06/data.parquet` `8ab30621461f59c6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=07/data.parquet` `127b11644406aad1`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=08/data.parquet` `fdc638e60cbc8807`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=09/data.parquet` `b61bd2fb499ad6f2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=10/data.parquet` `540d55e84e48e9b6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=11/data.parquet` `f2c0ba61bec17549`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2017/month=12/data.parquet` `5d9d39bffc32c9c2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=01/data.parquet` `7140ba1fca5202fe`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=02/data.parquet` `92efa4cc14a3dea8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=03/data.parquet` `3be15e9839bb5318`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=04/data.parquet` `13525665528a2954`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=05/data.parquet` `6eaebce1ea679c49`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=06/data.parquet` `87dfa00be9c64827`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=07/data.parquet` `a7ae936c237668b6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=08/data.parquet` `e5467c409b734d43`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=09/data.parquet` `fb97df3988f618fc`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=10/data.parquet` `40acde1e002f80aa`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=11/data.parquet` `a4f8d25b65eccf57`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2018/month=12/data.parquet` `3ce3878dad725ba2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=01/data.parquet` `0c7f0fa6b34f9d33`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=02/data.parquet` `ef6771f9b4ab931e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=03/data.parquet` `539c25a976c2c8d2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=04/data.parquet` `ee28a16289b46462`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=05/data.parquet` `bbb85fb19a5ed9b6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=06/data.parquet` `b954067cd92681c8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=07/data.parquet` `330d4b36f9b52ad4`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=08/data.parquet` `c451b2fb40fcdcf8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=09/data.parquet` `225bbe55eaa4e79e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=10/data.parquet` `ee3b7f1643e0dc60`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=11/data.parquet` `1a51bf8e76d679c0`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2019/month=12/data.parquet` `df80842f871a683b`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=01/data.parquet` `b9d18f8f715aabf7`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=02/data.parquet` `b13525d89d7e25a1`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=03/data.parquet` `76c4fc10d9e38ab7`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=04/data.parquet` `4ea5ec56c38a1af2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=05/data.parquet` `a0679beb7916efb6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=06/data.parquet` `6ddd70be32df62b9`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=07/data.parquet` `365d127f0447ba79`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=08/data.parquet` `83446be8d95cea03`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=09/data.parquet` `4bf070e59140e862`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=10/data.parquet` `51cccac691d48ef6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=11/data.parquet` `4b9497ce29fa7cb5`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2020/month=12/data.parquet` `92ffd8d194229e3c`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=01/data.parquet` `96a7c08881ee5aa3`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=02/data.parquet` `95f8f408b7d82fd3`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=03/data.parquet` `14c7a8a1f669a8dd`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=04/data.parquet` `b0fdee95e9d8331e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=05/data.parquet` `1d09c2504bcc28db`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=06/data.parquet` `6bfdad074ee87595`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=07/data.parquet` `26e9f8471c728ada`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=08/data.parquet` `740f587b11aef829`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=09/data.parquet` `cfa940961afd5f12`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=10/data.parquet` `53ded646487ba38c`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=11/data.parquet` `49c0e7db814c7902`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2021/month=12/data.parquet` `6dbe5897d43472fe`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=01/data.parquet` `d79f4c86445357ff`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=02/data.parquet` `3c669108bdd8b9c2`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=03/data.parquet` `1e5ad5d809c0b863`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=04/data.parquet` `01dc0f2dcbe954f3`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=05/data.parquet` `9e794a6e023d58f0`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=06/data.parquet` `8ae252a70a6c82f8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=07/data.parquet` `0a802bebc02122ca`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=08/data.parquet` `f278c64341d032ce`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=09/data.parquet` `d00954658c5d6c42`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=10/data.parquet` `119333e6975ee23c`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=11/data.parquet` `4f9bcdd4e79538cb`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2022/month=12/data.parquet` `eb8fc211f211c701`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=01/data.parquet` `415493a1b749d234`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=02/data.parquet` `ac4c43e40613a936`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=03/data.parquet` `5dc0a9f9ca41dce8`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=04/data.parquet` `24c96ef1bc8dcb01`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=05/data.parquet` `3d3f2282b3119f18`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=06/data.parquet` `91f9b73e60371db4`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=07/data.parquet` `7ff5b552f1b99966`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=08/data.parquet` `c906d7c2592a136e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=09/data.parquet` `44631117f3dca75f`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=10/data.parquet` `d09e3d01e8d07707`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=11/data.parquet` `f99b25fde18b8af6`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2023/month=12/data.parquet` `e0d38f445e7ac940`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=01/data.parquet` `6cc1ac8e448e543d`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=02/data.parquet` `9e9102d08d223336`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=03/data.parquet` `d977368806975036`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=04/data.parquet` `17ddf9aff2361b85`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=05/data.parquet` `36bccce6d500e25e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=06/data.parquet` `d058a38538c40021`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=07/data.parquet` `9495f82e7c001f2e`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=08/data.parquet` `8a96b54e79456a21`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=09/data.parquet` `148b4851d0b7cdc3`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=10/data.parquet` `7c896e2fc10ef428`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=11/data.parquet` `47e28474807d01b9`
  - `.worktrees/sb-6-engine-gate/data/bars/USATECHIDXUSD/dev/year=2024/month=12/data.parquet` `87abc087babbb991`
- **SPX**: 12 files, combined hash `5dab165628430ed9`
  - `data/bars_m1_paired/USA500IDXUSD/year=2015/part-00.parquet` `1347662ba1fd0da5`
  - `data/bars_m1_paired/USA500IDXUSD/year=2016/part-00.parquet` `bd4028a907e5111f`
  - `data/bars_m1_paired/USA500IDXUSD/year=2017/part-00.parquet` `ade50a5a28a7cb4d`
  - `data/bars_m1_paired/USA500IDXUSD/year=2018/part-00.parquet` `3efcfc1be129bc6c`
  - `data/bars_m1_paired/USA500IDXUSD/year=2019/part-00.parquet` `822ffd229a73bfa6`
  - `data/bars_m1_paired/USA500IDXUSD/year=2020/part-00.parquet` `7b2e47d37dd1becb`
  - `data/bars_m1_paired/USA500IDXUSD/year=2021/part-00.parquet` `86b73e0c3bc1ca7d`
  - `data/bars_m1_paired/USA500IDXUSD/year=2022/part-00.parquet` `ebf25ef79d1e1a0e`
  - `data/bars_m1_paired/USA500IDXUSD/year=2023/part-00.parquet` `1ed1c80f0da02a0e`
  - `data/bars_m1_paired/USA500IDXUSD/year=2024/part-00.parquet` `7fb2bea631342642`
  - `data/bars_m1_paired/USA500IDXUSD/year=2025/part-00.parquet` `2c3e709d19a10389`
  - `data/bars_m1_paired/USA500IDXUSD/year=2026/part-00.parquet` `6b51433dc0943b5a`
- **US30**: 12 files, combined hash `0ad8784de1b9f3ed`
  - `data/bars_m1_paired/USA30IDXUSD/year=2015/part-00.parquet` `39c370a1ec1d8c28`
  - `data/bars_m1_paired/USA30IDXUSD/year=2016/part-00.parquet` `abb865610371596c`
  - `data/bars_m1_paired/USA30IDXUSD/year=2017/part-00.parquet` `55741cf25fa771e7`
  - `data/bars_m1_paired/USA30IDXUSD/year=2018/part-00.parquet` `5fa64abbf00ec57e`
  - `data/bars_m1_paired/USA30IDXUSD/year=2019/part-00.parquet` `18842de7e34c3f2d`
  - `data/bars_m1_paired/USA30IDXUSD/year=2020/part-00.parquet` `99d22f8f43b1dd2b`
  - `data/bars_m1_paired/USA30IDXUSD/year=2021/part-00.parquet` `d9b167c2e14a90d9`
  - `data/bars_m1_paired/USA30IDXUSD/year=2022/part-00.parquet` `4ee0b89d489e9542`
  - `data/bars_m1_paired/USA30IDXUSD/year=2023/part-00.parquet` `dbe94383187c2af1`
  - `data/bars_m1_paired/USA30IDXUSD/year=2024/part-00.parquet` `a2ee966bcec316e6`
  - `data/bars_m1_paired/USA30IDXUSD/year=2025/part-00.parquet` `f529f64c88d0dc99`
  - `data/bars_m1_paired/USA30IDXUSD/year=2026/part-00.parquet` `75ccc4c08de762e7`

## Reproduce

```
python -m pytest tests/unit/smc_sb -q
python scripts/c21_data_audit.py      # writes out/c21/data_audit.{md,json}
python scripts/c21_repro_report.py    # writes this file
```

No strategy run exists yet (execution gate in spec §0).
