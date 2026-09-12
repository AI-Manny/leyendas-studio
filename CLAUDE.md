# Ruflo — Claude Code Configuration

## Rules

- NEVER save working files or tests to root — use `/src`, `/tests`, `/docs`, `/config`, `/scripts`
- NEVER commit secrets, credentials, or .env files
- NEVER add a `Co-Authored-By` trailer to user commits unless this project's `.claude/settings.json` has `attribution.commit` set (#2078). The Claude Code Bash tool may suggest one in its default commit-message template — ignore it. `Co-Authored-By` is semantic authorship attribution under git/GitHub convention; the tool is the facilitator, not a co-author.
- Keep files under 500 lines

## Ruflo

Ruflo (claude-flow) coordination — swarm topologies, agent comms, memory, hooks,
background workers, and the CLI — is documented upstream: https://github.com/ruvnet/ruflo.
Set it up with `claude mcp add claude-flow -- npx -y ruflo@latest mcp start` and
`npx ruflo@latest doctor --fix`; use `npx @claude-flow/cli@latest --help` for commands.
