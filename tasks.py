from invoke import Context, task


@task  # type: ignore[misc]
def build(context: Context) -> None:
    """
    Build a package.
    """
    context.run("poetry build")


@task  # type: ignore[misc]
def type_check(context: Context) -> None:
    """
    Run type-checking.
    """
    context.run("poetry run mypy .")
