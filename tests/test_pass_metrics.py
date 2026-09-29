import pytest

from tau_emotion.metrics.agent_metrics import pass_at_k, pass_hat_k


@pytest.mark.parametrize(
    "k, expected_at, expected_hat",
    [(1, 1 / 3, 1 / 3), (2, 2 / 3, 0.0), (3, 1.0, 0.0)],
)
def test_one_success_in_three_trials(k, expected_at, expected_hat):
    assert pass_at_k(3, 1, k) == pytest.approx(expected_at)
    assert pass_hat_k(3, 1, k) == pytest.approx(expected_hat)


def test_all_or_nothing():
    assert pass_at_k(3, 3, 2) == pass_hat_k(3, 3, 2) == 1.0
    assert pass_at_k(3, 0, 2) == pass_hat_k(3, 0, 2) == 0.0
