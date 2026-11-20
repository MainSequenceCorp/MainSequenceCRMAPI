---
name: purchasing-orders
description: Manage supplier orders, receive goods or accept services, and create one linked vendor bill.
---

# Purchasing Orders

Read the order, version and line UID before a fulfillment action. Receive
physical stock into the reviewed location, or use service acceptance for a
service line. Those are different owner commands. Read fulfillment and the
existing bill link before asking the owner to create a vendor bill. The handoff
creates a draft and links it atomically. A stale receipt or bill result needs
read-back before retrying.

Consult the [tool reference](references/tools.md) and the live MCP schema before calling a tool.
