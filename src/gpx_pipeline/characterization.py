"""S01-CHR v1.0.0: non-destructive, streaming GPX input characterization.

This is a separate admission path. The stricter F08 production export validator
is deliberately unchanged. Characterization evaluates *eligibility*, not the
outcome of temporal, kinematic, geographic or sensor-quality validation.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from datetime import datetime
from hashlib import sha256
from math import isfinite
from io import BytesIO
from pathlib import Path
from functools import lru_cache
import json
import re

from lxml import etree

from .interoperability import GPX11_NAMESPACE, GPXLimits
from .production_schemas import _compile_schemas

GPX = f"{{{GPX11_NAMESPACE}}}"
PROFILES = tuple(f"GPX-{number:02}" for number in range(1, 6))
FIELDS = ("ele", "time", "hr", "cad", "atemp", "name", "fix", "sat",
          "hdop", "vdop", "pdop", "geoidheight")
SENSORS = ("hr", "cad", "atemp")
STRUCTURAL = {"gpx", "trk", "trkseg", "trkpt", "rte", "rtept", "wpt", "extensions"}
TPX = {f"http://www.garmin.com/xmlschemas/TrackPointExtension/v{v}" for v in (1, 2)}
SENSOR_ELEMENT = {"hr": "hr", "cad": "cad", "atemp": "atemp"}
XML_DECL = re.compile(br"^\s*<\?xml\s+[^?]*encoding\s*=\s*['\"]([^'\"]+)['\"]", re.I)


@lru_cache(maxsize=1)
def _schemas():
    """Compile and integrity-check bundled offline GPX/Garmin schemas."""
    return _compile_schemas()


@contextmanager
def _stream(source: bytes | Path):
    if isinstance(source, bytes):
        yield BytesIO(source)
    else:
        with Path(source).open("rb") as handle:
            yield handle


def _source_identity(source: bytes | Path, limits: GPXLimits):
    """Digest a path in constant memory, before any XML interpretation."""
    digest = sha256()
    size = 0
    prefix = b""
    with _stream(source) as handle:
        for block in iter(lambda: handle.read(65536), b""):
            if not prefix:
                prefix = block[:4096]
            size += len(block)
            if size > limits.max_bytes:
                # Do not continue consuming an oversize source.
                return None, size, prefix
            digest.update(block)
    return digest.hexdigest(), size, prefix


def _source_record(digest, size, prefix):
    declared_match = XML_DECL.search(prefix)
    declared = declared_match.group(1).decode("ascii", "replace") if declared_match else None
    effective = ("UTF-16" if prefix.startswith((b"\xff\xfe", b"\xfe\xff"))
                 else "UTF-8" if prefix.startswith(b"\xef\xbb\xbf") else declared or "UTF-8")
    return dict(source_sha256=digest, bytes=size, encoding_declared=declared,
                encoding_effective=effective, namespace_uri=None,
                gpx_version=None, creator=None)


def _coverage(eligible=0, present=0, valid=None):
    if valid is None:
        valid = present
    if not 0 <= valid <= present <= eligible:
        raise ValueError("coverage count invariant violated")
    status = ("NOT_APPLICABLE" if not eligible else "ABSENT" if not present
              else "COMPLETE" if valid == eligible else "INVALID" if valid != present
              else "PARTIAL")
    return dict(eligible=eligible, present=present, valid=valid,
                ratio=valid / eligible if eligible else None, status=status, evidence=[])


def _coverage_map(points):
    n = len(points) if isinstance(points, list) else points["points"]
    if isinstance(points, list):
        counts = Counter(f for point in points for f in point["fields"])
    else:
        counts = points["counts"]
    return {f: _coverage(n, counts[f]) for f in FIELDS}


def _point(element):
    """Inspect one native point; do not retain its XML tree."""
    fields = set()
    try:
        lat, lon = float(element.get("lat")), float(element.get("lon"))
    except (ValueError, TypeError) as exc:
        raise _CoreInvalid("point latitude/longitude not numeric") from exc
    if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon < 180:
        raise _CoreInvalid("point coordinate outside GPX bounds")
    data = {"coords": (lat, lon)}
    for child in element:
        if not isinstance(child.tag, str):
            continue
        q = etree.QName(child)
        if q.namespace == GPX11_NAMESPACE and q.localname in FIELDS:
            fields.add(q.localname)
            if q.localname == "time":
                value = (child.text or "").strip()
                try:
                    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    data["time"] = parsed if parsed.tzinfo is not None else None
                    data["time_precision_digits"] = len(re.search(r"T\d{2}:\d{2}:\d{2}\.(\d+)", value).group(1)) if re.search(r"T\d{2}:\d{2}:\d{2}\.(\d+)", value) else 0
                    data["time_timezone_known"] = parsed.tzinfo is not None
                except ValueError:
                    data["time"] = None
        if q.namespace == GPX11_NAMESPACE and q.localname == "extensions":
            for vendor in child.iterdescendants():
                if isinstance(vendor.tag, str):
                    name = etree.QName(vendor)
                    if name.namespace in TPX and name.localname in SENSOR_ELEMENT:
                        fields.add(name.localname)
    data["fields"] = fields
    return data


def _new_feature(kind, number):
    return dict(kind=kind, index=number, name=None, points=0, segments=0,
                counts=Counter(), usable_pairs=0, elevation_pairs=0,
                time_pairs=0, timed_geo_pairs=0, triples=0, last=None, last2=None,
                contains_crossing=False, min_lat=None, max_lat=None,
                min_lon=None, max_lon=None, min_time=None, max_time=None,
                precision_digits=set(), unknown_zone_count=0, segment_sizes=[])


def _append_point(feature, point):
    feature["points"] += 1
    feature["counts"].update(point["fields"])
    lat, lon = point["coords"]
    for key, value in (("lat", lat), ("lon", lon)):
        lo, hi = "min_" + key, "max_" + key
        feature[lo] = value if feature[lo] is None else min(feature[lo], value)
        feature[hi] = value if feature[hi] is None else max(feature[hi], value)
    if "time" in point["fields"]:
        feature["precision_digits"].add(point.get("time_precision_digits", 0))
        if point.get("time") is None:
            feature["unknown_zone_count"] += 1
        else:
            time = point["time"]
            feature["min_time"] = time if feature["min_time"] is None else min(feature["min_time"], time)
            feature["max_time"] = time if feature["max_time"] is None else max(feature["max_time"], time)
    previous = feature["last"]
    if previous is not None:
        valid_edge = previous["coords"] != point["coords"]
        if valid_edge:
            feature["usable_pairs"] += 1
        if valid_edge and "ele" in previous["fields"] and "ele" in point["fields"]:
            feature["elevation_pairs"] += 1
        if previous.get("time") is not None and point.get("time") is not None:
            feature["time_pairs"] += 1
            if valid_edge:
                feature["timed_geo_pairs"] += 1
        if abs(previous["coords"][1] - point["coords"][1]) > 180:
            feature["contains_crossing"] = True
    if feature["last2"] is not None and all(
            p.get("time") is not None for p in (feature["last2"], previous, point)):
        feature["triples"] += 1
    feature["last2"], feature["last"] = previous, point


def _matches(f, global_state):
    usable = f["usable_pairs"] > 0
    n, c = f["points"], f["counts"]
    ele_full, time_full = c["ele"] == n, c["time"] == n
    named = bool(f["name"])
    sensors = any(c[x] for x in SENSORS)
    no_global_private = not any(global_state[x] for x in (
        "metadata_present", "any_core_name", "any_core_time", "extension_content"))
    no_optional = not global_state["optional_content"]
    result = []
    for profile in PROFILES:
        status = "NO_MATCH"
        if usable:
            if profile == "GPX-01":
                if ele_full and time_full and all(c[x] for x in SENSORS):
                    status = "MATCH"
                elif c["ele"] or c["time"] or sensors:
                    status = "PARTIAL"
            elif profile == "GPX-02" and not (c["time"] or sensors):
                status = "MATCH" if ele_full and named else "PARTIAL" if c["ele"] or named else "NO_MATCH"
            elif profile == "GPX-03" and not (c["time"] or c["ele"] or sensors):
                status = "MATCH" if named else "PARTIAL"
            elif profile == "GPX-04" and no_global_private:
                status = "MATCH" if ele_full else "PARTIAL" if c["ele"] else "NO_MATCH"
            elif profile == "GPX-05" and no_optional:
                status = "MATCH"
        result.append(dict(profile=profile, result=status,
                           reasons=[] if status == "MATCH" else [
                               "NO_USABLE_LINE" if not usable else "FIELD_PATTERN_MISMATCH"]))
    return result


def _classify(features, declared):
    active = [f for f in features if f["has_usable_line"]]
    exact = [{m["profile"] for m in f["matches"] if m["result"] == "MATCH"} for f in active]
    partial = [{m["profile"] for m in f["matches"] if m["result"] == "PARTIAL"} for f in active]
    candidates = sorted(set().union(*(x or y for x, y in zip(exact, partial)))) if active else []
    statuses = ["AMBIGUOUS" if len(x or y) > 1 else "UNCLASSIFIED" if not x else "SINGLE"
                for x, y in zip(exact, partial)]
    if not active or "UNCLASSIFIED" in statuses:
        status = "UNCLASSIFIED"
    elif "AMBIGUOUS" in statuses:
        status = "AMBIGUOUS"
    elif len(set(next(iter(x)) for x in exact)) > 1:
        status = "MIXED"
    else:
        status = "SINGLE"
    resolved = next(iter(exact[0])) if status == "SINGLE" else None
    if declared and (not active or any(declared not in matches for matches in exact)):
        status, resolved = "DECLARED_CONFLICT", None
    return dict(status=status, resolved_profile=resolved,
                declared_profile=declared, intent_basis="DECLARED" if declared else "UNKNOWN",
                candidate_profiles=candidates, reasons=[] if status == "SINGLE" else [status])


def _capability(state, scope, prereqs=(), evidence=()):
    return dict(state=state, scope=scope, prerequisites=list(prereqs), evidence=list(evidence))


def _capabilities(features, unknown_extensions):
    result = {}
    states = ("horizontal_line", "elevation_profile", "grade", "temporal_L3",
              "kinematic_L4", "acceleration", "vertical_reference_assessment",
              "geometric_spatial_overlay")
    for f in features:
        fid, n = f["feature_id"], f["point_count"]
        c = f["coverage"]
        usable = f["has_usable_line"]
        def put(name, state, prereqs=()):
            result[f"{fid}:{name}"] = _capability(state, fid, prereqs,
                                                      (f"{n} primary points",))
        put("horizontal_line", "ELIGIBLE_FOR_VALIDATION" if usable else "UNAVAILABLE",
            () if usable else ("two consecutive distinct points in one segment",))
        elevpairs = f["_elevation_pairs"]
        elstate = "UNAVAILABLE" if not elevpairs else (
            "ELIGIBLE_FOR_VALIDATION" if c["ele"]["status"] == "COMPLETE" else "PARTIALLY_ELIGIBLE")
        put("elevation_profile", elstate, () if elevpairs else ("valid adjacent elevation pair",))
        put("grade", elstate if elevpairs else "UNAVAILABLE",
            () if elevpairs else ("positive-distance elevation pair",))
        timedpairs = f["_time_pairs"]
        tstate = "UNAVAILABLE" if not timedpairs else (
            "ELIGIBLE_FOR_VALIDATION" if c["time"]["status"] == "COMPLETE" else "PARTIALLY_ELIGIBLE")
        put("temporal_L3", tstate, () if timedpairs else ("adjacent comparable timestamps",))
        put("kinematic_L4", tstate if f["_timed_geo_pairs"] else "UNAVAILABLE",
            ("L3 positive elapsed-time validation remains pending",) if f["_timed_geo_pairs"] else ("timed distinct-coordinate pair",))
        put("acceleration", "ELIGIBLE_FOR_VALIDATION" if f["_triples"] else "UNAVAILABLE",
            () if f["_triples"] else ("three adjacent time-comparable points",))
        put("vertical_reference_assessment", "INDETERMINATE" if c["ele"]["present"] else "UNAVAILABLE",
            ("documented elevation reference",))
        put("geometric_spatial_overlay", "PARTIALLY_ELIGIBLE" if usable else "UNAVAILABLE",
            ("external overlay layer",))
        for sensor in SENSORS:
            put("sensor:"+sensor, "ELIGIBLE_FOR_VALIDATION" if c[sensor]["valid"] else
                "INDETERMINATE" if unknown_extensions else "UNAVAILABLE",
                () if c[sensor]["valid"] else ("recognized telemetry",))
    return result


def _failure(report, code, requirement, admission_field, evidence):
    report["report_kind"] = "ADMISSION_FAILURE"
    report["admission"][admission_field] = "FAIL"
    report["diagnostics"] = [dict(code=code, requirement_id=requirement,
                                  severity="ERROR", location=None,
                                  evidence=[str(evidence)[:240]])]
    return report


def characterize_gpx(source: bytes | Path, *, limits: GPXLimits = GPXLimits(),
                     declared_profile: str | None = None) -> dict:
    """Return a schema-shaped accepted or failure report without rewriting GPX.

    File-path input uses incremental reads; XML is scanned with iterparse and
    parsed-point subtrees are discarded. Input limits protect exceptional vendor
    extension subtrees. No downstream L3/L4 validity is asserted.
    """
    if declared_profile is not None and declared_profile not in PROFILES:
        raise ValueError("declared_profile must be GPX-01 through GPX-05")
    digest, size, prefix = _source_identity(source, limits)
    config_digest = sha256(json.dumps(dict(max_bytes=limits.max_bytes,
        max_nodes=limits.max_nodes, max_depth=limits.max_depth,
        declared_profile=declared_profile), sort_keys=True).encode()).hexdigest()
    report = dict(report_version="1.0.0", report_kind="ADMISSION_FAILURE",
                  run=dict(contract_id="S01-CHR-v1.0.0", contract_status="APPROVED",
                           implementation_id="gpx_pipeline.characterization.v1",
                           configuration_digest=config_digest, evidence_status="EXECUTED"),
                  source=_source_record(digest, size, prefix),
                  admission=dict(xml_status="NOT_EXECUTED", gpx_xsd_status="NOT_EXECUTED",
                                 vendor_status="NOT_EXECUTED", resource_status="NOT_EXECUTED"),
                  diagnostics=[])
    if digest is None:
        return _failure(report, "INPUT_LIMIT", "CHR-12", "resource_status", "max_bytes exceeded")
    schemas = _schemas()  # integrity-pinned local schemas; no network loading
    resource = report["admission"]
    inventory = dict(waypoints=0, routes=0, route_points=0, tracks=0,
                     track_segments=0, track_points=0, empty_segments=0,
                     singleton_segments=0)
    globals_ = dict(metadata_present=False, any_core_name=False,
                    any_core_time=False, extension_content=False,
                    optional_content=False)
    point_counters = {key: dict(points=0, counts=Counter()) for key in (
        "track_points", "route_points", "waypoints")}
    features = []
    current = None
    stack = []
    segment_size = 0
    foreign = Counter()
    known_foreign = False
    unknown_foreign = False
    known_root_count = 0
    node_count = 0
    fix_fields = set()
    descriptive_fields = Counter()
    foreign_nodes = 0
    try:
        with _stream(source) as handle:
            parser = etree.iterparse(handle, events=("start", "end"), no_network=True,
                                     resolve_entities=False, load_dtd=False,
                                     huge_tree=False, remove_blank_text=False)
            for event, element in parser:
                if not isinstance(element.tag, str):
                    continue
                q = etree.QName(element)
                local = q.localname
                is_core = q.namespace == GPX11_NAMESPACE
                if event == "start":
                    stack.append(element)
                    node_count += 1
                    if node_count > limits.max_nodes or len(stack) > limits.max_depth:
                        raise _ResourceLimit("nodes/depth limit exceeded")
                    if node_count == 1:
                        report["source"].update(namespace_uri=q.namespace,
                            gpx_version=element.get("version"), creator=element.get("creator"))
                    if not is_core:
                        foreign_nodes += 1
                        foreign[(q.namespace or "", local)] += 1
                        if q.namespace in schemas:
                            known_foreign = True
                        else:
                            unknown_foreign = True
                        globals_["extension_content"] = True
                        globals_["optional_content"] = True
                    elif local not in STRUCTURAL:
                        globals_["optional_content"] = True
                    if is_core and local == "metadata":
                        globals_["metadata_present"] = True
                    if is_core and local == "name":
                        globals_["any_core_name"] = True
                    if is_core and local == "time":
                        globals_["any_core_time"] = True
                    if is_core and local in ("name", "desc", "cmt", "src", "link", "type", "sym", "number", "keywords", "author", "copyright"):
                        descriptive_fields[local] += 1
                    if is_core and local in ("fix", "sat", "hdop", "vdop", "pdop"):
                        fix_fields.add(local)
                    if is_core and local == "trk" and len(stack) == 2:
                        current = _new_feature("trk", inventory["tracks"])
                        inventory["tracks"] += 1
                    if is_core and local == "rte" and len(stack) == 2:
                        current = _new_feature("rte", inventory["routes"])
                        inventory["routes"] += 1
                    if is_core and local == "trkseg":
                        inventory["track_segments"] += 1
                        if current:
                            current["segments"] += 1
                            current["last"], current["last2"] = None, None
                        segment_size = 0
                    continue
                # end event -- vendor subtree remains intact until its containing point clears
                parent = element.getparent()
                parent_q = etree.QName(parent).namespace if parent is not None and isinstance(parent.tag, str) else None
                if not is_core and q.namespace in schemas and parent_q != q.namespace:
                    if not schemas[q.namespace].validate(etree.ElementTree(element)):
                        raise _VendorInvalid(f"{q.namespace}: {schemas[q.namespace].error_log.last_error}")
                    known_root_count += 1
                if is_core and local == "name" and current is not None and parent is not None:
                    if parent.tag in (GPX+"trk", GPX+"rte"):
                        current["name"] = (element.text or "").strip() or None
                if is_core and local in ("trkpt", "rtept", "wpt"):
                    point = _point(element)
                    scope = {"trkpt": "track_points", "rtept": "route_points", "wpt": "waypoints"}[local]
                    inventory[scope] += 1
                    point_counters[scope]["points"] += 1
                    point_counters[scope]["counts"].update(point["fields"])
                    if current is not None and local != "wpt":
                        _append_point(current, point)
                    if local == "trkpt":
                        segment_size += 1
                    # Bound resident tree size on long tracks / routes.
                    element.clear()
                    if parent is not None:
                        while element.getprevious() is not None:
                            del parent[0]
                elif is_core and local == "trkseg":
                    if current is not None:
                        current["segment_sizes"].append(segment_size)
                    if segment_size == 0:
                        inventory["empty_segments"] += 1
                    elif segment_size == 1:
                        inventory["singleton_segments"] += 1
                    element.clear()
                    if parent is not None:
                        while element.getprevious() is not None:
                            del parent[0]
                elif is_core and local in ("trk", "rte") and current is not None:
                    features.append(current)
                    current = None
                    element.clear()
                    if parent is not None:
                        while element.getprevious() is not None:
                            del parent[0]
                if len(stack) == 1 and local == "gpx":
                    if element.getroottree().docinfo.doctype:
                        raise _SecurityInvalid("DOCTYPE prohibited")
                stack.pop()
        resource["xml_status"] = "PASS"
        resource["resource_status"] = "PASS"
        # Independently check the authoritative GPX XSD in a second, streaming pass.
        with _stream(source) as handle:
            iterator = etree.iterparse(handle, events=("end",), schema=schemas[GPX11_NAMESPACE],
                                       no_network=True, resolve_entities=False,
                                       load_dtd=False, huge_tree=False)
            for _, element in iterator:
                if element.tag in (GPX+"trkpt", GPX+"rtept", GPX+"wpt", GPX+"trkseg", GPX+"rte"):
                    element.clear()
                    parent = element.getparent()
                    if parent is not None:
                        while element.getprevious() is not None:
                            del parent[0]
        resource["gpx_xsd_status"] = "PASS"
    except _ResourceLimit as exc:
        return _failure(report, "INPUT_RESOURCE_LIMIT", "CHR-12", "resource_status", exc)
    except _SecurityInvalid as exc:
        return _failure(report, "XML_SECURITY", "CHR-01", "xml_status", exc)
    except _CoreInvalid as exc:
        return _failure(report, "GPX_COORDINATE_INVALID", "CHR-03", "gpx_xsd_status", exc)
    except _VendorInvalid as exc:
        return _failure(report, "RECOGNIZED_VENDOR_XSD_INVALID", "CHR-06", "vendor_status", exc)
    except etree.XMLSyntaxError as exc:
        field = "gpx_xsd_status" if resource["xml_status"] == "PASS" else "xml_status"
        return _failure(report, "GPX_XSD_INVALID" if field == "gpx_xsd_status" else "XML_INVALID",
                        "CHR-01", field, str(exc).splitlines()[0])
    if not isinstance(source, bytes):
        after, _, _ = _source_identity(source, limits)
        if after != digest:
            return _failure(report, "SOURCE_CHANGED", "INV-001", "resource_status", "source changed during inspection")
    resource["vendor_status"] = ("INDETERMINATE" if unknown_foreign else
                                 "PASS" if known_foreign else "NOT_APPLICABLE")
    report["report_kind"] = "CHARACTERIZATION"
    report["inventory"] = inventory
    report["field_coverage"] = {name: _coverage_map(data) for name, data in point_counters.items()}
    global_optional = globals_.copy()
    reported_features = []
    for f in features:
        matches = _matches(f, global_optional)
        fid = f"{f['kind']}:{f['index']}"
        reported_features.append(dict(feature_id=fid, kind=f["kind"],
            source_index=f["index"], name=f["name"], point_count=f["points"],
            segment_count=f["segments"], has_usable_line=bool(f["usable_pairs"]),
            coverage=_coverage_map(f), matches=matches,
            _elevation_pairs=f["elevation_pairs"], _time_pairs=f["time_pairs"],
            _timed_geo_pairs=f["timed_geo_pairs"],
            _triples=f["triples"], _contains_crossing=f["contains_crossing"],
            _latitude_extent=(f["min_lat"], f["max_lat"]),
            _longitude_extent=(f["min_lon"], f["max_lon"]),
            _segment_sizes=tuple(f["segment_sizes"]),
            _time_min=f["min_time"], _time_max=f["max_time"],
            _time_precision=tuple(sorted(f["precision_digits"])),
            _unknown_timezone_count=f["unknown_zone_count"]))
    for f in reported_features:
        if f["point_count"]:
            evidence = [f"latitude_range={f['_latitude_extent'][0]:.9f}..{f['_latitude_extent'][1]:.9f}"]
            if f["_contains_crossing"]:
                evidence.append("longitude_extent=ANTIMERIDIAN_SPLIT_REQUIRED")
            else:
                evidence.append(f"longitude_range={f['_longitude_extent'][0]:.9f}..{f['_longitude_extent'][1]:.9f}")
            report["diagnostics"].append(dict(code="COORDINATE_EXTENT", requirement_id="CHR-03",
                severity="INFO", location=f["feature_id"], evidence=evidence))
    for f in reported_features:
        if f["kind"] == "trk":
            report["diagnostics"].append(dict(code="SEGMENT_BOUNDARIES", requirement_id="CHR-08",
                severity="INFO", location=f["feature_id"],
                evidence=["segment_point_counts=" + ",".join(map(str, f["_segment_sizes"]))]))
        if f["coverage"]["time"]["present"]:
            evidence = ["fractional_second_digits=" + ",".join(map(str, f["_time_precision"])),
                        f"timezone_missing_count={f['_unknown_timezone_count']}"]
            if f["_time_min"] is not None:
                evidence += [f"earliest_comparable_time={f['_time_min'].isoformat()}",
                             f"latest_comparable_time={f['_time_max'].isoformat()}"]
            report["diagnostics"].append(dict(code="TEMPORAL_COVERAGE", requirement_id="CHR-05",
                severity="INFO", location=f["feature_id"], evidence=evidence))
    if descriptive_fields:
        report["diagnostics"].append(dict(code="DESCRIPTIVE_INVENTORY", requirement_id="CHR-07",
            severity="INFO", location=None,
            evidence=[f"{key}={value}" for key, value in sorted(descriptive_fields.items())]))
    report["classification"] = _classify(reported_features, declared_profile)
    report["capabilities"] = _capabilities(reported_features, unknown_foreign)
    report["features"] = [{k: v for k, v in f.items() if not k.startswith("_")}
                          for f in reported_features]
    report["extensions"] = [dict(namespace_uri=ns, element_qname=f"{{{ns}}}{name}",
        occurrences=n, recognized=ns in schemas,
        source_reference=None) for (ns, name), n in sorted(foreign.items())]
    elevation_count = sum(x["counts"]["ele"] for x in point_counters.values())
    geoid_count = sum(x["counts"]["geoidheight"] for x in point_counters.values())
    reference_details = ([f"geoidheight_count={geoid_count}; geoid model unverified"] if geoid_count
                         else ["no vertical datum/model identified"] if elevation_count else [])
    report["reference_evidence"] = dict(horizontal_reference="WGS84_GPX11_CONVENTION",
        vertical_reference="UNKNOWN" if elevation_count else "NOT_APPLICABLE",
        geoid_model=None, evidence=reference_details)
    report["provenance"] = dict(origin="UNKNOWN", basis=[], privacy_status="NOT_CERTIFIED")
    report["resource_metrics"] = dict(xml_element_count=node_count,
        vendor_extension_element_count=foreign_nodes, peak_memory_bytes=None,
        extension_payload_bytes=None, parser_mode="STREAMING")
    antimeridian = any(f["_contains_crossing"] for f in reported_features)
    timestamps = sum(x["counts"]["time"] for x in point_counters.values())
    comparable = sum(x["_time_pairs"] for x in reported_features)
    report["summary_evidence"] = dict(metadata_present=globals_["metadata_present"],
        any_core_name=globals_["any_core_name"], any_core_time=globals_["any_core_time"],
        segment_boundaries_preserved=True,
        antimeridian_status="CROSSING" if antimeridian else "NO_CROSSING" if features else "NOT_APPLICABLE",
        fix_fields=sorted(fix_fields),
        temporal_comparability="NO_TIMESTAMPS" if not timestamps else
            "COMPARABLE" if comparable and all(x["counts"]["time"] == x["points"] for x in features) else
            "PARTIAL" if comparable else "INDETERMINATE",
        geodesic_line_suitable=any(f["has_usable_line"] for f in reported_features))
    return report


class _ResourceLimit(Exception):
    pass


class _SecurityInvalid(Exception):
    pass


class _VendorInvalid(Exception):
    pass


class _CoreInvalid(Exception):
    pass