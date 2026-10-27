"""Insert only the known synthetic fixture into an explicitly confirmed target."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection, transaction

from app.dbmodels.models import Game, Player, Possession, Team
from app.demo_data import build_demo_data, validate_demo_data

GROUPS = (("teams", Team), ("games", Game), ("players", Player), ("possessions", Possession))

def _normal(value):
    return json.loads(json.dumps(value, default=str))

def _matches(data):
    for name, model in GROUPS:
        fields = list(data[name][0]) if data[name] else ["id"]
        actual = sorted((_normal(row) for row in model.objects.values(*fields)), key=lambda r: r["id"])
        expected = sorted((_normal(row) for row in data[name]), key=lambda r: r["id"])
        if actual != expected:
            return False
    return True

class Command(BaseCommand):
    help = "Load the independently authored synthetic demo without deleting existing data."

    def handle(self, *args, **options):
        cfg = connection.settings_dict
        name = cfg.get("NAME", "")
        if (settings.APP_ENV not in {"local", "test"} or
            cfg.get("HOST") not in {"localhost", "127.0.0.1", "::1"} or
            not name.startswith("lineup_demo") or
            settings.DEMO_DATABASE_CONFIRMED != name):
            raise CommandError("Demo loading requires an explicitly confirmed disposable local/test target")
        try:
            data = build_demo_data()
            validate_demo_data(data)
        except (ValueError, KeyError, TypeError):
            raise CommandError("Synthetic fixture validation failed; no rows were changed") from None
        try:
            with transaction.atomic():
                # Serialize loaders and block concurrent writes while checking exact content.
                # No SQL contains input or connection values.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT to_regnamespace('app') IS NOT NULL")
                    if not cursor.fetchone()[0]:
                        raise CommandError("Provision the app schema before loading data")
                    cursor.execute("LOCK TABLE app.team, app.game, app.player, app.possession IN EXCLUSIVE MODE")
                if _matches(data):
                    self.stdout.write("Synthetic fixture already present; no rows changed.")
                    return
                if any(model.objects.exists() for _, model in GROUPS):
                    raise CommandError("Existing application data differs; no rows were changed")
                for name, model in GROUPS:
                    model.objects.bulk_create([model(**row) for row in data[name]])
                self.stdout.write("Loaded 3 synthetic teams, 21 players, 3 games and 36 possessions.")
        except DatabaseError:
            raise CommandError("Demo loading failed; the transaction was rolled back") from None
