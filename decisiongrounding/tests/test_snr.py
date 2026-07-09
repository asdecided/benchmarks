"""signal_to_noise: SNR = |paired diff_mean| / across-seed diff_std, honestly
gated on >=2 seeds."""

from scoring.snr import signal_to_noise


def _ds(n_seeds, series, key="rac_vs_naive_rag"):
    return {"n_seeds": n_seeds, "paired": {key: series}}


def _e(N, diff_mean, diff_std):
    return {"N": N, "diff_mean": diff_mean, "diff_std": diff_std,
            "diff_ci": [0, 0], "n": 3, "values": []}


def test_snr_is_signal_over_noise():
    ds = _ds(3, [_e(300, 0.40, 0.10)])
    rec = signal_to_noise(ds)["pairs"]["rac_vs_naive_rag"]["by_n"][0]
    assert rec["signal"] == 0.40 and rec["noise"] == 0.10
    assert rec["snr"] == 4.0 and rec["noise_dominated"] is False and rec["flag"] is None


def test_noise_dominated_when_snr_below_one():
    rec = signal_to_noise(_ds(3, [_e(300, 0.05, 0.20)]))["pairs"]["rac_vs_naive_rag"]["by_n"][0]
    assert rec["snr"] == 0.25 and rec["noise_dominated"] is True


def test_single_seed_is_not_estimable():
    rec = signal_to_noise(_ds(1, [_e(300, 0.40, 0.0)]))["pairs"]["rac_vs_naive_rag"]["by_n"][0]
    assert rec["snr"] is None and rec["flag"] == "noise_not_estimable"
    assert rec["noise_dominated"] is False


def test_zero_noise_nonzero_signal_is_clean_separation():
    rec = signal_to_noise(_ds(4, [_e(300, 0.30, 0.0)]))["pairs"]["rac_vs_naive_rag"]["by_n"][0]
    assert rec["snr"] is None and rec["clean_separation"] is True
    assert rec["flag"] == "zero_noise_clean_separation"


def test_zero_noise_zero_signal_is_no_effect():
    rec = signal_to_noise(_ds(4, [_e(300, 0.0, 0.0)]))["pairs"]["rac_vs_naive_rag"]["by_n"][0]
    assert rec["snr"] is None and rec["flag"] == "no_effect"


def test_headline_taken_at_largest_n():
    ds = _ds(3, [_e(10, 0.02, 0.2), _e(300, 0.5, 0.1)])
    pair = signal_to_noise(ds)["pairs"]["rac_vs_naive_rag"]
    assert pair["headline_N"] == 300 and pair["headline"]["snr"] == 5.0


def test_multiple_contrasts_and_missing_paired():
    ds = {"n_seeds": 3, "paired": {
        "rac_vs_naive_rag": [_e(300, 0.4, 0.1)],
        "rac_vs_no_grounding": [_e(300, 0.9, 0.05)],
    }}
    out = signal_to_noise(ds)
    assert set(out["pairs"]) == {"rac_vs_naive_rag", "rac_vs_no_grounding"}
    assert out["pairs"]["rac_vs_no_grounding"]["headline"]["snr"] == 18.0
    # legacy dataset with no paired block -> empty, not an error
    assert signal_to_noise({"n_seeds": 1})["pairs"] == {}
