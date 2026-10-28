"""F07 conservative Garmin transfer-workflow and export compatibility audits.

A validated GPX document does not certify Garmin application conversion,
device transfer, alert behavior, or offline navigation. All checks are offline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from lxml import etree

from .garmin_export import (
    GarminExportError, NavigationExportResult, _geometry,
)
from .interoperability import (
    GPX11_NAMESPACE, GPXDocument, GPXError, GPXSchemaError,
    SchemaRegistry, parse_gpx,
)

_NS = f"{{{GPX11_NAMESPACE}}}"


class GarminVerificationError(ValueError):
    """Reject incorrect verification configuration or source association."""


@dataclass(frozen=True, slots=True)
class GarminCompatibilityOptions:
    """Specify the exact transfer path and required schema evidence."""

    workflow: Literal[
        "explore-web-tracks", "explore-web-routes", "connect-course"
    ] = "explore-web-tracks"
    require_xsd: bool = True

    def __post_init__(self) -> None:
        """Reject unsupported transfer pathways."""
        if self.workflow not in {
            "explore-web-tracks", "explore-web-routes", "connect-course"
        }:
            raise ValueError("Unknown Garmin transfer workflow")
        if type(self.require_xsd) is not bool:
            raise ValueError("require_xsd must be boolean")


@dataclass(frozen=True, slots=True)
class GarminSchemaRegistry:
    """Require locally supplied authoritative schemas; never fetch remotely."""

    gpx11_xsd: Path | None = None
    extensions: dict[str, Path] | None = None

    def as_registry(self) -> SchemaRegistry:
        """Provide F01's GPX schema contract without mutating the registry."""
        return SchemaRegistry(
            gpx11_xsd=self.gpx11_xsd,
            extensions=dict(self.extensions or {}),
        )


@dataclass(frozen=True, slots=True)
class GarminVerificationFinding:
    """Classify a reproducible compatibility or missing-evidence condition."""

    code: str
    severity: Literal["error", "unverified", "info"]
    explanation: str


@dataclass(frozen=True, slots=True)
class GeometryVerificationResult:
    """Compare complete original/navigation tree structures and identities."""

    exact_coordinate_and_segment_match: bool
    exact_waypoint_xml_match: bool
    source_geometry_sha256: str
    exported_geometry_sha256: str
    checkpoint_map_preserved: bool


@dataclass(frozen=True, slots=True)
class TransferCompatibilityResult:
    """Store transfer workflow and explicit known import thresholds."""

    workflow: str
    track_points_limit: int | None
    route_points_limit: int | None
    waypoint_import_limit: int | None
    within_known_limits: bool | None


@dataclass(frozen=True, slots=True)
class GarminCompatibilityResult:
    """Distinguish software validity from physical-device verification."""

    schema_version: str
    device_id: str
    software_status: Literal["incompatible", "unverified", "validated"]
    physical_device_verified: bool
    source_sha256: str
    export_sha256: str
    schema_validated: bool
    geometry: GeometryVerificationResult | None
    transfer: TransferCompatibilityResult
    findings: tuple[GarminVerificationFinding, ...]


def _source_geometry_hash(root) -> str:
    """Fingerprint track/route coordinates and structural boundaries."""
    payload = json.dumps(
        _geometry(root), ensure_ascii=False, separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _waypoint_xml(root) -> tuple[bytes, ...]:
    """Retain all names, comments, metadata and extensions for waypoint audit."""
    return tuple(
        etree.tostring(item, method="c14n")
        for item in root.findall(_NS + "wpt")
    )


def _source_checkpoint_map(root, result):
    """Validate manifest order and identity of mandatory source waypoints."""
    waypoints = root.findall(_NS + "wpt")
    positions = [order for order, _ in result.checkpoints]
    if len(set(positions)) != len(positions):
        return False
    return all(
        type(order) is int and order > 0
        and type(index) is int and 0 <= index < len(waypoints)
        for order, index in result.checkpoints
    ) and tuple(sorted(result.checkpoints)) == result.checkpoints


def _limit_findings(root, workflow):
    """Apply Explore website *import-mode* limits, not device storage limits."""
    findings = []
    tracks = root.findall(_NS + "trk")
    routes = root.findall(_NS + "rte")
    waypoint_count = len(root.findall(_NS + "wpt"))
    if workflow == "connect-course":
        findings.append(GarminVerificationFinding(
            "CONNECT_POINT_LIMIT_UNVERIFIED", "unverified",
            "No verified numerical Connect course import limit is encoded",
        ))
        return TransferCompatibilityResult(
            workflow, None, None, None, None,
        ), findings

    # Explore website converts all imported lines according to the selected
    # import mode. Thus tracks and routes share the *selected* line ceiling.
    point_limit = 10000 if workflow == "explore-web-tracks" else 200
    lines = [
        ("track", index, sum(
            len(segment.findall(_NS + "trkpt"))
            for segment in track.findall(_NS + "trkseg")
        ))
        for index, track in enumerate(tracks)
    ] + [
        ("route", index, len(route.findall(_NS + "rtept")))
        for index, route in enumerate(routes)
    ]
    for kind, index, count in lines:
        if count > point_limit:
            findings.append(GarminVerificationFinding(
                "EXPLORE_LINE_LIMIT_EXCEEDED", "error",
                f"{kind} {index}: {count} points exceeds selected "
                f"Explore website import mode limit {point_limit}",
            ))
    if waypoint_count > 500:
        findings.append(GarminVerificationFinding(
            "EXPLORE_WAYPOINT_IMPORT_LIMIT_EXCEEDED", "error",
            f"{waypoint_count} waypoints exceed Explore website import limit 500",
        ))
    if workflow == "explore-web-routes" and any(
        len(track.findall(_NS + "trkseg")) > 1 for track in tracks
    ):
        findings.append(GarminVerificationFinding(
            "SEGMENT_TO_ROUTE_CONVERSION_UNVERIFIED", "unverified",
            "Explore conversion of multi-segment tracks to routes may alter topology",
        ))
    return TransferCompatibilityResult(
        workflow,
        10000 if workflow == "explore-web-tracks" else 200,
        10000 if workflow == "explore-web-tracks" else 200,
        500,
        not any(f.severity == "error" for f in findings),
    ), findings


def _extension_findings(root, registry):
    """Fail closed on unregistered Garmin/third-party extension namespaces.

    The F01 strict schema implementation validates registered namespaces when
    a local XSD is provided. GPX lax extension allowance alone does not count.
    """
    findings = []
    registered = (registry.extensions or {}) if registry else {}
    seen = set()
    for element in root.iter():
        if not isinstance(element.tag, str):
            continue
        namespace = etree.QName(element).namespace
        if namespace not in {None, GPX11_NAMESPACE}:
            seen.add(namespace)
    for namespace in sorted(seen):
        if namespace not in registered:
            findings.append(GarminVerificationFinding(
                "EXTENSION_SCHEMA_UNAVAILABLE", "error",
                f"No registered local extension schema for {namespace}",
            ))
    return findings


def verify_garmin_export(
    source: GPXDocument,
    exported: NavigationExportResult,
    *,
    options: GarminCompatibilityOptions = GarminCompatibilityOptions(),
    schemas: GarminSchemaRegistry | None = None,
) -> GarminCompatibilityResult:
    """Verify export integrity, geometry, strict XSD and transfer constraints.

    Verification is independent of the exporter, except for using its
    immutable output contract and geometry canonicalization. Incompatible
    bytes are reported, not quietly discarded or rewritten.
    """
    findings = []
    def finding(code, severity, message):
        findings.append(GarminVerificationFinding(code, severity, message))

    source_sha = sha256(source.xml).hexdigest()
    export_sha = sha256(exported.gpx).hexdigest()
    if exported.source_sha256 != source_sha:
        finding("SOURCE_HASH_MISMATCH", "error", "Export references another source")
    if exported.export_sha256 != export_sha:
        finding("EXPORT_HASH_MISMATCH", "error", "Export bytes differ from manifest")

    expected_path = (
        "explore" if exported.profile.device_id == "etrex-se"
        else "connect" if exported.profile.device_id == "instinct-2x-tactical"
        else None
    )
    if expected_path is None or not options.workflow.startswith(expected_path):
        finding("PROFILE_WORKFLOW_MISMATCH", "error",
                "Transfer workflow is incompatible with target device")
    root = None
    geometry = None
    schema_validated = False
    try:
        source_root = source.tree()
        exported_doc = parse_gpx(exported.gpx, strict=False)
        root = exported_doc.tree()
        if root.get("version") != "1.1" or not root.get("creator"):
            finding("GPX_HEADER_INVALID", "error",
                    "Missing GPX 1.1 version or creator attribute")
        source_geo = _source_geometry_hash(source_root)
        output_geo = _source_geometry_hash(root)
        source_waypoints = _waypoint_xml(source_root)
        output_waypoints = _waypoint_xml(root)
        exact_geo = _geometry(source_root) == _geometry(root)
        exact_wpt = source_waypoints == output_waypoints
        checkpoints_valid = _source_checkpoint_map(source_root, exported)
        geometry = GeometryVerificationResult(
            exact_geo, exact_wpt, source_geo, output_geo, checkpoints_valid,
        )
        if not exact_geo or not exact_wpt:
            finding("NAVIGATION_GEOMETRY_OR_WAYPOINT_CHANGED", "error",
                    "Track/route or waypoint XML differs from source")
        if not checkpoints_valid:
            finding("CHECKPOINT_MAP_INVALID", "error",
                    "Manifest checkpoint index/order is inconsistent")
        if (
            exported.audit.geometry_fingerprint != source_geo
            or not exported.audit.exact_geometry_match
        ):
            finding("GEOMETRY_AUDIT_MISMATCH", "error",
                    "Stored geometry audit does not match source")
        findings.extend(_extension_findings(root, schemas))
        if schemas is None or schemas.gpx11_xsd is None:
            finding("GPX_XSD_UNAVAILABLE", "unverified",
                    "No authoritative local GPX 1.1 XSD supplied")
        else:
            try:
                # F01 strict validation applies GPX structural XSD and
                # locally registered extension schema validation.
                parse_gpx(exported.gpx, registry=schemas.as_registry(), strict=True)
                schema_validated = not any(
                    f.code == "EXTENSION_SCHEMA_UNAVAILABLE" for f in findings
                )
            except (GPXSchemaError, GPXError) as exc:
                finding("GPX_XSD_INVALID", "error", str(exc))
    except (GPXError, ValueError, etree.LxmlError) as exc:
        finding("EXPORT_XML_INVALID", "error", str(exc))
    if root is None:
        transfer = TransferCompatibilityResult(
            options.workflow, None, None, None, None,
        )
    else:
        transfer, import_findings = _limit_findings(root, options.workflow)
        findings.extend(import_findings)
    if options.require_xsd and not schema_validated:
        finding("REQUIRED_XSD_NOT_VALIDATED", "error",
                "Strict schema verification is required for this workflow")
    if not any(f.severity == "error" for f in findings):
        status = ("unverified" if any(
            f.severity == "unverified" for f in findings
        ) else "validated")
    else:
        status = "incompatible"
    return GarminCompatibilityResult(
        "1.0.0", exported.profile.device_id, status, False,
        source_sha, export_sha, schema_validated,
        geometry, transfer, tuple(findings),
    )


def garmin_verification_json(result: GarminCompatibilityResult) -> bytes:
    """Produce stable finite-only JSON for local compatibility evidence."""
    return (json.dumps(
        asdict(result), sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(",", ":"),
    ) + "\n").encode("utf-8")
