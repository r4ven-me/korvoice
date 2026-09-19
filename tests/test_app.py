from korvoice.app import args_to_command, build_arg_parser


def _parse(argv):
    return build_arg_parser().parse_args(argv)


def test_default_is_daemon():
    assert args_to_command(_parse([])) == {"action": "daemon"}


def test_settings_flag():
    assert args_to_command(_parse(["--settings"])) == {"action": "settings"}


def test_history_flag():
    assert args_to_command(_parse(["--history"])) == {"action": "history"}


def test_quit_flag():
    assert args_to_command(_parse(["--quit"])) == {"action": "quit"}


def test_quit_takes_priority_over_settings():
    assert args_to_command(_parse(["--quit", "--settings"])) == {"action": "quit"}
