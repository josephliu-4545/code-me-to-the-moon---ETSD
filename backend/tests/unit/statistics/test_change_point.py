import pytest

from app.statistics.change_point import detect_step, pettitt

YEARS = list(range(2001, 2025))
NOISE = [0.12, -0.08, 0.15, -0.11, 0.03, -0.14, 0.09, -0.02, 0.06, -0.13, 0.1, -0.05,
         0.14, -0.09, 0.01, -0.12, 0.08, -0.03, 0.11, -0.07, 0.04, -0.1, 0.13, -0.06]


def test_pettitt_hand_computed() -> None:
    # Ranks 1,2,3,4,5,6 with the low half first: U peaks after index 2 at |2*6 - 3*7| = 9.
    k, u, p = pettitt([1.0, 2.0, 3.0, 10.0, 11.0, 12.0])
    assert (k, u) == (2, 9)
    assert p == pytest.approx(2 * 2.718281828459045 ** (-6 * 81 / (216 + 36)))


def test_step_is_detected_at_the_right_year() -> None:
    values = [29.0 + n if year <= 2007 else 27.5 + n for year, n in zip(YEARS, NOISE)]
    result = detect_step(YEARS, values)
    assert result["status"] == "step_detected"
    assert (result["last_year_before"], result["first_year_after"]) == (2007, 2008)
    assert result["shift"] == pytest.approx(-1.5, abs=0.15)


def test_smooth_trend_is_not_called_a_step() -> None:
    values = [20 + 0.05 * (year - 2001) + n / 10 for year, n in zip(YEARS, NOISE)]
    result = detect_step(YEARS, values)
    assert result["pettitt_p_value"] < 0.05  # Pettitt alone reacts to a monotonic trend
    assert result["step_fits_better_than_line"] is False
    assert result["status"] == "none"


def test_noise_has_no_step_and_short_series_is_not_tested() -> None:
    assert detect_step(YEARS, [20 + n for n in NOISE])["status"] == "none"
    assert detect_step(YEARS[:5], NOISE[:5])["status"] == "not_tested"
