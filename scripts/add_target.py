import argparse
import getpass
import re
from pathlib import Path
from urllib.parse import urlparse

from target_config import (
    DEFAULT_SECRETS_FILE,
    DEFAULT_TARGETS_FILE,
    load_secrets,
    load_targets,
    save_secrets,
    save_targets,
)



def prompt_nonempty(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("空欄にはできません。")


def prompt_booth_url() -> str:
    while True:
        url = prompt_nonempty("BOOTHの検索・一覧URL: ")
        parsed = urlparse(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname == "booth.pm"
            and parsed.username is None
            and parsed.password is None
            and parsed.port in {None, 443}
        ):
            return url
        print("https://booth.pm/ から始まるURLを入力してください。")


def prompt_discord_webhook_url() -> str:
    while True:
        url = getpass.getpass("Discord Webhook URL（入力は表示されません）: ").strip()
        parsed = urlparse(url)
        if (
            parsed.scheme == "https"
            and parsed.hostname in {"discord.com", "discordapp.com"}
            and parsed.username is None
            and parsed.password is None
            and parsed.port in {None, 443}
            and re.fullmatch(
                r"/api/webhooks/\d+/[A-Za-z0-9._-]+", parsed.path
            )
        ):
            return url
        print("有効なDiscord Webhook URLを入力してください。")


def prompt_yes_no(label: str, default: bool) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        answer = input(label + suffix).strip().lower()
        if not answer:
            return default
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("y または n で回答してください。")


def add_target(path: Path, secrets_path: Path) -> bool:
    data = load_targets(path)
    secrets = load_secrets(secrets_path)
    webhook_name = prompt_nonempty("Webhook名: ")
    url = prompt_booth_url()
    free_only = prompt_yes_no("無料バリエーションがある商品のみにしますか？", False)

    duplicate = next(
        (
            target
            for target in data["targets"]
            if isinstance(target, dict)
            and target.get("webhook_name") == webhook_name
            and target.get("url") == url
        ),
        None,
    )
    if duplicate is not None:
        print("同じWebhook名とURLのターゲットは既に登録されています。")
        return False

    webhook_url = None
    if webhook_name in secrets:
        print(f"Webhook名 '{webhook_name}' のSecretは登録済みです。")
    else:
        webhook_url = prompt_discord_webhook_url()

    print("\n追加内容")
    print(f"  Webhook名: {webhook_name}")
    print(f"  URL: {url}")
    print(f"  無料商品のみ: {'はい' if free_only else 'いいえ'}")
    if not prompt_yes_no("この内容で追加しますか？", True):
        print("追加をキャンセルしました。")
        return False

    data["targets"].append({
        "webhook_name": webhook_name,
        "url": url,
        "free_only": free_only,
    })
    if webhook_url is not None:
        secrets[webhook_name] = webhook_url

    save_targets(path, data)
    save_secrets(secrets_path, secrets)
    print(f"{path} に追加しました。")
    if webhook_url is not None:
        print(f"{secrets_path} にWebhook URLを追加しました。")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="質問に答えてBOOTH監視URLをtargets.jsonへ追加します。"
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
        add_target(args.file, args.secrets_file)
    except (KeyboardInterrupt, EOFError):
        print("\n追加をキャンセルしました。")


if __name__ == "__main__":
    main()
