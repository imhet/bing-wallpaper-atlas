"""工作流 YAML 的静态约束。

2026-11-04 事故：CF 部署步骤的 if 里写了 secrets.CLOUDFLARE_API_TOKEN != ''，
GitHub Actions 的表达式语法不接受 secrets 出现在 step-level if——不是这一步被跳过，
而是整个 daily.yml 解析失败（gh workflow run 直接 422），每日抓取与 Pages 部署一起挂掉。
secrets 只能出现在 env / with 里，需要判断时先在 shell 里读成 step output。
"""

from pathlib import Path

import pytest
import yaml

WORKFLOWS = sorted((Path(__file__).resolve().parent.parent / ".github" / "workflows").glob("*.yml"))


def iter_steps(workflow):
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            yield job, step


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_workflow_parses(path):
    assert yaml.safe_load(path.read_text(encoding="utf-8")), f"{path.name} 不是有效的工作流"


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_no_secrets_in_step_if(path):
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    bad = [
        step.get("name") or step.get("uses")
        for _, step in iter_steps(wf)
        if "secrets." in str(step.get("if", ""))
    ]
    assert not bad, f"{path.name}: 这些步骤的 if 用了 secrets 上下文，工作流会整体解析失败 → {bad}"
