"""
python manage.py usage_report [--days N] [--include-demo] [--csv FILE]

The usage numbers (users/usage.py): unique users, sessions and their length, who came back, messages, Bulba,
spend. --csv writes one row per user. On Railway: run it from the service's shell, or open /users/stats/.
"""
from django.core.management.base import BaseCommand

from users import usage


class Command(BaseCommand):
    help = "Print usage numbers (unique users, sessions, messages, spend)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None, help="Only the last N days of activity")
        parser.add_argument("--include-demo", action="store_true", help="Count the shared demo account too")
        parser.add_argument("--csv", default="", help="Also write one row per user to this file")

    def handle(self, *args, days=None, include_demo=False, csv="", **options):
        data = usage.report(days=days, exclude=() if include_demo else ("demo",))
        out = self.stdout
        out.write(f"Usage {'over the last ' + str(days) + ' days' if days else 'since the start'}"
                  f"{'' if include_demo else ' (without the demo account)'}\n")
        for key, value in data["summary"].items():
            out.write(f"  {key.replace('_', ' '):<26} {value}\n")
        out.write("\nActive users by day:\n")
        for day, n in data["active_by_day"][:14]:
            out.write(f"  {day}  {n}\n")
        out.write("\nPer user:\n")
        for r in data["users"]:
            out.write(f"  {r['username']:<20} days {r['active_days']:>3}  sessions {r['sessions']:>3}  "
                      f"minutes {r['minutes']:>5}  messages {r['messages']:>5}  spend ${r['spend']:.2f}\n")
        if csv:
            with open(csv, "w", encoding="utf-8", newline="") as f:
                f.write(usage.csv_text(data))
            out.write(f"\nWrote {len(data['users'])} rows to {csv}\n")
