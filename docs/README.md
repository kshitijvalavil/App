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
