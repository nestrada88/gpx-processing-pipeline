"""F10 deterministic field-readiness limits for independent Garmin devices.

These are conservative pre-transfer checks: passing them does not establish
on-device course conversion, geometry fidelity, or navigation functionality.
"""

from __future__ import annotations

from dataclasses import dataclass

from .garmin_export import NavigationExportResult
from .interoperability import GPX11_NAMESPACE, GPXDocument


_NS = f"{{{GPX11_NAMESPACE}}}"
ETREX_SE_COURSE_POINT_LIMIT = 200
ETREX_SE_STORED_COURSE_LIMIT = 50


@dataclass(frozen=True, slots=True)
class OperationalFinding:
    """Describe a known device constraint or missing verification evidence."""

    code: str
    severity: str
    detail: str


@dataclass(frozen=True, slots=True)
class OperationalReadiness:
    """Distinguish machine-checkable safety from physical-device observations."""

    device_id: str
    software_compatible: bool
    physical_transfer_verified: bool
    physical_navigation_verified: bool
    findings: tuple[OperationalFinding, ...]


def verify_device_readiness(
    source: GPXDocument,
    exported: NavigationExportResult,
) -> OperationalReadiness:
    """Check documented device course limits without altering source geometry.

    eTrex SE uses courses rather than track navigation. A point count that
    fits Explore's track import limit can still exceed the 200-point course
    capacity of the eTrex SE. This check fails closed to prevent silent
    simplification being interpreted as source-fidelity.
    """
    root = source.tree()
    findings: list[OperationalFinding] = []
    if exported.profile.device_id == "etrex-se":
        tracks = root.findall(_NS + "trk")
        routes = root.findall(_NS + "rte")
        lines = [
            ("track", i, sum(
                len(segment.findall(_NS + "trkpt"))
                for segment in trk.findall(_NS + "trkseg")
            ))
            for i, trk in enumerate(tracks)
        ]
        lines.extend(
            ("route", i, len(rte.findall(_NS + "rtept")))
            for i, rte in enumerate(routes)
        )
        if len(lines) > ETREX_SE_STORED_COURSE_LIMIT:
            findings.append(OperationalFinding(
                "ETREX_COURSE_COUNT_EXCEEDED", "error",
                f"{len(lines)} source lines exceed the device's "
                f"{ETREX_SE_STORED_COURSE_LIMIT} stored-course ceiling",
            ))
        for kind, i, count in lines:
            if count > ETREX_SE_COURSE_POINT_LIMIT:
                findings.append(OperationalFinding(
                    "ETREX_COURSE_POINT_LIMIT_EXCEEDED", "error",
                    f"{kind} {i}: {count} points exceed the device's "
                    f"{ETREX_SE_COURSE_POINT_LIMIT} points-per-course limit",
                ))
        if any(len(trk.findall(_NS + "trkseg")) > 1 for trk in tracks):
            findings.append(OperationalFinding(
                "ETREX_SEGMENT_CONVERSION_UNVERIFIED", "unverified",
                "Explore may alter separate track-segment topology "
                "when converting to a course",
            ))
    elif exported.profile.device_id == "instinct-2x-tactical":
        findings.append(OperationalFinding(
            "INSTINCT_COURSE_LIMIT_UNVERIFIED", "unverified",
            "No reliable fixed course-point limit established for this model",
        ))
    else:
        findings.append(OperationalFinding(
            "UNKNOWN_DEVICE", "error", "Unrecognized Garmin device profile",
        ))
    findings.append(OperationalFinding(
        "FIELD_DEVICE_TEST_UNVERIFIED", "unverified",
        "Course import, offline navigation and alerts require measured evidence",
    ))
    return OperationalReadiness(
        exported.profile.device_id,
        not any(f.severity == "error" for f in findings),
        False, False, tuple(findings),
    )
