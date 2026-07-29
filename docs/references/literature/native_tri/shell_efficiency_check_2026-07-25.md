# Shell Efficiency Check for Phase 3 (native_tri) — 2026-07-25

Scope: before implementing `TRI-SHELL-DOMAIN1`/`TRI-SHELL-PROVENANCE1`/
`TRI-SHELL-COST1`, verify whether the literature has since solved the
"rebuilding a bijective shell after every local edit is too expensive"
problem for an *iterative* local-operator loop (hundreds of sequential
split/collapse/flip/smooth ops), as opposed to Jiang 2020's one-shot
shell built once for a single transfer operation.

## What was searched

1. Web search: "incremental bijective shell update", "dynamic shell
   maintenance remeshing", "amortized shell rebuild local edit", "cheap
   per-operation containment check remeshing shell".
2. Forward-citation check of Jiang 2020 (`10.1145/3414685.3417769`) and
   Liu 2024 (`10.1145/3658207`) for 2024-2026 follow-ups specifically on
   making shell/bijective checks cheap for an iterative local-operator
   loop.
3. Re-read of our own `citation_snowball_batch2.md` (lines 169-171,
   205-212), which already flagged an unverified forward reference: **"Zhu
   et al. 2026 (BijectiveRemesh)"** — noted only as a name in prose, no
   DOI, no access status, filed as a batch-3 "sweep forward citations"
   TODO. This session resolved and read that reference.

## Findings

**The reference resolves and is exactly on-topic, but it does not close the
gap — it relocates it.**

- **Zhu, Tao, Hu, Panozzo, Zorin (2026), "BijectiveRemesh: Maintaining
  Bijective Mappings for Data Transfer Across Remeshed Manifolds."**
  arXiv:2605.30744 (May 2026), OPEN — https://arxiv.org/abs/2605.30744,
  full text https://arxiv.org/pdf/2605.30744. No venue/DOI beyond the
  arXiv preprint found; treat as unreviewed at this date. This is the
  paper our own snowball note anticipated as "chained per-operation
  atlases" vs Jiang 2020's "static shell domain" — confirmed by the
  abstract: it builds the bijection by **chaining local bijective atlases
  defined per remeshing primitive** (collapse/split/swap/smooth for
  triangle meshes; Steinitz/Maxwell-Cremona lifting for tet meshes),
  rather than one global shell.
- This is precisely the "one atlas per local edit instead of one shell for
  the whole sequence" architecture our task description was looking for.
  It is real, it resolves, and it is the closest thing in the literature
  to an "incremental" bijective-provenance mechanism for iterative
  remeshing.
- **But it is reported as ~110x slower per operation than plain
  remeshing**, quoting the paper: *"Constructing the bijective local
  atlases adds approximately 110x overhead per operation compared to
  performing remeshing operations alone."* The stated cause is per-patch
  auxiliary triangulation plus iterative energy minimization with
  inversion-preventing line search — i.e., the per-op check is not cheap,
  it is a full local optimization.
- Scalability is explicitly limited, not just slow: on Thingi10k,
  **4,998/5,139 models succeeded; 141 timed out after a 12-hour budget**,
  concentrated in models needing more than ~700k operations. The authors'
  only mitigation is deferred/batched construction — record local-patch
  data during remeshing, then build the atlases **in parallel afterward**
  — which is itself an admission that per-edit online cost is not solved;
  it is being pushed to an offline/parallel post-pass, structurally the
  same "amortize over a batch, don't pay per edit" move our own plan
  already proposes for the envelope/shell tiers.
- No timing comparison to Jiang 2020 or Liu 2024 appears in the paper (no
  head-to-head per-op cost number against the static shell's per-op
  containment+normal check).
- No other 2024-2025 paper surfaced that addresses cheap per-operation
  shell/bijective checks for an iterative loop. Citation-search results for
  Jiang 2020 and Liu 2024 return only the known family (Jiang 2021
  high-order tet shells, Liu 2024 curved shell, and now Zhu 2026) — all of
  which are one-shot-build or per-op-expensive, none targeting amortized
  online maintenance during hundreds of sequential edits.

## Verdict

**Confirmed: the "cheap per-edit shell/bijective check for an iterative
local-operator loop" problem is still open in the literature as of this
search.** The one new, on-point paper (Zhu 2026 BijectiveRemesh) is not a
counter-example — it is direct 2026 evidence *for* the cost concern: its
authors independently arrived at "chained per-op atlases" and found it
110x per-op, then fell back to batching/parallelizing rather than solving
per-edit cost. This corroborates, rather than resolves, the open cost
concern already flagged in our own plan.

## Recommended contract tiering for Phase 3 (unchanged in spirit, now with
literature backing that no cheaper answer exists yet)

Do not wait on the literature for a per-edit-cheap shell. Use the
two-level split already implied by the plan, made explicit:

1. **Per-operation gate (every split/collapse/flip/smooth):** sampled
   two-sided Hausdorff (`TRI-ERROR-GATE1`) hardened by Cheng 2019's
   progressive S1-S4 audit (`TRI-PROGRESSIVE-SAMPLE1`) for the draft/
   standard tiers, or Wang 2020's exact envelope containment
   (`TRI-ENV-ACCUM1`/`TRI-NORMAL-CONE1`) for the standard/fine tiers —
   both are the cheap primitives already measured as near-constant-cost
   per query in our corpus (Wang 2020: ~5e-5 s/query, eps-independent).
   Do **not** run full shell containment/normal checks per edit; both
   Jiang 2020 (paper's own admission: "not suitable for interactive
   applications") and Zhu 2026 (110x/op) independently confirm this is
   too expensive to run inside the hot loop.
2. **Coarse checkpoint (once per round, not once per edit):** rebuild or
   refresh the bijective shell (Jiang 2020 linear shell as the practical
   target) at round boundaries — e.g., after a fixed batch of accepted
   ops or at phase transitions — and run the shell's containment +
   normal-vs-field check there. This amortizes the expensive one-shot
   shell build over many edits instead of paying it (or Zhu 2026's 110x
   atlas cost) per edit, and matches Zhu 2026's own fallback strategy of
   deferring/batching atlas construction rather than doing it inline.
3. **Fine/contract tier exit gate:** final symmetric verification pass
   (`TRI-SYMMETRIC-VERIFY-1`, Yang 2020) plus one full shell containment
   pass at the end of the round sequence, so provenance correctness is
   certified at checkpoint granularity even though the shell is never
   rebuilt per edit.
4. **Re-open this question** only if a future paper reports genuinely
   amortized (sub-linear per-op) shell maintenance — track this by
   re-running this same search against Zhu 2026's own forward citations
   in ~2 quarters, since it is a May-2026 preprint and its stated
   parallelization mitigation may mature into a real per-op-cheap method.

## Screening notes

- Jiang 2020 DOI `10.1145/3414685.3417769` and Liu 2024 DOI
  `10.1145/3658207` both previously verified FULL_READ (see the
  respective per-paper notes in this directory); not re-verified here
  beyond re-reading their text for this question.
- Zhu 2026 arXiv:2605.30744 confirmed to resolve (abstract page and PDF
  both fetched); OPEN access. No DOI was invented — arXiv preprint only,
  flagged as such above.
