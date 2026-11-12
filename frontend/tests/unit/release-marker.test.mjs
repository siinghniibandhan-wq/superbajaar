import test from "node:test";
import assert from "node:assert/strict";

test("canonical frontend build embeds the exact Amplify commit marker", async () => {
  const previousAwsCommitId = process.env.AWS_COMMIT_ID;
  const previousGithubSha = process.env.GITHUB_SHA;
  process.env.AWS_COMMIT_ID = "a".repeat(40);
  delete process.env.GITHUB_SHA;

  try {
    const { default: config } = await import("../../vite.config.js?release-marker-test");
    const marker = config.plugins.find(plugin => plugin.name === "super-bajaar-release-marker");

    assert.ok(marker, "frontend Vite config must install the release marker plugin");
    const html = marker.transformIndexHtml("<html><head></head><body></body></html>");
    assert.match(html, /<meta name="sb-release" content="a{40}"\s*\/>/);
  } finally {
    if (previousAwsCommitId === undefined) delete process.env.AWS_COMMIT_ID;
    else process.env.AWS_COMMIT_ID = previousAwsCommitId;
    if (previousGithubSha === undefined) delete process.env.GITHUB_SHA;
    else process.env.GITHUB_SHA = previousGithubSha;
  }
});
