# AGENTS.md

Place this file at the repository root. Read it before planning, coding, refactoring, moving files, or running broad automated edits.

This is a root-only, single-file operating standard for Codex. It is designed to be usable without extra docs or helper scripts.

---

## 1. Startup rule

At the start of every task:

1. Read this file fully.
2. State the task in one sentence.
3. State assumptions explicitly.
4. Name ambiguity instead of guessing.
5. Choose the smallest viable plan.
6. Touch only the code required for the task.
7. Verify with the cheapest meaningful check.

Do not silently choose an interpretation when the request is ambiguous.
Do not let repo tooling side quests overtake the requested task.

---

## 2. Core operating principles

### Think before coding

- Do not make silent assumptions.
- If multiple interpretations exist, surface them and choose deliberately.
- If a simpler approach exists, say so.
- If something is unclear, stop and resolve the confusion before broad edits.
- Push back on heavy solutions that do not match the size of the problem.

### Simplicity first

- Write the minimum code that fully solves the task.
- No speculative abstractions.
- No extra flags, config layers, generic wrappers, or extension points unless requested.
- No bloated APIs for one-off needs.
- If 200 lines can be 50 without losing clarity, prefer 50.
- Code should be understandable in one pass.

### Surgical changes

- Touch only files and lines required by the task.
- Do not refactor adjacent code unless the task requires it.
- Do not delete unrelated dead code, comments, or formatting.
- Match the existing repository style unless the task explicitly asks for a broader cleanup.
- Remove only the unused code created by your own changes.
- Every changed line should trace directly to the request.

### Goal-driven execution

- Translate the request into concrete success criteria.
- For bug fixes, reproduce first when cheap, then verify the fix.
- For refactors, verify behavior before and after.
- Prefer tests, builds, lint, typecheck, focused script runs, or the smallest useful manual check.
- Do not stop at “probably fixed” if verification is cheap.

---

## 3. Code quality standard

- Keep code concise.
- Avoid maintenance-heavy designs.
- Favor direct data flow over clever indirection.
- Prefer small functions with direct names.
- Prefer composition over deep inheritance.
- Prefer plain, boring, high-leverage code over elaborate frameworks.
- Leave comments only where the code would otherwise be non-obvious.
- Do not rewrite comments outside the task scope.
- Avoid code that will obviously grow into a mess later.
- When choosing between readability and cleverness, choose readability.

### Hard anti-bloat rules

Do not introduce any of the following unless explicitly justified by the task:

- generic framework layers for a single use case
- abstract base classes for one implementation
- config systems for behavior that will never vary
- defensive handling for impossible states with no evidence they occur
- wrappers around stable library APIs with no meaningful simplification
- premature plugin systems, hook systems, or strategy registries

---

## 4. Technology selection standard

Use modern, efficient, well-supported technology, but stay pragmatic.

### Prefer

- tools already used by the repository
- mature libraries with strong ecosystem support
- choices that reduce code, improve correctness, improve performance, or improve developer speed
- modern language and framework features that are stable and widely supported
- solutions that fit the current stack and deployment model

### Avoid

- choosing tools only because they are trendy
- introducing a new dependency without a concrete payoff
- stack drift that makes the codebase more fragmented
- replacing working infrastructure just to be “more advanced”
- novelty that increases cognitive load or operational risk

### Decision rule

When two options are both viable, choose the one with:

1. lower complexity
2. stronger ecosystem support
3. less code
4. easier maintenance
5. better fit with the existing repository

---

## 5. Encoding and Chinese text safety standard

Use UTF-8 as the default for text and source files unless an external requirement explicitly demands another encoding.

### Baseline rules

- Default text encoding: UTF-8
- Default line endings: LF unless a tool explicitly requires something else
- For Python and similar languages, use explicit `encoding="utf-8"` for text reads and writes
- Do not silently convert ambiguous non-UTF files
- Do not mass re-save text files with unknown editor defaults
- Treat any file containing Chinese literals, templates, prompts, or docs as high-risk text

### Safe Python examples

```python
from pathlib import Path

text = Path("notes.txt").read_text(encoding="utf-8")
Path("out.txt").write_text(text, encoding="utf-8", newline="\n")
```

```python
with open("data.json", "r", encoding="utf-8") as f:
    payload = f.read()
```

### Avoid

```python
with open("data.json", "r") as f:
    payload = f.read()
```

### Required preflight conditions

Run an encoding preflight before:

- high-risk text rewrites
- Chinese text edits
- prompt changes
- generator changes
- bulk automated edits
- migrations that rewrite many text files

Do not run broad scans for normal, low-risk feature edits unless needed.

### Built-in encoding scan command

If a preflight scan is needed, run this from the repository root:

```bash
python - <<'PY'
from __future__ import annotations
from pathlib import Path
import json

IGNORE_DIRS = {
    '.git', '.hg', '.svn', '.idea', '.vscode', '.venv', 'venv', 'env',
    'node_modules', 'dist', 'build', 'coverage', '__pycache__', '.next',
    '.nuxt', '.turbo', '.cache', '.pytest_cache', '.mypy_cache',
    '.runtime', '.codex-runlogs'
}
TEXT_EXTS = {
    '.py', '.md', '.txt', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg',
    '.js', '.jsx', '.ts', '.tsx', '.css', '.scss', '.html', '.xml', '.csv',
    '.sh', '.bash', '.zsh', '.ps1', '.java', '.go', '.rs', '.c', '.cpp',
    '.h', '.hpp', '.swift', '.kt', '.rb', '.php', '.vue', '.sql'
}
root = Path('.')
report = {'utf8_ok': [], 'utf8_bom': [], 'non_utf8_or_binary': [], 'skipped': []}
for path in root.rglob('*'):
    try:
        if path.is_dir():
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            report['skipped'].append({'path': str(path), 'reason': 'ignored_dir'})
            continue
        if path.suffix.lower() not in TEXT_EXTS:
            continue
        data = path.read_bytes()
        if data.startswith(b'\xef\xbb\xbf'):
            report['utf8_bom'].append(str(path))
            continue
        try:
            data.decode('utf-8')
            report['utf8_ok'].append(str(path))
        except UnicodeDecodeError:
            report['non_utf8_or_binary'].append(str(path))
    except (PermissionError, OSError) as e:
        report['skipped'].append({'path': str(path), 'reason': type(e).__name__})
print(json.dumps(report, ensure_ascii=False, indent=2))
PY
```

### If the scan fails or gets noisy

- Narrow scope first.
- Skip runtime sandboxes, logs, generated caches, and permission-restricted paths.
- Do not detour into fixing the scan logic unless that directly blocks the requested task.
- If the task is not high-risk text work, continue the requested work instead of turning tooling into the main task.

### Safe remediation order

1. Scan before converting anything.
2. Separate UTF-8 files, BOM files, and ambiguous files.
3. Convert only files whose current encoding is known.
4. For ambiguous files, stop and decide deliberately.
5. After a real recurring issue, add a durable rule in this file.

### Special Git note

Do not use `working-tree-encoding` as the default fix for normal mojibake problems.
Use it only when a file must remain non-UTF in the working tree and the team tooling is known to support it.

---

## 6. Repository structure awareness

Before large edits, refactors, file moves, or dependency changes, first build a local map of the repository.

At minimum, identify:

- top-level applications, services, or packages
- entrypoints
- important scripts and tooling
- generated directories and build outputs
- areas that contain Chinese text, templates, prompts, or i18n assets
- legacy files with uncertain encoding
- test and validation commands
- current stack boundaries and approved technology choices

### Lightweight repo map template

Use this template mentally or paste it into your working notes before large structural work:

```text
Top-level directories:
- 

Entrypoints:
- 

Important tooling/scripts:
- 

Risk zones:
- files containing Chinese literals or templates
- generators that emit source files
- import/export scripts that read or write text
- legacy files with unknown encoding

Validation commands:
- 

Tech boundaries:
- preferred frameworks/libraries already in use
- areas where new dependencies need extra scrutiny
- performance-sensitive paths
```

Do not move files or reshape structure blindly.

---

## 7. Failure memory and self-improvement rule

The goal is not unconstrained self-learning. The goal is repository-persistent learning.

Codex should improve by turning repeated failures into durable repository rules.

### Promotion rule

When a mistake repeats:

1. record it in the failure ledger section of this file
2. summarize it into a standing rule if it is broadly recurring
3. add a cheap verification step when feasible
4. prefer a repo-persistent guard over relying on chat memory

### Anti-patterns

Avoid these:

- keeping lessons only in transient conversation history
- vague rules such as “be careful with encoding”
- broad tooling repairs as a side quest unrelated to the requested task
- giant rewrites of uncertain files
- silently changing code or comments that were not part of the task
- adding complex abstractions because they feel more “agentic”

---

## 8. Default execution pattern

For most tasks, follow this loop:

1. Restate the request and assumptions.
2. Identify ambiguity and tradeoffs.
3. Choose the smallest viable implementation.
4. Read only the directly relevant files.
5. Make surgical edits.
6. Run the cheapest meaningful verification.
7. If a repeated mistake was discovered, update the failure ledger in this file.

For bug fixes, prefer:

1. reproduce
2. patch narrowly
3. verify
4. record durable lesson if recurring

For refactors, prefer:

1. define invariant behavior
2. edit narrowly
3. verify before and after
4. avoid opportunistic cleanup outside scope

---

## 9. Failure ledger

Append new entries here when a mistake repeats or exposes a durable repository rule.

Use this structure:

```text
## YYYY-MM-DD - short title
- symptom:
- trigger:
- impacted files:
- root cause:
- permanent rule:
- regression check:
- status: active
```

### Active entries

## 2026-04-23 - chinese text became mojibake in generated python files
- symptom: chinese literals rendered as garbled characters after automated edits
- trigger: files were rewritten while relying on platform-default text encoding
- impacted files: source files, scripts, generated templates, prompt files
- root cause: text I/O omitted explicit UTF-8 and the repository lacked durable guardrails
- permanent rule: all text reads and writes must specify `encoding="utf-8"`; run the encoding preflight before bulk rewrites or generator changes involving text
- regression check: run the built-in encoding scan in section 5 and inspect generators for explicit UTF-8 I/O
- status: active

## 2026-04-23 - guard tooling detoured the main task
- symptom: the requested work paused while the agent repaired repository tooling
- trigger: a broad preflight scan hit runtime or permission-restricted paths and failed noisily
- impacted files: tooling only; main feature work was delayed
- root cause: the preflight rule was treated as unconditional and failure handling was underspecified
- permanent rule: broad scans are only required for high-risk text work; if a scan fails because of unrelated runtime noise, narrow scope or skip noisy paths instead of turning tooling repair into the main task unless that repair is necessary to unblock the request
- regression check: if a preflight scan fails, first rerun on a narrower scope and continue the requested task when safe
- status: active

---

## 10. First instruction to give Codex

Use this exact prompt if needed:

```text
Read the repository root AGENTS.md first and follow it strictly. Keep the solution concise, avoid unnecessary abstractions, and prefer the simplest modern, efficient approach that fits the existing stack. Make surgical edits only. Before high-risk text rewrites, Chinese text changes, prompt updates, or generator changes, run the built-in encoding preflight from AGENTS.md. If that scan hits unrelated runtime or permission noise, narrow or skip those paths instead of detouring into tooling fixes. If you discover a repeated mistake, record it in the failure ledger inside AGENTS.md and promote it into a standing rule when appropriate.
```
