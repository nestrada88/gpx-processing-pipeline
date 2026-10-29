"""F10 field-evidence record validation and file-identity regressions.

All observations are synthetic. Passing tests do not certify Garmin field use.
"""

from hashlib import sha256
import json

import pytest

from gpx_pipeline.field_evidence import (
    FieldEvidenceRecord, FieldObservation, field_evidence_json,
)


SOURCE = b"<gpx>synthetic source</gpx>"
EXPORTED = b"<gpx>synthetic navigation export</gpx>"
SOURCE_HASH = sha256(SOURCE).hexdigest()
EXPORT_HASH = sha256(EXPORTED).hexdigest()


def record(**changes):
    """Construct a valid record, overriding only the tested field."""
    values = {
        "device_id": "etrex-se",
        "firmware": "1.0",
        "transfer_workflow": "explore-web-tracks",
        "source_sha256": SOURCE_HASH,
        "export_sha256": EXPORT_HASH,
        "observations": (),
    }
    values.update(changes)
    return FieldEvidenceRecord(**values)


@pytest.mark.parametrize("check", [
    "unknown-check", "", "Offline_navigation",
])
def test_unknown_observation_checks_rejected(check):
    with pytest.raises(ValueError, match="Unknown field check or outcome"):
        FieldObservation(check, "unverified", None)


@pytest.mark.parametrize("outcome", [
    "success", "", "PASS", "observed",
])
def test_unknown_observation_outcomes_rejected(outcome):
    with pytest.raises(ValueError, match="Unknown field check or outcome"):
        FieldObservation("offline_navigation", outcome, None)


@pytest.mark.parametrize("outcome", ["passed", "failed"])
@pytest.mark.parametrize("reference", [None, ""])
def test_observed_outcomes_require_evidence_reference(outcome, reference):
    with pytest.raises(ValueError, match="require evidence reference"):
        FieldObservation("offline_navigation", outcome, reference)


@pytest.mark.parametrize("outcome", ["passed", "failed", "unverified"])
def test_whitespace_only_reference_rejected(outcome):
    with pytest.raises(ValueError, match="must not be blank"):
        FieldObservation("offline_navigation", outcome, "   ")


@pytest.mark.parametrize(
    ("reference_length", "notes_length", "valid"),
    [(1024, 2048, True), (1025, 0, False), (0, 2049, False)],
)
def test_evidence_text_exact_length_boundaries(
    reference_length, notes_length, valid,
):
    reference = "r" * reference_length or None
    if valid:
        observation = FieldObservation(
            "course_geometry", "passed", reference, "n" * notes_length,
        )
        assert len(observation.evidence_reference) == 1024
        assert len(observation.notes) == 2048
    else:
        with pytest.raises(ValueError, match="size limits"):
            FieldObservation(
                "course_geometry", "unverified", reference,
                "n" * notes_length,
            )


@pytest.mark.parametrize("device_id", ["", "etrex", "instinct-2x", "other"])
def test_unknown_device_rejected(device_id):
    with pytest.raises(ValueError, match="Unsupported field device"):
        record(device_id=device_id)


@pytest.mark.parametrize("firmware", ["", " \t ", "x" * 129])
def test_missing_or_oversized_firmware_rejected(firmware):
    with pytest.raises(ValueError, match="Firmware version"):
        record(firmware=firmware)


def test_firmware_exact_limit_accepted():
    assert len(record(firmware="v" * 128).firmware) == 128


@pytest.mark.parametrize("workflow", ["", "connect", "explore-app"])
def test_unknown_transfer_workflow_rejected(workflow):
    with pytest.raises(ValueError, match="Unknown transfer workflow"):
        record(transfer_workflow=workflow)


@pytest.mark.parametrize("workflow", ["explore-web-tracks", "explore-web-routes"])
def test_valid_etrex_workflows_accepted(workflow):
    assert record(transfer_workflow=workflow).device_id == "etrex-se"


def test_etrex_connect_workflow_rejected():
    with pytest.raises(ValueError, match="eTrex requires an Explore"):
        record(transfer_workflow="connect-course")


@pytest.mark.parametrize("workflow", ["explore-web-tracks", "explore-web-routes"])
def test_instinct_explore_workflow_rejected(workflow):
    with pytest.raises(ValueError, match="Instinct requires a Connect"):
        record(device_id="instinct-2x-tactical", transfer_workflow=workflow)


def test_instinct_connect_workflow_accepted():
    assert record(
        device_id="instinct-2x-tactical",
        transfer_workflow="connect-course",
    ).device_id == "instinct-2x-tactical"


@pytest.mark.parametrize("digest", [
    "", "z" * 64, "A" * 64, "f" * 63, "f" * 65, "f" * 63 + "\n",
])
@pytest.mark.parametrize("field", ["source_sha256", "export_sha256"])
def test_invalid_digest_rejected(field, digest):
    with pytest.raises(ValueError, match="SHA-256"):
        record(**{field: digest})


def test_duplicate_observations_rejected():
    observation = FieldObservation("offline_navigation", "unverified", None)
    with pytest.raises(ValueError, match="Duplicate"):
        record(observations=(observation, observation))


def test_file_identity_detects_mutation_of_either_artifact():
    evidence = record()
    assert evidence.matches(SOURCE, EXPORTED)
    assert not evidence.matches(SOURCE + b"altered", EXPORTED)
    assert not evidence.matches(SOURCE, EXPORTED + b"altered")
    assert not evidence.matches(EXPORTED, SOURCE)


def test_deterministic_json_preserves_unverified_status_without_inference():
    evidence = record(observations=(
        FieldObservation("offline_navigation", "unverified", None),
        FieldObservation("course_geometry", "failed", "field-log-01"),
    ))
    first = field_evidence_json(evidence)
    assert first == field_evidence_json(evidence)
    assert first.endswith(b"\n")
    parsed = json.loads(first)
    assert parsed["observations"][0]["outcome"] == "unverified"
    assert parsed["observations"][0]["evidence_reference"] is None
    assert parsed["observations"][1]["outcome"] == "failed"
    assert parsed["source_sha256"] == SOURCE_HASH


def test_empty_observation_tuple_is_allowed_not_a_physical_success():
    evidence = record(observations=())
    assert evidence.observations == ()
    assert json.loads(field_evidence_json(evidence))["observations"] == []
