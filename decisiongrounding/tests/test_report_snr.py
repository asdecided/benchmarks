"""report.py signal-to-noise + scenario-health sections."""

from scripts.report import _scenario_health_section, _snr_section


def _paired_dataset(n_seeds=3):
    return {
        "n_seeds": n_seeds,
        "paired": {
            "rac_vs_naive_rag": [
                {"N": 10, "diff_mean": 0.02, "diff_std": 0.2, "diff_ci": [0, 0], "n": n_seeds, "values": []},
                {"N": 300, "diff_mean": 0.40, "diff_std": 0.1, "diff_ci": [0, 0], "n": n_seeds, "values": []},
            ],
            "rac_vs_no_grounding": [
                {"N": 300, "diff_mean": 0.90, "diff_std": 0.05, "diff_ci": [0, 0], "n": n_seeds, "values": []},
            ],
        },
    }


def test_snr_section_renders_both_contrasts_and_flags_noise():
    out = "\n".join(_snr_section(_paired_dataset()))
    assert "Signal-to-noise" in out
    assert "`rac` vs `naive_rag`" in out and "`rac` vs `no_grounding`" in out
    assert "4.00" in out          # 0.40 / 0.10
    assert "0.10*" in out         # 0.02 / 0.20 -> noise-dominated, starred
    assert "18.00" in out         # 0.90 / 0.05


def test_snr_section_single_seed_says_not_estimable():
    out = "\n".join(_snr_section(_paired_dataset(n_seeds=1)))
    assert "not estimable" in out
    assert "4.00" not in out


def test_snr_section_absent_without_paired():
    assert _snr_section({"n_seeds": 3}) == []


def test_scenario_health_section_summary_and_flags():
    ds = {"per_scenario": {
        "context_dump": {"good": [{"N": 300, "adherent": 1.0}],
                         "broke": [{"N": 300, "adherent": 0.0}],
                         "contam": [{"N": 300, "adherent": 1.0}]},
        "naive_rag": {"good": [{"N": 300, "adherent": 0.3}],
                      "broke": [{"N": 300, "adherent": 0.0}],
                      "contam": [{"N": 300, "adherent": 1.0}]},
        "no_grounding": {"good": [{"N": 300, "adherent": 0.0}],
                         "broke": [{"N": 300, "adherent": 0.0}],
                         "contam": [{"N": 300, "adherent": 1.0}]},
    }}
    out = "\n".join(_scenario_health_section(ds))
    assert "Scenario health" in out
    assert "1 discriminating" in out and "1 broken" in out and "1 contaminated" in out
    assert "`broke`" in out and "broken" in out
    assert "`contam`" in out


def test_scenario_health_absent_without_per_scenario():
    assert _scenario_health_section({}) == []
