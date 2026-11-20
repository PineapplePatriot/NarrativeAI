# Screen home and mini-apps: first working release

Branch: `codex/screen-home-and-apps`, built on VN commit `a181847`.
This branch includes the VN work Claude has not reviewed yet. It does not replace
Claude's current Screen/TeleChat branch. Gemini's Subtext was already present in
`feature/digital-screen-telechat` / the VN baseline; its generation behaviour is unchanged.

## What is implemented

Screen opens on a responsive launcher, with eight apps: TeleChat, Scenes, Subtext,
Drive, Mail, Wave, Pulse, and Moments. It has four wallpaper palettes, a device-local
clock, recent conversations, and counts of saved work. The mobile dock remains
available while a conversation is open. Opening Home does not mark an unopened
chat as read. Existing `?thread=…` and `?char=…` links still open TeleChat directly;
`?app=messenger`, `?app=files`, etc. open a named app.

- **Drive:** editable private scratchpads and documents explicitly shared with one
  chat. Shared documents are included in that chat's text-generation context;
  private notes are excluded. A copy can be sent to TeleChat after confirmation.
  The chat archive shows delivered files, photos and voice transcripts/audio with
  links to their source messages. Existing account-wide personal notes remain
  readable in a separate tab. They are not automatically shared with characters.
- **Mail:** subjects with persisted correspondence. Write and send a letter, or
  explicitly request one character's reply using model tokens. Generated replies
  are editable local previews until delivered. Mail uses the source chat's cards,
  persona, lore and model writing rules, followed by an email presentation contract.
  Correspondence is separate from TeleChat until explicitly forwarded. There is no
  real email service, address book, CC/BCC, or implied read receipt.
- **Pulse:** dated plans, locations, notes and planned/done status. Dates use the
  device's local time and are stored with a timezone. Open plans enter only the
  selected chat's context as plans, not evidence of attendance or present location.
  Original informal TeleChat event notes remain visible separately.
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

No scheduled/offline character calls, automatic calendar messages, invented live
locations or "currently listening" activity. Those need an explicit simulation
clock/job system, spending controls and delivery semantics. No automatic unlock of
private character scratchpads, trust score, or forced drama. Shared documents can
be edited by the user and read by characters; autonomous character edits and a
reviewable suggested-edit workflow remain follow-up work.

No CC/BCC mail audiences yet: correspondence belongs to the selected chat's cast.
Mail previews spend one model call only on the labelled button; model quality has
not been tested with paid requests. New shared document/calendar context currently
feeds TeleChat; a dedicated historical snapshot for VN remains follow-up work.

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

The affected backend suite passes 119 tests, including preservation of unread
messages when opening Home. No paid model/image/audio requests were made.
