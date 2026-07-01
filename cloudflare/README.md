# Cloudflare Worker dispatcher

Cloudflare Workers Cron TriggersからGitHub Actionsの`workflow_dispatch`を実行する。

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

プロンプトへGitHub tokenを入力する。Tokenをソースコードや
`wrangler.jsonc`へ記載しないこと。

## 3. ローカルテスト

`.dev.vars`を作成して次の形式でTokenを記載する。このファイルはGitから除外される。

```dotenv
GITHUB_TOKEN="github_pat_..."
```

```bash
npm run dev
curl "http://localhost:8787/__scheduled?cron=47+*+*+*+*"
```

## 4. デプロイ

```bash
npm run check
npm run deploy
```

Cron Triggerの変更はCloudflare全体への反映に最大15分かかることがある。
