# mypy: ignore-errors
import os
import sys
from contextlib import contextmanager
from pathlib import Path

from invoke import Context, task

# Currently, some operations require a live (running)
# Django server.  In other words, these operations may
# use HTTP to connect/interact with the application.  For
# now, we'll disable these sort of operations in our
# CI platform (Github Actions).
DISABLE_IN_CI = sys.platform.startswith("linux")

GIT_ROOT = Path(__file__).resolve().parent
# Previously (and in other Django projects) we may have
# used a project sub-directory as our primary Django
# project directory.  Here, we use the git root.
# DJ_PROJECT_ROOT = GIT_ROOT / "moosedj"
DJ_PROJECT_ROOT = GIT_ROOT

DJANGO_DEBUG_ENVIRONMENT = {
    "MOOSE_DJANGO_DEBUG": "TRUE",
    "MOOSE_DJANGO_UPLOAD_PATH": str(GIT_ROOT / "local-uploads"),
    "PYTHONUNBUFFERED": "DISABLE_STDOUT_BUFFER",
    "MOOSE_DJANGO_SECRET_KEY": "changeme",
}

DOCKER_REQUIRE_EXISTING_LOCAL_DB = bool(
    os.environ.get("DOCKER_USE_EXISTING_LOCAL_DB", False)
)
LOCAL_DB_FILE = Path(DJ_PROJECT_ROOT / "db.sqlite3")


@contextmanager
def environ(env, replace=False):
    """
    A context manager to temporarily change the environment variables.

    This can be used in scenarios where you'd prepend env FOO="bar" when running a program.
    """
    # adopted from https://github.com/pyinvoke/invoke/issues/259
    original_environ = os.environ.copy()
    if replace:
        os.environ.clear()
    os.environ.update(env)
    yield
    os.environ.update(original_environ)


@task
def destroy_local_database(context):
    """
    NOTE: It can be useful to keep a local database, so that you can have some
    dummy state persisted.  For example: users accounts (admin and non-admin), as
    well as other (domain) data.
    """
    print("WARNING: Local database file (if it exists) is being removed.")
    LOCAL_DB_FILE.unlink(missing_ok=True)


@task
def initialize_local_database(context):
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(DJ_PROJECT_ROOT):
            context.run("poetry run python manage.py makemigrations")
            context.run("poetry run python manage.py migrate")
            context.run(
                'env DJANGO_SUPERUSER_PASSWORD="moosedj" poetry run python manage.py createsuperuser --username="admin" --email="noreply@moose.com" --noinput'
            )

    django_admin_check(context)


def find_local_database(context):
    local_db_exists = False
    with context.cd(DJ_PROJECT_ROOT):
        local_db_exists = LOCAL_DB_FILE.is_file()

    return local_db_exists


def ensure_local_ssl_certs_exist(context, cert_path="certs"):
    mkcert_additional_info = """

This project uses 'mkcert' to establish local trust for our docker-ized deployment.

To guarantee the project works properly, be sure you have done the following:

            1. At the bottom of your /etc/hosts file, add the following:

# Added for 'mkcert'
127.0.0.1       local.example

            1. Run 'mkcert -install' to trust your local CA

            For more information, see: https://github.com/FiloSottile/mkcert
    """

    print(mkcert_additional_info)
    if not os.path.exists(GIT_ROOT / cert_path):
        os.makedirs(GIT_ROOT / cert_path)
        print(f"Creating certificates at '{cert_path}'")
        context.run(
            f"mkcert -key-file {GIT_ROOT / cert_path}/server-key.pem -cert-file {GIT_ROOT / cert_path}/server-crt.pem local.example"
        )
    else:
        print(f"Certificates at '{cert_path}' already exist. Skipping cert creation.")


@task
def build(context: Context) -> None:
    """
    Build a package.
    """
    context.run("poetry build")


@task
def type_check(context: Context) -> None:
    """
    Run type-checking.
    """
    context.run("poetry run mypy .")


@task
def clean(context, pty=True, color=True):
    """
    Clean all __pycache__ folders.
    """
    import pathlib

    [p.unlink() for p in pathlib.Path(".").rglob("*.py[co]")]
    [p.rmdir() for p in pathlib.Path(".").rglob("__pycache__")]


@task
def run_server(context, pty=False, color=False):
    """
    Run the local, native, web server.
    """
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(DJ_PROJECT_ROOT):
            if find_local_database(context):
                print("WARNING: A local database file DOES exist.")
                context.run("poetry run python manage.py runserver")

            else:
                print("ERROR: A local database file DOES NOT exist.", file=sys.err)
                sys.exit(1)


@task
def run_dockerized_server(context, pty=False, color=False):
    """
    Run the local, dockerized, collection of web services.
    """
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(GIT_ROOT):
            docker_compose_up_cmd = (
                "docker compose up --build --abort-on-container-exit"
            )
            ensure_local_ssl_certs_exist(context, cert_path="certs")
            if DOCKER_REQUIRE_EXISTING_LOCAL_DB:
                if find_local_database(context):
                    print("WARNING: A local database file DOES exist.")
                    context.run(docker_compose_up_cmd)

                else:
                    print(
                        "ERROR: A local database file DOES NOT exist.", file=sys.stderr
                    )
                    sys.exit(1)
            else:
                context.run(docker_compose_up_cmd)


@task
def create_django_app(context):
    """
    Django sub-projects are called "apps".  This will automatically create one for you.
    """
    with context.cd(GIT_ROOT):
        context.run("poetry install")

    with context.cd(DJ_PROJECT_ROOT):
        # Add some whitespace
        print("\n\n")
        app_name = input("Give your new Django app a name: ")
        context.run(f"poetry run python manage.py startapp {app_name}")


@task
def test_show_all_pytest(context):
    """
    Display tests that pytest can execute.
    """
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(DJ_PROJECT_ROOT):
            if find_local_database(context):
                print("WARNING: A local database file DOES exist.")
                context.run("poetry run pytest --collect-only")

            else:
                print("ERROR: A local database file DOES NOT exist.", file=sys.err)
                sys.exit(1)


@task
def test_run_all_pytest(context):
    """
    Run project-wide test suite, using 'pytest'.
    """
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(DJ_PROJECT_ROOT):
            if find_local_database(context):
                print("WARNING: A local database file DOES exist.")
                context.run("poetry run pytest .")

            else:
                print("ERROR: A local database file DOES NOT exist.", file=sys.err)
                sys.exit(1)


@task
def test_run_all_unittest(context, pty=True, color=True):
    """
    Run project-wide test suite, using 'unittest'.

    More info: https://docs.djangoproject.com/en/dev/topics/testing/
    """
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(DJ_PROJECT_ROOT):
            if find_local_database(context):
                print("WARNING: A local database file DOES exist.")
            else:
                print("WARNING: A local database file DOES NOT exist.")
                initialize_local_database(context)

            context.run("poetry run python manage.py test")


@task
def test_run_one_unittest(context, filename, pty=True, color=True):
    """
    Run a given test file, using 'unittest'.

    More info: https://docs.djangoproject.com/en/dev/topics/testing/
    """
    with environ(DJANGO_DEBUG_ENVIRONMENT):
        with context.cd(DJ_PROJECT_ROOT):
            if find_local_database(context):
                print("WARNING: A local database file DOES exist.")
            else:
                print("WARNING: A local database file DOES NOT exist.")
                initialize_local_database(context)

            context.run(f"poetry run python manage.py test {filename}")


@task
def django_admin_check(context, pty=True):
    """
    Exeecute Django's built-in "check" to verify configuration.
    """
    with context.cd(DJ_PROJECT_ROOT):
        with environ(DJANGO_DEBUG_ENVIRONMENT):
            # Using 'python manage.py check' is ike 'django-admin check', but it uses
            # project specific configuration & works with poetry
            context.run("poetry run python manage.py check")

            if not DISABLE_IN_CI:
                context.run("poetry run python manual_authentication_check.py")


@task
def django_shell(context):
    """
    Helper to execute Django's built-in "shell".

    TODO: Research a cleaner implementation.  For now, the implementation
     here is good enough.

     Ideal implementation is simple, like:
        context.run("poetry run moosedj/manage.py shell")
    """

    with context.cd(DJ_PROJECT_ROOT):
        with environ(DJANGO_DEBUG_ENVIRONMENT, replace=True):
            dj_shell_vars = GIT_ROOT / "dj-shell-vars.env"
            dj_shell_vars.unlink(missing_ok=True)
            with open(dj_shell_vars, "wt") as s:
                for key, value in os.environ.items():
                    s.write(f'{key}="{value}"\n')

        print(
            """

        A ".env" file has been generated for the Django shell.

        To launch the shell, run the following command:

        export $(cat dj-shell-vars.env | xargs) && cd moosedj && poetry run python manage.py shell

        """
        )

    # Note: Using this call does not work.
    # context.run("export $(cat dj-shell-vars.env | xargs) && poetry run moosedj/manage.py shell")


@task
def run_huey_consumer(context, pty=True):
    """
    Exeecute 'manage.py run_huey' with proper configuration.

    More info:
    - https://huey.readthedocs.io/en/latest/contrib.html#running-the-consumer
    """
    with context.cd(DJ_PROJECT_ROOT):
        with environ(DJANGO_DEBUG_ENVIRONMENT):
            # Using 'python manage.py check' is ike 'django-admin check', but it uses
            # project specific configuration & works with poetry
            context.run("poetry run python manage.py run_huey")


# Useful when debugging
if __name__ == "__main__":
    from invoke import Context, Local, task

    c = Context()
    runner = Local(c)
    create_django_app(runner.context)
