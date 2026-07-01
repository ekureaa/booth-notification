import argparse
from pathlib import Path

from target_config import (
    DEFAULT_SECRETS_FILE,
    DEFAULT_TARGETS_FILE,
    load_secrets,
    load_targets,
    print_targets,
    save_secrets,
    save_targets,
)


def prompt_target_number(target_count: int) -> int | None:
    while True:
        answer = input("削除する番号（qでキャンセル）: ").strip().lower()
        if answer in {"q", "quit"}:
            return None
        try:
            index = int(answer) - 1
        except ValueError:
            index = -1
        if 0 <= index < target_count:
            return index
        print(f"1から{target_count}までの番号を入力してください。")


def confirm_removal(target: dict, remove_secret: bool) -> bool:
    print("\n削除対象")
    print(f"  Webhook名: {target.get('webhook_name', '不明')}")
    print(f"  URL: {target.get('url', '不明')}")
    print(f"  ローカルSecretも削除: {'はい' if remove_secret else 'いいえ'}")
    while True:
        answer = input("本当に削除しますか？ [y/N]: ").strip().lower()
        if not answer or answer in {"n", "no"}:
            return False
        if answer in {"y", "yes"}:
            return True
        print("y または n で回答してください。")


def remove_target(path: Path, secrets_path: Path) -> bool:
    data = load_targets(path)
    secrets = load_secrets(secrets_path)
    targets = data["targets"]
    print_targets(targets)
    if not targets:
        return False

    index = prompt_target_number(len(targets))
    if index is None:
        print("削除をキャンセルしました。")
        return False

    target = targets[index]
    webhook_name = target.get("webhook_name")
    webhook_is_still_used = any(
        other_index != index
        and isinstance(other_target, dict)
        and other_target.get("webhook_name") == webhook_name
        for other_index, other_target in enumerate(targets)
    )
    remove_secret = webhook_name in secrets and not webhook_is_still_used

    if not confirm_removal(target, remove_secret):
        print("削除をキャンセルしました。")
        return False

    targets.pop(index)
    if remove_secret:
        del secrets[webhook_name]

    save_targets(path, data)
    if remove_secret:
        save_secrets(secrets_path, secrets)
    print(f"{path} から削除しました。")
    if remove_secret:
        print(f"{secrets_path} からWebhook URLを削除しました。")
    elif webhook_is_still_used and webhook_name in secrets:
        print("同じWebhook名を使うターゲットが残るため、Secretは保持しました。")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BOOTH監視URLを選択して削除します。"
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_TARGETS_FILE,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--secrets-file",
        type=Path,
        default=DEFAULT_SECRETS_FILE,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    try:
        remove_target(args.file, args.secrets_file)
    except (KeyboardInterrupt, EOFError):
        print("\n削除をキャンセルしました。")


if __name__ == "__main__":
    main()
