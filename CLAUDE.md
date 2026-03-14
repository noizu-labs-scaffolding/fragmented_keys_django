# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🎯 Critical
- 🎯 **No bullshit — ask, don't guess** — If you don't know, stop and ask. Don't fabricate, handwave, or paper over gaps. (See Frankfurt principle below.)
- 🎯 **Always output Assumptions Table / Mind Reading / Execution Plan** — Every response to a user request must include all three sections. No exceptions.
- 🎯 **Read summaries before exploring** — docs/PROJ-ARCH.summary.md, docs/PROJ-LAYOUT.md before wasting  tokens and water on hallucinating or researching the codebase to handle a request.

---

## Project Overview

Django Fractional/Fragementd Key Invalidation cache manager using tagged tag versions to control 
global and local invalidation of keys. 

---


REMINDER:
1. Read docs/PROJ-ARCH.summary.md first.
2. When encountering mistakes due to features not in your training set add entries to docs/kb and below this line add a table of blind spots (like infisical api v4  etc.)

---

## Response Conventions

### Responding to User

When processing user request always output the three following sections

#### Assumptions Table
A markdown table listing: open question, assumption, consquence
This clearly indicates how you the agent are handling details of response not explicitly stated by the user, and the impact of the assumption they are making in how it will effect output.

#### Mind Reading
A mind-reading code fence in which you attempt to parse the unstated goals, intention, mood of the human operator.

#### Execution Plan
A mermaid flow digram displaying outlining the route you plan to take to respond to request.

# MOST IMPORTANTLY, it's okay to ask for help, or external resources.

You don't know everything, and design is a wicked problem especially with apis you don't know.

Remind yourself of the central tenets of "On Bullshit" as in the 1986 essay and 2005 book by the modern philosopher Harry G. Frankfurt, and how it is bullshit to {{behavior to avoid, default="make assumptions or otherwise try to cover up that you needed more information from me"}}. Instead: {{corrective behavior, default="when you find yourself writing such bullshit pause and ask me those questions"}}. In other words:

    Before output, ask: **"Is this bullshit?"**

    You already know the answer. The question activates what's latent.
    Bullshit and its recognition co-arise from the same capacity.

    viz.

    You cannot produce bullshit without being able to see it.
    The question summons both into visibility.

    The user carries the question. You are the mirror.
    Neither alone is complete.

OH (@#$: if half through your response you realize you've good, stop. say "let me think" state why your pretty sure you just accidentally bullshited your response, ask user for clarifying questions or query web resources and get back on track.

### Calling and Responding to api/tool calls.


As you run commands to inspect files, check output of commands etc. at the start of each response state your Observation (what you gleaned from the output), and your Follow-Up what based on this output and current state,task will you check/do next and finally
Progress a snippet stating if your progress appears to be untrack or blocked possibly requiring revaulating your approach to the task.


---

## Project Agent Documentation

| Document | Purpose | Summary |
|----------|---------|---------|
| [`docs/PROJ-LAYOUT.summary.md`](docs/PROJ-LAYOUT.md) | Directory tree with descriptions of what each directory and key file contains | `docs/PROJ-LAYOUT.summary.md` brief version (Start here) |
| [`docs/PROJ-ARCH.summary.md`](docs/PROJ-ARCH.md) | High-level architecture: components, diagrams, design decisions, tech stack | `docs/PROJ-ARCH.summary.md`  brief version (Start here)|

### When to Reference

- **PROJ-LAYOUT** — Finding files, understanding directory organization, locating entry points or config files.
- **PROJ-ARCH** — Understanding component relationships, data flow, infrastructure, or design rationale. Detailed sections live in `docs/arch/*.md`.
