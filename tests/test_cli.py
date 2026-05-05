import contextlib
import io
import unittest

from futufolio.cli import main, parse_command
from futufolio.models import RebalanceAction, RebalanceResult


class FakeClient:
    def __init__(self):
        self.commands = []

    def rebalance(self, command):
        self.commands.append(command)
        return RebalanceResult(command=command, status="dry-run", message="fake ok")


class CliTests(unittest.TestCase):
    def test_parse_set_command(self):
        command = parse_command(["msft", "50%", "--dry-run", "--portfolio", "pfl0137605"])
        self.assertEqual(command.symbol, "MSFT")
        self.assertIs(command.action, RebalanceAction.SET)
        self.assertEqual(command.percent, "50")
        self.assertTrue(command.dry_run)
        self.assertEqual(command.portfolio_code, "PFL0137605")

    def test_parse_close_alias_zero(self):
        command = parse_command(["MSFT", "0"])
        self.assertIs(command.action, RebalanceAction.CLOSE)
        self.assertEqual(command.percent, "0")

    def test_main_uses_injected_client_and_prints_result(self):
        client = FakeClient()
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["MSFT", "25"], client=client)
        self.assertEqual(exit_code, 0)
        self.assertEqual(client.commands[0].percent, "25")
        self.assertEqual(stdout.getvalue().strip(), "fake ok")


if __name__ == "__main__":
    unittest.main()
