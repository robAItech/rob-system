# GStack AI Project Configuration
# Ne briši te datoteke. Ta datoteka usmerja Claude Code k uporabi GStack veščin.

## Skills
- gstack: Available at C:/Users/Robert.slavec/.claude/skills/gstack/SKILL.md

## Project Rules
- Ta projekt je testno okolje za GStack.
- Vsa koda naj bo profesionalno komentirana in modularna.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules (all 54 gstack skills):

Planning / reviews:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design plan review → invoke /plan-design-review
- DX plan review → invoke /plan-devex-review
- Full review pipeline → invoke /autoplan
- Design system from scratch → invoke /design-consultation
- Self-tune questions → invoke /plan-tune
- Backlog-ready spec/issue → invoke /spec

Implementation / review:
- Code review/diff check → invoke /review
- Second opinion (cross-model) → invoke /codex
- Bugs/errors → invoke /investigate
- Visual polish → invoke /design-review
- Design variants/exploration → invoke /design-shotgun
- Production HTML/CSS → invoke /design-html
- Live DX audit → invoke /devex-review
- QA/testing site behavior + fix → invoke /qa
- QA report only → invoke /qa-only
- Pull data from a web page → invoke /scrape
- Codify a scrape flow → invoke /skillify

Ship / deploy:
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Post-deploy monitoring → invoke /canary
- Ship queue dashboard → invoke /landing-report
- Update docs after ship → invoke /document-release
- Generate missing docs → invoke /document-generate
- Configure deploy → invoke /setup-deploy
- Upgrade gstack → invoke /gstack-upgrade

Operations / memory:
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Manage learnings → invoke /learn
- Weekly retrospective → invoke /retro
- Code quality dashboard → invoke /health
- Performance regression → invoke /benchmark
- Cross-model benchmark → invoke /benchmark-models
- Security audit → invoke /cso
- Setup gbrain → invoke /setup-gbrain
- Sync gbrain → invoke /sync-gbrain

Browser / agents:
- Web browsing / headless browser → invoke /browse
- Visible GStack browser → invoke /open-gstack-browser
- Import browser cookies → invoke /setup-browser-cookies
- Pair remote agent with browser → invoke /pair-agent

iOS QA:
- iOS live-device QA → invoke /ios-qa
- iOS bug fix → invoke /ios-fix
- iOS design audit → invoke /ios-design-review
- iOS debug cleanup → invoke /ios-clean
- iOS bridge resync → invoke /ios-sync

Safety / tools:
- Destructive command guard → invoke /careful
- Restrict edits to a directory → invoke /freeze
- Full safety mode → invoke /guard
- Remove edit lock → invoke /unfreeze
- Markdown to PDF → invoke /make-pdf
- Diagram generation → invoke /diagram

Router:
- Which gstack skill fits → invoke /gstack
