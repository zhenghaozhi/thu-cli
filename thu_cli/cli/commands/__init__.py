"""Commands package.

Each domain (auth / learn / info / campus / academic) is a subpackage with:

    __init__.py     exports ``register_root(domain_subparsers)`` that adds the
                    domain's own subparser and auto-discovers sibling command files.
    <cmd>.py        one file per command — NAME / HELP / register / handle.
"""
