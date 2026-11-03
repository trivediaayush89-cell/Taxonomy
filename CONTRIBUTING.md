# Contributing to Skill Taxonomy Dispatcher

## Authoring Skill Frontmatter

Every skill directory in Antigravity or your skills repository must include a `SKILL.md` file with a YAML frontmatter block at the very top:

```markdown
---
name: my-specialized-skill
description: Brief one-sentence description of what problems this skill solves.
category: domain.subcategory
tags:
  - keyword1
  - keyword2
  - topic
status: active
priority: 80
---

# My Specialized Skill
Full skill instructions and reference materials follow here...
```

### Frontmatter Fields

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | Yes | Unique identifier of the skill matching the directory name. |
| `description` | string | Yes | 1-2 sentence description indexed for keyword matching. |
| `category` | string | Yes | Hierarchical domain (e.g., `ui.frontend`, `security.blockchain`, `ops.performance`). |
| `tags` | list[str] | Recommended | Domain keywords used by the resolver to match intent. |
| `status` | string | Optional | `active` (default), `experimental`, or `deprecated`. |
| `priority` | integer | Optional | `0` to `100` (default `50`). Used as a tie-breaker when multiple skills match. |

---

## Running Verification & Tests

Before submitting changes or adding new skills:

1. **Verify Integrity**:
   ```bash
   taxonomy check --skills-dir path/to/skills
   ```
2. **Run Golden Eval Suite**:
   ```bash
   pytest -v
   ```
3. **Test with `explain`**:
   ```bash
   taxonomy explain "your sample user prompt" --skills-dir path/to/skills
   ```
