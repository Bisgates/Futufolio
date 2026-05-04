# alpha_second_v3

Utilities for Alpha Second workflows.

## Futu Portfolio Automation

The current utility automates FutuNiuniu portfolio position management on macOS.

Script:

```bash
fabu_utils/futu_portfolio.py
```

Examples:

```bash
python3 fabu_utils/futu_portfolio.py MSFT
python3 fabu_utils/futu_portfolio.py MSFT 100
python3 fabu_utils/futu_portfolio.py MSFT 50
python3 fabu_utils/futu_portfolio.py MSFT close
python3 fabu_utils/futu_portfolio.py MSFT 0
python3 fabu_utils/futu_portfolio.py MSFT --dry-run
python3 fabu_utils/futu_portfolio.py MSFT 100 --no-record
python3 fabu_utils/futu_portfolio.py MSFT 50 --portfolio PFL0137605
FUTU_PORTFOLIO_CODE=PFL0137605 python3 fabu_utils/futu_portfolio.py MSFT 50
python3 fabu_utils/futu_portfolio.py MSFT 50 --portfolio PFL0137605 --discard-open-manager
```

Notes:

- `close` and `0` remove the holding by clicking the trash icon, not by setting the position input to zero.
- Use `--portfolio PFL0137605` to select a specific Futu portfolio before opening Portfolio Manager.
- You can also set `FUTU_PORTFOLIO_CODE=PFL0137605` instead of passing `--portfolio` every time.
- Use `--discard-open-manager` only when a previous dry run or manual edit left Portfolio Manager open and you want the script to close it without saving first.
- After a successful confirmed change, the script appends a record to `fabu_utils/alpha_second.csv`.
- Use `--no-record` to skip writing the record file.
- The script uses macOS Accessibility UI automation.
- It requires FutuNiuniu to be installed at `/Applications/FutuNiuniu.app`.
- macOS Accessibility permission must be granted to the terminal app running Python.
