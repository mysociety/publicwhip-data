import rich_click as click
from .process import fetch_and_move_pw


@click.group()
def cli():
    pass


def main():
    cli()


@cli.command()
def download():
    fetch_and_move_pw()


if __name__ == "__main__":
    main()
