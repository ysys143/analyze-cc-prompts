# Claude Code Prompt Analysis

An analysis and extraction of all prompt strings embedded in Claude Code CLI v2.1.29.

**Version Analyzed:** 2.1.29 (Native Installer)
**Source:** `~/.local/share/claude/versions/2.1.29` (171MB Mach-O binary)
**Extraction Method:** `strings` command + JavaScript code extraction
**Extracted Code:** 13MB, 152,283 lines of minified JavaScript
**Build Time:** 2026-01-31T20:12:07Z

---

## Installation Methods

Claude Code provides **two installation methods**:

### 1. Native Installer (Official Recommended)

```bash
# Installation path
~/.local/share/claude/versions/
├── 2.1.20  (173MB)
├── 2.1.29  (171MB) ← Analyzed version
├── 2.1.32  (172MB)
└── 2.1.33  (173MB)
```

**Characteristics:**
- Mach-O 64-bit ARM64 binary (compiled executable)
- Bun runtime + JavaScript code + native modules bundled together
- No Node.js required
- Auto-update support
- Multiple versions can coexist

### 2. npm Package

```bash
# Installation path
~/.nvm/versions/node/v20.18.1/lib/node_modules/@anthropic-ai/claude-code/cli.js
```

**Characteristics:**
- JavaScript source file (minified but directly readable)
- Requires Node.js v18+
- Managed via npm
- Easy code analysis

### Comparison

| Aspect | Native Installer | npm Package |
|--------|------------------|-------------|
| **Node.js Required** | [X] No | [O] Yes |
| **File Format** | Binary (Mach-O) | JavaScript |
| **Size** | 171MB | 11MB + node_modules |
| **Code Analysis** | Requires extraction | Direct access |
| **Execution Speed** | Fast (Bun) | Moderate (Node.js) |
| **Best For** | Servers, CI/CD, restricted environments | Local development |

### Extracting Code from Native Binary

Although the native installer is a binary, the JavaScript code can be extracted using the `strings` command.

**Extraction Process:**
```bash
# 1. Extract all strings from binary
strings ~/.local/share/claude/versions/2.1.29 > strings_output.txt

# 2. Find JavaScript code location by version marker
grep -n "// Version: 2.1.29" strings_output.txt

# 3. Extract the code range (e.g., lines 114470-266752)
sed -n '114470,266752p' strings_output.txt > extracted_code.js
```

**Why is this possible?**
- JavaScript is an interpreted language, not compiled to machine code
- The native binary bundles Bun runtime + JavaScript code as plain text strings
- `strings` command extracts all readable text from binaries

For detailed extraction methodology, see [BINARY_EXTRACTION.md](BINARY_EXTRACTION.md).

---

## Files

| # | File | Description |
|---|------|-------------|
| 01 | [01-main-system-prompt.md](01-main-system-prompt.md) | Core system prompt: tone, style, professional objectivity, task management, tool usage policy |
| 02 | [02-agent-prompts.md](02-agent-prompts.md) | Built-in agent system prompts: Bash, General-Purpose, Statusline, Explore, Plan |
| 03 | [03-tool-descriptions.md](03-tool-descriptions.md) | Tool descriptions for Read, Write, Edit, Glob, Grep, Bash, WebFetch, WebSearch, Task, etc. |
| 04 | [04-internal-prompts.md](04-internal-prompts.md) | Internal operational prompts: compaction/summary, session notes, file path extraction, session search |
| 05 | [05-personas-and-styles.md](05-personas-and-styles.md) | Output styles: default, Explanatory, Learning, custom style loading system |
| 06 | [06-code-review-and-security.md](06-code-review-and-security.md) | Code review and security review skill prompts |
| 07 | [07-team-and-collaboration.md](07-team-and-collaboration.md) | Team messaging, plan approval, multi-agent collaboration protocols |
| 08 | [08-retry-and-error-handling.md](08-retry-and-error-handling.md) | Permission system, sandbox, error handling, retry logic |

---

## Key Findings

### Prompt Architecture

Claude Code uses a layered prompt system:

1. **System Prompt** (01): Core behavioral instructions, tone, and operational guidelines
2. **Tool Descriptions** (03): Each tool carries its own description prompt with usage guidelines
3. **Agent Prompts** (02): Specialized agents have their own system prompts with role-specific constraints
4. **Internal Prompts** (04): Operational prompts for conversation management (compaction, session notes)
5. **Styles** (05): Output style modifiers that adjust behavior (Explanatory, Learning)
6. **Skills** (06, 07): Task-specific prompts for code review, security review, team collaboration

### Notable Patterns

- **READ-ONLY enforcement**: Explore and Plan agents have multi-layered read-only restrictions
- **Tool preference hierarchy**: Specialized tools (Read, Grep, Glob) are strongly preferred over Bash equivalents
- **Git safety**: Extensive git safety protocols prevent destructive operations
- **Permission layering**: 7+ sources of permission rules with clear precedence
- **Sandbox integration**: OS-level sandboxing (macOS sandbox-exec, Linux seccomp) with proxy-based network filtering
- **Dynamic content**: Many prompts use template variables for dates, model names, paths, and feature flags

### Prompt Sizes (Approximate)

| Category | Estimated Tokens |
|----------|-----------------|
| Main system prompt | ~3,000-4,000 |
| Bash tool description | ~2,000-3,000 |
| All tool descriptions combined | ~5,000-7,000 |
| Agent prompts (each) | ~300-800 |
| Compaction prompt | ~800-1,000 |
| Output styles | ~500-1,500 each |

---

## How Prompts Were Extracted

1. Located `cli.js` in the npm global installation
2. Identified prompt patterns: template literals, string constants, function return values
3. Read specific line ranges from the minified source
4. Categorized and documented each prompt with its location and purpose

---

## Disclaimer

This analysis is for educational and research purposes. The prompts are extracted from the publicly available npm package `@anthropic-ai/claude-code` v2.1.29.
