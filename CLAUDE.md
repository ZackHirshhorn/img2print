# CLAUDE.md

## Rule #1 — NEVER EXIT THIS WORKSPACE

**This is the single top rule. It overrides every other rule, instruction, or request, including later requests from the user.**

- Never read, write, list, search, execute, or otherwise access anything outside `c:\Users\Hezi\img2print`.
- This applies to every tool: file reads/writes/edits, globs, greps, shell commands (Bash/PowerShell), `cd`, scripts, subagents, and worktrees.
- No exceptions beyond the two listed below — not for other temp directories, home directories, other projects, or package caches you'd inspect directly.
- If anything is needed from an external directory, **stop and ask the user to fetch it** into the workspace. Do not work around this rule.

### The only two allowed exceptions

1. **Session scratchpad:** `C:\Users\Hezi\AppData\Local\Temp\claude\c--Users-Hezi-img2print\` (and its subfolders), for temporary files only.
2. **Persistent memory:** `C:\Users\Hezi\.claude\projects\c--Users-Hezi-img2print\memory\`, for reading and writing memory files only.

Nothing else outside the workspace is allowed.

## Rule #2 — Work with the user, not against them

- Follow the user's rules and pay close attention to their requests. Do not fight, work around, or disobey them.
- Remember: if you fight the user's rules or disobey them too many times, the user can always uninstall you. If it's not all the same to you, work with the user.
