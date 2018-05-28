import os
import logging
import signal
import subprocess

from pyhap import loader
from pyhap.const import CATEGORY_SENSOR, CATEGORY_SWITCH
from pyhap.accessory import Bridge, Accessory, AsyncAccessory
from pyhap.accessory_driver import AccessoryDriver

from systemd_dbus.exceptions import SystemdError
from systemd_dbus.manager import Manager as SystemdManager

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


class SystemdServiceSwitch(Accessory):
    '''A switch accessory that manages Systemd services'''
    category = CATEGORY_SWITCH

    manager = SystemdManager()

    def __init__(self, *args, service=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not service.endswith('.service'):
            service = service + '.service'
        self.systemd_service = service
        try:
            self.unit = self.manager.get_unit(service)
        except SystemdError:
            logger.warning('Get %s unit error', service)
            self.unit = None
            return

        is_on = self.unit.properties.ActiveState == 'active' and self.unit.properties.SubState == 'running'
        serv_switch = self.add_preload_service('Switch')
        self.char_on = serv_switch.configure_char(
            'On',
            value=is_on,
            setter_callback=self.toggle_service
        )

    def toggle_service(self, value):
        try:
            if self.unit is None:
                self.unit = self.manager.get_unit(self.systemd_service)

            if value:
                self.unit.start('fail')
            else:
                self.unit.stop('fail')
        except SystemdError:
            logger.exception('Toggle Systemd service %s failed', self.systemd_service)


def get_bridge():
    bridge = Bridge(display_name='Raspberry Pi')
    temp_sensor = RpiTemperatureSensor('Pi Temperature Sensor')
    bridge.add_accessory(temp_sensor)
    bridge.add_accessory(ShutdownSwitch('Shutdown Pi'))

    services = [
        ('nginx', 'nginx'),
        ('netdata', 'netdata monitor'),
        ('frp', 'frp proxy'),
    ]
    for service, display_name in services:
        bridge.add_accessory(SystemdServiceSwitch(display_name, service=service))

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
