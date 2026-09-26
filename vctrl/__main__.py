import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="vctrl", description="Virtual control software")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("run", help="headless tracking loop (added in A13)")
    sub.add_parser("record", help="record fixture sessions (added in A5)")
    sub.add_parser("replay", help="replay a fixture session (added in A12)")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(f"command {args.command!r} not implemented yet (Plan A in progress)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
