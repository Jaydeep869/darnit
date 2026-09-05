# Experiment 3: Auditing a Real Badged Research Artifact (NDSS'25 `gittuf-ndss-eval`) with Darnit's Reproducibility Plugin

**Date:** 2026-09-05  
**Auditor / Experimenter:** Jaydeep  
**Assisting Agent / MCP Tooling:** Antigravity  
**Repository:** `darnit` (`packages/darnit`, `packages/darnit-reproducibility`)  
**Target:** `experiments/03-ndss-gittuf-eval`  
**Target Repository:** `https://github.com/adityasaky/gittuf-ndss-eval`  
**Target Git Commit:** `3a962352e3a33fbcf2687c2ee75a9051713b2788`  
**Target Zenodo DOI:** [`10.5281/zenodo.14252266`](https://doi.org/10.5281/zenodo.14252266)  
**Associated Paper:** *"Rethinking Trust in Forge-Based Git Security"* (NDSS 2025) by Aditya Sirish (NYU SSL / NJIT), Pat Zielinski (NJIT), et al.  
**Framework:** `reproducibility` v0.1.0  

---

## 1. Executive Summary

Scientific software reproducibility is frequently evaluated in computer systems research through formal **Artifact Evaluation (AE)** processes (e.g., ACM, IEEE, USENIX, and NDSS Artifact Evaluation Committees). When an artifact is awarded badges such as **Artifact Available**, **Artifact Functional**, and **Results Reproduced**, the academic community certifies that the authors provided sufficient documentation, environments, and automated scripts for independent researchers to verify their claims.

In this experiment, we audit a real, award-badged scientific artifact: the official evaluation package for **`gittuf`** (an OpenSSF git-security project) presented at **NDSS 2025**:
- Paper: *"Rethinking Trust in Forge-Based Git Security"*
- Authors: Aditya Sirish (NYU Secure Systems Lab / NJIT), Pat Zielinski, et al.
- Repository: `https://github.com/adityasaky/gittuf-ndss-eval` (Zenodo DOI: `10.5281/zenodo.14252266`).

Unlike synthetic test cases designed to intentionally break or satisfy static rules, this repository was constructed by leading security and software supply-chain researchers specifically to meet real-world scientific reproducibility standards.

### Summary Audit Result:
```text
=== reproducibility Audit Results ===
Total: 5 | Pass: 1 | Fail: 1 | Warn: 3 | N/A: 0
```

### Key Findings & Insights:
1. **The Superficial Pass (False Positive in `repro_build_env_declared`):**
   - Darnit awards a **PASS** (confidence 0.85) to `RE-01.02` (`BuildEnvDeclared`) simply because `Dockerfile` exists in the repository.
   - However, a technical inspection reveals that the Dockerfile begins with `FROM alpine:latest` (an unpinned, floating base image) followed by `RUN apk update && apk add git openssh go python3 py3-click` (unpinned system package installations).
   - Over time, running `docker build` against this Dockerfile will pull differing Alpine Linux releases, differing C standard libraries (`musl`), and differing tool versions, breaking long-term reproducibility. Darnit's check is currently a shallow filename check rather than an environment hygiene parser.
2. **The Partial Failure (`repro_deps_pinned`):**
   - Darnit reports **FAIL** on `RE-01.01` (`DependenciesPinned`) because `requirements.txt` is detected without an accompanying lock file (`uv.lock`, `poetry.lock`, etc.).
   - While `requirements.txt` contains an exact pin (`click==8.1.7`), it lacks cryptographic hash pinning and transitive resolution.
   - Crucially, darnit completely overlooked the primary software under evaluation: `gittuf` itself, which is written in Go and installed dynamically via `RUN go install github.com/gittuf/gittuf@v0.7.0` without any `go.mod` or `go.sum` in the evaluation repository.
3. **The Blind Spot in Hermeticity (`repro_hermetic_build`):**
   - `RE-02.01` reports `WARN` (inconclusive) with 0 violations found.
   - The scanner checked `Dockerfile`, but its internal suspicious patterns tuple (`_SUSPICIOUS_PATTERNS`) contains `pip install`, `npm install`, `curl`, and `wget`, but completely omits `go install`, `go get`, `cargo install`, and `gem install`.
   - Consequently, `RUN go install github.com/gittuf/gittuf@v0.7.0` (which fetches arbitrary Go modules from GitHub and proxy.golang.org over the public internet during image build) was marked as **safe**!
4. **Mismatch Between SLSA/Binary Reproducibility and Scientific Badging:**
   - Darnit’s reproducibility plugin currently models reproducibility through the lens of **Software Supply Chain Security** (SLSA Level 3, Sigstore/Cosign provenance, and bit-for-bit binary determinism via `SOURCE_DATE_EPOCH` / `reprotest`).
   - Academic artifact evaluation operates on an **Empirical & Functional Model** (runnability, testability, environmental isolation via Docker, and archival persistence via Zenodo DOIs).
   - Because academic artifacts rarely publish SLSA GitHub Actions workflows, `RE-02.02` and `RE-03.01` uniformly yield inconclusive `WARN` results, providing zero actionable insight into whether the computational results themselves are reproducible.

---

## 2. Setup & Target Repository Structure

The target repository was cloned directly from GitHub:
```bash
git clone https://github.com/adityasaky/gittuf-ndss-eval experiments/03-ndss-gittuf-eval
```

### 2.1 Git Metadata
- **Commit SHA:** `3a962352e3a33fbcf2687c2ee75a9051713b2788`
- **Commit Date:** 2024-11-30
- **Author:** Pat Zielinski (`70954403+patzielinski@users.noreply.github.com`)
- **Commit Message:** `Add License file`
- **Branch:** `master`

### 2.2 Repository File Tree
```text
experiments/03-ndss-gittuf-eval/
├── Dockerfile                  # Container environment specification (16 lines)
├── LICENSE                     # Apache 2.0 license
├── README.md                   # Comprehensive evaluation walkthrough & instructions
├── experiment1.py              # Test script: Unilateral Policy Modification
├── experiment2.py              # Test script: Delegations
├── experiment3.py              # Test script: RSL Divergence
├── experiment4.py              # Test script: Policy Violation and Independent Verification
├── images/
│   └── ex2-delegations.png    # Architecture diagram of trust delegations
├── keys/                       # Pre-generated cryptographic keys for experiments
│   ├── authorized, authorized.pub
│   ├── developer1, developer1.pub
│   ├── developer2, developer2.pub
│   ├── developer3, developer3.pub
│   ├── root, root.pub
│   ├── targets, targets.pub
│   └── unauthorized, unauthorized.pub
├── requirements.txt            # Python requirements manifest (1 line: click==8.1.7)
└── utils.py                    # Helper routines for running steps and assertions
```

### 2.3 Detailed Inspection of Manifests & Environment Declarations

#### A. Dockerfile (`experiments/03-ndss-gittuf-eval/Dockerfile`)
```dockerfile
FROM alpine:latest

RUN apk update && apk add git openssh go python3 py3-click

WORKDIR /root

ENV PATH="/root/go/bin:$PATH"

RUN go install github.com/gittuf/gittuf@v0.7.0

RUN gittuf version

ADD experiment1.py experiment2.py experiment3.py experiment4.py utils.py /root/

ADD keys /root/keys
```

**Reproducibility Analysis of the Dockerfile:**
- `FROM alpine:latest`: Floating tag. `alpine:latest` points to the newest Alpine image on Docker Hub. Between Alpine 3.19, 3.20, and 3.21, packages and standard libraries change significantly.
- `RUN apk update && apk add ...`: Floating packages. Alpine does not guarantee long-term retention of older package builds in its edge/latest mirrors.
- `RUN go install github.com/gittuf/gittuf@v0.7.0`: Dynamic network compilation at build time. Does not use a `go.sum` lockfile, relying instead on Go's default proxy and tag resolution.
- Hermeticity: Highly non-hermetic build process.

#### B. Python Dependencies (`requirements.txt`)
```text
click==8.1.7
```
- Exactly one dependency is specified with an exact version (`==8.1.7`).
- No hashes (`--hash=sha256:...`) are provided.
- No lockfile (`uv.lock`, `poetry.lock`, `Pipfile.lock`) exists.

#### C. CI / Automation Files
- No `.github/` directory exists.
- No GitLab CI, CircleCI, Jenkinsfile, or Travis CI configurations exist.
- Evaluation is intended to be run interactively or automated locally via Docker or native Python (`python3 experiment1.py --automatic True`).

---

## 3. Darnit Reproducibility Plugin Audit Execution

### 3.1 CLI Invocation & Untruncated Terminal Output

Command:
```bash
uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all
```

**Full Untruncated Terminal Output:**
```text
WARNING: Plugin 'reproducibility' failed verification but will be loaded anyway: Package 'reproducibility' not found
INFO: Discovered implementation: reproducibility v0.1.0
WARNING: Plugin 'hello' failed verification but will be loaded anyway: Package 'hello' not found
INFO: Discovered implementation: hello v0.1.0
WARNING: Plugin 'gittuf' failed verification but will be loaded anyway: Package 'gittuf' not found
INFO: Discovered implementation: gittuf v0.1.0
WARNING: Plugin 'example-hygiene' failed verification but will be loaded anyway: Package 'example-hygiene' not found
INFO: Discovered implementation: example-hygiene v0.1.0
WARNING: Plugin 'openssf-baseline' failed verification but will be loaded anyway: Package 'openssf-baseline' not found
INFO: Discovered implementation: openssf-baseline v0.1.0
INFO: Discovered 5 implementation(s)
WARNING: Running in terminal mode (no LLM consultation). For full capabilities, use 'darnit serve' with an MCP client.
INFO: Discovered 6 framework(s)
INFO: Auditing /home/jd/open_Source/LFX/Ossf/darnit/experiments/03-ndss-gittuf-eval with 5 controls
INFO: Project context for when-clause evaluation: {'platform': 'github', 'languages': [], 'license_type': 'apache-2.0'}

=== reproducibility Audit Results ===

Total: 5 | Pass: 1 | Fail: 1 | Warn: 3 | N/A: 0


--- Failures ---
  ✗ RE-01.01: FAIL - Dependency manifests found but no lock files: requirements.txt (pip requirements)

--- Warnings ---
  ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required

--- Passed (1) ---
  ✓ RE-01.02: PASS - Build environment declared via: Dockerfile (Docker)
```

Exit code: `1` (due to the presence of 1 failure in `RE-01.01`).

---

### 3.2 Full JSON Evidence Output (`-o json`)

Command:
```bash
uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all -o json
```

```json
{
  "framework": "reproducibility",
  "results": [
    {
      "id": "RE-01.02",
      "status": "PASS",
      "details": "Build environment declared via: Dockerfile (Docker)",
      "level": 1,
      "sieve_phase": "deterministic",
      "confidence": 0.85,
      "evidence": {
        "env_files_found": [
          "Dockerfile (Docker)"
        ]
      },
      "resolving_pass_index": 0,
      "resolving_pass_handler": "repro_build_env_declared",
      "authority": "dispositive",
      "pass_history": [
        {
          "phase": "deterministic",
          "checks_performed": [
            "handler:repro_build_env_declared"
          ],
          "result": {
            "outcome": "pass",
            "message": "Build environment declared via: Dockerfile (Docker)",
            "confidence": 0.85
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-02.02",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 2,
      "sieve_phase": "manual",
      "evidence": {
        "files_checked": [],
        "provenance_signals": [],
        "verification_steps": [
          "Check CI workflow for sigstore/cosign signing steps",
          "Look for .intoto.jsonl or attestation files in releases",
          "Verify SLSA provenance is generated (slsa-github-generator or equivalent)"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "pattern",
          "checks_performed": [
            "handler:repro_provenance_exists"
          ],
          "result": {
            "outcome": "inconclusive",
            "message": "No provenance attestation steps found in CI workflows",
            "confidence": 0.0
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": [
            "handler:manual"
          ],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-01.01",
      "status": "FAIL",
      "details": "Dependency manifests found but no lock files: requirements.txt (pip requirements)",
      "level": 1,
      "sieve_phase": "deterministic",
      "evidence": {
        "lock_files_found": [],
        "loose_manifests_found": [
          "requirements.txt (pip requirements)"
        ]
      },
      "resolving_pass_index": 0,
      "resolving_pass_handler": "repro_deps_pinned",
      "authority": "dispositive",
      "pass_history": [
        {
          "phase": "deterministic",
          "checks_performed": [
            "handler:repro_deps_pinned"
          ],
          "result": {
            "outcome": "fail",
            "message": "Dependency manifests found but no lock files: requirements.txt (pip requirements)",
            "confidence": 0.8
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-02.01",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 2,
      "sieve_phase": "manual",
      "evidence": {
        "files_scanned": [
          "Dockerfile"
        ],
        "violations_found": [],
        "deferred_found": [
          "Dockerfile: 'apk add' (image build context)"
        ],
        "strong_signal": null,
        "verification_steps": [
          "Review all CI files (GitHub Actions, GitLab CI, CircleCI, Jenkinsfile, etc.) for network-fetch commands during build",
          "Review Makefiles, build scripts (scripts/build*, scripts/install*), and Dockerfiles for the same",
          "Check for curl, wget, pip install (without --no-index), npm install (without --ci), brew install in build steps",
          "Verify all dependencies come from the lock file, not fetched live at build time",
          "For a PASS without a strong signal, confirm via Witness attestation, Nix flake build, or Bazel network sandbox"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "pattern",
          "checks_performed": [
            "handler:repro_hermetic_build"
          ],
          "result": {
            "outcome": "inconclusive",
            "message": "No suspicious patterns found in 1 scanned file(s) — grep absence alone cannot confirm hermeticity; a strong signal (Witness, Nix, Bazel sandbox) or manual review is needed",
            "confidence": 0.4
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": [
            "handler:manual"
          ],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    },
    {
      "id": "RE-03.01",
      "status": "WARN",
      "details": "Could not automatically verify - manual verification required",
      "level": 3,
      "sieve_phase": "manual",
      "evidence": {
        "files_checked": [],
        "reproducibility_signals": [],
        "verification_steps": [
          "Run the build twice and compare checksums of output artifacts",
          "Check reprotest or diffoscope output if available",
          "Look for timestamps or random seeds embedded in build output",
          "Verify SOURCE_DATE_EPOCH is set in CI to normalize timestamps"
        ]
      },
      "authority": "suggestive",
      "pass_history": [
        {
          "phase": "pattern",
          "checks_performed": [
            "handler:repro_bit_for_bit"
          ],
          "result": {
            "outcome": "inconclusive",
            "message": "No reproducibility signals found — manual verification required",
            "confidence": 0.0
          },
          "duration_ms": 0
        },
        {
          "phase": "manual",
          "checks_performed": [
            "handler:manual"
          ],
          "result": {
            "outcome": "inconclusive",
            "message": "Manual verification required",
            "confidence": null
          },
          "duration_ms": 0
        }
      ]
    }
  ],
  "summary": {
    "total": 5,
    "pass": 1,
    "fail": 1,
    "warn": 3,
    "na": 0
  }
}
```

---

## 4. Evaluation Table

| Control ID | Name | Status | Agree? | Real-world Context & Technical Analysis |
|:---|:---|:---:|:---:|:---|
| **RE-01.01** | `DependenciesPinned` | **FAIL** | **Partially Agree with Status, Disagree with Depth** | **Why FAIL occurred:** `requirements.txt` was detected, but no lockfile (`uv.lock`, `poetry.lock`, etc.) exists. Although `click==8.1.7` is pinned, pip requirements lack hash pinning and transitive locking.<br>**The Major Blind Spot:** Darnit completely missed the primary software component: `gittuf` itself. `gittuf` is installed in the container via `RUN go install github.com/gittuf/gittuf@v0.7.0`. There is no `go.mod` or `go.sum` in this repository. Darnit flagged the minor Python runner wrapper, but completely missed the unpinned Go dependency chain. |
| **RE-01.02** | `BuildEnvDeclared` | **PASS** | **CRITICAL DISAGREE (False Positive)** | **Why PASS occurred:** Darnit saw a file named `Dockerfile` and instantly marked the control as `PASS` with 0.85 confidence.<br>**Why it is a False Positive:** The Dockerfile uses `FROM alpine:latest` and `RUN apk update && apk add git openssh go python3 py3-click`. Floating base images and unversioned package manager installs violate the core definition of a declared, reproducible build environment. Over time, Alpine repository updates will alter the underlying libc, compiler, and utilities. |
| **RE-02.01** | `HermeticBuild` | **WARN** | **Disagree with Analysis (False Negative)** | **Why WARN occurred:** Darnit found `0` violations in `Dockerfile` and fell back to `WARN` because no "strong signal" (Nix, Bazel sandbox, Witness) was detected.<br>**Why it is a False Negative:** The Dockerfile runs `go install github.com/gittuf/gittuf@v0.7.0`, which downloads binaries/modules over the public internet during the build. Darnit’s `_SUSPICIOUS_PATTERNS` only checks for `curl`, `wget`, `pip install`, `npm install`, and `apt-get install`, omitting `go install`, `go get`, and `cargo install`. |
| **RE-02.02** | `ProvenanceExists` | **WARN** | **Agree with Status, Disagree with Conceptual Model** | **Why WARN occurred:** Checks exclusively for GitHub Actions CI workflows containing Sigstore, Cosign, or SLSA provenance attestations. None were found, leading to `INCONCLUSIVE` (WARN).<br>**Academic Context:** Scientific research artifacts are published to Zenodo with persistent digital object identifiers (DOIs), metadata records, and cryptographic archive hashes. Darnit has no awareness of Zenodo, OSF, or academic provenance mechanisms. |
| **RE-03.01** | `BitForBitReproducible` | **WARN** | **Agree with Status, Disagree with Conceptual Model** | **Why WARN occurred:** Searches CI workflows for `SOURCE_DATE_EPOCH`, `reprotest`, or `diffoscope`. Finding none, it reports `INCONCLUSIVE` (WARN).<br>**Academic Context:** NDSS and ACM badging evaluate **experimental and computational repeatability** (functional equivalence of outputs across trials), not supply-chain binary bit-for-bit equality of executables. |

---

## 5. In-Depth Comparative Analysis

### 5.1 What Did Darnit Accurately Catch?
1. **Absence of Modern Python Lock Files:**
   Darnit correctly identified that `requirements.txt` is an unlocked manifest. In Python ecosystems, `requirements.txt` alone does not prevent downstream breakage caused by transitive dependency updates (e.g. if `click` had unpinned sub-dependencies).
2. **Absence of Continuous Integration Pipelines:**
   Darnit accurately recognized that no GitHub Actions or CI workflows exist in this repository, correctly preventing false positives on CI-based provenance or automated testing controls.
3. **Detection of the Docker Containerization File:**
   Darnit identified that the repository provides a `Dockerfile` intended to configure the environment.

---

### 5.2 What False Positives Occurred?

#### The `repro_build_env_declared` False Positive:
Control `RE-01.02` is titled *"Build environment is explicitly declared"*.

In `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`:
```python
def repro_build_env_declared_handler(config, ctx):
    env_files = {
        "Dockerfile": "Docker",
        "flake.nix": "Nix flake",
        ...
    }
    found = [f"{filename} ({label})" for filename, label in env_files.items() if (path / filename).exists()]
    if found:
        return HandlerResult(status=HandlerResultStatus.PASS, message=f"Build environment declared via: {', '.join(found)}", confidence=0.85)
```

**The Fatal Flaw:**
The handler performs **zero semantic inspection of the file content**. 
- In `gittuf-ndss-eval/Dockerfile`:
  ```dockerfile
  FROM alpine:latest
  RUN apk update && apk add git openssh go python3 py3-click
  ```
- Line 1 uses `latest`.
- Line 3 runs `apk update` and installs unpinned packages.
- When an evaluator runs `docker build` today versus two years from now, Alpine Linux will have moved from version 3.20 to 3.22+, `git` will have upgraded, and `go` will have upgraded. In fact, if Alpine removes deprecated packages or changes ABI behavior, the build will fail entirely.
- By awarding a **PASS (confidence 0.85)**, darnit creates a **dangerous false sense of security**: it marks a demonstrably unpinned, mutable build environment as compliant.

---

### 5.3 What False Negatives Occurred?

#### 1. The `repro_hermetic_build` Network Fetch Miss:
`repro_hermetic_build_handler` in `handlers.py` attempts to identify live network fetches during build steps.
Lines 153–162:
```python
_SUSPICIOUS_PATTERNS: tuple[str, ...] = (
    "curl ",
    "wget ",
    "pip install ",
    "npm install",
    "yarn install",
    "apt-get install",
    "brew install",
)
```
In `gittuf-ndss-eval/Dockerfile`:
```dockerfile
RUN go install github.com/gittuf/gittuf@v0.7.0
```
- `go install` contacts the internet, downloads Git repositories and Go module zip files from proxy.golang.org or GitHub, and compiles them into `/root/go/bin`.
- Because `"go install "` is omitted from `_SUSPICIOUS_PATTERNS`, darnit classified this line as **safe**!
- Furthermore, `cargo install`, `gem install`, `pipx install`, and `cpm install` are similarly missing from `_SUSPICIOUS_PATTERNS`.

#### 2. The Uninspected Go Dependency Ecosystem:
- The core artifact under test in the NDSS paper is `gittuf`.
- Darnit’s `repro_deps_pinned_handler` checks for `go.sum` and `go.mod`.
- Because neither exists in `experiments/03-ndss-gittuf-eval`, darnit concluded that only `requirements.txt` existed.
- Darnit has no cross-file awareness connecting the build steps in `Dockerfile` to the missing dependency declarations.

---

### 5.4 Does Darnit's Check Model Align with Real-World Scientific Artifact Badging?

The Association for Computing Machinery (ACM) and major security symposiums (NDSS, USENIX Security, IEEE S&P) employ standardized Artifact Review and Badging guidelines:

| Badging Category | ACM / NDSS AE Criteria | Darnit Check Equivalent | Alignment Assessment |
|:---|:---|:---|:---|
| **Artifact Available** | Author-hosted or archived on Zenodo, Figshare, Dryad, or Software Heritage with a permanent DOI. | `repro_provenance_exists` (`RE-02.02`) | **MISALIGNED:** Darnit only searches for Sigstore/Cosign and SLSA in GitHub Actions. It ignores Zenodo DOIs, `.zenodo.json`, and `CITATION.cff`. |
| **Artifact Functional** | Documented, consistent, complete, and exercisable. Evaluator can run test scripts and obtain expected outputs without fatal crashes. | `repro_build_env_declared` (`RE-01.02`), `repro_deps_pinned` (`RE-01.01`) | **PARTIALLY ALIGNED, SHALLOW:** Darnit checks for file names (e.g. `Dockerfile`), but cannot test runnability or execution semantics. |
| **Results Reproduced** | The main experimental results reported in the paper have been independently produced by the reviewers. | `repro_bit_for_bit` (`RE-03.01`) | **FUNDAMENTALLY MISALIGNED:** Academic reproducibility measures *statistical, algorithmic, and functional consistency* (e.g., verifying that Experiment 1 blocks unauthorized policy modifications). Darnit checks for *cryptographic byte-for-byte binary determinism* (`SOURCE_DATE_EPOCH`, `diffoscope`). |

#### The Ontological Divide:
1. **Supply-Chain Determinism (Darnit's Paradigm):**
   Originating from reproducible-builds.org and SLSA (Google / OpenSSF), this model is designed for software distributions (Debian, Tor, Android). Its goal is to prove that binary packages match source code without vendor compromise.
2. **Empirical Scientific Reproducibility (NDSS/ACM's Paradigm):**
   Originating from scientific methodology, its goal is to prove that scientific claims are valid, repeatable, and robust against environmental variation. A paper evaluation artifact is not a production software distribution; it is an experimental apparatus.

When darnit evaluates an academic repository like `gittuf-ndss-eval`, it applies the rigid rules of supply-chain binary verification to an experimental test harness, failing on the wrong criteria and passing on superficial signals.

---

## 6. Repo Hygiene & Repeatability Logs

### 6.1 Repo Hygiene (`git status --porcelain`)

We verified whether `darnit audit` leaves any temporary files, cached configs, or artifacts in the target directory or workspace.

#### Workspace Root Status:
```bash
$ git status --porcelain experiments/03-ndss-gittuf-eval
?? experiments/03-ndss-gittuf-eval/
```

#### Inside `experiments/03-ndss-gittuf-eval`:
```bash
$ git status --porcelain
(Clean - no output)
```

After multiple runs of `darnit audit` (both human-readable and JSON format), `git status --porcelain` remained completely clean. **Hygiene is verified.**

---

### 6.2 Audit Idempotency (3 Consecutive Runs)

We ran 3 consecutive audits on the unchanged target repository to evaluate determinism and output stability.

#### Trial 1: Standard Invocations (Randomized Python Hash Seed)
```bash
uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all > /tmp/audit_e3_run1.txt 2>&1
uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all > /tmp/audit_e3_run2.txt 2>&1
uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all > /tmp/audit_e3_run3.txt 2>&1

diff -u /tmp/audit_e3_run1.txt /tmp/audit_e3_run2.txt
diff -u /tmp/audit_e3_run2.txt /tmp/audit_e3_run3.txt
```

**Diff Output Across Runs:**
```diff
--- /tmp/audit_e3_run1.txt
+++ /tmp/audit_e3_run2.txt
@@ -23,8 +23,8 @@
   ✗ RE-01.01: FAIL - Dependency manifests found but no lock files: requirements.txt (pip requirements)
 
 --- Warnings ---
-  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
 
 --- Passed (1) ---

--- /tmp/audit_e3_run2.txt
+++ /tmp/audit_e3_run3.txt
@@ -23,9 +23,9 @@
   ✗ RE-01.01: FAIL - Dependency manifests found but no lock files: requirements.txt (pip requirements)
 
 --- Warnings ---
-  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
-  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
   ⚠ RE-02.02: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-03.01: WARN - Could not automatically verify - manual verification required
+  ⚠ RE-02.01: WARN - Could not automatically verify - manual verification required
 
 --- Passed (1) ---
   ✓ RE-01.02: PASS - Build environment declared via: Dockerfile (Docker)
```

**Analysis:**
This reconfirms **Bug Report #2 from Experiments 1 and 2**:
In `packages/darnit/src/darnit/config/merger.py:424`, controls are aggregated using Python `set` iteration without sorting by `control_id`. Under standard Python hash randomization, the warning order changes pseudo-randomly between consecutive runs on identical files.

#### Trial 2: Deterministic Hash Seed (`PYTHONHASHSEED=0`)
```bash
PYTHONHASHSEED=0 uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all > /tmp/audit_e3_seed1.txt 2>&1
PYTHONHASHSEED=0 uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all > /tmp/audit_e3_seed2.txt 2>&1
PYTHONHASHSEED=0 uv run darnit audit experiments/03-ndss-gittuf-eval --framework reproducibility --show-all > /tmp/audit_e3_seed3.txt 2>&1

diff -u /tmp/audit_e3_seed1.txt /tmp/audit_e3_seed2.txt && diff -u /tmp/audit_e3_seed2.txt /tmp/audit_e3_seed3.txt
```

**Diff Output:**
```text
(0 differences — 100% byte-for-byte identical across runs)
```

---

## 7. Upstream Bug Reports & Feature Recommendations

### Bug Report 7: `repro_build_env_declared` false positive on unpinned Docker base images (`:latest`) and floating package installations

```markdown
### Summary
`repro_build_env_declared` awards `PASS` (confidence 0.85) if a `Dockerfile` exists, regardless of whether the base image is pinned to a digest or specific release, and regardless of whether packages installed in the Dockerfile are unversioned (`apk add`, `apt-get install`).

### Environment
- darnit version: dev / main branch
- Plugin: `darnit-reproducibility` v0.1.0
- Target: Repositories with Dockerfiles using floating tags (e.g. `FROM alpine:latest`)

### Steps to Reproduce
1. Create a minimal `Dockerfile`:
   ```dockerfile
   FROM alpine:latest
   RUN apk update && apk add git
   ```
2. Run `darnit audit . --framework reproducibility --show-all`.

### Expected Behavior
`repro_build_env_declared` should either:
- Downgrade the result to `WARN` or `FAIL` because the base image tag is floating (`latest`) and packages are unpinned.
- Or provide a distinct check / lower confidence score indicating that while a Dockerfile exists, the build environment itself is mutable and non-pinned.

### Actual Behavior
The control passes with high confidence:
```text
✓ RE-01.02: PASS - Build environment declared via: Dockerfile (Docker)
```
Evidence records only: `env_files_found: ["Dockerfile (Docker)"]`.

### Proposed Fix
In `repro_build_env_declared_handler`:
1. Parse the `FROM` directive in Dockerfiles.
2. If the tag is `latest`, missing, or unpinned to a specific version or `@sha256:...` digest, flag it as unpinned.
3. Check if package management commands (`apt-get`, `apk`, `yum`, `dnf`) install packages without pinned versions.
```

---

### Bug Report 8: `repro_hermetic_build` misses language package installers (`go install`, `cargo install`, `gem install`)

```markdown
### Summary
`_SUSPICIOUS_PATTERNS` in `repro_hermetic_build_handler` only inspects for `curl`, `wget`, `pip install`, `npm install`, `yarn install`, `apt-get install`, and `brew install`. It completely ignores standard package and binary installers for other major ecosystems:
- Go (`go install`, `go get`)
- Rust (`cargo install`, `cargo binstall`)
- Ruby (`gem install`)
- Python (`pipx install`)

### Environment
- darnit version: dev / main branch
- Plugin: `darnit-reproducibility` v0.1.0

### Steps to Reproduce
1. Create a `Dockerfile` containing:
   ```dockerfile
   FROM golang:1.22
   RUN go install github.com/gittuf/gittuf@v0.7.0
   ```
2. Run `darnit audit . --framework reproducibility --show-all`.

### Expected Behavior
`repro_hermetic_build` should detect that `go install github.com/...` fetches dependencies over the public network during the build step and flag a violation or deferred warning.

### Actual Behavior
`repro_hermetic_build` reports:
```text
"No suspicious patterns found in 1 scanned file(s)"
```
`violations_found` is empty.

### Proposed Fix
Extend `_SUSPICIOUS_PATTERNS` in `packages/darnit-reproducibility/src/darnit_reproducibility/handlers.py`:
```python
_SUSPICIOUS_PATTERNS: tuple[str, ...] = (
    "curl ",
    "wget ",
    "pip install ",
    "pipx install ",
    "npm install",
    "yarn install",
    "apt-get install",
    "brew install",
    "go install ",
    "go get ",
    "cargo install ",
    "gem install ",
)
```
```

---

### Feature Recommendation: Scientific Artifact Evaluation (AE) Framework Support

```markdown
### Problem Statement
Darnit currently conflates *Software Supply Chain Security* (SLSA, Cosign, bit-for-bit binary determinism) with *Scientific Computational Reproducibility*. When academic repositories badged for reproducibility (e.g. by ACM, NDSS, IEEE, USENIX) are evaluated with darnit, they receive poor or misleading ratings because academic artifacts prioritize:
1. Long-term archival persistence (Zenodo DOIs, Software Heritage IDs).
2. Automation and execution test harnesses (`experiment*.py`, test suites).
3. Documentation and reproducible results replication, rather than signed SLSA provenance workflows.

### Proposed Enhancement: `reproducibility-academic` Framework
Introduce an academic/scientific profile or framework extension with controls tailored to scientific computing:
1. `RE-ACAD-01` (`ArchivalDOI`): Verify the presence of a Zenodo DOI, Figshare DOI, or Software Heritage SWHID in `README.md` or `.zenodo.json` / `CITATION.cff`.
2. `RE-ACAD-02` (`ContainerPinning`): Audit Dockerfiles specifically for immutable base image digests (`@sha256:...`) and pinned package manager versions.
3. `RE-ACAD-03` (`AutomatedExecutionHarness`): Check for non-interactive test run capabilities (e.g. CLI flags like `--automatic` or Makefile test targets).
4. `RE-ACAD-04` (`RandomSeedDeclared`): Scan scripts for deterministic pseudo-random number generator seeding.
```
