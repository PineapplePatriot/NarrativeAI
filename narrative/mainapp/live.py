"""
Work that outlives the page: a chat reply or a "Write my message" keeps going on the server when they leave the
page (another page in the app, a closed tab, a phone that slept), and the page picks it up again when they come
back.

- A reply is written by a background thread into a Job: every NDJSON line the page would have received is kept
  in order. The page that asked follows it live; a page opened later follows it from the start (the lines replay,
  then it goes on live). The thread finishes the reply and saves it whether anyone is watching or not.
- Stop asks the job to stop (its connection closing no longer does): what arrived so far is kept, as before.
- "Write my message" runs in its own request; its result is kept here until a page has put it in the box.

Jobs live in this process's memory. The app runs as one process (Dockerfile: one worker, several threads), so
every request sees the same jobs; a restart forgets them (a reply in progress is then lost, as before).
"""
import threading
import time

KEEP = 1800      # seconds a finished job is kept for a page coming back to it
IDLE = 10        # seconds of silence before a keep-alive line (the page's watchdog counts any line as life)

_jobs = {}
_lock = threading.Lock()


class Job:
    def __init__(self, kind):
        self.kind = kind
        self.lines = []          # NDJSON lines, in order (a reply)
        self.result = None       # the finished answer (a written message)
        self.done = False
        self.cancel = False      # Stop was pressed
        self.started = time.time()
        self.ended = None
        self._cond = threading.Condition()

    def put(self, line):
        with self._cond:
            self.lines.append(line)
            self._cond.notify_all()

    def finish(self, result=None):
        with self._cond:
            if result is not None:
                self.result = result
            self.done, self.ended = True, time.time()
            self._cond.notify_all()

    def follow(self, start=0):
        """Every line from `start` on, as they come, then the end (blank keep-alive lines while it's quiet)."""
        i = start
        while True:
            with self._cond:
                if i >= len(self.lines) and not self.done:
                    self._cond.wait(timeout=IDLE)
                batch, i, done = self.lines[i:], len(self.lines), self.done
            yield from batch
            if done and not batch:
                return
            if not batch and not done:
                yield "\n"


def key(user, chat, kind):
    return f"{kind}:{user.id}:{chat.id}"


def _tidy():
    now = time.time()
    for k in [k for k, j in _jobs.items() if j.done and now - (j.ended or now) > KEEP]:
        _jobs.pop(k, None)


def start(k, kind):
    """A new job under `k`, or None while one is still running there."""
    with _lock:
        _tidy()
        old = _jobs.get(k)
        if old and not old.done:
            return None
        job = _jobs[k] = Job(kind)
        return job


def get(k):
    with _lock:
        _tidy()
        return _jobs.get(k)


def running(k):
    job = get(k)
    return bool(job and not job.done)


def drop(k):
    with _lock:
        _jobs.pop(k, None)


def run_in_background(job, lines):
    """Pull `lines` (a generator) in a thread of its own, into `job`. Stop closes the generator, which keeps what
    arrived (its own GeneratorExit handling)."""
    def work():
        from django.db import close_old_connections, connection
        close_old_connections()
        try:
            for line in lines:
                if job.cancel:
                    lines.close()
                    job.put('{"type": "stopped"}\n')
                    break
                job.put(line)
        except Exception as e:  # never leave a page waiting forever
            import json
            import logging
            logging.getLogger(__name__).exception("A background reply failed")
            job.put(json.dumps({"type": "error", "error": f"Something went wrong while writing: {e}"}) + "\n")
        finally:
            job.finish()
            connection.close()
    from django.conf import settings
    if getattr(settings, "LIVE_INLINE", False):
        work_inline(job, lines)
        return
    threading.Thread(target=work, daemon=True).start()


def work_inline(job, lines):
    """The same as the thread, in this one (tests)."""
    try:
        for line in lines:
            if job.cancel:
                lines.close()
                job.put('{"type": "stopped"}\n')
                break
            job.put(line)
    finally:
        job.finish()
