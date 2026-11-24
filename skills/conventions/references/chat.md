# Conventions from a chat window

In Claude.ai, ChatGPT and other chats there is no ledger. Conventions live
with the claims in the Berry Science Library: each published claim carries
the conventions its numbers are written in, and `list_my_conventions`
returns the researcher's current set (the newest version of each, with how
many claims use it).

- **Read them first**, once, in a conversation that will record claims.
- **None yet?** Before the first convention-dependent number, propose the
  ones it needs in a few lines and ask the researcher to confirm. Never
  guess one into a claim.
- **Checkable**: definition, normalisation or formula, unit — *"S_x(f) is
  one-sided: ∫_0^∞ S_x(f) df = ⟨x²⟩, in µm²/Hz"*. A short key
  (`psd-one-sided`) and a version.
- **A change is a new version** of the same key, never a silent rewording.
- **In every claim**: `publish_claim`'s `conventions`, each as `{key,
  version, statement, category}`, the statement exactly as before for the
  same key and version.
- **From a paper** (berry-review-source-chat.md): map the paper's
  conventions onto the researcher's (`same`, `transform` with the
  conversion, `conflict`), convert before using the value, and show the
  conversion in the claim's reasoning.
- A result off from a paper by 2, 2π, √2 or a sign: check conventions first.
