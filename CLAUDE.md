## Serena MCP (Always Do First)

**Step 1 — Always activate Serena and read memories before any code exploration:**

```
mcp__serena__activate_project(project: "kingpin")
mcp__serena__read_memory(memory_file_name: "quick_reference")
```

**Step 2 — If this is a new project (or first conversation), run onboarding:**

```
mcp__serena__check_onboarding_performed()
# If onboarding has NOT been performed yet:
mcp__serena__onboarding()
```
