import argparse
from pathlib import Path

from target_config import DEFAULT_TARGETS_FILE, load_targets, print_targets


def main() -> None:
    parser = argparse.ArgumentParser(description="BOOTH監視URLの一覧を表示します。")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_TARGETS_FILE,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    data = load_targets(args.file)
    print_targets(data["targets"])


if __name__ == "__main__":
    main()
