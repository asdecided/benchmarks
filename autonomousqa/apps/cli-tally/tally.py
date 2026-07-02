#!/usr/bin/env python3
"""tally — a frozen sample CLI for the autonomousqa benchmark.

A stateless number cruncher: every invocation reads its arguments, prints a
result, and exits. Stdlib only; frozen once published.

Exit codes: 0 success, 2 usage error (bad subcommand or non-numeric input).
"""
import json
import sys

VERSION = "tally 1.0.0"
USAGE = """usage: tally.py <command> [--json] <numbers...>

commands:
  sum    print the total of the numbers
  stats  print count, min, max, and sum
  sort   print the numbers in ascending order
  --version  print the tool version
"""


def parse_numbers(raw: list[str]) -> list[int]:
    numbers = []
    for token in raw:
        try:
            numbers.append(int(token))
        except ValueError:
            print(f"tally: '{token}' is not a number", file=sys.stderr)
            raise SystemExit(2)
    return numbers


def main(argv: list[str]) -> int:
    if not argv:
        print(USAGE, file=sys.stderr, end="")
        return 2
    if argv[0] in ("--version", "-V"):
        print(VERSION)
        return 0
    command = argv[0]
    rest = argv[1:]
    as_json = "--json" in rest
    rest = [a for a in rest if a != "--json"]
    if command not in ("sum", "stats", "sort"):
        print(f"tally: unknown command '{command}'", file=sys.stderr)
        return 2
    if not rest:
        print(f"tally: {command} needs at least one number", file=sys.stderr)
        return 2
    numbers = parse_numbers(rest)
    if command == "sum":
        result = {"sum": sum(numbers)}
        print(json.dumps(result) if as_json else str(result["sum"]))
    elif command == "stats":
        result = {
            "count": len(numbers),
            "min": min(numbers),
            "max": max(numbers),
            "sum": sum(numbers),
        }
        print(json.dumps(result) if as_json
              else f"count={result['count']} min={result['min']} max={result['max']} sum={result['sum']}")
    else:  # sort
        ordered = sorted(numbers)
        print(json.dumps({"sorted": ordered}) if as_json else " ".join(str(n) for n in ordered))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
