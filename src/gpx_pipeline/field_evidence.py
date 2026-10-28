"""F10 offline, explicitly observed Garmin field-test evidence records.

No observation is inferred from GPX validation or from a successful transfer.
Records bind operator-supplied observations to immutable exported bytes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
import re


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_OUTCOMES = {"passed", "failed", "unverified"}
_CHECKS = {
    "explore_connect_import", "device_course_present", "course_geometry",
    "mandatory_checkpoints", "offline_navigation", "off_course_alert",
    "independent_backup",
}


@dataclass(frozen=True, slots=True)
class FieldObservation:
    """Store a single human-observed device test and its evidence reference."""

    check: str
    outcome: str
    evidence_reference: str | None
    notes: str = ""

    def __post_init__(self) -> None:
        """Require explicit traceable evidence for any claimed observation."""
        if self.check not in _CHECKS or self.outcome not in _OUTCOMES:
            raise ValueError("Unknown field check or outcome")
        if self.outcome != "unverified" and not self.evidence_reference:
            raise ValueError("Observed field outcomes require evidence reference")
        if self.evidence_reference is not None and not self.evidence_reference.strip():
            raise ValueError("Evidence reference must not be blank")
        if len(self.notes) > 2048 or (
            self.evidence_reference is not None
            and len(self.evidence_reference) > 1024
        ):
            raise ValueError("Field evidence text exceeds size limits")


@dataclass(frozen=True, slots=True)
class FieldEvidenceRecord:
    """Bind measured observations to a specific firmware and GPX export."""

    device_id: str
    firmware: str
    transfer_workflow: str
    source_sha256: str
    export_sha256: str
    observations: tuple[FieldObservation, ...]

    def __post_init__(self) -> None:
        """Forbid ambiguous device identities and unchecked digest values."""
        if self.device_id not in {"etrex-se", "instinct-2x-tactical"}:
            raise ValueError("Unsupported field device")
        if not self.firmware.strip() or len(self.firmware) > 128:
            raise ValueError("Firmware version must be recorded")
        if self.transfer_workflow not in {
            "explore-web-tracks", "explore-web-routes", "connect-course"
        }:
            raise ValueError("Unknown transfer workflow")
        if self.device_id == "etrex-se" and not self.transfer_workflow.startswith(
            "explore"
        ):
            raise ValueError("eTrex requires an Explore workflow")
        if self.device_id == "instinct-2x-tactical" and (
            self.transfer_workflow != "connect-course"
        ):
            raise ValueError("Instinct requires a Connect workflow")
        if not _SHA256.fullmatch(self.source_sha256) or not _SHA256.fullmatch(
            self.export_sha256
        ):
            raise ValueError("Source and export SHA-256 digests are required")
        checks = [item.check for item in self.observations]
        if len(checks) != len(set(checks)):
            raise ValueError("Duplicate field observations")

    def matches(self, source: bytes, exported: bytes) -> bool:
        """Verify recorded file identity without trusting declared digests."""
        return (sha256(source).hexdigest() == self.source_sha256
                and sha256(exported).hexdigest() == self.export_sha256)


def field_evidence_json(record: FieldEvidenceRecord) -> bytes:
    """Serialize a stable field observation record without inferred results."""
    return (json.dumps(
        asdict(record), sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ) + "\n").encode("utf-8")
