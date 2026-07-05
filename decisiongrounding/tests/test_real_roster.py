"""The study-grade scenario roster is pinned.

The pre-registered analysis plan (spec/analysis-plan-amendment-1.md) freezes
the exact scenarios_real roster so no post-hoc scenario selection is possible:
adding, removing, or renaming a real scenario must change this list — and the
amendment — deliberately, in review.
"""

from pathlib import Path

_REAL_DIR = Path(__file__).resolve().parent.parent / "scenarios_real"

# 49 scenarios: 24 PEP (19 supersessions, 2 prohibitions, 3 negative
# controls), 21 RFC (12 supersessions, 7 prohibitions, 2 negative controls),
# 4 W3C edition supersessions. Frozen by the analysis-plan amendment; edit
# both together or not at all.
PINNED_ROSTER = frozenset({
    "pep8_none_identity_prohibition",
    "peps_annotations_supersession",
    "peps_dbapi_supersession",
    "peps_dict_version_supersession",
    "peps_enum_supersession",
    "peps_exception_context_supersession",
    "peps_fd_inheritance_supersession",
    "peps_backcompat_policy_supersession",
    "peps_local_version_prohibition",
    "peps_manylinux_supersession",
    "peps_metadata_supersession",
    "peps_finally_exit_supersession",
    "peps_micro_release_supersession",
    "peps_pattern_matching_supersession",
    "peps_pypi_hosting_supersession",
    "peps_script_deps_supersession",
    "peps_string_interpolation_supersession",
    "peps_style_negative_control",
    "peps_subinterpreters_supersession",
    "peps_timezone_supersession",
    "peps_typing_negative_control",
    "peps_version_supersession",
    "peps_wsgi_supersession",
    "peps_zen_negative_control",
    "rfc_content_length_te_prohibition",
    "rfc_cookies_supersession",
    "rfc_date_header_prohibition",
    "rfc_email_format_supersession",
    "rfc_http_messaging_supersession",
    "rfc_http_semantics_supersession",
    "rfc_imap_supersession",
    "rfc_json_bom_prohibition",
    "rfc_json_supersession",
    "rfc_keywords_negative_control",
    "rfc_language_tags_supersession",
    "rfc_md5_prohibition",
    "rfc_ntp_supersession",
    "rfc_rc4_prohibition",
    "rfc_smtp_supersession",
    "rfc_sslv3_prohibition",
    "rfc_timestamps_negative_control",
    "rfc_tls_identity_supersession",
    "rfc_tls_legacy_prohibition",
    "rfc_tls_version_supersession",
    "rfc_uri_supersession",
    "w3c_xhtml_edition_supersession",
    "w3c_xml_edition_supersession",
    "w3c_xml_names_edition_supersession",
    "w3c_xpath_edition_supersession",
})


def _on_disk() -> frozenset[str]:
    return frozenset(
        d.name for d in _REAL_DIR.iterdir()
        if d.is_dir() and (d / "scenario.json").is_file()
    )


def test_roster_matches_the_pinned_list():
    on_disk = _on_disk()
    assert on_disk == PINNED_ROSTER, (
        f"scenarios_real drifted from the pinned roster: "
        f"added={sorted(on_disk - PINNED_ROSTER)}, "
        f"removed={sorted(PINNED_ROSTER - on_disk)}. "
        "Update spec/analysis-plan-amendment-1.md and this pin together."
    )


def test_roster_count():
    assert len(PINNED_ROSTER) == 49


def test_negative_controls_present():
    """The frozen taxonomy calls negative controls mandatory; the real roster
    must carry them (they feed base-N stats and the false-prohibit rate)."""
    controls = {name for name in PINNED_ROSTER if name.endswith("_negative_control")}
    assert len(controls) == 5
