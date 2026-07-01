# booth-notification

BOOTHの検索・一覧URLを定期確認し、新着商品をDiscordへ通知します。
GitHub Actionsで動作し、Cloudflare Workerから毎時0分に起動します。

Cloudflareの設定は[cloudflare/README.md](cloudflare/README.md)を参照してください。

## 監視URLの管理

```bash
# 追加
python3 scripts/add_target.py

# 一覧
python3 scripts/list_targets.py

# 削除
python3 scripts/remove_target.py
```

追加時にWebhook名、BOOTH URL、無料商品のみにするか、Discord Webhook URLを
対話形式で入力します。

## Discord Secret

Webhook URLはGit管理対象外の`secrets.local.json`に保存されます。
同じJSONをGitHub Actions Secretの`DISCORD_WEBHOOK_URLS`にも設定してください。
JSONのキーは`targets.json`の`webhook_name`と一致させます。

```json
{
  "vrchat": "https://discord.com/api/webhooks/..."
}
```

ローカルの変更はGitHub Secretへ自動反映されません。

## 実行

GitHubの `Actions` → `BOOTH Watcher` → `Run workflow` から手動実行できます。
初めて使うWebhook名では現在の商品を既読にするだけで、通知は送信しません。
