# Cloudflare Worker dispatcher

Cloudflare Workers Cron TriggersからGitHub Actionsの`workflow_dispatch`を実行する。
アプリ本体の設定と操作方法は[../README.md](../README.md)を参照する。

## 1. GitHub tokenを作成

Fine-grained personal access tokenを次の設定で作成する。

- Repository access: `Only select repositories` → `booth-notification`
- Repository permissions: `Actions` → `Read and write`

## 2. WorkerへSecretを登録

```bash
cd cloudflare
npm install
npx wrangler login
npx wrangler secret put GITHUB_TOKEN
```

## 3. デプロイ

```bash
npm run check
npm run deploy
```

現在の設定では毎時0分（`0 * * * *`、UTC）に実行する。
