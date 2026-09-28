---
name: mf-research
description: Standards and note format for external research - sources, citations, facts vs inferences, thesis impact. Use for scout research tasks.
user-invocable: false
---

# Research notes

Write to `project/memory/literature/<slug>.md` (technical) or `research/notes/<slug>.md` (market),
and add one line to `project/memory/literature/INDEX.md`: `- <slug> — <one-line takeaway> (<date>)`.

```markdown
# <question>
Date: <YYYY-MM-DD> · Task: <T id> · Confidence: high|medium|low
## Answer (≤ 5 sentences)
## Sources
| id | citation | url | type (paper/doc/datasheet/news/filing) | accessed |
## Findings
- [S1] fact, with numbers, units, and conditions
- (inference) clearly marked reasoning that goes beyond the sources
## Relevance to ModuleForge
## Thesis impact: none | weakens | strengthens | unclear — why
## Open questions
```
Primary sources first. Quote numbers exactly with conditions. Never cite a source you did not open.
