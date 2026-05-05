import unittest

from futufolio import FutuPortfolioClient, RebalanceAction, RebalanceResult


class ApiTests(unittest.TestCase):
    def test_client_set_position_builds_command(self):
        calls = []

        def runner(command):
            calls.append(command)
            return RebalanceResult(command=command, status="done", message="ok")

        result = FutuPortfolioClient(runner=runner).set_position(
            "msft",
            75,
            dry_run=True,
            portfolio_code="pfl0137605",
        )

        self.assertEqual(result.message, "ok")
        self.assertEqual(calls[0].symbol, "MSFT")
        self.assertIs(calls[0].action, RebalanceAction.SET)
        self.assertEqual(calls[0].percent, "75")
        self.assertTrue(calls[0].dry_run)
        self.assertEqual(calls[0].portfolio_code, "PFL0137605")

    def test_client_close_position_builds_command(self):
        calls = []

        def runner(command):
            calls.append(command)
            return RebalanceResult(command=command, status="done", message="ok")

        FutuPortfolioClient(runner=runner).close_position("msft", record=True)
        self.assertIs(calls[0].action, RebalanceAction.CLOSE)
        self.assertTrue(calls[0].record)


if __name__ == "__main__":
    unittest.main()
