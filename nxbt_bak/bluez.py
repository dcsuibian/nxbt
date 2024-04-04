import subprocess
import re
import os
import time
import logging
from shutil import which
import random
from pathlib import Path

import dbus

SERVICE_NAME = "org.bluez"
BLUEZ_OBJECT_PATH = "/org/bluez"
ADAPTER_INTERFACE = SERVICE_NAME + ".Adapter1"
PROFILEMANAGER_INTERFACE = SERVICE_NAME + ".ProfileManager1"
DEVICE_INTERFACE = SERVICE_NAME + ".Device1"


def find_object_path(bus, service_name, interface_name, object_name=None):
    """Searches for a D-Bus object path that contains a specified interface
    under a specified service.

    :param bus: A DBus object used to access the DBus.
    :type bus: DBus
    :param service_name: The name of a D-Bus service to search for the
    object path under.
    :type service_name: string
    :param interface_name: The name of a D-Bus interface to search for
    within objects under the specified service.
    :type interface_name: string
    :param object_name: The name or ending of the object path,
    defaults to None
    :type object_name: string, optional
    :return: The D-Bus object path or None, if no matching object
    can be found
    :rtype: string
    """

    manager = dbus.Interface(
        bus.get_object(service_name, "/"),
        "org.freedesktop.DBus.ObjectManager")

    # Iterating over objects under the specified service
    # and searching for the specified interface
    for path, ifaces in manager.GetManagedObjects().items():
        managed_interface = ifaces.get(interface_name)
        if managed_interface is None:
            continue
        # If the object name wasn't specified or it matches
        # the interface address or the path ending
        elif (not object_name or
              object_name == managed_interface["Address"] or
              path.endswith(object_name)):
            obj = bus.get_object(service_name, path)
            return dbus.Interface(obj, interface_name).object_path

    return None


def find_objects(bus, service_name, interface_name):
    """Searches for D-Bus objects that contain a specified interface
    under a specified service.

    :param bus: A DBus object used to access the DBus.
    :type bus: DBus
    :param service_name: The name of a D-Bus service to search for the
    object path under.
    :type service_name: string
    :param interface_name: The name of a D-Bus interface to search for
    within objects under the specified service.
    :type interface_name: string
    :return: The D-Bus object paths matching the arguments
    :rtype: array
    """

    manager = dbus.Interface(
        bus.get_object(service_name, "/"),
        "org.freedesktop.DBus.ObjectManager")
    paths = []

    # Iterating over objects under the specified service
    # and searching for the specified interface within them
    for path, ifaces in manager.GetManagedObjects().items():
        managed_interface = ifaces.get(interface_name)
        if managed_interface is None:
            continue
        else:
            obj = bus.get_object(service_name, path)
            path = str(dbus.Interface(obj, interface_name).object_path)
            paths.append(path)

    return paths


def toggle_clean_bluez(toggle):
    """Enables or disables all BlueZ plugins,
    BlueZ compatibility mode, and removes all extraneous
    SDP Services offered.
    Requires root user to be run. The units and Bluetooth
    service will not be restarted if the input plugin
    already matches the toggle.

    :param toggle: A boolean element indicating if BlueZ 
    should be cleaned (True) or not (False)
    :type toggle: boolean
    :raises PermissionError: If the user is not root
    :raises Exception: If the units can't be reloaded
    :raises Exception: If sdptool, hciconfig, or hcitool are not available.
    """

    service_path = "/lib/systemd/system/bluetooth.service"
    override_dir = Path("/run/systemd/system/bluetooth.service.d")
    override_path = override_dir / "nxbt.conf"

    if toggle:
        if override_path.is_file():
            # Override exist, no need to restart bluetooth
            return

        with open(service_path) as f:
            for line in f:
                if line.startswith("ExecStart="):
                    exec_start = line.strip() + " --compat --noplugin=*"
                    break
            else:
                raise Exception("systemd service file doesn't have a ExecStart line")

        override = f"[Service]\nExecStart=\n{exec_start}"

        override_dir.mkdir(parents=True, exist_ok=True)
        with override_path.open("w") as f:
            f.write(override)
    else:
        try:
            os.remove(override_path)
        except FileNotFoundError:
            # Override doesn't exist, no need to restart bluetooth
            return

    # Reload units
    _run_command(["systemctl", "daemon-reload"])

    # Reload the bluetooth service with input disabled
    _run_command(["systemctl", "restart", "bluetooth"])

    # Kill a bit of time here to ensure all services have restarted
    time.sleep(0.5)


def _run_command(command):
    """Runs a specified command on the shell of the system.
    If the command is run unsuccessfully, an error is raised.
    The command must be in the form of an array with each term
    individually listed. Eg: ["which", "bash"]

    :param command: A list of command terms
    :type command: list
    :raises Exception: On command failure or error
    """
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)

    cmd_err = result.stderr.decode("utf-8").replace("\n", "")
    if cmd_err != "":
        raise Exception(cmd_err)

    return result


def replace_mac_addresses(adapter_paths, addresses):
    """Replaces a list of adapter's Bluetooth MAC addresses
    with Switch-compliant Controller MAC addresses. If the
    addresses argument is specified, the adapter path's
    MAC addresses will be reset to respective (index-wise)
    address in the list.

    :param adapter_paths: A list of Bluetooth adapter paths
    :type adapter_paths: list
    :param addresses: A list of Bluetooth MAC addresses,
    defaults to False
    :type addresses: bool, optional
    """
    if which("hcitool") is None:
        raise Exception("hcitool is not available on this system." +
                        "If you can, please install this tool, as " +
                        "it is required for proper functionality.")
    if which("hciconfig") is None:
        raise Exception("hciconfig is not available on this system." +
                        "If you can, please install this tool, as " +
                        "it is required for proper functionality.")

    if addresses:
        assert len(addresses) == len(adapter_paths)

    for i in range(len(adapter_paths)):
        adapter_id = adapter_paths[i].split('/')[-1]
        mac = addresses[i].split(':')
        cmds = ['hcitool', '-i', adapter_id, 'cmd', '0x3f', '0x001',
                f'0x{mac[5]}', f'0x{mac[4]}', f'0x{mac[3]}', f'0x{mac[2]}',
                f'0x{mac[1]}', f'0x{mac[0]}']
        _run_command(cmds)
        _run_command(['hciconfig', adapter_id, 'reset'])


def find_devices_by_alias(alias, return_path=False, created_bus=None):
    """Finds the Bluetooth addresses of devices
    that have a specified Bluetooth alias. Aliases
    are converted to uppercase before comparison
    as BlueZ usually converts aliases to uppercase.

    :param address: The Bluetooth MAC address
    :type address: string
    :return: The path to the D-Bus object or None
    :rtype: string or None
    """

    if created_bus is not None:
        bus = created_bus
    else:
        bus = dbus.SystemBus()
    # Find all connected/paired/discovered devices
    devices = find_objects(
        bus,
        SERVICE_NAME,
        DEVICE_INTERFACE)

    addresses = []
    matching_paths = []
    for path in devices:
        # Get the device's address and paired status
        device_props = dbus.Interface(
            bus.get_object(SERVICE_NAME, path),
            "org.freedesktop.DBus.Properties")
        device_alias = device_props.Get(
            DEVICE_INTERFACE,
            "Alias").upper()
        device_addr = device_props.Get(
            DEVICE_INTERFACE,
            "Address").upper()

        # Check for an address match
        if device_alias.upper() == alias.upper():
            addresses.append(device_addr)
            matching_paths.append(path)

    # Close the dbus connection if we created one
    if created_bus is None:
        bus.close()

    if return_path:
        return addresses, matching_paths
    else:
        return addresses


class BlueZ():
    """Exposes the BlueZ D-Bus API as a Python object.
    """

    def __init__(self, adapter_path="/org/bluez/hci0"):

        self.logger = logging.getLogger('nxbt')

        self.bus = dbus.SystemBus()
        self.device_path = adapter_path

        # If we weren't able to find an adapter with the specified ID,
        # try to find any usable Bluetooth adapter
        if self.device_path is None:
            self.device_path = find_object_path(
                self.bus,
                SERVICE_NAME,
                ADAPTER_INTERFACE)

        # If we aren't able to find an adapter still
        if self.device_path is None:
            raise Exception("Unable to find a bluetooth adapter")

        # Load the adapter's interface
        self.logger.debug(f"Using adapter under object path: {self.device_path}")
        self.device = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                self.device_path),
            "org.freedesktop.DBus.Properties")

        self.device_id = self.device_path.split("/")[-1]

        # Load the ProfileManager interface
        self.profile_manager = dbus.Interface(self.bus.get_object(
            SERVICE_NAME, BLUEZ_OBJECT_PATH),
            PROFILEMANAGER_INTERFACE)

        self.adapter = dbus.Interface(
            self.bus.get_object(
                SERVICE_NAME,
                self.device_path),
            ADAPTER_INTERFACE)

    @property
    def address(self):
        """Gets the Bluetooth MAC address of the Bluetooth adapter.

        :return: The Bluetooth Adapter's MAC address
        :rtype: string
        """

        return self.device.Get(ADAPTER_INTERFACE, "Address").upper()

    def set_class(self, device_class):
        if which("hciconfig") is None:
            raise Exception("hciconfig is not available on this system." +
                            "If you can, please install this tool, as " +
                            "it is required for proper functionality.")
        _run_command(['hciconfig', self.device_id, 'class', device_class])

    @property
    def name(self):
        """Gets the name of the Bluetooth adapter.

        :return: The name of the Bluetooth adapter.
        :rtype: string
        """

        return self.device.Get(ADAPTER_INTERFACE, "Name")

    def set_alias(self, value):
        """异步设置蓝牙适配器的别名。如果你想检查设置的值，在运行别名获取器之前需要等待一段时间。
        """
        self.device.Set(ADAPTER_INTERFACE, "Alias", value)

    def set_pairable(self, value):
        dbus_value = dbus.Boolean(value)
        self.device.Set(ADAPTER_INTERFACE, "Pairable", dbus_value)

    def set_pairable_timeout(self, value):
        dbus_value = dbus.UInt32(value)
        self.device.Set(ADAPTER_INTERFACE, "PairableTimeout", dbus_value)

    def set_discoverable(self, value):
        dbus_value = dbus.Boolean(value)
        self.device.Set(ADAPTER_INTERFACE, "Discoverable", dbus_value)

    def set_discoverable_timeout(self, value):
        """Sets the discoverable time (in seconds) for the discoverable
        property. Setting this property to 0 results in an infinite
        discoverable timeout.

        :param value: The discoverable timeout value in seconds
        :type value: int
        """

        dbus_value = dbus.UInt32(value)
        self.device.Set(
            ADAPTER_INTERFACE,
            "DiscoverableTimeout",
            dbus_value)

    def set_powered(self, value):
        """Switches the adapter on or off.

        :param value: A boolean value switching the adapter on or off
        :type value: boolean
        """

        dbus_value = dbus.Boolean(value)
        self.device.Set(ADAPTER_INTERFACE, "Powered", dbus_value)

    def register_profile(self, profile_path, uuid, opts):
        """Registers an SDP record on the BlueZ SDP server.

        Options (non-exhaustive, refer to BlueZ docs for
        the complete list):

        - Name: Human readable name of the profile

        - Role: Specifies precise local role. Either "client"
        or "servier".

        - RequireAuthentication: A boolean value indicating if
        pairing is required before connection.

        - RequireAuthorization: A boolean value indiciating if
        authorization is needed before connection.

        - AutoConnect: A boolean value indicating whether a
        connection can be forced if a client UUID is present.

        - ServiceRecord: An XML SDP record as a string.

        :param profile_path: The path for the SDP record
        :type profile_path: string
        :param uuid: The UUID for the SDP record
        :type uuid: string
        :param opts: The options for the SDP server
        :type opts: dict
        """

        return self.profile_manager.RegisterProfile(profile_path, uuid, opts)

    def remove_device(self, path):
        """Removes a device that's been either discovered, paired,
        connected, etc.

        :param path: The D-Bus path to the object
        :type path: string
        """

        self.adapter.RemoveDevice(
            self.bus.get_object(SERVICE_NAME, path))

    def find_connected_devices(self, alias_filter=False):
        """Finds the D-Bus path to a device that contains the
        specified address.

        :param address: The Bluetooth MAC address
        :type address: string
        :return: The path to the D-Bus object or None
        :rtype: string or None
        """

        devices = find_objects(
            self.bus,
            SERVICE_NAME,
            DEVICE_INTERFACE)
        conn_devices = []
        for path in devices:
            # Get the device's connection status
            device_props = dbus.Interface(
                self.bus.get_object(SERVICE_NAME, path),
                "org.freedesktop.DBus.Properties")
            device_conn_status = device_props.Get(
                DEVICE_INTERFACE,
                "Connected")
            device_alias = device_props.Get(
                DEVICE_INTERFACE,
                "Alias").upper()

            if device_conn_status:
                if alias_filter and device_alias == alias_filter.upper():
                    conn_devices.append(path)
                else:
                    conn_devices.append(path)

        return conn_devices
