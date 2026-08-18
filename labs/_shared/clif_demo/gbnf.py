r"""The same CLIF subset (`grammar.CLIF_SUBSET_EBNF`) re-authored as GBNF
-- llama.cpp's own grammar-constrained-decoding format, a distinct dialect
from this module's CLIF EBNF (its own comment-syntax, literal-string
quoting, and character-class rules), per docs/backlog/0007's step 3 and
its "Open questions" section's own observation that "`llama.cpp`'s own
constrained-decoding dialect is GBNF, not k0mmand3r's x-grammar."

GBNF syntax grounding: llama.cpp's own grammar documentation and shipped
example grammars (`grammars/README.md`, `grammars/json.gbnf` in the
llama.cpp repo, https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md,
current at implementation time 2026-08-13) -- `::=` productions, `"..."`
literals, `[...]` character classes, `|` alternation, `*`/`+`/`?`
repetition, and (critically, confirmed from `json.gbnf`'s own explicit
`ws` rule between every token) that GBNF does **not** implicitly skip
whitespace between tokens the way EBNF-with-a-separate-lexer does --
every place two tokens can be separated by whitespace needs an explicit
`ws` reference in the rule, or the grammar will reject real spaced-out
CLIF text. That is the one substantive translation step from the CLIF
EBNF above (which relies on a tokenizer to strip whitespace first): this
grammar inlines whitespace-skipping at every join point instead.

Two gotchas found by direct trial against the live server (neither
documented in the README skimmed above, both discovered by a real HTTP
400 -- `{"error":{"message":"failed to parse grammar"}}` -- at
implementation time, isolated by bisecting a minimal grammar against the
live `/completion` endpoint until each one broke in isolation):

1. A backslash-escaped literal `-` inside a `[...]` character class
   (`[A-Za-z0-9_\-]`, the usual regex-flavoured way to write "underscore
   or hyphen") makes llama.cpp's grammar parser reject the whole grammar.
   Placing the `-` unescaped at the end of the class instead
   (`[A-Za-z0-9_-]`) parses and behaves correctly -- that is the form
   used below.
2. **Alternatives (`|`) cannot start a continuation line.** The common
   BNF pretty-printing style --
       sentence ::= atomic-sentence
                  | and-sentence
   -- fails to parse for this server's grammar loader; every alternative
   for a rule must appear on the rule's own `::=` line. (Confirmed with a
   two-line isolated repro: `a ::= "x"\n | "y"` fails, `a ::= "x" | "y"`
   on one line succeeds.) This is *not* how the CLIF EBNF in `grammar.py`
   is laid out -- that file uses the conventional multi-line style
   because it's read by humans and a Python string, never fed to
   llama.cpp -- so this is a genuine, GBNF-specific formatting
   constraint the CLIF-to-GBNF translation had to account for, not a
   cosmetic choice.

Both are left in as real findings for the next person authoring GBNF from
a regex/BNF background -- this repo did not find either documented
up front.

The `root` rule name is required by llama.cpp's grammar loader (the
server's `grammar` request field is compiled starting from `root`).
"""
from __future__ import annotations

from typing import Final

CLIF_SUBSET_GBNF: Final[str] = r"""
root        ::= ws sentence ws

sentence    ::= atomic-sentence | and-sentence | if-sentence | forall-sentence | exists-sentence

atomic-sentence ::= "(" ws name (ws term)* ws ")"

and-sentence    ::= "(" ws "and" (ws sentence)+ ws ")"
if-sentence     ::= "(" ws "if" ws sentence ws sentence ws ")"
forall-sentence ::= "(" ws "forall" ws bindings ws sentence ws ")"
exists-sentence ::= "(" ws "exists" ws bindings ws sentence ws ")"

term        ::= name | numeral | function-term
function-term ::= "(" ws name (ws term)+ ws ")"

bindings    ::= "(" ws binding (ws binding)* ws ")"
binding     ::= name | "(" ws name ws name ws ")"

name        ::= [A-Za-z] [A-Za-z0-9_-]*
numeral     ::= [0-9]+

ws          ::= [ \t\n]*
"""
