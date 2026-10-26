# Token usage dashboard — static version

`index.html` is a **fully self-contained** dashboard. Open it and drop your
Claude Code logs onto it (the `~/.claude/projects` folder, or any `.jsonl`
files). All parsing and cost estimation happen **in your browser** — nothing is
uploaded anywhere, and there is no server.

## Use it without hosting

Just open `docs/index.html` in a browser (double-click it, or File → Open).
Then click **Load folder** and pick your `~/.claude/projects` folder.

## Host it on GitHub Pages (shareable URL)

1. Push this branch to GitHub.
2. Repo **Settings → Pages**.
3. Under **Build and deployment → Source**, choose **Deploy from a branch**.
4. Pick this branch and the **/docs** folder, then **Save**.
5. After a minute it's live at `https://<your-user>.github.io/<repo>/`.

The hosted page still reads logs only from *your* machine when you load them —
your usage data never goes to GitHub or anyone else.

## Seeing new chats (live refresh)

In Chrome or Edge, click **Connect folder** and pick your `~/.claude/projects`
folder. The **↻ Refresh** button then re-reads that folder so chats you've had
since you loaded it show up, and **Auto** re-reads every 30s/1m/5m. The folder
reconnects on your next visit (one click to re-grant access). Other browsers
fall back to **Pick files** / drag-and-drop, which load a one-time snapshot.

Only Claude Code sessions saved on this computer (`~/.claude/projects`) appear.
Sessions you run on the web/cloud aren't stored locally, so they won't show here.
