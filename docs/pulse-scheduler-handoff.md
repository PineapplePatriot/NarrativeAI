# Pulse: agenda, invitations, chat reminders and VN handoff

Implemented on `codex/screen-home-and-apps`, extending the existing Screen/VN work.
No live provider calls were used for verification. No production deployment was made.

## User flow

1. In Pulse, choose a story/chat and create a one-off plan. Set its time, place,
   purpose, duration, participants, and clock. All dates are shown in the device's
   timezone; the request carries an aware instant and an IANA timezone name.
2. Record an agreement already reached in chat, or press **Send invitation to chat**.
   Sending is free: it posts the invitation as the user's message/file in that chat.
3. **Get character replies** makes one request to the main chat model with the
   source chat's persona, cards, lore and writing rules. Each selected character
   must return one accepted, tentative or declined reply. Valid replies are posted
   together in chat. All accepted confirms the plan; any decline marks it declined;
   other valid combinations are tentative. No reply model call runs automatically.
4. For a confirmed plan, **Prepare VN scene** opens the normal launch form for free.
   It carries the saved plan's cast, time, location and purpose. Actual **Launch**
   uses normal VN generation. Missing image generation defaults off. Existing writing,
   roleplay/directing, and response-mode controls remain available.
5. Optional chat reminders run only for confirmed plans. A reminder is a system
   message with **View plan**, not a generated character reply. The plan can also
   open its source chat. Older `[EVENT]` notes can seed a new plan, but users must
   choose a date and save it before an informal note becomes scheduled.

The agenda groups Today, Upcoming, Earlier and closed plans according to each
plan's clock. It shows status and Real/Story labels. Home counts exclude declined,
cancelled and completed plans.

## Clock and state semantics

- **Real time** follows server time, independently of the phone's story offset.
- **Story clock** follows that chat's existing `clock_offset`, including later
  clock changes. Moving one chat's clock cannot move another chat's reminder.
- Nonexistent local times during a DST jump are rejected by the UI. Repeated hours
  use the browser's native offset choice. The API accepts an explicit aware instant
  and validates the IANA zone. Editing preserves seconds and sub-second instants
  when the displayed second was not changed.
- Time, place, duration, title, purpose or participant changes reset invitation
  replies and return a live plan to Planned. Confirm it again after an agreement.
  Changing just a reminder lead time does not invent new RSVPs.
- Cancelling, completing, declining or unconfirming disables delivery. Expired
  reminders for events whose duration has ended are skipped, without inventing
  attendance or marking the plan completed.
- Starting a VN freezes a plan snapshot and uses only its selected participants.
  The phone clock and calendar completion status stay unchanged. Later calendar
  edits do not rewrite an episode in progress. An open episode must be parked or
  finished before preparing another one.
- Model replies are generated outside the write transaction. A conditional revision
  update prevents a late response from confirming a rescheduled plan or posting
  obsolete replies. Invalid/partial model replies leave the invitation unchanged.

## Scheduling and deployment

Migration `0043_pulse_reminders` adds one persisted reminder record per plan.
The source plan remains a `ScreenEntry`; old plans acquire scheduler metadata when
saved. Existing plans do not suddenly gain reminders: the default is Off.

The record stores due time, clock, source revision, enable state, a schedule
fingerprint, delivery time and last-check time. Claiming delivery and appending the
chat message commit in one transaction. Repeated ticks do not duplicate a reminder;
minor saves preserve its delivery marker. Rescheduling replaces the due time.
The bounded worker rotates checks for future story-clock jobs and ignores real-time
jobs that are not due yet.

From `narrative`, the commands are:

```sh
python manage.py pulse_tick                 # one pass, all users
python manage.py pulse_tick --user-id 42     # one account
python manage.py pulse_tick --watch         # continuous timer, normally every 60 seconds
python manage.py pulse_tick --watch --interval 30 --limit 200
```

The Docker image now starts `scripts/start-server.sh`: migrations, the existing
seed step, a Pulse watch process, and the existing Gunicorn configuration. Both
processes use the same `NARRATIVE_DATA_DIR` / SQLite disk. Shutdown forwards signals
and waits for both children; a failed migration starts neither. Watch mode logs
and retries transient tick failures. The image installs `tzdata` for named zones.
A deployment that overrides Docker's CMD must also run the timer against the same
database. Do not put a second service on an independent SQLite disk.

The authenticated messenger poll and a visible-Screen minute tick also perform a
free per-account pass. The manual **Check due reminders** button is useful for
verification. Offline delivery comes from the server process, so it does not rely
on an open browser. This creates unread TeleChat messages; browser-closed OS push
notifications are not implemented. Delivery latency is approximately one timer
interval plus processing time, not an exact-second service.

## Integration touchpoints

- `pulse.py`: validation, invite/reply workflow, scene snapshots and delivery.
- `screen_apps.py`: event save hooks, scheduler status in payloads, Pulse actions.
- `pulse.js`: editor, agenda, invitation controls and visible-Screen timer.
- `messenger.js`: reminder links and a refresh that cannot override a chat switch
  already in flight. Normal text generation still lives in TeleChat.
- `vn_scenes.py` / `vn_scenes.js` and the VN view: free preparation followed by a
  server-validated, exact-cast launch; calendar context is frozen at launch.
- Docker/startup command: offline scheduling on the shared database.

If Claude adds a concurrent migration with the same number, rename this migration
or add a merge migration before integrating. No app settings JSON is replaced by
Pulse saves. Custom user themes, recurring plans, per-character routine editors,
automatic character-authored reminders and external calendar integrations are
follow-up work. Current Screen list limits (200 entries per chat) still apply.

## Verification

The affected backend suite passes **143 tests**, including free/idempotent delivery,
clock changes, expiry/cancellation, revision conflicts, cast/owner validation,
model-response validation and the scheduled-scene context.

From `narrative`:

```sh
../.venv-pinned/bin/python manage.py test mainapp.test_pulse mainapp.test_screen_apps mainapp.test_screen_lore mainapp.test_vn_workflow mainapp.test_vn_scenes mainapp.test_messenger mainapp.test_messenger_actions mainapp.tests.BulbaTextingTests
```

For a fresh disposable browser fixture, create a data directory and migrate it.
Run `scripts/seed_screen_workflow.py`, then `scripts/seed_pulse_workflow.py` through
`manage.py shell`. Run `scripts/run_pulse_browser_server.py` through the same shell
with the same `NARRATIVE_DATA_DIR`; it binds `127.0.0.1:8767`. This stand-in server
replaces invitation and scene generation, and blocks other model/image requests.
Then, from the repository root:

```sh
VN_TEST_URL=http://127.0.0.1:8767 VN_TEST_SESSION_FILE=/tmp/narrative-pulse-check/browser-session.json CHROMIUM_PATH=/usr/bin/chromium node scripts/check_pulse_workflow.cjs
.venv-pinned/bin/python scripts/check_server_start.py
```

The browser check covers the full invite → reply → VN flow, unsaved-input and
active-episode guards, free preparation, duplicate-free reminders, direct plan
links, chat-note import, and reminders arriving during a chat switch at 390/1280px.
The startup smoke test covers migration failure, web-exit cleanup and termination
of both web and timer processes. Existing mini-app, VN/lore workflow and edge
browser checks also pass against a normal disposable server.
