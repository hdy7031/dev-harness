## Software profile

Objective: deliver a strong real user/product outcome with sufficient maintainability.

Default priority: user path and product experience > correctness/stability > maintainability > formal process, test counts, and audit completeness. This does not license incorrect or unsafe behavior.

- Make the real user path work before pursuing architectural perfection.
- Product and UX quality are part of completion; inspect actual experience when relevant.
- Use minimum sufficient verification for ordinary UI and features.
- Raise verification for state machines, migrations, atomic writes, security, destructive operations, and other high-risk logic.
- Avoid premature refactoring; improve structure when it serves the current outcome.
- Do not let verification routinely dominate implementation and product polish; deeper checks need a concrete risk or failure to resolve.
