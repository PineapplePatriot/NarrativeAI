# Screen home and mini-apps: first working release

Branch: `codex/screen-home-and-apps`, built on VN commit `a181847`.
This branch includes the VN work Claude has not reviewed yet. It does not replace
Claude's current Screen/TeleChat branch. Gemini's Subtext was already present in
`feature/digital-screen-telechat` / the VN baseline; its generation behaviour is unchanged.

## What is implemented

Screen opens on a responsive launcher, with eight apps: TeleChat, Scenes, Subtext,
Drive, Mail, Wave, Pulse, and Moments. It has four gradient palettes and three GPT-generated illustrated wallpapers, a device-local
clock, recent conversations, and counts of saved work. The mobile dock remains
available while a conversation is open. On phones it shows Home, Chats, Scenes
and Alerts; other apps open through Home rather than a scrolling row of ten icons. Opening Home does not mark an unopened
chat as read. Existing `?thread=…` and `?char=…` links still open TeleChat directly;
`?app=messenger`, `?app=files`, etc. open a named app.

- **Drive:** editable private scratchpads and documents explicitly shared with one
  chat. Shared documents are included in that chat's text-generation context;
  private notes are excluded. A copy can be sent to TeleChat after confirmation.
  The chat archive shows delivered files, photos and voice transcripts/audio with
  links to their source messages. Existing account-wide personal notes remain
  readable in a separate tab. They are not automatically shared with characters.
  A shared document can invite an edit from a character in its chat. The labelled
  request makes one model call against the saved version and stores a proposal,
  without updating the document or chat facts. Review the before/replacement text,
  optionally edit the replacement, then apply or reject it. Applying requires an
  unchanged document revision and no unsaved local changes. Stale proposals must
  be rejected or replaced by a fresh request. Accepted/rejected proposals keep
  their author, base revision and before/after text. The latest 30 proposals per
  chat are listed; older proposals remain stored.
- **Mail:** subjects with persisted correspondence. Write and send a letter, or
  explicitly request one character's reply using model tokens. Generated replies
  are editable local previews until delivered. Mail uses the source chat's cards,
  persona, lore and model writing rules, followed by an email presentation contract.
  Correspondence is separate from TeleChat until explicitly forwarded. There is no
  real email service, address book, CC/BCC, or implied read receipt.
- **Pulse:** one-off agendas with real/story clocks, selected participants, invitation
  replies and recorded status. Confirmed plans can prepare a VN launch with their
  exact cast, time, place and purpose, and opt into free chat reminders. The server
  timer supports offline delivery; older informal chat event notes can seed a dated
  plan after user review. See `pulse-scheduler-handoff.md` for state and clock rules.
- **Wave:** persisted track titles, artists, links and mood notes, plus the source
  chat's existing voice archive. Songs open on their external service. Saved voice
  audio uses native controls and no autoplay. Missing audio/photos link back to
  their original message; opening Wave does not generate replacements. Sending a
  track to TeleChat shares a text snapshot without generating a response.

The new apps each have an explicit Story / chat selector. Changing it does not
silently change the open TeleChat conversation. New app drafts retain their text
across app switches, chat switches and request failures, using the existing
account-namespaced session-draft store. Blocked storage falls back to memory with
a copy-before-reload message. A saved document must be selected again after a full
page reload to recover its local draft. Conflicts retain local input and expose
the current server version; loading it requires confirmation.
App lists are cached while switching apps. Use Refresh for other-tab changes;
refreshing retains the local draft and its original revision, so it cannot silently
overwrite a newer saved version.

## Data and integration

Migration `0041_screen_entries` adds `ScreenEntry`, with owner, chat, kind, revision,
text and app-specific data. Deleting a source chat cascades its app records.
Records are separate from `ChatSettings.appearance`, so saving an app does not
rewrite TeleChat, Subtext, or VN settings. API requests filter by both user and chat.
Conditional revision updates prevent concurrent editors from silently overwriting
one another. Mail preview revisions also prevent delivering an outdated preview.
Migration `0042_document_proposals` adds the server-side proposal records. They
are scoped through their source document and cascade when it is deleted. Applying
and marking a proposal reviewed commit together, preventing duplicate acceptance.

The template includes `partials/screen_apps.html`, `screen_home.css`, and
`screen_home.js`. The script wraps the existing app-switch function after the
Subtext/VN hooks have registered. It preserves those hooks. Small shared touchpoints:

1. New models/migration and route `screen/apps/api/`.
2. Template app dock, partial, script and endpoint URL.
3. `messenger.build_messenger_prompt`: append `screen_apps.context_for(thread)`.
4. `screen_hub`: clear unread only when actually opening TeleChat.

If Claude creates another `0041` migration, rename this migration before merging,
or create a merge migration with both leaves. No production migration or deployment
has been performed here. Apply migrations before opening the new apps.

## Deliberately deferred

Pulse's server timer delivers system reminders without model calls. Recurring
plans, routine editors, automatic character-authored calls/messages, trust unlocks
and external calendar integrations remain follow-up work. Character document
edits still require a user request and review.

No CC/BCC mail audiences yet: correspondence belongs to the selected chat's cast.
Mail previews spend one model call only on the labelled button; model quality has
not been tested with paid requests. Shared document context currently feeds TeleChat. Pulse plans have a dedicated
historical snapshot when they launch a VN episode.

The archive is a live view of source messages, not a durable duplicate backup;
deleting a message removes its archive item. It displays the latest 200 media
attachments. Record lists display the latest 200 entries per chat with an explicit
notice when more exist. Older records remain stored; pagination/search is a
follow-up before large histories. Home counts include all saved records.

## Verification

From `narrative`:

```sh
../.venv-pinned/bin/python manage.py migrate --noinput
../.venv-pinned/bin/python manage.py test mainapp.test_screen_apps mainapp.test_screen_lore mainapp.test_vn_workflow mainapp.test_vn_scenes mainapp.test_messenger mainapp.test_messenger_actions mainapp.tests.BulbaTextingTests
```

Use the disposable database/session instructions in `vn-episodes-handoff.md`, then
run from the repository root (replace the URL/fixture directory as appropriate):

```sh
VN_TEST_URL=http://127.0.0.1:8766 VN_TEST_SESSION_FILE=/tmp/narrative-home-check/browser-session.json CHROMIUM_PATH=/usr/bin/chromium node scripts/check_screen_home.cjs
```

The browser check exercises Home, wallpaper, Drive creation and draft recovery,
chat isolation, failed/conflicting saves, delayed refreshes, navigating during mail
generation, mail previews and delivery, calendar plans, and Wave
at 390px and 1280px. Model requests are mocked/blocked. Existing integrated VN and
lore/browser edge checks also run with `?app=messenger` so their direct-chat entry
point remains explicit.

The affected backend suite passes 143 tests, including preservation of unread
messages when opening Home. App model/audio validation used mocked responses. The wallpaper assets were
generated separately with the image-generation tool; no OpenRouter generations
were used for validation.

To verify Drive proposals in the disposable fixture, seed with
`scripts/seed_drive_proposals.py` through `manage.py shell` (as for the main fixture),
then run `scripts/check_drive_proposals.cjs` with the same `VN_TEST_URL`,
`VN_TEST_SESSION_FILE`, and `CHROMIUM_PATH`. It checks reviewed replacements,
unsaved-input guards, persistence, stale proposals, and rejection at both widths.


## Visual alignment and wallpapers

Screen now loads NarrativeAI's shared `base.css` and uses its purple primary
buttons, title treatment, card radius, borders and panel colours in the new apps.
This is visual alignment; custom user themes remain a separate future feature.
The static wallpaper pack lives under `mainapp/img/screen-wallpapers` with a source
README. All three images total about 230 KB as WebP; no generation occurs on selection.
Wallpaper choices are validated, scoped by account in local storage, and also
retained in the session draft fallback. Unknown saved values fall back to Dusk;
blocked storage still allows changing the wallpaper for the current page.

Layout fixes include a four-column launcher at tablet widths, bounded widgets for
long chat names, phone-sized touch controls and safe-area spacing, a Home action
that returns to the top, stable app-tile keyboard focus during background updates,
and collapsed history for already reviewed document proposals.

Run `scripts/check_screen_wallpapers.cjs` with the same fixture environment to
verify assets, layout, focus, persistence and storage denial at 320, 390, 768,
1024 and 1280 px. The mini-app, Drive proposal, VN/lore workflow and edge browser
checks also pass at phone/desktop widths. The 124-test backend baseline was unchanged
by this visual pass.

Pulse scheduler and VN integration details: [pulse-scheduler-handoff.md](pulse-scheduler-handoff.md).
