#!/usr/bin/env python3
"""PR acceptance gate: judge a pull request against the program rules (D-045, report only).

Verdicts: REJECT (a mechanical rule failed), NEEDS_HUMAN (all mechanical rules pass but a judgement remains, or a role is
unassigned or has not approved), APPROVE (everything passes and every required approval is recorded on the current head).
The gate never approves, merges or edits anything; it reports.

  pr_gate.py static --gate gate.json --base origin/main --head HEAD [--json OUT] [--markdown OUT]
      Inside a PR checkout (the GitHub Action). Checks that need only the PR's commits and files.
      Exit 1 only on REJECT; NEEDS_HUMAN and APPROVE-able both exit 0 (the check is "no mechanical violation").
  pr_gate.py remote --manifest repo-pipeline.json --repo REPO --pr N [--json OUT] [--markdown OUT]
      Any repo's PR through `gh`: static rules plus required workflows green on the head SHA and approvals on the head.
      Exit 1 on REJECT, 0 otherwise; the verdict is in the output.
  pr_gate.py export --manifest repo-pipeline.json --repo REPO     print the gate.json for a repository

Rules (ids are stable): R01 commit format, R02 task exists and is open for work, R03 acceptance criteria changed,
R04 protected paths, R05 completion record, R06 required workflows, R07 required approvals, R08 dependencies (info).
Stdlib only. Imports check_commit_format from ../security.
"""
import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "security"))
import check_commit_format as CF  # noqa: E402

PASS, FAIL, HUMAN, INFO, NOTEVAL = "PASS", "FAIL", "NEEDS_HUMAN", "INFO", "NOT_EVALUATED"
OPEN_STATES = ("READY", "IN_PROGRESS", "IN_REVIEW", "CHANGES_REQUESTED")
CLOSED_STATES = ("ACCEPTED", "CANCELLED", "DEFERRED")
SHA = re.compile(r"\b[0-9a-f]{40}\b")


def R(rule, level, msg):
    return {"rule": rule, "level": level, "message": msg}


def task_table(text, prefix):
    """{task_id: status text} from the first two columns of Markdown table rows whose id starts with prefix."""
    out = {}
    for ln in (text or "").splitlines():
        m = re.match(r"^\|\s*(" + re.escape(prefix) + r"-[A-Z0-9-]*\d+)\s*\|(.*)$", ln)
        if m:
            cells = [c.strip() for c in m.group(2).split("|")]
            out[m.group(1)] = cells[1] if len(cells) > 1 else ""
    return out


def state_of(status_text):
    s = status_text.upper()
    for st in CLOSED_STATES + OPEN_STATES + ("NOT_STARTED", "BLOCKED"):
        if re.match(r"^" + st + r"\b", s):
            return st
    return "UNKNOWN"


def static_rules(gate, commits, files, read, registry_note=None):
    """commits: [{sha, message}], files: [{path, status}], read(which, path) -> text|None with which in base/head."""
    res = []
    code, prefix = gate["code"], gate["task_prefix"]
    adopted = (gate.get("commit_standard") or {}).get("adopted", True)
    soft = "" if adopted else "this repository has not adopted the commit standard yet (PD-019): "
    miss = FAIL if adopted else HUMAN
    # R01 commit format and R02 task
    bad, tasks = [], []
    for c in commits:
        probs = CF.problems(c["message"])
        if probs:
            bad.append(f"{c['sha'][:10]}: {'; '.join(probs)}")
        tasks += [(c["sha"], t) for t in CF.task_ids(c["message"])]
    if not commits:
        res.append(R("R01", NOTEVAL, "no commits found for this PR"))
    elif bad:
        res.append(R("R01", miss, soft + "commit format: " + " | ".join(bad)))
    else:
        res.append(R("R01", PASS, f"{len(commits)} commit(s) follow Conventional Commits with one Task footer"))
    ids = sorted({t for _, t in tasks})
    reg = (gate.get("task_registry") or {}).get("type", "repo-tasks-md")
    if not ids and commits and all(CF.declares_none(c["message"]) for c in commits):
        res.append(R("R02", PASS, "every commit declares 'Tasks: None' (docs or chore with a stated reason): no task to check"))
    elif not ids:
        res.append(R("R02", miss if commits else NOTEVAL, soft + "no Task: ID to check"))
    elif reg == "program-baseline":
        b = read("program", "v2/tracking/baseline.json")
        known = {t["id"] for t in json.loads(b)["tasks"]} if b else None
        for t in ids:
            if known is None:
                res.append(R("R02", HUMAN, f"{t}: the program baseline could not be read here, so the task was not checked"))
            elif t in known:
                res.append(R("R02", PASS, f"{t} is a task in the kritva-program baseline"))
            else:
                res.append(R("R02", FAIL, f"{t} is not a task in v2/tracking/baseline.json (kritva-program)"))
    elif reg == "program-inventory":
        b = read("program", "v2/tracking/planning_inventory.json")
        known = ({x["task_id"] for g in json.loads(b)["groups"] if g["repository"] == gate["github_repo"] for x in g.get("tasks", [])} if b else None)
        for t in ids:
            if known is None:
                res.append(R("R02", HUMAN, f"{t}: the planning inventory could not be read here, so the task was not checked"))
            elif t in known:
                res.append(R("R02", HUMAN, f"{t} is registered in the planning inventory (planning only, no credit); the owner decides whether it is started"))
            else:
                res.append(R("R02", FAIL, f"{t} is not in v2/tracking/planning_inventory.json for {gate['github_repo']}"))
    elif reg == "none":
        for t in ids:
            res.append(R("R02", HUMAN, f"{t}: this repository has no machine-readable task registry registered yet (PD-004), so the task was not checked"))
    else:
        base_tasks = task_table(read("base", "planning/TASKS.md"), prefix)
        reg_src = "base"
        if not base_tasks:
            base_tasks, reg_src = task_table(read("head", "planning/TASKS.md"), prefix), "head"
        for t in ids:
            if not t.startswith(prefix + "-"):
                res.append(R("R02", FAIL, f"{t} does not use this repository's task prefix {prefix}"))
            elif t not in base_tasks:
                res.append(R("R02", FAIL, f"{t} is not in planning/TASKS.md ({reg_src} branch)"))
            else:
                st = state_of(base_tasks[t])
                if reg_src == "head":
                    res.append(R("R02", HUMAN, f"{t}: the task registry is created by this PR itself, so it cannot authorise the PR; the owner must approve the task"))
                elif st in CLOSED_STATES:
                    res.append(R("R02", FAIL, f"{t} is {st}: work on a closed task"))
                elif st in OPEN_STATES:
                    res.append(R("R02", PASS, f"{t} exists and is {st}"))
                else:
                    res.append(R("R02", HUMAN, f"{t} is {st or 'UNKNOWN'} ({base_tasks[t][:60]}): the owner must approve or start the task"))
    paths = {f["path"]: f["status"] for f in files}
    # R03 acceptance criteria
    ac = paths.get("ACCEPTANCE_CRITERIA.md")
    if ac is None:
        res.append(R("R03", PASS, "ACCEPTANCE_CRITERIA.md not changed"))
    elif ac == "added":
        res.append(R("R03", HUMAN, "ACCEPTANCE_CRITERIA.md is new: criteria need review before they bind"))
    else:
        res.append(R("R03", HUMAN, f"ACCEPTANCE_CRITERIA.md {ac}: accepted criteria change only through a new version under change control"))
    # R04 protected paths
    hit = sorted(p for p in paths if p != "ACCEPTANCE_CRITERIA.md" and any(p == q or (q.endswith("/") and p.startswith(q)) for q in gate.get("protected_paths", [])))
    res.append(R("R04", HUMAN, "protected paths changed: " + ", ".join(hit)) if hit else R("R04", PASS, "no protected path changed"))
    # R05 completion record
    cr = "COMPLETION_RECORD.md"
    if cr not in paths:
        res.append(R("R05", PASS, "no completion record in this PR"))
    else:
        text = read("head", cr) or ""
        ms = re.findall(r"^\s*Milestone(?: ID)?\s*:\s*(\S+)\s*$", text, re.M | re.I)
        probs = []
        if not ms:
            probs.append("no 'Milestone:' line")
        for m in ms:
            if not re.match(rf"^V2-M[0-8]-{re.escape(code)}-\d{{3}}$", m):
                probs.append(f"milestone {m} is not a V2-Mn-{code}-NNN id")
        if not SHA.search(text):
            probs.append("no 40-hex commit SHA as evidence")
        res.append(R("R05", FAIL, "completion record invalid: " + "; ".join(probs)) if probs else
                   R("R05", HUMAN, f"completion record for {', '.join(ms)} needs the owner's approval; a merge does not close a milestone"))
    return res


def remote_rules(gate, manifest, pr):
    """pr: {author, head_sha, checks: [{workflow, state}], reviews: [{login, state, commit}]}."""
    res = []
    for wf in gate["required_github_checks"]:
        st = [c["state"] for c in pr["checks"] if wf in (c.get("workflow"), c.get("job"))]
        if not st:
            res.append(R("R06", HUMAN if wf == "pr-acceptance-gate" else FAIL, f"required workflow {wf} has no run on head {pr['head_sha'][:7]}" + (" (not rolled out in this repo yet)" if wf == "pr-acceptance-gate" else "")))
        elif all(s == "SUCCESS" for s in st):
            res.append(R("R06", PASS, f"{wf}: SUCCESS on head {pr['head_sha'][:7]}"))
        elif any(s in ("PENDING", "QUEUED", "IN_PROGRESS") for s in st):
            res.append(R("R06", HUMAN, f"{wf} still running"))
        else:
            res.append(R("R06", FAIL, f"{wf}: {', '.join(sorted(set(st)))} (needs SUCCESS)"))
    roles, people = manifest["roles"], manifest.get("people", {})
    for role in gate["required_approvals"]:
        holders = roles[role]["holders"]
        if not holders:
            res.append(R("R07", HUMAN, f"{role} is UNASSIGNED (decision PD-007), so this approval cannot be satisfied"))
            continue
        logins = {people[h]["github_login"] for h in holders if h in people}
        if not logins:
            res.append(R("R07", HUMAN, f"{role}: holders {holders} have no recorded GitHub login"))
            continue
        ok = [r for r in pr["reviews"] if r["login"] in logins and r["state"] == "APPROVED" and r["commit"] == pr["head_sha"]]
        stale = [r for r in pr["reviews"] if r["login"] in logins and r["state"] == "APPROVED" and r["commit"] != pr["head_sha"]]
        if ok:
            res.append(R("R07", PASS, f"{role} approved on the current head"))
        elif pr["author"] in logins and len(logins) == 1:
            res.append(R("R07", HUMAN, f"{role}: the only holder authored this PR and GitHub does not count self-approval; merging needs a ruleset bypass or a second reviewer"))
        else:
            res.append(R("R07", HUMAN, f"{role}: no approval on the current head" + (" (an earlier approval is stale)" if stale else "")))
    deps = gate.get("depends_on", [])
    res.append(R("R08", INFO, f"depends on {', '.join(deps)}; dependency version pins are not recorded yet, so compatibility is not checked" if deps else "no dependencies"))
    return res


def verdict(results):
    lv = {r["level"] for r in results}
    if FAIL in lv:
        return "REJECT"
    if HUMAN in lv or NOTEVAL in lv:
        return "NEEDS_HUMAN"
    return "APPROVE"


def markdown(repo, head, results, mode):
    v = verdict(results)
    L = [f"<!-- pr-acceptance-gate -->", f"## PR acceptance gate: {v} ({mode})", "",
         f"Repository {repo}, head {head[:10] if head else 'unknown'}. Report only: this gate approves, merges and changes nothing. "
         "REJECT means a mechanical rule failed; NEEDS_HUMAN means a judgement or approval remains; APPROVE means every rule passed and every required approval is on the current head.", "",
         "| Rule | Result | Detail |", "|---|---|---|"]
    L += [f"| {r['rule']} | {r['level']} | {r['message'].replace('|', '/')} |" for r in results]
    if mode == "static":
        L += ["", "Required workflows (R06) and approvals (R07) are not evaluated inside the PR run; use `pr_gate.py remote` or `ship-prs.sh` for those."]
    return "\n".join(L) + "\n"


# ---------------- adapters
def sh(*a, check=True):
    r = subprocess.run(a, capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(a[:3])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def local_inputs(base, head):
    commits = []
    for blk in sh("git", "log", "--no-merges", "--format=%H%x00%B%x01", f"{base}..{head}").split("\x01"):
        if blk.strip():
            h, m = blk.lstrip("\n").split("\x00", 1)
            commits.append({"sha": h, "message": m})
    st = {"A": "added", "M": "modified", "D": "removed", "R": "renamed"}
    files = []
    for ln in sh("git", "diff", "--name-status", "--no-renames", f"{base}...{head}").splitlines():
        s, p = ln.split("\t", 1)
        files.append({"path": p, "status": st.get(s[0], "modified")})

    def read(which, path):
        r = subprocess.run(["git", "show", f"{base if which == 'base' else head}:{path}"], capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else None
    return commits, files, read


def remote_inputs(repo, pr, run=sh):
    v = json.loads(run("gh", "pr", "view", str(pr), "-R", repo, "--json", "author,headRefOid,baseRefName,commits,reviews,statusCheckRollup"))
    commits = [{"sha": c["oid"], "message": (c["messageHeadline"] + "\n\n" + c.get("messageBody", "")).rstrip() + "\n"} for c in v["commits"]]
    files = [{"path": f["filename"], "status": f["status"]} for f in json.loads(run("gh", "api", "--paginate", f"repos/{repo}/pulls/{pr}/files"))]
    head, base = v["headRefOid"], v["baseRefName"]

    def read(which, path):
        try:
            if which == "program":
                out = run("gh", "api", f"repos/KritvaOS/kritva-program/contents/{path}?ref=main")
            else:
                out = run("gh", "api", f"repos/{repo}/contents/{path}?ref={base if which == 'base' else head}")
        except RuntimeError:
            return None
        return base64.b64decode(json.loads(out)["content"]).decode("utf-8")
    pr_info = {"author": v["author"]["login"], "head_sha": head,
               "checks": [{"workflow": c.get("workflowName") or c.get("name") or c.get("context"), "job": c.get("name"), "state": c.get("conclusion") or c.get("status") or ""} for c in v["statusCheckRollup"]],
               "reviews": [{"login": r["author"]["login"], "state": r["state"], "commit": (r.get("commit") or {}).get("oid")} for r in v["reviews"]]}
    for c in pr_info["checks"]:
        c["state"] = {"success": "SUCCESS", "failure": "FAILURE", "completed": "SUCCESS"}.get(c["state"].lower(), c["state"].upper())
    return commits, files, read, pr_info


def gate_for(manifest, repo):
    for r in manifest["repositories"]:
        if repo in (r["repo_id"], r["github_repo"]):
            return {"repo_id": r["repo_id"], "github_repo": r["github_repo"], "code": r["code"], "task_prefix": r["task_prefix"], "kind": r["kind"],
                    "depends_on": r["depends_on"], "task_registry": r.get("task_registry", {"type": "repo-tasks-md"}), "commit_standard": r.get("commit_standard", {"adopted": True}), "required_github_checks": r["required_github_checks"], "required_approvals": r["required_approvals"],
                    "protected_paths": r.get("protected_paths", []), "manifest_id": manifest["manifest_id"], "manifest_status": manifest["status"]}
    raise SystemExit(f"unknown repository {repo!r}")


def emit(a, repo, head, results, mode):
    out = {"repo": repo, "head": head, "mode": mode, "verdict": verdict(results), "results": results}
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md = markdown(repo, head, results, mode)
    if a.markdown:
        Path(a.markdown).write_text(md, encoding="utf-8")
    print(md)
    return 1 if out["verdict"] == "REJECT" else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["static", "remote", "export"])
    ap.add_argument("--gate"); ap.add_argument("--base"); ap.add_argument("--head", default="HEAD")
    ap.add_argument("--manifest"); ap.add_argument("--repo"); ap.add_argument("--pr")
    ap.add_argument("--json"); ap.add_argument("--markdown")
    a = ap.parse_args(argv)
    if a.cmd == "static":
        gate = json.loads(Path(a.gate).read_text(encoding="utf-8"))
        commits, files, read = local_inputs(a.base, a.head)
        head = sh("git", "rev-parse", a.head).strip()
        return emit(a, gate["github_repo"], head, static_rules(gate, commits, files, read), "static")
    manifest = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    gate = gate_for(manifest, a.repo)
    if a.cmd == "export":
        print(json.dumps(gate, indent=2, sort_keys=True))
        return 0
    commits, files, read, pr = remote_inputs(gate["github_repo"], a.pr)
    results = static_rules(gate, commits, files, read) + remote_rules(gate, manifest, pr)
    return emit(a, gate["github_repo"], pr["head_sha"], results, "remote")


if __name__ == "__main__":
    sys.exit(main())
