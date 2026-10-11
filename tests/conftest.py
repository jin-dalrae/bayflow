def pytest_addoption(parser):
    parser.addoption(
        "--atlas",
        action="store_true",
        default=False,
        help="Verify real organizer Atlas read/write and recursive evolution; requires .env and network access.",
    )
    parser.addoption(
        "--llm",
        action="store_true",
        default=False,
        help="Verify one real model-driven proposal; consumes configured provider tokens.",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "atlas: explicit external organizer Atlas integration test"
    )
    config.addinivalue_line("markers", "llm: explicit real model integration test")
