# Operational scripts

Scripts must be explicit, safe-by-default, and require clear environment selection. Never make a script silently reset a database. Admin creation must be idempotent and must not print passwords or tokens.
