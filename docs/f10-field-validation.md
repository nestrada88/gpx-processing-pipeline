# F10 — Offline operational and field verification

F10 separates **software readiness**, **import conversion**, and **observed
physical navigation**. CI can establish only the first. The two physical
navigators must be independently tested without an active mobile connection.

## eTrex SE hard limits

Garmin publishes 50 stored courses and **200 points per course**:
https://support.garmin.com/da-DK/?faq=Hg2pM7ov4oAql6IzzaB398

The Garmin Explore website has different *import* thresholds (up to 10,000
trackpoints when importing as tracks). Import eligibility does **not** prove
that the final eTrex SE course preserves a 10,000-point source.

For safety F10 rejects a source line over 200 points for eTrex export rather
than automatically simplifying the original geometry. It also rejects more
than 50 source lines. Actual Garmin conversion of multi-segment tracks and
source routes remains explicitly **unverified**. The source analytical
dataset is not subject to device navigation limits.

No numerical course point limit is asserted for the Instinct 2X Tactical
without an independently verified device-specific reference.

## Repeatable field procedure (manual; not performed by CI)

For **each** device independently:

1. Record exact model, firmware version, transfer path, original GPX SHA-256
   and exported GPX SHA-256.
2. Import through its documented workflow (eTrex SE: Garmin Explore; Instinct
   2X Tactical: Garmin Connect); capture actual success/failure evidence.
3. Verify course appears on the device. Record the observed start, finish,
   waypoint identities and point/segment fidelity if exportable.
4. Disable network access and verify route viewing/navigation independently
   on the device, without smartphone assistance.
5. Walk a controlled deviation to test off-course feedback *only in safe
   terrain*; record alert behavior without assuming a device feature exists.
6. Record observed results and stable local evidence paths/identifiers in
   `FieldEvidenceRecord`. Unobserved operations must be `unverified`.
7. If a post-import Garmin course cannot be exported, mark exact course
   geometry fidelity as `unverified` rather than estimating equality from
   screenshots.

No test claims a physical pass without supplied evidence. An exported GPX
checksum verifies the local file only, not the Garmin-converted course.

## Reliability verification

- 199/200/201 and 10,000 trackpoint boundary tests separate import limits from
  eTrex device capacity.
- CI injects publication failure before staging rename and verifies cleanup.
- Deterministic manifests allow repeated-run artifact comparison.
- Numerical tests use independent WGS84 geodesic reference values.
- Field observations are strictly operator-supplied and tied to both hashes.
- Optional DEM uncertainty, missing-data, and adaptive sampling behaviors
  continue under the existing F03/F06 regression suite.

F10 does not create device control software, a field data service, or external
approval processes. No device transfer or field observation was performed by
this implementation.
