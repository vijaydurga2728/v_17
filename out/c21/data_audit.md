# Cycle 21 data-integrity audit (development data, no strategy execution)

Range audited: XNYS dates 2018-01-01 -> 2024-12-31; context data from 2017-11-01.

| check | NAS100 | SPX | US30 |
|---|---|---|---|
| symbol | USATECHIDXUSD | USA500IDXUSD | USA30IDXUSD |
| files | 120 | 12 | 12 |
| rows | 2471669 | 2471669 | 2471669 |
| validate_m1 | pass | pass | FAIL: crossed quotes (ask_o < bid_o) |
| duplicate_ts | 0 | 0 | 0 |
| nan_prices | 0 | 0 | 0 |
| non_positive_prices | 0 | 0 | 0 |
| crossed_o | 0 | 0 | 48 |
| crossed_h | 0 | 0 | 58 |
| crossed_l | 0 | 0 | 33 |
| crossed_c | 0 | 0 | 47 |
| inconsistent_bid_ohlc | 0 | 0 | 0 |
| inconsistent_ask_ohlc | 0 | 0 | 0 |
| saturday_bars | 0 | 0 | 0 |
| sunday_before_17_bars | 0 | 0 | 0 |
| crossed_bar_ny_dates | [] | [] | ['2020-03-10', '2020-03-11'] |
| crossed_bars_in_0930_1600 | 0 | 0 | 0 |
| window_0930_1105_bars | 176364 | 176364 | 176364 |
| window_bars_identical_to_previous | 965 | 1160 | 1004 |
| first_bar_ny | 2017-11-01 00:00:00-04:00 | 2017-11-01 00:00:00-04:00 |  |
| last_bar_ny | 2024-12-31 16:13:00-05:00 | 2024-12-31 16:13:00-05:00 |  |
| xnys_dates | 1761 | 1761 |  |
| dates_missing_m1_0930_1105 | 0 | 0 |  |
| dates_missing_1559_bar | 9 | 9 |  |
| daily_sessions_not_xnys | 54 | 54 |  |
| asia_range_available_share | 1.0 | 1.0 |  |
| weeks_with_sunday_reopen_bar_share | 0.9890710382513661 | 0.9890710382513661 |  |

## NAS100

- **spread_10_1105**: `{'median': 1.3999999999996362, 'p95': 1.5399999999990541, 'p99': 1.6500000000005457, 'max': 5.311999999999898, 'zero_share': 0.0}`
- **dates_missing_m1_examples**: `[]`
- **dates_no_data_at_all**: `[]`
- **dates_missing_1559_examples**: `['2020-11-27', '2020-12-24', '2021-11-26', '2022-11-25', '2023-07-03', '2023-11-24', '2024-07-03', '2024-11-29', '2024-12-24']`
- **xnys_dates_without_daily_session**: `[]`
- **largest_minute_jumps_0930_1105**: `[(463.51500000000124, '2020-03-16 09:46:00-04:00'), (250.10499999999956, '2020-03-09 09:35:00-04:00'), (31.41700000000128, '2024-07-26 10:00:00-04:00'), (29.904999999999745, '2018-02-14 09:35:00-05:00'), (27.274999999999636, '2023-08-07 10:09:00-04:00')]`
- **rows_per_year**: `{'2017': 57405, '2018': 348435, '2019': 348435, '2020': 345405, '2021': 343992, '2022': 342874, '2023': 341270, '2024': 343853}`

## SPX

- **spread_10_1105**: `{'median': 0.500999999999749, 'p95': 0.5309999999999491, 'p99': 0.7513600000002777, 'max': 2.080000000000382, 'zero_share': 0.0}`
- **dates_missing_m1_examples**: `[]`
- **dates_no_data_at_all**: `[]`
- **dates_missing_1559_examples**: `['2020-11-27', '2020-12-24', '2021-11-26', '2022-11-25', '2023-07-03', '2023-11-24', '2024-07-03', '2024-11-29', '2024-12-24']`
- **xnys_dates_without_daily_session**: `[]`
- **largest_minute_jumps_0930_1105**: `[(179.7470000000003, '2020-03-16 09:45:00-04:00'), (86.94550000000027, '2020-03-09 09:49:00-04:00'), (26.172499999999673, '2020-03-12 09:50:00-04:00'), (25.622999999999593, '2022-10-14 10:00:00-04:00'), (17.754500000000007, '2022-10-24 09:45:00-04:00')]`
- **rows_per_year**: `{'2017': 57405, '2018': 348435, '2019': 348435, '2020': 345405, '2021': 343992, '2022': 342874, '2023': 341270, '2024': 343853}`

## US30

- **spread_10_1105**: `None`
- **dates_missing_m1_examples**: `None`
- **dates_no_data_at_all**: `None`
- **dates_missing_1559_examples**: `None`
- **xnys_dates_without_daily_session**: `None`
- **largest_minute_jumps_0930_1105**: `None`
- **rows_per_year**: `None`

## SMT 5-minute timestamp synchronization (10:00-11:00, share of primary candles matched)

`{'skipped': 'validation failure'}`

## Final exam (2012-2014) M1 availability (paths only, no reads)

`{'NAS100': {'years_on_disk': [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024], 'has_2012_2014': False}, 'SPX': {'years_on_disk': [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], 'has_2012_2014': False}, 'US30': {'years_on_disk': [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], 'has_2012_2014': False}}`
