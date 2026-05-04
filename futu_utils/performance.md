# Futu Portfolio Performance

## Goal

Measure and keep the real-confirm portfolio update path fast.

The performance target is:

| Scenario | Target |
| --- | ---: |
| Existing holding, same target percent | `< 1s` |
| First build after delete | `< 1s` |

## Default Test Command

Use a real confirm. Do not use `--dry-run` for performance testing.

Rebalance changes are not recorded by default, so the normal timing command is:

```bash
/usr/bin/time -p python3 futu_utils/futu_portfolio.py MSFT 100
```

The success line also prints script-measured elapsed time:

```text
Done: MSFT position set to 100%. Elapsed: 0.78s.
```

If you explicitly test recording overhead, add `--record`; that writes `futu_utils/record.csv`.

## Repeat Test

Do not use repeated builds to measure first-build speed. If a symbol has
already been built once, delete it first, then measure the next build:

```bash
python3 futu_utils/futu_portfolio.py MSFT close
/usr/bin/time -p python3 futu_utils/futu_portfolio.py MSFT 100
```

Use the repeat loop only for the existing-row hot path:

```bash
for i in 1 2 3 4 5; do
  echo "run $i"
  /usr/bin/time -p python3 futu_utils/futu_portfolio.py MSFT 100
done
```

## Latest Local Result

Tested with `MSFT` already present in the Portfolio Manager table.

| Run | Real Time |
| ---: | ---: |
| 1 | `0.88s` |
| 2 | `0.72s` |
| 3 | `0.68s` |
| 4 | `0.68s` |
| 5 | `0.67s` |

Conclusion: the hot path is now below 1 second on the local machine.

## First-Build Result

Measured with the required close-then-build flow:

```bash
python3 futu_utils/futu_portfolio.py MSFT close
/usr/bin/time -p python3 futu_utils/futu_portfolio.py MSFT 100
```

Latest local result:

| Metric | Time |
| --- | ---: |
| Script elapsed output | `0.93s` |
| `/usr/bin/time real` | `0.97s` |

Conclusion: first build after delete is now below 1 second locally.

## What Was Optimized

- Existing-row fast path: if the symbol is already in the right-side portfolio table, the script skips stock search and checkbox selection.
- First-build fast path: after search result stabilization, the script checks only the first result checkbox and clicks the fixed first-row checkbox position.
- Percentage field fast path: after selecting the first result, the script uses the first visible right-table percentage field instead of scanning by symbol.
- Confirm fast path: the script clicks the fixed confirm-button position and keeps the old AX lookup as fallback.
- Direct AX text setting: text fields use `AXValue` assignment first, with clipboard paste kept as fallback.
- Faster window handling: app/window activation avoids AppleScript when Accessibility can make the app frontmost directly.
- Narrower search scan: stock search result lookup scans the left result table instead of the whole manager window.
- Shorter event pauses: mouse/key event delays were reduced while keeping a small pause for UI reliability.

## Notes

- The first-build result assumes the symbol was deleted immediately before the measured build.
- The script verifies the first search-result checkbox title before fixed-position clicking, to avoid selecting a stale/wrong result.
- Actual timing depends on FutuNiuniu UI refresh speed, macOS Accessibility latency, and current machine load.
