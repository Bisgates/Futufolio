# Futu Portfolio Automation Design

## Goal

Automate a repeatable portfolio operation in FutuNiuniu on macOS:

1. Open the Portfolio Manager window.
2. Search for a stock code.
3. Select the exact search result.
4. Set the target position percentage.
5. Confirm the change.
6. Support close/removal by clicking the row's trash icon.
7. Append a rebalance record after successful confirmation.

Primary command examples:

```bash
python3 fabu_utils/futu_portfolio.py MSFT 100
python3 fabu_utils/futu_portfolio.py MSFT close
python3 fabu_utils/futu_portfolio.py MSFT 0
python3 fabu_utils/futu_portfolio.py MSFT 100 --no-record
```

## Scope

This utility controls the FutuNiuniu desktop UI. It is not a Futu OpenAPI client and does not submit brokerage orders directly.

Supported actions:

| Action | Example | Behavior |
| --- | --- | --- |
| Build/default position | `python3 fabu_utils/futu_portfolio.py MSFT` | Set `MSFT` to `100%` |
| Set custom position | `python3 fabu_utils/futu_portfolio.py MSFT 50` | Set `MSFT` to `50%` |
| Close/remove position | `python3 fabu_utils/futu_portfolio.py MSFT close` | Click the row trash icon, then confirm |
| Close/remove alias | `python3 fabu_utils/futu_portfolio.py MSFT 0` | Same as `close`; does not type `0` into the position box |
| Dry run | `python3 fabu_utils/futu_portfolio.py MSFT --dry-run` | Fill/select but do not click final confirm |
| Skip record | `python3 fabu_utils/futu_portfolio.py MSFT 100 --no-record` | Confirm the UI operation but do not append `alpha_second.csv` |

## Rebalance Record

After a successful confirmed operation, the script appends a row to:

```bash
fabu_utils/alpha_second.csv
```

The file uses the same column format as `/Volumes/ssd/us_stock_data/TriggerData/多空.csv`:

```csv
日期,时间,股票名称,代码,变化前持仓,变化后持仓,成交价,说明
```

Record behavior:

- The file is created next to `futu_portfolio.py` if it does not exist.
- `成交价` is left blank because the UI automation flow does not always expose a reliable execution price.
- `--dry-run` never writes a record because it does not click final confirm.
- `--no-record` skips recording.

## Implementation

The script uses macOS Accessibility APIs through PyObjC:

- `ApplicationServices` for Accessibility tree traversal and element actions.
- `Quartz` for reliable mouse and keyboard events.
- `pbcopy` for clipboard-based text input, because Futu's custom fields accept pasted text more reliably than raw key events.

Main UI controls used:

| UI Element | Detection Method |
| --- | --- |
| Portfolio tab | `AXButton` with label/description containing `组合` |
| Portfolio Manager button | `AXButton` containing `组合管理` |
| Manager window | `AXWindow` title `组合管理` |
| Search field | Left-side direct `AXTextField` in the manager window |
| Search result checkbox | Visible `AXCheckBox` whose title matches the stock symbol |
| Position input | Right-side visible `AXTextField` on the selected symbol row |
| Delete/trash icon | Right-side `AXButton` with description `paint_tool_delete` |
| Confirm button | `AXButton` with description `pub_button_default` |

## Close Behavior

Close is intentionally implemented as a row deletion:

1. Open `组合管理`.
2. Locate the current holding row on the right side by exact symbol text.
3. Locate the row's `paint_tool_delete` button.
4. Click the trash icon.
5. Click the confirm button.
6. Verify the manager window closes.

This matches the intended UI behavior and avoids treating `0` as a position percentage.

## Speed Notes

The script avoids scanning the full Accessibility tree when possible, because Futu may expose a long off-screen watchlist on the left side. For close/removal, it scans only the right side of the manager window.

Observed local timings during validation:

- Open/build/confirm flow: about 2 to 3 seconds.
- Close/remove flow after optimization: about 1 second.

Actual timing depends on Futu UI refresh speed and macOS Accessibility response time.

## Requirements

- macOS.
- `/Applications/FutuNiuniu.app` installed.
- Python 3 with PyObjC modules available.
- Accessibility permission granted to the terminal app running the script.

If PyObjC is missing:

```bash
python3 -m pip install pyobjc
```

## Safety and Limitations

- This is GUI automation, so UI layout changes in FutuNiuniu can break selectors.
- The script checks that the manager window closes after confirm, but it does not verify backend portfolio state through an API.
- Avoid moving/clicking the mouse while the script is running.
- Use `--dry-run` before changing a new symbol or after FutuNiuniu updates.
