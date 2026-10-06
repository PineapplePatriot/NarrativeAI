# Putting NarrativeAI online (Railway)

About 15 minutes of clicking, about $5 a month. You end up with a link like
`https://narrativeai-production.up.railway.app` and a demo account for graders.

**Why Railway:** it builds the app straight from the GitHub repo and gives it a **volume**: a disk that
survives restarts and updates. The app keeps its database, chats and pictures there. Most free hosts wipe
their disk on every restart, which would lose all of that.

Do this after the pull request is merged, so Railway builds the finished version.

## 1. Account

1. Go to <https://railway.com> and sign in with GitHub.
2. Pick the **Hobby** plan ($5 a month, which includes $5 of usage; this app should stay within it).
3. When asked, let Railway see the `NarrativeAI` repository.

## 2. The project

1. **New Project → Deploy from GitHub repo →** `PineapplePatriot/NarrativeAI`.
2. Railway finds the `Dockerfile` and starts building. The first build fails or keeps restarting until
   steps 3 and 4 are done; that's expected.

## 3. The disk (volume)

1. On the project canvas, right-click the NarrativeAI service → **Attach volume**.
2. Mount path: `/data`. Size: the smallest is plenty.

## 4. Settings (variables)

Open the service → **Variables** → add these. Values you make up yourself are marked *(yours)*.

| Name | Value |
|---|---|
| `DJANGO_DEBUG` | `0` |
| `DJANGO_SECRET_KEY` | *(yours)* a long random string, 50+ characters. A password manager's generator works; never reuse it anywhere. |
| `NARRATIVE_DATA_DIR` | `/data` |
| `DEMO_PASSWORD` | *(yours)* the password graders will type |
| `DEMO_OPENROUTER_KEY` | *(optional)* an OpenRouter key just for the demo (see below) |
| `DEMO_MODEL` | *(optional)* defaults to `mimo-v2-6-pro`; any file name in `narrative/mainapp/data/models/` without `.json` |

Type these into Railway only, never into a chat (including with Bulba or with me).

**The demo key.** Without it, graders log in and are asked for their own OpenRouter key. With it, they can
chat straight away on your money, so make a **separate key** at <https://openrouter.ai/keys> and give it a
**credit limit** there (for example $10). The app's own monthly limit ($25) also applies, and it's shared
by everyone using the demo account.

## 5. The link

1. Service → **Settings → Networking → Generate Domain**. That's your link.
2. Railway redeploys. In **Deployments → View logs** you should see
   `Demo account 'demo' ready` and then gunicorn starting.

Open the link, log in as `demo` with your `DEMO_PASSWORD`, and check a chat reply arrives.

## What graders get

- **Link:** the domain from step 5
- **Login:** `demo` / your `DEMO_PASSWORD`
- A starter preset for the demo model and a demo character, Il Dottore (Genshin Impact, after version 6.6),
  with a full card, a lorebook, all nine mood pictures and a theme (background, music, dialogue colour). They
  can also register their own account and go through Bulba's setup.
- If the demo account was made before Dottore was added, it keeps Rose and gets Dottore on the next deploy.
- A guide at `/main/guide/` (also linked from the login page and the top bar): what to try in five minutes.

## Updating

Every push to the main branch rebuilds and redeploys by itself. The volume (database, chats, pictures)
stays. Database changes (migrations) run automatically on start.

## If something goes wrong

- **"Bad Request (400)":** the domain isn't known yet; redeploy once after generating it.
- **Everything vanished after an update:** the volume isn't attached at `/data`, or `NARRATIVE_DATA_DIR`
  is missing.
- **Replies never arrive:** check the demo key and its credit limit on OpenRouter, and the logs.
- **Pictures or voices missing:** they live on the volume; files from your own computer aren't uploaded.
  Add them again through the app.
