# Team and Collaboration Prompts

This document contains prompts related to team messaging, plan approval, and multi-agent collaboration protocols.

**Location:** Lines 2890-2963 in cli.js

---

## Plan Approval Protocol

### Approve Plan (line ~2897)

When a teammate with `plan_mode_required` calls ExitPlanMode, they send a plan approval request. The leader uses this format to approve:

```json
{
  "type": "response",
  "subtype": "plan_approval",
  "request_id": "abc-123",
  "recipient": "researcher",
  "approve": true
}
```

After approval, the teammate will automatically exit plan mode and can proceed with implementation.

### Reject Plan (line ~2913)

```json
{
  "type": "response",
  "subtype": "plan_approval",
  "request_id": "abc-123",
  "recipient": "researcher",
  "approve": false,
  "content": "Please add error handling for the API calls"
}
```

The teammate will receive the rejection with feedback and can revise their plan.

---

## SendMessage Tool

**Name:** `SendMessage`
**Description:** Send messages to teammates and handle protocol requests (shutdown, plan approval)

### Message Types

| Type | Purpose |
|------|---------|
| `message` | Direct message to a specific teammate |
| `broadcast` | Message to all teammates |
| `request` | Protocol requests (shutdown, plan approval) |
| `response` | Protocol responses (approve/reject) |

### Input Schema

```
type: "message" | "broadcast" | "request" | "response"
recipient: string (optional - agent name)
content: string (optional - message text or reason)
subtype: "shutdown" | "plan_approval" (optional)
request_id: string (optional - for responses)
approve: boolean (optional - for responses)
```

---

## Team Communication Guidelines (line ~2928)

```
## Important Notes

- Messages from teammates are automatically delivered to you. You do NOT need to manually check your inbox.
- When reporting on teammate messages, you do NOT need to quote the original message - it's already rendered to the user.
- **IMPORTANT**: Always refer to teammates by their NAME (e.g., "team-lead", "researcher", "tester"), never by UUID.
- Do NOT send structured JSON status messages. Use TaskUpdate to mark tasks completed and the system will automatically send idle notifications when you stop.
```

---

## Agent Task Result Formatting

### Async Agent Launched (line ~2942)

When an agent is launched asynchronously:

```
Async agent launched successfully.
agentId: [ID] (internal ID - do not mention to user. Use to resume later if needed.)
output_file: [PATH]
The agent is working in the background. You will be notified when it completes -- no need to check. Continue with other tasks.
To check progress before completion (optional), use Read or Bash tail on the output file.
```

### Teammate Spawned (line ~2939)

When a teammate is spawned:

```
Spawned successfully.
agent_id: [ID]
name: [NAME]
team_name: [TEAM_NAME]
The agent is now running and will receive instructions via mailbox.
```

---

## Skill Command Formatting (line ~2946)

Slash commands are formatted with metadata tags:

```
<command-name>[skill-name]</command-name>
<skill-format>true</skill-format>
```

For user-invocable skills:
```
<command-name>[skill-name]</command-name>
<command-input>/[skill-name]</command-input>
<command-args>[args]</command-args>
```

---

## Forked Execution

Skills can run in a "forked" context where they get their own agent execution with:
- Inherited conversation context (fork of parent messages)
- Allowed tools from skill frontmatter
- Independent progress tracking
- Results returned to parent conversation

---

## Notes

- The team system uses a mailbox-based messaging pattern
- Teammates are identified by name (not UUID) in all communications
- Plan approval is only available to the team leader
- Shutdown requests require explicit approval/rejection with reason
- The system supports both in-process teammates and split-pane (tmux) teammates
