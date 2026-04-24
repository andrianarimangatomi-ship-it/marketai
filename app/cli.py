import click
from flask.cli import with_appcontext
from app.extensions import db

@click.command()
@with_appcontext
def init_db():
    """Initialize the database."""
    db.create_all()
    click.echo('Database initialized.')

@click.command()
@with_appcontext
def drop_db():
    """Drop all tables."""
    if click.confirm('Are you sure you want to drop all tables?'):
        db.drop_all()
        click.echo('Database dropped.')

def init_app(app):
    app.cli.add_command(init_db)
    app.cli.add_command(drop_db)
