# Futu Portfolio Rebalance

A focused Python utility for automating **single-symbol** FutuNiuniu portfolio target-weight changes on macOS.

The project intentionally exposes a small public interface and keeps the fragile macOS Accessibility details behind it.

## What This Tool Does

- Opens FutuNiuniu's **Portfolio Manager** window.
- Selects one stock symbol.
- Sets its target position percentage.
- Removes a holding when the target is `close`, `delete`, `remove`, `rm`, or `0`.
- Optionally writes a local CSV record after a confirmed change.

It is **not** a Futu OpenAPI client and does **not** place brokerage orders directly.

## Environment: uv

This project uses `uv` for environment management.

```bash
uv sync
```

For real macOS UI automation, install the PyObjC extra:

```bash
uv sync --extra macos
```

Run checks:

```bash
uv run python -m unittest discover -s tests -v
```

## CLI Usage

Recommended entrypoint:

```bash
uv run futu-portfolio MSFT
uv run futu-portfolio MSFT 100
uv run futu-portfolio MSFT 50
uv run futu-portfolio MSFT close
uv run futu-portfolio MSFT 0
uv run futu-portfolio MSFT --dry-run
uv run futu-portfolio MSFT 100 --record
uv run futu-portfolio MSFT 50 --portfolio PFL0137605
```

Compatibility entrypoints still work:

```bash
python3 futu_portfolio.py MSFT 100
python3 futu_utils/futu_portfolio.py MSFT 100
python3 -m futu_utils MSFT 100
```

You can also set a default portfolio code:

```bash
FUTU_PORTFOLIO_CODE=PFL0137605 uv run futu-portfolio MSFT 50
```

Use `--discard-open-manager` only when a previous dry run or manual edit left Portfolio Manager open and you want the script to close it without saving first.

## Python API

External scripts should use the public API instead of importing UI selector modules.

```python
from futu_utils import FutuPortfolioClient

client = FutuPortfolioClient()
client.set_position("MSFT", 50, portfolio_code="PFL0137605")
client.close_position("MSFT")
```

Command-object style is also supported:

```python
from futu_utils import FutuPortfolioClient, RebalanceAction, RebalanceCommand

command = RebalanceCommand(
    symbol="MSFT",
    action=RebalanceAction.SET,
    percent="50",
    dry_run=True,
)
result = FutuPortfolioClient().rebalance(command)
print(result.message)
```

## Recording

Confirmed operations are **not recorded by default**.

Use `--record` or `record=True` to append:

```text
futu_utils/record.csv
```

Column format:

```csv
日期,时间,股票名称,代码,变化前持仓,变化后持仓,成交价,说明
```

`--dry-run` never writes a record because it does not click final confirm.

## Requirements

- macOS.
- `/Applications/FutuNiuniu.app` installed.
- macOS Accessibility permission granted to the terminal app running Python.
- PyObjC installed through `uv sync --extra macos` for real UI automation.

## Project Structure

```text
futu_portfolio.py          # top-level convenience entrypoint
futu_utils/
  api.py                   # public Python interface
  models.py                # command/result/geometry data models
  cli.py                   # argparse and command rendering
  rebalance.py             # high-level set/remove workflows
  manager_ui.py            # Portfolio Manager selectors
  portfolio_selector.py    # portfolio-code selection helpers
  futu_app.py              # Futu app/window navigation
  ax_utils.py              # Accessibility and input helpers
  pyobjc_runtime.py        # lazy PyObjC loading and permission checks
  recorder.py              # optional record.csv writer
  futu_portfolio.py        # legacy package entrypoint
```

## Safety Notes

- This is GUI automation; Futu UI layout changes can break selectors.
- The script verifies that Portfolio Manager closes after confirm, but it does not verify backend portfolio state through an API.
- Avoid moving/clicking the mouse while the script is running.
- Use `--dry-run` before changing a new symbol or after FutuNiuniu updates.
