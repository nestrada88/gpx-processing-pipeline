# S01-CHR v1.0.0 — Executed Contract Verification Evidence

**Contract:** S01-CHR-v1.0.0, approved and baselined by PR #73.  
**Implementation PR:** #74, `stage01/input-characterization-implementation`.  
**Test source revision:** `82551d95c99b1100e225a87c36cc3272160cece9` (before this evidence-only commit).  
**CI run:** [41134292541](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/41134292541).

## Reproducible observed results

| Evidence | Python 3.11 | Python 3.12 |
|---|---|---|
| Full GitHub Actions job | SUCCESS | SUCCESS |
| Tests passed | 556 | 556 |
| Pytest failures | 0 | 0 |
| Nonfatal warnings | 186 | 132 |
| Project branch coverage (pytest-cov) | 96% | 96% |
| `characterization.py` branch coverage | 93% | 93% |
| Authoritative pinned GPX/Garmin schema imports | Used | Used |
| Installed CLI subprocess tests | Included | Included |

Artifacts: [Python 3.11 coverage](https://github.com/nestrada88/gpx-processing-pipeline/actions/runs/41134292541/artifacts/13014621699) and the run's corresponding Python 3.12 artifact.

## Executed assertions

- `tests/test_s01_characterization.py`: CHRV-001 through CHRV-024 (24 scenario groups; CHRV-013 checks Garmin TPX v1 and v2), all passed.
- Report shape is independently validated with JSON Schema Draft 2020-12 in every scenario.
- `tests/test_s01_cli_characterize.py`: installed CLI positive, declared-conflict, resource rejection, malformed XML, and unknown-extension policy separation, all passed.
- `test_exv_preservation_and_no_mutation` and CHRV-021 verify the original source bytes remain unchanged for representative cases.
- Existing F01/F08/F09 regressions are included in the full suite and passed.

## Evidence boundaries / remaining gaps

- Test success does **not** demonstrate all EXV-001…EXV-010 as individually executed negative contracts. A complete EXV mapping and broader input corpus remain separate work.
- CHRV-022 verifies streaming mode, 1200 point counts, and configured byte-limit failure; it does **not** establish a statistically calibrated peak-memory bound for very large extension/metadata subtrees.
- The test corpus is controlled/synthetic. No empirical GNSS field measurements, privacy-anonymization guarantee, vendor hardware checks, or Layer 3/4 downstream quality verdict is asserted.
- `S01-SCOPE-EXC-v1.0.0` and `S01-CHR-v1.0.0` definitions have not changed.
- PR #74 remains open until reviewed and merged. Stage 01 remains OPEN.

This is execution evidence for a particular implementation revision and CI run, not a claim that the complete Stage 01 has passed its exit gates.
