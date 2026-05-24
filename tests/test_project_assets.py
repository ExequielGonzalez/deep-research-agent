from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_docker_compose_assets_exist_and_encode_runtime_contract():
    compose_path = REPO_ROOT / "docker-compose.yml"
    script_path = REPO_ROOT / "scripts" / "compose-agent.sh"

    compose_text = compose_path.read_text(encoding="utf-8")

    assert "postgres:" in compose_text
    assert "app:" in compose_text
    assert "POSTGRES_DB: ${POSTGRES_DB:-deep_research}" in compose_text
    assert "pg_isready" in compose_text
    assert "DEEP_RESEARCH_POSTGRES_DB_URL" in compose_text
    assert script_path.exists()
    assert script_path.stat().st_mode & 0o111


def test_skill_and_html_documentation_exist():
    skill_path = REPO_ROOT / ".github" / "skills" / "deep-research-agent-compose" / "SKILL.md"
    workflow_path = REPO_ROOT / ".github" / "skills" / "deep-research-agent-compose" / "references" / "workflow.md"
    html_doc_path = REPO_ROOT / "docs" / "implementation.html"

    skill_text = skill_path.read_text(encoding="utf-8")
    html_text = html_doc_path.read_text(encoding="utf-8")

    assert "name: deep-research-agent-compose" in skill_text
    assert "Use when asked to operate the deep research CLI" in skill_text
    assert workflow_path.exists()
    assert "<!DOCTYPE html>" in html_text
    assert "Docker Compose" in html_text
    assert "Decisiones técnicas tomadas" in html_text
