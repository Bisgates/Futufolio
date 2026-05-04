import unittest

from futu_utils.models import Rect, RebalanceAction, RebalanceCommand, RebalanceResult


class ModelTests(unittest.TestCase):
    def test_rect_properties(self):
        rect = Rect(10, 20, 30, 40)
        self.assertEqual(rect.cx, 25)
        self.assertEqual(rect.cy, 40)
        self.assertEqual(rect.right, 40)
        self.assertEqual(rect.bottom, 60)

    def test_rebalance_command_normalizes_public_inputs(self):
        command = RebalanceCommand(
            symbol=" msft ",
            action="set",
            percent="50%",
            portfolio_code=" pfl0137605 ",
        )
        self.assertEqual(command.symbol, "MSFT")
        self.assertIs(command.action, RebalanceAction.SET)
        self.assertEqual(command.percent, "50")
        self.assertEqual(command.portfolio_code, "PFL0137605")
        self.assertFalse(command.record)

    def test_close_command_forces_zero_percent(self):
        command = RebalanceCommand(symbol="MSFT", action=RebalanceAction.CLOSE, percent="80")
        self.assertEqual(command.percent, "0")

    def test_result_output_lines_put_record_before_message(self):
        command = RebalanceCommand(symbol="MSFT")
        result = RebalanceResult(command=command, status="done", message="Done", record_path=None)
        self.assertEqual(result.output_lines(), ["Done"])


if __name__ == "__main__":
    unittest.main()
