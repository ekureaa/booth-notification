interface Env {
  GITHUB_TOKEN: string;
}

interface ScheduledController {
  cron: string;
  scheduledTime: number;
}

interface ExecutionContext {
  waitUntil(promise: Promise<unknown>): void;
}

const DISPATCH_URL =
  "https://api.github.com/repos/ekureaa/booth-notification/actions/workflows/booth-watch.yml/dispatches";

async function dispatchWorkflow(env: Env): Promise<void> {
  const response = await fetch(DISPATCH_URL, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      "Content-Type": "application/json",
      "User-Agent": "booth-notification-dispatcher",
      "X-GitHub-Api-Version": "2026-03-10",
    },
    body: JSON.stringify({ ref: "main" }),
  });

  const responseBody = await response.text();
  if (!response.ok) {
    throw new Error(
      `GitHub workflow dispatch failed (${response.status}): ${responseBody}`,
    );
  }

  let responseData: unknown;
  if (responseBody) {
    try {
      responseData = JSON.parse(responseBody);
    } catch {
      responseData = responseBody;
    }
  }

  console.log("GitHub workflow_dispatch accepted", {
    status: response.status,
    scheduledAt: new Date().toISOString(),
    response: responseData,
  });
}

export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<void> {
    console.log("Cron Trigger received", {
      cron: controller.cron,
      scheduledTime: new Date(controller.scheduledTime).toISOString(),
    });
    await dispatchWorkflow(env);
  },
};
