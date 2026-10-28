"""F07 conservative Garmin navigation GPX exports.

This exporter preserves source track/route coordinate tokens, segment structure,
and waypoint identity. Valid GPX bytes are NOT proof of successful transfer or
course fidelity after Garmin Explore/Connect conversion.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Literal

from lxml import etree

from .interoperability import (
    GPX11_NAMESPACE, GPXDocument, GPXSchemaError, SchemaRegistry,
    parse_gpx,
)
from .spatial import validate_spatial
from .waypoints import WaypointCatalog

_NS = f"{{{GPX11_NAMESPACE}}}"
_TOP_LEVEL = ("metadata", "wpt", "rte", "trk", "extensions")
_TRACK = ("name", "cmt", "desc", "src", "link", "number", "type",
          "extensions", "trkseg")
_ROUTE = ("name", "cmt", "desc", "src", "link", "number", "type",
          "extensions", "rtept")
_SEGMENT = ("trkpt", "extensions")
_POINT = ("ele", "time", "magvar", "geoidheight", "name", "cmt", "desc",
          "src", "link", "sym", "type", "fix", "sat", "hdop", "vdop",
          "pdop", "ageofdgpsdata", "dgpsid", "extensions")


class GarminExportError(ValueError):
    """Reject ambiguous or incompatible navigation exports."""


@dataclass(frozen=True, slots=True)
class GarminDeviceProfile:
    """Identify a device without assuming undocumented capacity limits."""

    device_id: str
    product_name: str
    transfer_path: str
    waypoint_limit: int | None


ETREX_SE = GarminDeviceProfile(
    "etrex-se", "Garmin eTrex SE", "Garmin Explore: GPX import to course", 1000
)
INSTINCT_2X_TACTICAL = GarminDeviceProfile(
    "instinct-2x-tactical", "Garmin Instinct 2X Solar Tactical",
    "Garmin Connect: GPX course import", None,
)
_PROFILES = {p.device_id: p for p in (ETREX_SE, INSTINCT_2X_TACTICAL)}


@dataclass(frozen=True, slots=True)
class NavigationExportOptions:
    """Select output target and optional strict schema validation."""

    device_id: Literal["etrex-se", "instinct-2x-tactical"] = "etrex-se"
    require_strict_xsd: bool = False

    def __post_init__(self) -> None:
        """Reject unknown target profiles."""
        if self.device_id not in _PROFILES:
            raise ValueError("Unknown Garmin device profile")


@dataclass(frozen=True, slots=True)
class GarminCompatibilityFinding:
    """Describe validation limitations independently of successful generation."""

    code: str
    severity: str
    explanation: str


@dataclass(frozen=True, slots=True)
class NavigationGeometryAudit:
    """Compare exact source and export geometry tokens and topology."""

    track_count: int
    track_segment_count: int
    trackpoint_count: int
    route_count: int
    routepoint_count: int
    waypoint_count: int
    geometry_fingerprint: str
    exact_geometry_match: bool


@dataclass(frozen=True, slots=True)
class NavigationExportResult:
    """Contain bytes, profile, audit, immutable-source lineage and findings."""

    gpx: bytes
    profile: GarminDeviceProfile
    source_sha256: str
    export_sha256: str
    audit: NavigationGeometryAudit
    checkpoints: tuple[tuple[int, int], ...]
    findings: tuple[GarminCompatibilityFinding, ...]

    def manifest(self) -> bytes:
        """Return deterministic JSON without embedding the GPX payload."""
        payload = asdict(self)
        del payload["gpx"]
        return (json.dumps(
            payload, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"),
        ) + "\n").encode("utf-8")


def _children(element, tag):
    """Enumerate immediate GPX 1.1 children."""
    return element.findall(_NS + tag)


def _geometry(root):
    """Extract immutable coordinate strings and segment boundaries."""
    tracks = tuple(
        tuple(
            tuple((p.get("lat"), p.get("lon")) for p in _children(s, "trkpt"))
            for s in _children(t, "trkseg")
        ) for t in _children(root, "trk")
    )
    routes = tuple(
        tuple((p.get("lat"), p.get("lon")) for p in _children(r, "rtept"))
        for r in _children(root, "rte")
    )
    waypoints = tuple(
        (p.get("lat"), p.get("lon"), p.findtext(_NS + "name"))
        for p in _children(root, "wpt")
    )
    return tracks, routes, waypoints


def _geometry_audit(root, output):
    """Audit original and serialized geometry without float normalization."""
    original = _geometry(root)
    exported = _geometry(output)
    tracks, routes, waypoints = exported
    canonical = json.dumps(original, ensure_ascii=False, separators=(",", ":"))
    return NavigationGeometryAudit(
        track_count=len(tracks),
        track_segment_count=sum(len(track) for track in tracks),
        trackpoint_count=sum(len(segment) for track in tracks
                             for segment in track),
        route_count=len(routes),
        routepoint_count=sum(len(route) for route in routes),
        waypoint_count=len(waypoints),
        geometry_fingerprint=sha256(canonical.encode("utf-8")).hexdigest(),
        exact_geometry_match=original == exported,
    )


def _ordered_children(element, permitted):
    """Fail on unsupported or out-of-order GPX children, not silent stripping."""
    indices = []
    for child in element:
        if not isinstance(child.tag, str):
            raise GarminExportError("Unsupported processing node in GPX")
        if child.tag.startswith(_NS):
            name = child.tag[len(_NS):]
            if name not in permitted:
                raise GarminExportError(f"Unsupported GPX element: {name}")
            indices.append(permitted.index(name))
        else:
            raise GarminExportError("Unregistered extension namespace")
    if indices != sorted(indices):
        raise GarminExportError("Invalid GPX child order")


def _validate_safe_subset(root):
    """Bound output to core GPX 1.1 elements with recognized structure."""
    _ordered_children(root, _TOP_LEVEL)
    for tag in ("wpt", "rtept", "trkpt"):
        for element in root.iter(_NS + tag):
            _ordered_children(element, _POINT)
    for track in _children(root, "trk"):
        _ordered_children(track, _TRACK)
        for segment in _children(track, "trkseg"):
            _ordered_children(segment, _SEGMENT)
    for route in _children(root, "rte"):
        _ordered_children(route, _ROUTE)
    for element in root.iter():
        if isinstance(element.tag, str) and element.tag == _NS + "extensions":
            if len(element):
                raise GarminExportError(
                    "Extensions require a dedicated validated Garmin mapping"
                )
    # Metadata and link structures are not rewritten and must be validated
    # with a supplied GPX XSD before making strict-compliance claims.


def _checkpoint_map(root, catalog):
    """Bind explicit checkpoint order to original source waypoint indices."""
    if catalog is None:
        return ()
    waypoints = _children(root, "wpt")
    if len(catalog.entries) != len(waypoints):
        raise GarminExportError("Waypoint catalog does not match source count")
    orders = []
    for index, (entry, waypoint) in enumerate(zip(catalog.entries, waypoints)):
        if entry.index != index or (
            entry.latitude != float(waypoint.get("lat"))
            or entry.longitude != float(waypoint.get("lon"))
            or entry.name != waypoint.findtext(_NS + "name")
        ):
            raise GarminExportError("Waypoint catalog does not match source")
        if entry.checkpoint_order is not None:
            order = entry.checkpoint_order
            if type(order) is not int or order < 1:
                raise GarminExportError("Invalid checkpoint order")
            orders.append((order, index))
    if len(set(order for order, _ in orders)) != len(orders):
        raise GarminExportError("Duplicate checkpoint order")
    return tuple(sorted(orders))


def export_garmin_navigation(
    source: GPXDocument,
    *,
    options: NavigationExportOptions = NavigationExportOptions(),
    waypoints: WaypointCatalog | None = None,
    registry: SchemaRegistry | None = None,
) -> NavigationExportResult:
    """Create conservative, device-labeled GPX without route conversion.

    Optional strict validation uses locally supplied GPX 1.1 XSD; no network
    schema retrieval or undocumented Garmin extensions are synthesized.
    """
    spatial = validate_spatial(source)
    if not spatial.valid:
        raise GarminExportError("F02 spatial validation failed")
    root = source.tree()
    _validate_safe_subset(root)
    profile = _PROFILES[options.device_id]
    if options.require_strict_xsd and (
        registry is None or registry.gpx11_xsd is None
    ):
        raise GarminExportError("Strict GPX export requires a local GPX 1.1 XSD")
    if registry is not None and registry.gpx11_xsd is not None:
        parse_gpx(source.xml, strict=True, registry=registry)

    original = _geometry(root)
    tracks, routes, wpts = original
    if not any(len(segment) >= 2 for track in tracks for segment in track) and not any(
        len(route) >= 2 for route in routes
    ):
        raise GarminExportError("No navigable track segment or route")
    if profile.waypoint_limit is not None and len(wpts) > profile.waypoint_limit:
        raise GarminExportError("Device waypoint capacity exceeded")
    checkpoint_map = _checkpoint_map(root, waypoints)

    # Retain the entire original GPX 1.1 tree including coordinates, names,
    # comments, original timestamps and legal element order; the device marker
    # changes only the root creator attribute.
    root.set("creator", f"gpx-processing-pipeline/{profile.device_id}")
    serialized = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
    try:
        parsed = parse_gpx(
            serialized, strict=options.require_strict_xsd,
            registry=registry,
        )
    except GPXSchemaError as exc:
        raise GarminExportError("Export GPX schema validation failed") from exc
    exported_root = parsed.tree()
    audit = _geometry_audit(source.tree(), exported_root)
    if not audit.exact_geometry_match:
        raise GarminExportError("Navigation geometry changed during export")
    if not validate_spatial(parsed).valid:
        raise GarminExportError("Export spatial validation failed")
    findings = [
        GarminCompatibilityFinding(
            "DEVICE_TRANSFER_UNVERIFIED", "verification_required",
            "Garmin Explore/Connect import and device course fidelity must be tested",
        ),
        GarminCompatibilityFinding(
            "COURSE_CONVERSION_UNVERIFIED", "verification_required",
            "Source GPX tracks/routes may be transformed by Garmin software",
        ),
        GarminCompatibilityFinding(
            "NAVIGATION_ALERTS_UNVERIFIED", "verification_required",
            "GPX export does not guarantee off-course or waypoint alerts",
        ),
    ]
    if not options.require_strict_xsd:
        findings.append(GarminCompatibilityFinding(
            "XSD_NOT_VERIFIED", "verification_required",
            "No local GPX 1.1 XSD verification requested",
        ))
    if profile.waypoint_limit is None:
        findings.append(GarminCompatibilityFinding(
            "WAYPOINT_LIMIT_UNKNOWN", "informational",
            "Exact device waypoint capacity was not asserted",
        ))
    return NavigationExportResult(
        gpx=serialized, profile=profile,
        source_sha256=sha256(source.xml).hexdigest(),
        export_sha256=sha256(serialized).hexdigest(),
        audit=audit,
        checkpoints=checkpoint_map,
        findings=tuple(findings),
    )


def export_garmin_pair(
    source: GPXDocument,
    *,
    waypoints: WaypointCatalog | None = None,
    registry: SchemaRegistry | None = None,
    require_strict_xsd: bool = False,
) -> tuple[NavigationExportResult, NavigationExportResult]:
    """Produce two independently labeled device exports from one source."""
    return tuple(
        export_garmin_navigation(
            source,
            options=NavigationExportOptions(
                device_id=profile.device_id,
                require_strict_xsd=require_strict_xsd,
            ),
            waypoints=waypoints,
            registry=registry,
        )
        for profile in (ETREX_SE, INSTINCT_2X_TACTICAL)
    )
