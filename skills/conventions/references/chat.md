# Conventions from a chat window

In a chat window — Claude.ai, ChatGPT — there is no ledger. The
conventions live with the claims in the Berry Science Library: every claim
published carries the conventions its numbers are written in, and
`list_my_conventions` reads them back as the researcher's current set.

## The researcher's conventions

- **Read them first.** At the start of a conversation that will record
  claims, call `list_my_conventions`: the newest version of each
  convention the researcher's claims use, with how many claims use it.
- **None yet?** Before the first claim with a convention-dependent number
  (a spectral density, a frequency, a width, a sign), propose the ones it
  depends on in a few lines — in the first claim's setup message
  (berry-publish-claim-chat.md) — and ask the researcher to confirm. Do not
  guess a convention into a claim.
- **A convention is checkable**: the definition with its normalization or
  formula and the unit — *"S_x(f) is one-sided: ∫_0^∞ S_x(f) df = ⟨x²⟩, in
  µm²/Hz"*, not *"one-sided PSD"*. Each has a short key (`psd-one-sided`)
  and a version.
- **A change is a new version** of the same key, never a silent rewording:
  older claims keep the version they were written in.

## In every claim

Pass the conventions the claim's numbers depend on in `publish_claim`'s
`conventions`, each as `{key, version, statement, category}` — the
statement in full, exactly as before for the same key and version.

## Against a paper

When a claim takes something from a paper (berry-review-source-chat.md):
write down the paper's conventions for the passage, map each onto the
researcher's (`same`, `transform` with the conversion, `conflict`), apply
the transform before using the value, and show it in the claim's
reasoning. A result that disagrees with a paper by 2, 2π, √2 or a sign:
check the conventions first.
