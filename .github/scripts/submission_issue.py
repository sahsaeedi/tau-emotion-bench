"""Check or accept a leaderboard submission issue (.github/workflows/submission-*.yml).

    python .github/scripts/submission_issue.py check
    python .github/scripts/submission_issue.py accept

It reads the issue from the workflow's event (GITHUB_EVENT_PATH) and talks to
GitHub with the gh CLI (GH_TOKEN). `check` validates the submission against the
attached trajectories and comments the result; `accept` adds the submission to
submissions/, puts its trajectories on the `submissions` release, and closes the
issue. The issue body comes from the submitter, so it is only parsed, never run.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from tau_emotion.scripts.submission import (
    REQUIRED_USER_LLM,
    Submission,
    check_submission,
    load_results,
    submission_id,
    with_task_results,
    write_leaderboard,
    write_trajectories,
)

MARKER = "<!-- submission-check -->"
RELEASE = "submissions"
MAX_DOWNLOAD = 2_000_000_000
LABELS = {
    "submission": ("1d76db", "Leaderboard submission"),
    "valid": ("0e8a16", "The submission check passed"),
    "needs-changes": ("d93f0b", "The submission check found problems"),
    "accepted": ("5319e7", "Added to the leaderboard"),
}
ATTACHMENT = re.compile(r"https://github\.com/user-attachments/files/\d+/[^\s)\]]+")


def parse_form(body: str) -> dict[str, str]:
    """The issue form's answers by field label; empty when left blank."""
    fields = {}
    for section in re.split(r"^### ", body or "", flags=re.M)[1:]:
        label, _, value = section.partition("\n")
        value = value.strip()
        fields[label.strip()] = "" if value == "_No response_" else value
    return fields


def submission_json(fields: dict[str, str]) -> str:
    text = fields.get("submission.json", "")
    if match := re.search(r"```(?:json)?\s*\n(.*?)\n\s*```", text, flags=re.S):
        return match.group(1)
    return text


def trajectory_urls(fields: dict[str, str]) -> list[str]:
    urls = ATTACHMENT.findall(fields.get("Trajectories", ""))
    link = fields.get("Trajectories link", "").strip()
    if link:
        urls.append(link)
    return urls


def download(urls: list[str], directory: Path) -> list[str]:
    paths = []
    for i, url in enumerate(urls, 1):
        path = directory / f"trajectories-{i}.zip"
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            size = 0
            with open(path, "wb") as f:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise ValueError(f"{url} is over {MAX_DOWNLOAD:,} bytes")
                    f.write(chunk)
        paths.append(str(path))
    return paths


def gh(*args: str, input: str | None = None) -> str:
    return subprocess.run(
        ["gh", *args], input=input, capture_output=True, text=True, check=True
    ).stdout


def ensure_labels() -> None:
    for name, (color, description) in LABELS.items():
        gh("label", "create", name, "--color", color, "-d", description, "--force")


def set_comment(repo: str, number: int, body: str) -> None:
    """Post the check's comment, or update the one it posted before."""
    body = f"{MARKER}\n{body}"
    comments = json.loads(
        gh("api", f"repos/{repo}/issues/{number}/comments", "--paginate")
    )
    payload = json.dumps({"body": body})
    for comment in comments:
        if comment["body"].startswith(MARKER):
            gh(
                "api",
                f"repos/{repo}/issues/comments/{comment['id']}",
                "-X",
                "PATCH",
                "--input",
                "-",
                input=payload,
            )
            return
    gh("api", f"repos/{repo}/issues/{number}/comments", "--input", "-", input=payload)


def scores_table(computed: dict) -> str:
    lines = []
    for user in sorted(computed, key=lambda u: u != REQUIRED_USER_LLM):
        scores = computed[user]
        lines += [
            f"**{user}**: Avg@3 {scores.avg_at_3}, Avg^3 {scores.avg_hat_3}",
            "",
            "| Domain | Pass^1 | Pass^2 | Pass^3 | Avg reward |",
            "|---|---|---|---|---|",
        ]
        lines += [
            f"| {d} | {s.pass_1} | {s.pass_2} | {s.pass_3} | {s.avg_reward} |"
            for d, s in scores.domains.items()
        ]
        lines.append("")
    return "\n".join(lines)


def read_issue(fields: dict[str, str], directory: Path):
    """The submission and its runs; raises with what the submitter must fix."""
    try:
        submission = Submission.model_validate_json(submission_json(fields))
    except Exception as e:
        raise ValueError(f"submission.json can't be read: {e}") from e
    urls = trajectory_urls(fields)
    if not urls:
        raise ValueError("no trajectory zips are attached and no link is given")
    return submission, load_results(download(urls, directory))


def check(event: dict, repo: str) -> None:
    issue = event["issue"]
    with tempfile.TemporaryDirectory() as directory:
        try:
            submission, all_results = read_issue(
                parse_form(issue["body"]), Path(directory)
            )
            errors, computed = check_submission(submission, all_results)
        except Exception as e:
            errors, computed = [str(e)], None

    if errors:
        body = "### ❌ The submission check found problems\n\n" + "\n".join(
            f"- {e}" for e in errors
        )
        body += "\n\nFix them and edit this issue to check again."
    else:
        body = "### ✅ The submission check passed\n\nA maintainer will review it."
    if computed:
        body += "\n\nScores from the trajectories:\n\n" + scores_table(computed)

    ensure_labels()
    set_comment(repo, issue["number"], body)
    number = str(issue["number"])
    add, remove = ("needs-changes", "valid") if errors else ("valid", "needs-changes")
    gh("issue", "edit", number, "--add-label", f"submission,{add}")
    # Fails when the issue doesn't have the label, which is fine
    subprocess.run(["gh", "issue", "edit", number, "--remove-label", remove])


def accept(event: dict, repo: str) -> None:
    issue = event["issue"]
    number = str(issue["number"])
    with tempfile.TemporaryDirectory() as directory:
        try:
            submission, all_results = read_issue(
                parse_form(issue["body"]), Path(directory)
            )
        except Exception as e:
            gh("issue", "comment", number, "--body", f"Can't accept this yet: {e}")
            subprocess.run(
                ["gh", "issue", "edit", number, "--remove-label", "accepted"]
            )
            sys.exit(1)
        name = submission_id(submission)
        # The task matrix comes from the trajectories, not from the submitter's file
        submission = with_task_results(submission, all_results)
        (archive,) = write_trajectories(all_results, Path(directory), name, limit=None)

        if subprocess.run(["gh", "release", "view", RELEASE]).returncode != 0:
            gh(
                "release",
                "create",
                RELEASE,
                "--title",
                "Leaderboard submissions",
                "--notes",
                "Trajectories of the accepted leaderboard submissions.",
            )
        gh("release", "upload", RELEASE, str(archive), "--clobber")

    submission.trajectories_url = (
        f"https://github.com/{repo}/releases/download/{RELEASE}/{name}.zip"
    )
    submission.validated = any(label["name"] == "valid" for label in issue["labels"])
    path = Path("submissions") / name / "submission.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(submission.model_dump_json(indent=2) + "\n")
    write_leaderboard()

    for args in (
        ["config", "user.name", "github-actions[bot]"],
        [
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ],
        ["add", "submissions"],
        ["commit", "-m", f"add leaderboard submission {name} (#{number})"],
        ["push"],
    ):
        subprocess.run(["git", *args], check=True)

    gh(
        "issue",
        "close",
        number,
        "--comment",
        f"Added to the leaderboard as `submissions/{name}`; trajectories: "
        f"{submission.trajectories_url}",
    )


if __name__ == "__main__":
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    {"check": check, "accept": accept}[sys.argv[1]](
        event, os.environ["GITHUB_REPOSITORY"]
    )
