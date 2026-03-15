import pytest
from pc_tool.common.uart_io import MCUSerialLink

def pytest_addoption(parser):
    parser.addoption("--port", default=None)
    parser.addoption("--baudrate", default=19200, type=int)
    parser.addoption("--mcu", default="atmega328p")

@pytest.fixture(scope="session")
def serial_link(request):
    port = request.config.getoption("--port")
    if port is None:
        pytest.skip("No --port provided, skipping hardware tests")
    link = MCUSerialLink(port=port, baudrate=request.config.getoption("--baudrate"))
    link.open()
    yield link
    link.close()