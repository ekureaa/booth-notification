import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS_FILE = ROOT / "targets.json"
DEFAULT_SECRETS_FILE = ROOT / "secrets.local.json"


def load_targets(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("targets"), list):
        raise ValueError(f"{path}: targets must be an array")
    return data


def save_targets(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_secrets(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(
        isinstance(name, str) and isinstance(url, str)
        for name, url in data.items()
    ):
        raise ValueError(f"{path}: expected a JSON object of Webhook URLs")
    return data


def save_secrets(path: Path, secrets: dict[str, str]) -> None:
    path.write_text(
        json.dumps(secrets, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)


def print_targets(targets: list[dict]) -> None:
    if not targets:
        print("監視ターゲットは登録されていません。")
        return

    for index, target in enumerate(targets, start=1):
        free_only = "はい" if target.get("free_only") else "いいえ"
        print(f"[{index}] {target.get('webhook_name', '不明')}")
        print(f"    URL: {target.get('url', '不明')}")
        print(f"    無料商品のみ: {free_only}")
