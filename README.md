# Berry Science agent skills

Science relies on trusted knowledge. [Berry Science](https://berry.science)
builds the tools that let research agents produce it: **standards for
agents**, **benchmarked reviewing**, and **a trusted database**.

This repository is the open part of that work. It contains the
instructions of our review agent as an [agent skill](https://agentskills.io),
so you can run the same reviewer on your own papers that we run on ours.
It starts with reviewing. Standards and the database are not in this
repository yet.

```
agent-skills/
├── .claude-plugin/
│   ├── plugin.json            the skills as a Claude Code plugin ("berry")
│   └── marketplace.json       lets Claude Code install it from this repo
└── skills/
    └── review-paper/
        ├── SKILL.md           the reviewer's instructions
        └── references/
            └── score-rubric.md
```

## The reviewer

`review-paper` reads a paper's **LaTeX source** and looks for **objective
errors**: a wrong number, an inconsistent unit, a flipped sign, a step that
does not follow, an invalid statistic, two parts of the paper that
contradict each other, a conclusion stronger than the results. Separately,
it may flag a *presentation weakness*: a passage that is not wrong but
that a reader in the field cannot follow.

It does not judge novelty, significance, style or writing quality. It is
told that an empty review is a good review when the paper holds up, and that
a false alarm costs as much as a miss.

It writes `review.json`: at most 10 findings, ranked most confident first,
each quoting the exact source text it is about, and a correctness score from
0 to 100 computed from the findings by a fixed rubric.

This version is our **baseline** reviewer: one reading pass over
arithmetic, units, signs, derivations and cross-references. It was
developed with Claude Opus 5 at medium reasoning effort.

## Install

**Claude Code**, as a plugin:

```
/plugin marketplace add berry-science/agent-skills
/plugin install berry@berry-science
```

The skill is then available as `/berry:review-paper`.

**Claude Code**, without the plugin: copy `skills/review-paper/` into
`~/.claude/skills/` (for all your projects) or into `.claude/skills/` in a
project.

**Claude.ai**: zip the `review-paper` folder and upload it as a custom
skill in your settings.

**Other agents**: the skill is a `SKILL.md` with a `references/` folder in
the open Agent Skills format. Where your agent does not read skills, the
body of `SKILL.md` works as a system prompt, with the rubric appended.

## Use

Get the LaTeX source of the paper. For an arXiv paper it is linked under
*TeX Source* on the abstract page. Then ask:

> Review the paper in `./paper/`.

or give an arXiv ID and let the agent download the source, if it is allowed
to run shell commands. The review is written to `review.json` beside the
source directory, and the agent summarises it in its reply.

The score maps to a verdict:

| Score | Verdict |
|---|---|
| 90–100 | clean |
| 70–89 | minor issues |
| 40–69 | major issues |
| below 40 | fundamentally flawed |

## Read a review as a list of candidates

A finding is a **candidate** error until a person who knows the field has
checked it. The reviewer produces false alarms, and each finding quotes the
exact source text so you can check it quickly. Use a review to decide where
to look, not as a verdict on the paper or its authors.

**Do not run the reviewer on a manuscript you received in confidence**, for
example to referee it for a journal. That manuscript belongs to its
authors. Check the journal's policy before passing it to any AI tool.

## Versions

The skill is taken from a reviewer bundle in our benchmark repository,
which is not public. The instructions are unchanged from that bundle except
where they referred to our harness, and `SKILL.md` adds a short section on
setting up the inputs.

| Version | Reviewer | Bundle commit |
|---|---|---|
| `v0.1.0` | baseline | `c2b7ff8` (2026-08-18) |

A change to how the reviewer judges a paper will come as a new version
here.

## Contact

Berry Science is pre-launch and in active development, at Leibniz
University Hannover. If the reviewer gets something wrong on your paper, we
would like to hear about it: open an issue, or write to Gabriel Müller
(g.mueller@iqo.uni-hannover.de) or Christian Struckmann
(struckmann@iqo.uni-hannover.de).

## License

[MIT](LICENSE).
