"""Pre-registration provenance (decision D1): what can and cannot be checked about the order of plan and runs.

Writes docs/preregistration_provenance.json from git and the run logs, plus the GitHub activity record of the first
upload (fetched once with the gh CLI and kept in the JSON, because the repository is private and the record cannot be
re-fetched by a reader). Fails closed if a run log does not name the pre-registration commit, if a pre-registration
commit is not an ancestor of the first uploaded commit, or if the first upload is not after both pre-registrations.

  python scripts/prereg_provenance.py [--refresh-github]
"""
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "preregistration_provenance.json"
PREREG = {"thickness-only": ("docs/PaperA_preregistration.md", "1bdbecc"),
          "material-choice": ("docs/PaperB_preregistration.md", "2b32a78")}
AMEND = ["776401b", "0adafae"]                      # material-choice amendments named in the run-log file names


def git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], check=True, capture_output=True, text=True).stdout.strip()


def commit(h):
    full, date, subj = git("log", "-1", "--format=%H%x09%ad%x09%s", "--date=iso-strict", h).split("\t", 2)
    return {"hash": full, "date": date, "subject": subj[:200]}


def ancestor(a, b):
    return subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", a, b]).returncode == 0


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    if "--refresh-github" in sys.argv or "github_first_upload" not in old:
        raw = subprocess.run(["gh", "api", "repos/havidaqoma/PEROdesign/activity?per_page=100&direction=asc"],
                             check=True, capture_output=True, text=True).stdout
        first = json.loads(raw)[0]
        gh = {"source": "GitHub REST API repos/{owner}/{repo}/activity (private repository; record kept here)",
              "retrieved": datetime.now().astimezone().isoformat(timespec="seconds"),
              "timestamp": first["timestamp"], "activity_type": first["activity_type"], "ref": first["ref"],
              "after": first["after"]}
    else:
        gh = old["github_first_upload"]
    pre = {}
    for lvl, (f, h) in PREREG.items():
        c = commit(h)
        if f not in git("show", "--name-only", "--format=", c["hash"]).splitlines():
            raise SystemExit(f"{h} does not add or change {f}")
        if not ancestor(c["hash"], gh["after"]):
            raise SystemExit(f"{h} is not an ancestor of the first uploaded commit {gh['after']}")
        pre[lvl] = {"file": f, **c}
    log_a = (REPO / "phase0" / "paperA" / "run.log").read_text(encoding="utf-8", errors="replace").splitlines()[0]
    m = re.match(r"=== PAPERA RUN (\S+) .* commit (\w+)", log_a)
    if not m or not pre["thickness-only"]["hash"].startswith(m.group(2)):
        raise SystemExit(f"thickness-only run log does not name the pre-registration commit: {log_a!r}")
    runs = {"thickness-only": {"log": "phase0/paperA/run.log", "started": m.group(1), "commit": m.group(2)}}
    logs = sorted(p.name for p in (REPO / "phase0" / "paperB" / "logs").glob("paperB_run_attempt*_*.log"))
    named = [re.search(r"_(\w{7})\.log$", n).group(1) for n in logs]
    if not named or named[0] != PREREG["material-choice"][1] or named[1:] != AMEND:
        raise SystemExit(f"material-choice run logs do not start from the pre-registration commit: {logs}")
    for h in AMEND:
        if not ancestor(pre["material-choice"]["hash"], h):
            raise SystemExit(f"amendment {h} does not descend from the pre-registration")
    runs["material-choice"] = {"logs": ["phase0/paperB/logs/" + n for n in logs],
                               "commits": [commit(h) for h in named]}
    upload = datetime.fromisoformat(gh["timestamp"].replace("Z", "+00:00"))
    for lvl, c in pre.items():
        if not datetime.fromisoformat(c["date"]) < upload:
            raise SystemExit(f"{lvl} pre-registration is not before the first upload")
    out = {"schema": "perodesign.prereg_provenance/v1",
           "what_can_be_checked": "Order of plan, amendments and runs through the git parent chain (each commit holds "
                                  "its parent's hash) and the run logs, which name the commit each run started from.",
           "what_cannot": "Absolute dates before the first upload rest on git commit dates in a then-private "
                          "repository; the first independent time stamp is the GitHub upload below, after the runs began.",
           "preregistration": pre, "runs": runs, "github_first_upload": gh}
    OUT.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: (v["date"] if "date" in v else v) for k, v in pre.items()}), gh["timestamp"])


if __name__ == "__main__":
    main()
