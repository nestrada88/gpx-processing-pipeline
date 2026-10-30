# GPX-Study — Stage 01 Input Characterization Contract

**Identifier:** `S01-CHR-v1.0.0`  
**Status:** **APPROVED — BASELINED**  
**Date:** 2026-10-30  
**Parent scope constraint:** `S01-SCOPE-EXC-v1.0.0` (**APPROVED**)  
**Verification companion:** `S01-CHR-VRF-v1.0.0` (reconciled draft; not executed)  
**Authoritative format:** GPX 1.1, https://www.topografix.com/gpx/1/1/

## 0. Status and normative language

This user-approved contract defines the classification and characterization requirements for Stage 01. The approved exclusion contract governs all work. `MUST`, `MUST NOT`, and `SHOULD` are normative for this functional contract; they are not claims of deployed functionality. Validation result `PASS` requires execution evidence; results below are test oracles, not observed outcomes.

Stage 01 inspects, characterizes, validates, and reports. It never changes source GPX, generates missing observations, interpolates gaps, combines segments, corrects coordinates/elevations/timestamps, or generates navigation products.

## 1. Input, admission, and feature units

- Input is an XML document claiming GPX 1.1. An **admitted document** passes security/size policy, XML well-formedness, and the official GPX 1.1 core XSD. A recognized vendor extension that fails its trusted versioned XSD also fails admission under this **approved strict-vendor policy**; an unknown well-formed foreign-namespace extension is inventoried as opaque without blocking core admission. Failed admission yields a *failure report*, never an accepted characterization. Admission-policy resource limits are external configuration inputs and are **not assigned arbitrary numeric values here**.
- Native topology: root `<gpx>`; `wpt` (standalone waypoint); `rte` containing ordered `rtept`; `trk` containing `trkseg` containing ordered `trkpt`. GPX 1.1 permits empty tracks, routes, and segments; core-valid does not imply LineString suitability.
- A **primary feature** for one of GPX-01…05 is a single `trk` or `rte` containing at least one **usable line**: for a track, at least one individual `trkseg` containing two consecutive, distinct valid coordinates; for a route, at least two consecutive, distinct route points. An isolated waypoint is not a line. Track segments are NEVER bridged.
- Profile compatibility is evaluated **per primary feature**, with document-global absence constraints applied where defined. Aggregated document identity is assigned only if all nonempty primary features have the same unique qualifying profile and no global conflict. Other feature kinds are inventoried; mixed routes/tracks may have different profiles. Empty features are characterized but not forced into a profile.
- `lat` and `lon` are point attributes, not GPX `<lat>`/`<lon>` child elements. Source root `creator` and `version` are mandatory in every valid profile, including the so-called minimal and privacy-filtered profiles.
- **Metadata presence** includes a core `<metadata>` container even if empty. **Core timestamp absence** means no GPX-namespace `<time>` at the relevant point level; privacy-filtered and minimal profiles additionally prohibit metadata `<time>`. **Name presence** at feature level is a nonblank `<trk><name>` or `<rte><name>` after whitespace trimming; standalone waypoint/point names alone do not satisfy the feature-name requirement.
- Sensor telemetry is detected only in explicitly recognized extension namespace/version + expanded XML name combinations. Unknown extension payloads are inventoried and preserved as opaque source content; they do not establish sensor type, lack of identity, or safe semantics. XML namespace prefix spelling is not semantically relevant.

## 2. Profile match semantics (approved policy)

A profile yields `MATCH`, `PARTIAL`, or `NO_MATCH`, with machine-readable reasons. `MATCH` means field-pattern compatibility, **not use-case intent, measurement authenticity, privacy safety, or validity of the observations**. `PARTIAL` means the usable-line input satisfies the profile's exclusion predicates and has some, but not all, positive discriminators; it is an advisory candidate, never an exact match. Any violated exclusion predicate produces `NO_MATCH`. `NO_MATCH` is incompatible with the essential geometry or declared profile. `intent` may be `DECLARED`, `CORROBORATED`, or `UNKNOWN`; the absence/presence pattern does not infer intent. Declaration conflicts are reported as `DECLARED_CONFLICT` and never override measurements.

| Profile | Required per usable feature | Required absence | Additional exact-match rule |
|---|---|---|---|
| `GPX-01` Complete Telemetry | Valid coordinates, `<ele>` and `<time>` on **every primary point**; supported sensor HR, cadence, and temperature each present at least once within that feature | None prescribed | Each of the three named sensors must be recognized and value-valid; their *per-point* coverage is reported separately. Other sensors optional. Strict all-point sensor coverage is a distinct diagnostic, not an automatic assumption. |
| `GPX-02` Static Trail / Route | Valid coordinates, `<ele>` on every primary point; nonblank **feature** `<name>` | No point `<time>` and no recognized sensor telemetry on that feature | Other descriptive/metadata fields may exist, subject to GPX XSD. |
| `GPX-03` 2D Footprint / Geometry | Valid coordinates and nonblank feature `<name>` | No point `<time>` or `<ele>` on that feature; no recognized sensor telemetry on that feature | External metadata may exist. A sensor-like unknown extension does not prove a recognized sensor. |
| `GPX-04` Privacy-Filtered Shape | Valid coordinates and `<ele>` on every primary point | No core `<metadata>` anywhere, no core `<name>` or `<time>` anywhere, and no extension content anywhere | **Never** infer anonymity or privacy intent. The mandatory source `creator`, geolocation itself, and other remaining data may be identifying; record privacy as `NOT_CERTIFIED`. |
| `GPX-05` Bare Minimal Line-String | Valid coordinates and usable line geometry | No optional core content (`<ele>`, `<time>`, `<name>`, metadata, descriptive or quality elements) and **no `<extensions>` content** at any location | GPX required root attributes and mandatory XML namespace remain. A line may come from `rtept` or `trkpt`. |

**Policy note:** GPX-01's HR/cadence/temperature inventory is an approved default resolution of the user-provided full-telemetry example; other activity use cases may require a versioned sensor inventory instead. Category 4 is renamed *Privacy-Filtered Shape* in technical decisions to avoid claiming successful anonymization; canonical user-facing category alias remains **Anonymous / Privacy-Filtered**.

### 2.1 Exact partial-match discriminators

A feature with no usable line receives `NO_MATCH` for all five profiles. Otherwise each profile uses the following deterministic evaluation order: test prohibited fields; if any are present return `NO_MATCH`; test complete positive requirements; if all succeed return `MATCH`; otherwise apply the profile-specific `PARTIAL` predicate below, else `NO_MATCH`.

| Profile | `PARTIAL` predicate after exclusions pass | Otherwise |
|---|---|---|
| GPX-01 | At least one observed point elevation, point timestamp, **or** recognized member of the required HR/cadence/temperature roster, but at least one required completeness condition fails | `NO_MATCH` |
| GPX-02 | At least one point elevation **or** a nonblank feature name, but some elevation is absent or feature name missing | `NO_MATCH` |
| GPX-03 | Elevation and point time absent, recognized telemetry absent, but required nonblank feature name missing | `NO_MATCH` |
| GPX-04 | Document-global metadata, name, time, and extension absences satisfied; elevation occurs at some, but not all, primary points | `NO_MATCH` |
| GPX-05 | Never partial: exactly bare minimal or `NO_MATCH` | `NO_MATCH` |

`GPX-01` has no prohibited-field constraint; its telemetry checks still require **recognized, valid** values. Profile match equality and all counts are evaluated on the same primary-feature point population. When no profile exactly matches, two or more partial candidates produce `AMBIGUOUS` (all are reported; no fabricated tie-breaking score). A single partial candidate produces `UNCLASSIFIED` with that candidate shown. Explicit declaration cannot turn a partial candidate into a match.

### 2.2 Classifier decision procedure

1. Reject accepted-characterization publication if core admission failed. Preserve rejection evidence.
2. Extract per-feature field counts, full document root-level counts, and source/extension inventory without modification.
3. Apply geometry suitability; no usable line -> `UNCLASSIFIED` for that feature, with `NO_USABLE_LINE` reason.
4. Evaluate all five profile predicates independently for every usable feature. Never select solely by an assumed order.
5. Exactly one `MATCH` -> compatible profile; two or more `MATCH` -> `AMBIGUOUS`. If no exact match exists and two or more `PARTIAL` candidates remain plausible without a declared disambiguating basis, report `AMBIGUOUS`; otherwise report `UNCLASSIFIED` with any partial candidate retained. Multiple features with different uniquely matched profiles -> `MIXED`.
6. If a declared input profile conflicts with observed fields, output `DECLARED_CONFLICT`; retain the calculated match(es), do not coerce classification.
7. Document-level `SINGLE` classification requires all nonempty primary features to have the same unique match, no unmatched usable feature, and no conflicting declaration. Mixed/empty stand-alone waypoints are inventoried separately; they must not be used to fabricate a route/track classification.
8. No probabilistic `profile_confidence` is emitted without a calibrated inference model; return categorical basis plus reason codes instead.

## 3. Field-coverage mathematics and semantics

All coverage metrics have a declared **scope**: `track_points`, `route_points`, `waypoints`, or `feature:<stable-index>`. Never silently mix standalone waypoints into route/track coverage. Primary-point population `N` includes all relevant points in that scope, irrespective of field presence.

For field `f`:

- `N_eligible(f)` = count of the points at which the field is meaningful.
- `N_present(f)` = count containing a syntactically present field occurrence; for attributes, present means the attribute exists.
- `N_valid(f)` = count whose value is permitted by the relevant schema/recognized extension validator. For opaque vendor data, validity is `INDETERMINATE`, not guessed.
- `coverage(f) = N_valid(f) / N_eligible(f)` when `N_eligible(f) > 0`.
- `N_eligible(f) = 0`: `coverage = null`, `status = NOT_APPLICABLE`; **never 0/0 or 100%**.
- `N_present=0,N_eligible>0`: `ABSENT`; `N_valid=N_eligible>0`: `COMPLETE`; `0<N_valid<N_eligible`: `PARTIAL`; syntactically present but invalid: `INVALID` for affected field and refer to its validation failure; undetermined extension semantics: `INDETERMINATE`.
- All counts MUST be nonnegative integers, `N_valid <= N_present <= N_eligible`, and numerical coverage MUST equal the fraction to within serialization round-trip tolerance. A partly invalid field records valid/present/missing/invalid counts independently; precedence `INVALID` when any invalid value is present, with coverage retained.
- Timestamp, name, sensor, and elevation inventories are counted **separately** for route points, track points, standalone waypoints, and each primary feature. Nonblank feature names are counted at `trk` / `rte`, not inferred from point names.
- Report document-global `metadata_present`, `any_core_name`, `any_core_time`, and extension inventory separately from point-level field coverage. For privacy/minimal predicates, global absence is checked explicitly.
- Large documents MUST support equivalent streaming counts without allocating a full document tree; no fixed full-tree switching threshold is standardized by GPX.

## 4. Capability predicates — eligibility only

Values: `ELIGIBLE_FOR_VALIDATION`, `PARTIALLY_ELIGIBLE`, `UNAVAILABLE`, `INDETERMINATE`. **Never `PASS`/`FAIL`** here; these belong to executed validator results. A field's presence does not certify downstream integrity.

| Capability | Eligibility predicate | Limits and decision |
|---|---|---|
| `horizontal_line` | At least two consecutive distinct points within one `trkseg` or `rte` | Never bridge segments; standalone points -> `UNAVAILABLE`. |
| `elevation_profile` | At least one usable adjacent pair with valid `<ele>` at both endpoints | `PARTIALLY_ELIGIBLE` if missing elevation elsewhere; all eligible pairs and complete coverage -> `ELIGIBLE_FOR_VALIDATION`. |
| `grade` | At least one valid adjacent point pair with both elevations and meaningfully nonzero geodesic displacement | Near-zero separation/uncertainty -> `INDETERMINATE`, not division by zero. |
| `temporal_L3` | At least one adjacent pair within a continuous segment/route with comparable timestamps | Full or partial time coverage yields eligible/partial; no positivity guaranteed until L3 executes. |
| `kinematic_L4` | At least one adjacent coordinate pair with comparable timestamps | `ELIGIBLE_FOR_VALIDATION` only as pending L3 gating; actual positive Δt is enforced by L3, not pre-certified. |
| `acceleration` | At least one triple of consecutive spatial points with comparable timestamps in same segment/route | L3 positivity and dynamic plausibility remain unverified. |
| `sensor:<name>` | At least one value validated against known extension namespace and field type | Per-field, per-feature eligibility; unknown vendor content -> `INDETERMINATE`. |
| `vertical_reference_assessment` | Elevation exists and some vertical reference evidence is available | Datum conversion eligibility is **not** automatically established by GPX `<ele>`; ambiguous height reference -> `INDETERMINATE`. |
| `geometric_spatial_overlay` | Sufficient valid coordinates and defined operation geometry | Requires external overlay layers for execution; this is capability characterization, not overlay execution. |

Invalid core/schema input is excluded from accepted characterization; an intentionally partial report may expose failure counts only as an admission diagnostic.

## 5. Characterization report contract

Machine-readable artifact: **`S01-CHR-REPORT.schema.json`** (JSON Schema Draft 2020-12). Two discriminated kinds:

- `CHARACTERIZATION` — only when secure admission, core XSD, resource checks, and recognized vendor-XSD checks (if any) passed; includes `source`, `admission`, `inventory`, `field_coverage`, `features`, `classification`, `capabilities`, `extensions`, `reference_evidence`, `provenance`, `diagnostics`, and `run`.
- `ADMISSION_FAILURE` — includes source identity when measurable, failed admission checks (including recognized vendor-XSD failure), controlled diagnostics, and no accepted `classification`/`capabilities` field.

Required semantics:

- Report version, contract ID, software/configuration identifiers, source digest and byte length, and deterministic diagnostics.
- `source.sha256` is an exact byte digest; source immutability requires comparing input bytes or digest before/after, not presuming a successful hash proves origin authenticity.
- `inventory` counts separate track/route/waypoint/segment totals; may identify empty and singleton segments.
- `features` identify feature type and stable positional indices (not rewritten GPX IDs); per-feature field coverage and candidate profile results.
- `classification.status` is one of `SINGLE`, `MIXED`, `AMBIGUOUS`, `UNCLASSIFIED`, `DECLARED_CONFLICT`; resolved profile may be null.
- `capabilities` express eligibility only, with evidence and blocking prerequisites.
- `diagnostics` record requirement identifier, location, severity, source facts, and reason code. No file-path exposure required in user-facing copies.
- `provenance` reports `UNKNOWN` unless substantiated; `creator` alone does not prove empirical acquisition; no probability/confidence score is invented.
- JSON Schema verifies report **shape**, not arithmetic invariants, classification truth, coverage fractions, or test execution. Those require explicit independent semantic assertions in the verification suite.
- An unknown namespace's subtree remains in the original source; the report may inventory its namespace, count, and evidence pointer without serializing large payloads into memory.

## 6. CHR-01 through CHR-12 — approved assertions

| ID | Required characterized information | Failure / uncertainty contract |
|---|---|---|
| CHR-01 | GPX namespace, version, creator, declared/effective encoding | Core invalid -> admission failure; UTF-8-only rule, if enabled, is policy not GPX requirement |
| CHR-02 | Root and nested wpt/rte/trk/trkseg/rtept/trkpt counts, including empty groups | No invented lines from singleton/empty segments |
| CHR-03 | Per-feature coordinate coverage, valid geometry, bounds with antimeridian-aware interpretation | Geographic range failures remain admission errors |
| CHR-04 | Per-scope `<ele>` presence/validity/coverage and unit indication | Unknown vertical reference is not a zero elevation |
| CHR-05 | Per-scope `<time>` coverage, precision, timezone comparability and available span | No Layer 3 monotonicity result in characterization |
| CHR-06 | Known sensor data and namespace/version; unknown extension inventory | No inferred semantics for opaque extension blocks |
| CHR-07 | Presence of metadata, feature-level and point-level names and descriptive fields | Empty names do not satisfy nonblank feature naming |
| CHR-08 | Track-segment counts and explicit boundaries; possible geometry separation | No GNSS-loss attribution or segment merging |
| CHR-09 | Presence of fix, sat, HDOP, VDOP, PDOP and recognized quality extensions | Presence is not GNSS accuracy certification |
| CHR-10 | WGS 84 coordinate convention and available datum/geoid evidence | Do not imply known orthometric/ellipsoidal reference from `<ele>` alone |
| CHR-11 | Source provenance facts and derived vs inferred status | No unsupported empirical/authentic/anonymous declaration |
| CHR-12 | Actual input bytes, element counts and extension payload inventory, within admission limits | Resource breaches fail safely; no inferred 16 MiB universal threshold |

## 7. Verification reconciliation

Companion file **`S01-CHR-VERIFICATION-v1.0.0.csv`** provides all **CHRV-001…CHRV-024** cases, independent test oracles, requirement traceability, profile applicability, and actual execution state. Every case starts `NOT_EXECUTED`. Test oracles are based on controlled fixture XML and independently maintained expectations, **never on outputs from the implementation under test**.

Required independent verification gates:

- V1: CHR-01…12 fully traced to fixture assertions.
- V2: All five categories have exact-positive, negative, and partial coverage; the classification suite includes mixed-feature and multiple-partial-candidate ambiguity subfixtures.
- V3: Structural counts, field coverage, and source bytes match independent oracles.
- V4: Characterization eligibility never claims downstream Layer 3/4 `PASS`.
- V5: Non-destructive EXC-001…020 / INV-001…010 / EXV-001…010 tests satisfy the approved exclusions.
- V6: Resource failure and streaming behavior bounded under documented configured limits.
- V7: Test execution records source digest, implementation/config version, expected/actual status, and evidence references.

**Gate status:** All are `NOT_VERIFIED`. The verification draft is reconciled at the *design* level only; it is not approved or executed.

## 8. Reconciled issues and explicit approval assumptions

1. **Profile identity vs pattern:** compatibility does not establish intent; declared profile conflicting with fields gets `DECLARED_CONFLICT`.
2. **Name rule:** nonblank track/route feature name required for GPX-02/03; a waypoint/point name is insufficient.
3. **Sensor roster:** GPX-01 default HR + cadence + temperature, each at least one recognized value per feature; full per-point coverage separately reported. **Approved for v1.0.0.**
4. **Coverage denominator:** relevant point population only; empty population produces null `NOT_APPLICABLE`.
5. **Mixed files:** classification per feature with `MIXED` document status; no arbitrary precedence.
6. **Privacy:** GPX-04 means privacy-filtered *shape compatibility*, never proof of actual anonymity; mandatory `creator` is separately disclosed as a residual risk.
7. **Outputs:** accepted characterization and admission failure are separate report shapes, not an ambiguous partial success.
8. **Known-vendor failures:** malformed recognized vendor telemetry causes admission failure under this approved strict-vendor policy; unknown foreign namespaces are preserved.
9. **No numerical hard limits:** schema/format constants are normative; performance and anomaly thresholds remain external uncalibrated configurations.

## 9. Sign-off and state

- `S01-SCOPE-EXC-v1.0.0`: **APPROVED; unchanged**.
- `S01-CHR-v1.0.0`: **APPROVED / BASELINED** (user decision, 2026-10-30).
- `S01-CHR-VRF-v1.0.0`: **RECONCILED DRAFT / EXECUTION NOT STARTED**.
- At definition approval, implementation and empirical tests were **NOT VERIFIED**. Subsequent repository inspection findings are recorded separately in `EXECUTION-READINESS.md`; no CHRV engine test execution has been established.
- Stage 01: **OPEN**.

**APPROVED by explicit user decision, 2026-10-30.** Transition to VERIFIED still requires implementation inspection and executed regression evidence. Publication of this document is not such evidence.