// amelia-refresh: asks GitHub to rebuild The Amelia Current on a schedule.
//
// GitHub's own scheduler runs this repository's timer hours late. A direct
// "run this workflow now" request is not delayed, so a Cloudflare Cron Trigger
// sends one every 30 minutes. The token lives in the Worker's secret
// GITHUB_TOKEN (never in this file) and can only start workflow runs on this
// one repository.

const REPO = "mcgoogs1-wq/amelia-island-scene";
const WORKFLOW = "build.yml";

export default {
  // runs on the Cron Trigger
  async scheduled(event, env, ctx) {
    ctx.waitUntil(triggerRebuild(env));
  },

  // visiting the Worker's address just shows it's alive (it does NOT trigger a rebuild)
  async fetch() {
    return new Response("amelia-refresh is running. It asks GitHub to rebuild the site every 30 minutes.\n");
  },
};

async function triggerRebuild(env) {
  if (!env.GITHUB_TOKEN) {
    console.log("GITHUB_TOKEN secret is not set");
    return;
  }
  const res = await fetch(
    `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "amelia-refresh-worker",
      },
      body: JSON.stringify({ ref: "main" }),
    }
  );
  // 204 = GitHub accepted it. Anything else is logged (Workers > Logs).
  if (res.status !== 204) {
    console.log("GitHub answered", res.status, await res.text());
  }
}
