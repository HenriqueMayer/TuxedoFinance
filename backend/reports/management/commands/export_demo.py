"""Export the data of the public demonstration. See ``reports.demo``."""

from django.core.management.base import BaseCommand, CommandError

from reports import demo


class Command(BaseCommand):
    help = (
        "Create a fictional owner in an EMPTY database and write the answers of the API "
        "that the public demonstration serves. Use a temporary data directory."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="The JSON file to write.")
        parser.add_argument("--language", choices=sorted(demo.TEXTS), default="en")

    def handle(self, *args, path, language, **options):
        try:
            count = demo.write(language, path)
        except RuntimeError as error:
            raise CommandError(str(error)) from None
        self.stdout.write(f"{count} answers written to {path} ({language}).")
