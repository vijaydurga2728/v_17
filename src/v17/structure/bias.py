from __future__ import annotations

from decimal import Decimal

import pandas as pd

from v17.common.types import TF, Bias, Side
from v17.structure.swings import detect_swings

EMA_PERIOD = 20


def compute_bias_fast(
    ema20_at: Decimal,
    last_close: Decimal,
    last_4h_swing_side: Side | None,
    pdh_pdl_side: Side | None = None,
    require_htf_sweep: bool = False,
) -> Bias:
    """Compute intraday directional bias using ICT multi-confluence doctrine.

    Priority order (ICT doctrine):
      1. 4H market structure is ALWAYS required — no swing → no bias.
      2. If a PDH/PDL liquidity-raid signal exists for today:
           - PDH swept (SELL) + 4H swing SELL → BEAR  (premium short)
           - PDL swept (BUY)  + 4H swing BUY  → BULL  (discount long)
           - Direction mismatch between PDH/PDL and 4H → NONE (conflicting)
      3. Fallback (no PDH/PDL today): original EMA20 + 4H alignment:
           - close > EMA20 AND 4H swing BUY  → BULL
           - close < EMA20 AND 4H swing SELL → BEAR

    Args:
        ema20_at:         Daily EMA20 value at today's open (no lookahead).
        last_close:       Previous daily close (completed bar).
        last_4h_swing_side: Most recent 4H swing direction; None → Bias.NONE.
        pdh_pdl_side:     Liquidity-raid direction from yesterday's sweep;
                          None if no sweep on the prior daily bar.
    """
    if last_4h_swing_side is None:
        return Bias.NONE

    if pdh_pdl_side is not None:
        # PDH/PDL sweep is the PRIMARY directional signal; 4H must confirm.
        if pdh_pdl_side == Side.BUY and last_4h_swing_side == Side.BUY:
            return Bias.BULL
        if pdh_pdl_side == Side.SELL and last_4h_swing_side == Side.SELL:
            return Bias.BEAR
        if require_htf_sweep:
            return Bias.NONE
        # Conflicting PDH/PDL vs 4H: fall through to EMA20 fallback instead
        # of returning NONE. Preserves tradeable days when ICT confluences
        # disagree but EMA20 + 4H still align.

    if require_htf_sweep:
        return Bias.NONE

    # Fallback: original EMA20 price-position + 4H swing alignment.
    daily_bull = last_close > ema20_at
    four_h_bull = last_4h_swing_side == Side.BUY
    if daily_bull and four_h_bull:
        return Bias.BULL
    if (not daily_bull) and (not four_h_bull):
        return Bias.BEAR
    return Bias.NONE


def compute_bias(
    df_1d: pd.DataFrame,
    df_4h: pd.DataFrame,
    pdh_pdl_side: Side | None = None,
    require_htf_sweep: bool = False,
) -> Bias:
    if len(df_1d) < EMA_PERIOD or len(df_4h) < EMA_PERIOD:
        return Bias.NONE
    ema20 = df_1d["close"].ewm(span=EMA_PERIOD, adjust=False).mean()
    last_close = float(df_1d["close"].iloc[-1])
    daily_bull = last_close > float(ema20.iloc[-1])

    swings_4h = detect_swings(df_4h, TF.H4, swing_length=3)
    if not swings_4h:
        return Bias.NONE
    last_4h = swings_4h[-1]
    four_h_bull = last_4h.side == Side.BUY

    if pdh_pdl_side is not None:
        if pdh_pdl_side == Side.BUY and last_4h.side == Side.BUY:
            return Bias.BULL
        if pdh_pdl_side == Side.SELL and last_4h.side == Side.SELL:
            return Bias.BEAR
        if require_htf_sweep:
            return Bias.NONE
        # Mismatch → fall through to EMA20 fallback (not NONE).

    if require_htf_sweep:
        return Bias.NONE

    if daily_bull and four_h_bull:
        return Bias.BULL
    if (not daily_bull) and (not four_h_bull):
        return Bias.BEAR
    return Bias.NONE
