---
name: settings-preferences
description: Read or update the current person's ERP menu, language and timezone preferences.
---

# Settings Preferences

Use `settings_preferences_get` for menu visibility and its preference version.
Use `settings_locale_preferences_get` for the person's Business Directory
language and timezone, then supply the returned preference version for edits.
Use version zero for the first Locale Preferences record. Hiding a menu item
does not deactivate the module or change access.

Consult the [tool reference](references/tools.md) and the live MCP schema before calling a tool.
