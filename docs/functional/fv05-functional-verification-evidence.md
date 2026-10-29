# FV-05 — Consolidated Functional Verification Evidence

## 1. Baseline and evidence rules

- Repository: `nestrada88/gpx-processing-pipeline`.
- Baseline: merged FV-04 PR #70, commit `6bf851fddbf1666ddbf59596aa1d875cb137885f`.
- Functional contract source: [FV-00 inventory](fv00-functional-verification-inventory.md).
- Evaluated evidence: [FV-01 PR #67](https://github.com/nestrada88/gpx-processing-pipeline/pull/67), [FV-02 PR #68](https://github.com/nestrada88/gpx-processing-pipeline/pull/68), [FV-03 PR #69](https://github.com/nestrada88/gpx-processing-pipeline/pull/69), [FV-04 PR #70](https://github.com/nestrada88/gpx-processing-pipeline/pull/70), and their passing branch CI logs.
- Latest verified branch run: [FV-04 run #40929192235](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40929192235), Python 3.11 and 3.12, **521 passing tests per environment**, 2,390 statements / 45 missed, 860 branches / 43 partially covered, **97% combined coverage**.
- Post-merge run [#40931215431](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/40931215431) was **in progress at the time of this evidence capture**; check current GitHub state before asserting a post-merge pass.
- Test-case presence and green CI support only their *actually asserted* outcomes. A general requirement is not considered fully tested merely because an adjacent scenario was tested.
- This is a documentation-only technical artifact, not a new functional test execution.

## 2. Functional contract traceability

Classification is scoped strictly to current evidence: **verified subset** = specific positive/negative behaviors exercised successfully; **partial** = key additional acceptance cases remain; **unverified** = no matching end-to-end evidence. These are evidence labels, not approvals or workflow gates.

| FV-00 ID | Functional responsibility | Direct evidence | Verified behavior | Evidence gap |
|---|---|---|---|---|
| FV-01 | Installed CLI and configuration | [PR #67](https://github.com/nestrada88/gpx-processing-pipeline/pull/67) | Installed console entrypoint, five subcommand help names, successful text/JSON validation, argparse/config failures and duplicate target rejection | Full CLI option permutation coverage and `--debug` exception behavior |
| FV-02 | Secure source validation | PRs #67, #69, #70 | Invalid spatial data, malformed XML and excess input bytes fail without published output; positive bundled GPX validation | Full negative corpus for every GPX/XSD/temporal gate and adversarial parser/resource combinations |
| FV-03 | Canonical enriched dataset | [PR #68](https://github.com/nestrada88/gpx-processing-pipeline/pull/68) | Multi-segment source identity; original elevation/time retention; no invented segment connector or DEM heights; SHA-256 lineage | More complex multi-track/route topology under the installed CLI |
| FV-04 | DEM enrichment | PR #68 | Known constant metre-valued local GeoTIFF sampled, recorded elevations retained, DEM input fingerprint preserved | NoData gaps, incompatible CRS/units, datum conversions and independent surveyed elevation reference |
| FV-05 | Adaptive terrain sampling | PR #68 | Derived, segment-separated interpolations for edges longer than default 200 m spacing; source GPX immutable | Missing/curved DEM surface and budget-limited refinement in the installed CLI |
| FV-06 | Recorded/forecast time separation | PRs #68, #70 | Missing-grade forecast unavailable unless flat grade expressly assumed; simulated forecast separate from recorded timestamps; byte-deterministic forecast | Checkpoint ETA plans with independent pacing/rest ground truth |
| FV-07 | Waypoint catalog | PRs #68, #69 | Waypoint identity/name/position preserved in analytics and Garmin export | Tagged/reverse-geocoded waypoint completeness and full checkpoint order via CLI |
| FV-08 | Planned/recorded comparison | [PR #69](https://github.com/nestrada88/gpx-processing-pipeline/pull/69) | Independent planned/recorded hashes; observed excursion/rejoin; observed elapsed time; no invented planned duration | Multi-segment, absent recorded-time and mixed-datum comparison cases at CLI boundary |
| FV-09 | Dual Garmin export | PR #69 | Independent eTrex SE and Instinct 2X device GPX, exact track/route token and waypoint identity against source; independent hash/readiness evidence | Garmin Explore/Connect import conversion and device-tested geometry are unverified |
| FV-10 | Software device gates | PR #69 | eTrex SE 201-point track rejected without publication; physical verification flags remain false | Actual storage/import thresholds, untested workflow permutations, firmware-dependent behavior |
| FV-11 | Command orchestration | PRs #67–#69 | `analyze` and analytics-only `process`; no implicit Garmin exports; explicit dual `export` | Exhaustive cross-command artifact combinations and selected `process --garmin` scenarios |
| FV-12 | Deterministic publication | [PR #70](https://github.com/nestrada88/gpx-processing-pipeline/pull/70) | Cross-destination byte equality, manifest SHA-256/size validation, no overwrite of existing path/symlink | Cross-host stability and crash-durable directory fsync/recovery |
| FV-13 | Offline/bounded operation | PRs #67, #70 | Missing GPX/size bounds; local validation subprocess with socket connect functions disabled | Offline whole `process`/DEM/Garmin workflow, all network surfaces and raster resource bounds |
| FV-14 | CLI error taxonomy | PRs #67, #69, #70 | CLI codes 2/3/4/5/6 exercised with associated command-level failures | Generic/unmapped processing errors, debug propagation and all security error variants |
| FV-15 | End-to-end lineage/repeatability | PRs #67–#70 | Source unchanged, every published artifact's digest and byte count independently checked, original DEM unchanged, repeatability across output directory names | Cross-platform/cross-dependency numerical byte identity and external data authenticity |

**Result:** Targeted software functional behaviors have passing evidence across all fifteen inventory headings; **none of these headings should be interpreted as exhaustive functional certification**. The gaps column is substantive and must not be dismissed based on total coverage.

## 3. Verified command-to-artifact workflows

| Command | Positive subprocess scenario | Negative or safety scenario | Evidence |
|---|---|---|---|
| `validate` | Text/JSON with input SHA-256 | Oversize, nonexistent or malformed GPX | FV-01/FV-04 |
| `analyze` | Canonical multi-segment dataset, local DEM, adaptive sampling and modeled forecast | Missing DEM dependency, invalid geometry, unwritable/occupied output paths | FV-01/FV-02/FV-04 |
| `process` | Analytical-only by default | Invalid GPX blocks publication | FV-01/FV-03/FV-04 |
| `export` | Two independently labeled Garmin files and software checks | eTrex SE course exceeds conservative 200-point ceiling | FV-03 |
| `compare` | Planned/recorded departure and observed rejoin | Independent planned/recorded rejection corpus not exhaustively exercised | FV-03 |

## 4. Important technical constraints

1. **Source authority.** The GPX source bytes, coordinate text, waypoint identity and original segment boundaries remain authoritative. Adaptive sampling and DEM heights are separate derived data; they do not reconstruct trail bends.
2. **Recorded versus modeled.** Original timestamp text is preserved. Forecast speed and ETA calculations are modeled, never presented as observed traversal.
3. **Garmin software versus device.** Static GPX schema/manifest verification and operational readiness do not prove Garmin Explore/Connect import or converted course geometry, alert/vibration behavior or offline independent navigation.
4. **Publication semantics.** Linux tested failure cases and simulated Windows collision checks do not prove native Windows no-replace guarantees, power-loss durability, or network filesystem atomicity.
5. **Scientific validity.** Constant-valued synthetic DEMs validate execution wiring, not real-world elevation uncertainty, horizontal/vertical datum accuracy or modeled activity duration against field observations.
6. **No global offline proof.** Blocking socket `connect` in the `validate` subprocess is stronger than an ordinary local run but not a complete network-denial integration test for all commands.

## 5. Residual functional work by practical impact

| Priority | Responsibility | Observable acceptance evidence still needed |
|---|---|---|
| High | Full enrichment correctness | Independent reference raster with known CRS, height units, vertical datum and NoData boundaries; verify CLI-derived elevations and adaptive sampling confidence |
| High | Navigation transfer readiness | Garmin Explore and Connect conversion comparison to immutable source GPX, course point ordering, import limits; native physical field testing stays **on hold** |
| High | Cross-platform publication integrity | Native Windows no-replace/collision and filesystem behavior, not a simulated `Path.rename` exception |
| Medium | CLI negative-space completeness | Invalid chronology, malformed namespaces/extensions, remaining typed failures and conditional option interactions via subprocess |
| Medium | Comparison diagnostics | Multi-segment topology, untimed recordings, checkpoint proximity and mismatched vertical datums through external CLI |
| Medium | Comprehensive offline execution | All five commands without network access, including local DEM and export |
| Medium | Operational reliability | Large GPX/DEM resource limits, interrupted publication, repeated runs, actionable logging and provenance |

## 6. Final functional disposition

**FV-00–FV-04 software functional regression evidence is consolidated**, with explicit acceptance limitations. The suite establishes that selected installed CLI workflows generate correctly structured, hash-verifiable outputs, reject specific invalid conditions and preserve input files. It is **not** proof of total functional coverage, geospatial scientific ground truth or Garmin field readiness.

- FV-05 modifies documentation only. No application runtime or test change is included.
- Keep unresolved cases visible rather than converting partial evidence into a pass for a wider requirement.
- Continue with **targeted risk-driven functional tests** only when a specific unverified contract matters; avoid manufacturing tests merely to increase percentage coverage.
- Garmin eTrex SE and Instinct 2X Solar Tactical real-device work remains **on hold**.

## 7. Reproduction

```bash
python -m pip install -e '.[test]'
python -m pytest -q --cov=gpx_pipeline --cov-branch --cov-report=term-missing
gpx-pipeline --help
```

See the [FV-00 functional execution inventory](fv00-functional-verification-inventory.md), [F09 CLI contract](../f09/cli-reference.md), [F09 publication](../f09/output-publication.md), [F07 Garmin boundaries](../F07-GARMIN-NAVIGATION-EXPORT.md), and [F10 field evidence](../F10-OPERATIONAL-RELIABILITY.md).
