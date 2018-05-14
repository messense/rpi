import os
import logging
import signal
import subprocess

from pyhap import loader
from pyhap.const import CATEGORY_SENSOR, CATEGORY_SWITCH
from pyhap.accessory import Bridge, Accessory, AsyncAccessory
from pyhap.accessory_driver import AccessoryDriver

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RpiTemperatureSensor(AsyncAccessory):
    """A sensor accessory that measures temperature of the Raspberry Pi it runs on"""
    category = CATEGORY_SENSOR

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        serv_temp = self.add_preload_service('TemperatureSensor')
        self.char_temp = serv_temp.configure_char('CurrentTemperature')

    @AsyncAccessory.run_at_interval(3)
    async def run(self):
        # FIXME: use asyncio subprocess
        temp = subprocess.check_output(['/usr/bin/vcgencmd', 'measure_temp']).decode().strip()[5:9]
        self.char_temp.set_value(float(temp))


class ShutdownSwitch(Accessory):
    """A switch accessory that executes sudo shutdown."""
    category = CATEGORY_SWITCH

    def __init__(self, *args, **kwargs):
        """Initialize and set a shutdown callback to the On characteristic."""
        super().__init__(*args, **kwargs)

        serv_switch = self.add_preload_service('Switch')
        self.char_on = serv_switch.configure_char(
            'On',
            value=1,
            setter_callback=self.execute_shutdown
        )

    def execute_shutdown(self, value):
        """Execute shutdown -h."""
        if not value:
            logger.info("Executing shutdown command.")
            os.system("sudo shutdown -h now")


def get_bridge():
    bridge = Bridge(display_name='Raspberry Pi')
    temp_sensor = RpiTemperatureSensor('Pi Temperature Sensor')
    bridge.add_accessory(temp_sensor)
    bridge.add_accessory(ShutdownSwitch('Shutdown Pi'))

    return bridge



if __name__ == '__main__':
    acc = get_bridge()

    # Start the accessory on port 51826
    driver = AccessoryDriver(acc, port=51826)
    # We want KeyboardInterrupts and SIGTERM (kill) to be handled by the driver itself,
    # so that it can gracefully stop the accessory, server and advertising.
    signal.signal(signal.SIGINT, driver.signal_handler)
    signal.signal(signal.SIGTERM, driver.signal_handler)
    # Start it!
    driver.start()
