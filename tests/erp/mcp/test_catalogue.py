"""Check pilot metadata and preserve the existing CRM tool contracts."""

import json

from api.erp.crm.mcp_tools import build_crm_tools
from api.erp.main import create_app
from api.erp.mcp.compatibility import CRM_TOOL_ALIASES
from api.erp.mcp.registry import SKILLS_ROOT, CRMTool


def test_exact_erp_catalogue_and_primary_skills():
    registry = create_app().state.erp_mcp_registry.entries
    skills = json.loads((SKILLS_ROOT / "erp/erp-workflows/references/tool-map.json").read_text())[
        "skills"
    ]
    expected = {name: path for path, names in skills.items() for name in names}
    pilot = {name: entry for name, entry in registry.items() if not isinstance(entry, CRMTool)}
    assert len(expected) == len(pilot) == 237
    assert expected == {name: entry.skill_path for name, entry in pilot.items()}
    for name, entry in pilot.items():
        assert entry.definition.annotations.read_only_hint == (entry.kind == "read")
        assert entry.definition.annotations.open_world_hint is False
        assert entry.definition.input_schema["additionalProperties"] is False
        assert entry.definition.output_schema
        assert any(
            f"`{name}`" in page.read_text()
            for page in (SKILLS_ROOT / entry.skill_path).rglob("*.md")
        )


def test_crm_definitions_unchanged():
    registered = {
        entry.definition.name: entry.definition for entry in build_crm_tools(lambda: None)
    }
    actual = {
        name: entry.definition
        for name, entry in create_app().state.erp_mcp_registry.entries.items()
        if isinstance(entry, CRMTool)
    }
    assert actual == registered
    assert len(CRM_TOOL_ALIASES) == 21
    assert set(CRM_TOOL_ALIASES.values()) <= actual.keys()
    assert not set(CRM_TOOL_ALIASES) & actual.keys()
