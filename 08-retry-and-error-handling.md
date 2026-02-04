# Retry, Error Handling, and Permission Prompts

This document contains prompts related to error handling, retry logic, permission management, and sandbox enforcement in Claude Code.

**Location:** Various locations in cli.js

---

## Permission System

### Permission Modes

| Mode | Description |
|------|-------------|
| `default` | Standard mode - asks for permissions as needed |
| `bypassPermissions` | Skip all permission prompts (can be disabled by policy) |
| `plan` | Plan mode - requires plan approval before implementation |
| `acceptEdits` | Auto-accept file edits |
| `dontAsk` | Deny all permission prompts silently |
| `delegate` | Coordinator/delegate mode for multi-agent |
| `coordinator` | Team coordinator mode |

### Permission Denied Messages

When permission is auto-denied (e.g., in async/background agents):

```
Permission to use [TOOL_NAME] has been auto-denied (prompts unavailable).
```

When explicitly denied by rule:

```
Permission to use [TOOL_NAME] has been denied.
```

### Rule-Based Permissions

Rules can be set at multiple levels:
- `cliArg` - Command line arguments
- `session` - Current session only
- `localSettings` - Project-local settings
- `userSettings` - User-wide settings
- `projectSettings` - Project settings (.claude/)
- `policySettings` - Enterprise/managed policy
- `flagSettings` - Feature flag controlled
- `command` - Per-command permissions

---

## Tool Permission Check Flow

```
1. Check deny rules -> If matched, DENY
2. Check ask rules -> If matched, ASK (unless sandbox auto-allows)
3. Check passthrough from tool's own checkPermissions
4. Check bypass mode -> If enabled, ALLOW
5. Check allow rules -> If matched, ALLOW
6. Default -> ASK user
```

---

## Sandbox System

### Sandbox Violation Handling

When a command violates sandbox restrictions, violations are tracked and appended to stderr:

```
<sandbox_violations>
[violation details from macOS sandbox or Linux seccomp]
</sandbox_violations>
```

### Sandbox Configuration

The sandbox system enforces:
- **Network restrictions:** Domain allowlists/denylists via HTTP and SOCKS proxies
- **Filesystem restrictions:** Read deny, write allow/deny paths
- **Process restrictions:** Command filtering and monitoring

### Temporary Directory in Sandbox

```
- IMPORTANT: For temporary files, use `/tmp/claude/` as your temporary directory
- The TMPDIR environment variable is automatically set to `/tmp/claude` when running in sandbox mode
- Do NOT use `/tmp` directly - use `/tmp/claude/` or rely on TMPDIR instead
```

---

## Compaction Error Messages

When compaction (conversation summarization) fails:

```
"Not enough messages to compact."
```

```
"Conversation too long. Press esc twice to go up a few messages and try again."
```

```
"Compaction interrupted. This may be due to network issues -- please try again."
```

---

## API Error Handling

API errors are prefixed with a sentinel string to detect failures:

```
API Error: [error details]
```

When the prompt is too long:

```
"Prompt too long" error triggers special handling
```

---

## Background Task Management

### Task States

| Status | Description |
|--------|-------------|
| `running` | Task is actively executing |
| `pending` | Task is queued/starting |
| `completed` | Task finished successfully |
| `failed` | Task encountered an error |
| `killed` | Task was manually terminated |

### Backgrounding Detection

Tasks can be backgrounded mid-execution. The system detects this via a signal:

```
When a foreground task is sent to background:
1. A background signal is sent
2. The task continues with its own abort controller
3. Output is written to a file at the agent's output path
4. Progress updates are tracked via the app state
```

---

## MCP Server Error Handling

### Connection Errors

When MCP servers fail to connect, errors are categorized:
- `mcp-config-invalid` - Invalid configuration
- `mcpb-download-failed` - Download failure
- `mcpb-extract-failed` - Extraction failure
- `mcpb-invalid-manifest` - Invalid manifest

### Enterprise MCP Policy

```
Cannot add MCP server "[NAME]": server is explicitly blocked by enterprise policy
Cannot add MCP server "[NAME]": not allowed by enterprise policy
```

---

## Bash Command Prefix Extraction

A separate AI call extracts command prefixes for security classification:

```
ONLY return the prefix. Do not return any other text, markdown markers, or other content or formatting.
```

Special responses:
- `"command_injection_detected"` - Possible injection attack
- `"git"` - Git command (handled separately)
- `"none"` - No recognizable prefix

---

## Session Memory Update Error Handling

Session notes updates have strict rules to prevent corruption:

```
CRITICAL RULES FOR EDITING:
- The file must maintain its exact structure with all sections, headers, and italic descriptions intact
- NEVER modify, delete, or add section headers
- NEVER modify or delete the italic section description lines
- ONLY update the actual content that appears BELOW the italic section descriptions
- Keep each section under ~[limit] tokens/words
```

If section sizes exceed limits, condensation warnings are generated.

---

## Notes

- Permission checks happen before every tool use
- The sandbox system operates at OS level (macOS sandbox-exec, Linux seccomp/BPF)
- Compaction has retry logic with configurable attempts
- Error messages are designed to be actionable for both the AI and the user
- MCP server errors include scope and severity metadata for proper handling
