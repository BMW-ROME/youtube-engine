# Voice-engine recovery

The original Chapter 2.1-2.4 ZIPs were located in the project folder and recovered
without changing the archives. The Chapter 2.3 archive omits its Python module;
its definitions are intact. One archived panel test also mistakenly treats a
dictionary fixture as a Reaction object. New tests use validated reactions.

The existing Distillation Engine passed its five original tests, but lacked guards
for orphaned references, ignored min_confidence, dropped list-shaped disagreement,
and promoted unsupported ideas. Those paths are corrected in voice_engine/.

Current evidence: 61 repository tests pass using synthetic fixtures. Original
evidence tests (3) and distillation tests (5) also pass against restored modules.
This does not complete the first real-source end-to-end exercise.

Archive SHA-256 provenance:
- Chapter 2.1: af01b738a8bccedfc776b7ebbd322d11ea79324a475d7cec2c4430fcbfbd4e48
- Chapter 2.2: 94e007df27098525fd1426f80ad2f15a6654d36c6d61a5e71b0c2f95cf29a711
- Chapter 2.3: 51dfd058b8a33ab111490e65fb564b4e25046b04fddb3e35ac0ca49dc785229e
- Chapter 2.4: c864dbdcb6c864af46ea58d4be022dba35fdd49f9136d888b64cd7399e816be6

Original private media remain separate from repository code. Next: WP-005.
