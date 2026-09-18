# Non-English feedback

**For:** Global products

## The problem

Reports arrive in Spanish, German, Japanese; the team triages in English.

## How the agents handle it

`intake` records an English summary plus the original language; searching the tracker uses the English summary so duplicates are found across languages; `writer` drafts clarification replies in the user's language.

## Example outcomes

- 'El juego se cierra cuando intento iniciar sesión con Google' → duplicate of OR-104 (Google sign-in) → +1 comment; a needs_info reply would be written in Spanish.

## What to configure

- Nothing beyond the bug-triage template.

## Value

One triage process for every market.
